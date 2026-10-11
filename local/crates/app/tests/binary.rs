//! SYNC-MS-012#runtime.run 테스트 관점 — 실행 파일 전체(유닉스). 임시 데이터 자리, 진짜 PostgreSQL.
//! 켜기 → /health·/api/me·가드 → 두 번째 실행 → SIGINT로 끄기 → 다시 켜기 → 아이디 충돌.

#![cfg(unix)]

use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::Path;
use std::process::{Child, Command, Output, Stdio};
use std::time::{Duration, Instant};

const BIN: &str = env!("CARGO_BIN_EXE_syncdoc-local");

fn spawn(data: &Path) -> Child {
    Command::new(BIN)
        .arg("--data-dir")
        .arg(data)
        .args(["--port", "0", "--no-browser", "--no-tray"])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("syncdoc-local")
}

/// instance.json이 생길 때까지 — 포트와 걸린 시간
fn wait_port(data: &Path, child: &mut Child) -> (u16, Duration) {
    let t0 = Instant::now();
    loop {
        if let Ok(text) = fs::read_to_string(data.join("instance.json")) {
            let v: serde_json::Value = serde_json::from_str(&text).expect("instance.json");
            return (v["port"].as_u64().expect("port") as u16, t0.elapsed());
        }
        if let Ok(Some(status)) = child.try_wait() {
            let mut err = String::new();
            child.stderr.take().unwrap().read_to_string(&mut err).ok();
            panic!("켜지기 전에 끝났다({status}) — {err}");
        }
        assert!(
            t0.elapsed() < Duration::from_secs(60),
            "60초 안에 안 켜졌다"
        );
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// 원시 HTTP/1.1 — Host를 시험이 정한다
fn http(port: u16, method: &str, path: &str, headers: &[(&str, &str)]) -> (u16, String) {
    let mut s = TcpStream::connect(("127.0.0.1", port)).expect("연결");
    let mut req = format!("{method} {path} HTTP/1.1\r\nConnection: close\r\nContent-Length: 0\r\n");
    for (k, v) in headers {
        req += &format!("{k}: {v}\r\n");
    }
    req += "\r\n";
    s.write_all(req.as_bytes()).unwrap();
    let mut buf = String::new();
    s.read_to_string(&mut buf).unwrap();
    let status = buf
        .split(' ')
        .nth(1)
        .and_then(|c| c.parse().ok())
        .unwrap_or(0);
    let body = buf
        .split_once("\r\n\r\n")
        .map(|(_, b)| b.to_string())
        .unwrap_or_default();
    (status, body)
}

fn interrupt(child: &mut Child) -> Output {
    let pid = child.id().to_string();
    assert!(
        Command::new("kill")
            .args(["-INT", &pid])
            .status()
            .unwrap()
            .success()
    );
    let t0 = Instant::now();
    loop {
        if child.try_wait().unwrap().is_some() {
            break;
        }
        assert!(
            t0.elapsed() < Duration::from_secs(20),
            "SIGINT 뒤 20초 안에 안 끝났다"
        );
        std::thread::sleep(Duration::from_millis(100));
    }
    let mut out = String::new();
    child.stdout.take().unwrap().read_to_string(&mut out).ok();
    let mut err = String::new();
    child.stderr.take().unwrap().read_to_string(&mut err).ok();
    Output {
        status: child.wait().unwrap(),
        stdout: out.into_bytes(),
        stderr: err.into_bytes(),
    }
}

#[test]
fn run_serve_second_instance_shutdown_restart_conflict() {
    let dir = tempfile::tempdir().unwrap();
    let data = dir.path();

    // 켜기 — 처음(initdb 포함)
    let mut child = spawn(data);
    let (port, first) = wait_port(data, &mut child);
    eprintln!("켜기(첫 실행): {first:?}");
    let host = format!("127.0.0.1:{port}");
    assert_eq!(
        http(port, "GET", "/health", &[("Host", &host)]),
        (200, r#"{"status":"ok"}"#.to_string())
    );
    let (status, me) = http(port, "GET", "/api/me", &[("Host", &host)]);
    assert_eq!(status, 200, "{me}");
    let me: serde_json::Value = serde_json::from_str(&me).unwrap();
    assert_eq!(
        (me["github_login"].as_str(), me["edition"].as_str()),
        (Some("local"), Some("closed"))
    );
    assert_eq!(
        http(port, "GET", "/health", &[("Host", "evil.example")]).0,
        403
    );
    assert_eq!(
        http(
            port,
            "GET",
            "/health",
            &[("Host", &format!("[::1]:{port}"))]
        )
        .0,
        200
    );
    assert_eq!(
        http(
            port,
            "POST",
            "/api/me",
            &[("Host", &host), ("Origin", "http://evil.example")]
        )
        .0,
        403
    );

    // 두 번째 실행 — 주소를 찍고 0
    let second = Command::new(BIN)
        .arg("--data-dir")
        .arg(data)
        .args(["--no-browser", "--no-tray"])
        .output()
        .unwrap();
    assert!(second.status.success());
    assert!(String::from_utf8_lossy(&second.stdout).contains(&format!("http://127.0.0.1:{port}/")));

    // 끄기
    let out = interrupt(&mut child);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!data.join("pgdata/postmaster.pid").exists());
    assert!(!data.join("instance.json").exists());

    // 다시 켜기 — 같은 데이터
    let mut child = spawn(data);
    let (port, again) = wait_port(data, &mut child);
    eprintln!("켜기(다시): {again:?}");
    let (_, me2) = http(
        port,
        "GET",
        "/api/me",
        &[("Host", &format!("127.0.0.1:{port}"))],
    );
    let me2: serde_json::Value = serde_json::from_str(&me2).unwrap();
    assert_eq!(me2["id"], me["id"]);
    assert!(interrupt(&mut child).status.success());

    // 아이디 충돌 — 다른 사람이 쓰는 아이디로 바꾸면 끝 코드 1과 문장, PostgreSQL은 멈춰 있다
    single_user(
        data,
        "INSERT INTO users (github_login, display_name, kind) VALUES ('taken', 'Taken', 'github')",
    );
    fs::write(data.join("settings.toml"), "LOCAL_LOGIN = \"taken\"\n").unwrap();
    let out = Command::new(BIN)
        .arg("--data-dir")
        .arg(data)
        .args(["--port", "0", "--no-browser"])
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&out.stderr).contains("이미 다른 사용자다"));
    assert!(!data.join("pgdata/postmaster.pid").exists());
}

/// 멈춘 서버에 단일 사용자 모드로 SQL 한 줄 — 암호를 몰라도 된다
fn single_user(data: &Path, sql: &str) {
    let bins = std::env::var("SYNCDOC_LOCAL_PG_DIR").expect("SYNCDOC_LOCAL_PG_DIR");
    let mut child = Command::new(Path::new(&bins).join("bin/postgres"))
        .arg("--single")
        .arg("-D")
        .arg(data.join("pgdata"))
        .args(["-c", "exit_on_error=on", "syncdoc"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(format!("{sql}\n").as_bytes())
        .unwrap();
    assert!(child.wait().unwrap().success());
}

/// 본문 있는 요청 — JSON
fn http_json(port: u16, method: &str, path: &str, body: &str) -> (u16, String) {
    let mut s = TcpStream::connect(("127.0.0.1", port)).expect("연결");
    let req = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    );
    s.write_all(req.as_bytes()).unwrap();
    let mut buf = String::new();
    s.read_to_string(&mut buf).unwrap();
    let status = buf
        .split(' ')
        .nth(1)
        .and_then(|c| c.parse().ok())
        .unwrap_or(0);
    let body = buf
        .split_once("\r\n\r\n")
        .map(|(_, b)| b.to_string())
        .unwrap_or_default();
    (status, body)
}

fn git(cwd: &Path, args: &[&str]) {
    let out = Command::new("git")
        .args(["-c", "user.name=밖", "-c", "user.email=out@example.com"])
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("git");
    assert!(
        out.status.success(),
        "{args:?}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
fn push_while_off_becomes_a_document_on_start() {
    let dir = tempfile::tempdir().unwrap();
    let data = dir.path();
    let mut child = spawn(data);
    let (port, _) = wait_port(data, &mut child);
    let (status, body) = http_json(
        port,
        "POST",
        "/api/projects",
        r#"{"storage": "server", "code": "BT", "name": "켜기 따라잡기"}"#,
    );
    assert_eq!(status, 201, "{body}");
    assert!(interrupt(&mut child).status.success());
    // 꺼진 동안 서버 저장소에 명세를 민다
    let out = dir.path().join("outside");
    git(
        dir.path(),
        &[
            "clone",
            "-q",
            data.join("origins/BT.git").to_str().unwrap(),
            out.to_str().unwrap(),
        ],
    );
    fs::write(
        out.join("docs/specs/02-PRD/BT-PRD-001.md"),
        "---\ndoc_id: BT-PRD-001\ntype: PRD\ntitle: 켜기\nstatus: draft\n---\n# 켜기\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 하나\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n",
    )
    .unwrap();
    git(&out, &["add", "-A"]);
    git(&out, &["commit", "-q", "-m", "spec: 꺼진 동안"]);
    git(&out, &["push", "-q", "origin", "HEAD:main"]);
    // 다시 켜면 따라잡기가 문서로 만든다
    let mut child = spawn(data);
    let (port, _) = wait_port(data, &mut child);
    let host = format!("127.0.0.1:{port}");
    let t0 = Instant::now();
    loop {
        let (_, docs) = http(port, "GET", "/api/projects/BT/docs", &[("Host", &host)]);
        if docs.contains("BT-PRD-001") {
            break;
        }
        assert!(
            t0.elapsed() < Duration::from_secs(30),
            "따라잡기가 안 됐다 — {docs}"
        );
        std::thread::sleep(Duration::from_millis(200));
    }
    assert!(interrupt(&mut child).status.success());
}

/// 연결이 안 되면(다시 켜는 중) 없음
fn try_json(port: u16, path: &str) -> Option<(u16, String)> {
    let mut s = TcpStream::connect(("127.0.0.1", port)).ok()?;
    let req = format!(
        "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
    );
    s.write_all(req.as_bytes()).ok()?;
    let mut buf = String::new();
    s.read_to_string(&mut buf).ok()?;
    let status = buf.split(' ').nth(1)?.parse().ok()?;
    Some((status, buf.split_once("\r\n\r\n")?.1.to_string()))
}

/// 다시 켜기를 기다린다 — `/api/local`의 마지막 다시 켜기가 그 종류가 될 때까지
fn wait_op(port: u16, kind: &str) -> serde_json::Value {
    let t0 = Instant::now();
    loop {
        if let Some((200, body)) = try_json(port, "/api/local") {
            let v: serde_json::Value = serde_json::from_str(&body).expect("이 PC");
            if v["last_op"]["kind"] == kind {
                return v;
            }
        }
        assert!(
            t0.elapsed() < Duration::from_secs(60),
            "60초 안에 다시 켜지지 않았다 — {kind}"
        );
        std::thread::sleep(Duration::from_millis(200));
    }
}

/// 다시 켜기(카드 L16, runtime.run) — 설정 저장 → 같은 포트로 다시 뜸 · 백업 → 되살리기 · 옮기기
#[test]
fn local_settings_backup_restore_move_restart_in_place() {
    let dir = tempfile::tempdir().unwrap();
    let data = dir.path().join("a");
    fs::create_dir_all(&data).unwrap();
    let mut child = spawn(&data);
    let (port, _) = wait_port(&data, &mut child);
    let (status, body) = http_json(port, "GET", "/api/local", "");
    assert_eq!(status, 200, "{body}");
    let v: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(
        v["data_dir"],
        std::path::absolute(&data)
            .unwrap()
            .to_string_lossy()
            .as_ref()
    );
    assert_eq!(v["backup"]["files"], serde_json::json!([]));
    assert!(v["last_op"].is_null() && !v["llm_api_key_set"].as_bool().unwrap());
    // 설정 저장 → 다시 켜기
    let backups = dir.path().join("b");
    let change = serde_json::json!({"name": "새 이름", "backup_dir": backups});
    let (status, body) = http_json(port, "PUT", "/api/local/settings", &change.to_string());
    assert_eq!((status, body.as_str()), (202, r#"{"restarting":true}"#));
    let v = wait_op(port, "settings");
    assert_eq!(v["name"], "새 이름");
    assert_eq!(v["backup"]["dir"], backups.to_string_lossy().as_ref());
    let (_, me) = http_json(port, "GET", "/api/me", "");
    assert!(me.contains("\"display_name\":\"새 이름\""), "{me}");
    let (status, body) = http_json(
        port,
        "PUT",
        "/api/local/settings",
        r#"{"backup_dir": "rel"}"#,
    );
    assert_eq!(status, 422, "{body}");
    // 백업 → 프로젝트 → 되살리기 → 프로젝트가 없다
    let (status, body) = http_json(port, "POST", "/api/local/backups", "");
    assert_eq!(status, 201, "{body}");
    let made: serde_json::Value = serde_json::from_str(&body).unwrap();
    let (status, body) = http_json(
        port,
        "POST",
        "/api/projects",
        r#"{"storage": "server", "code": "RST", "name": "되살리기 전"}"#,
    );
    assert_eq!(status, 201, "{body}");
    let (status, _) = http_json(
        port,
        "POST",
        "/api/local/restore",
        r#"{"name": "syncdoc-없음.tar"}"#,
    );
    assert_eq!(status, 404);
    let req = serde_json::json!({"name": made["name"]}).to_string();
    let (status, body) = http_json(port, "POST", "/api/local/restore", &req);
    assert_eq!(status, 202, "{body}");
    let v = wait_op(port, "restore");
    assert_eq!(v["last_op"]["ok"], true, "{v}");
    let (_, list) = http_json(port, "GET", "/api/projects", "");
    assert!(!list.contains("\"RST\""), "{list}");
    // 옮기기 — 잘못된 자리는 422, 맞으면 새 자리에서 같은 포트로
    let (status, body) = http_json(port, "POST", "/api/local/move", r#"{"dir": "rel"}"#);
    assert!(status == 422 && body.contains("data-dir-invalid"), "{body}");
    let moved = dir.path().join("moved");
    let req = serde_json::json!({"dir": moved}).to_string();
    let (status, body) = http_json(port, "POST", "/api/local/move", &req);
    assert_eq!(status, 202, "{body}");
    let v = wait_op(port, "move");
    assert_eq!(v["last_op"]["ok"], true, "{v}");
    assert_eq!(v["data_dir"], moved.to_string_lossy().as_ref());
    assert!(moved.join("pgdata").is_dir() && moved.join("instance.json").is_file());
    assert!(data.join("pgdata").is_dir(), "옛 자리는 그대로");
    assert!(!data.join("instance.json").exists());
    assert_eq!(v["name"], "새 이름", "설정도 옮겨 왔다");
    let out = interrupt(&mut child);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!moved.join("instance.json").exists());
}
