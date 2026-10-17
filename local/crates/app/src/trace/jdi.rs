//! Java 실행 기록 준비 (SYNC-MS-027#trace.java_setup, 카드 L34) — view_arc `native/java.mts`를 옮겼다.
//! JDI 디버거(`tracers/java/SyncdocJdi.java`)를 먼저 띄우고, 대상 JVM이 그 디버거에 붙게 `JAVA_TOOL_OPTIONS`에 jdwp
//! 에이전트(server=n, suspend=y)를 더한다. 대상 코드·빌드 설정은 고치지 않는다.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use regex::Regex;
use tokio::io::{AsyncBufReadExt, BufReader};

use super::{Kit, SpanTable};

/// 띄운 디버거와 대상에 줄 환경 변수
pub struct JavaSetup {
    pub child: tokio::process::Child,
    pub env: Vec<(String, String)>,
    pub port: u16,
}

fn java_bin(home: &Path) -> PathBuf {
    home.join("bin")
        .join(if cfg!(windows) { "java.exe" } else { "java" })
}

/// jdk.jdi가 든 JDK — `SYNCDOC_JAVA_HOME` → `JAVA_HOME` → PATH의 java. 없으면 없음
pub fn find_jdk() -> Option<PathBuf> {
    let mut homes: Vec<PathBuf> = ["SYNCDOC_JAVA_HOME", "JAVA_HOME"]
        .iter()
        .filter_map(std::env::var_os)
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .collect();
    if let Some(java) = super::which("java")
        && let Ok(real) = std::fs::canonicalize(java)
        && let Some(home) = real.parent().and_then(Path::parent)
    {
        homes.push(home.to_path_buf());
    }
    homes.into_iter().find(|home| {
        let java = java_bin(home);
        java.is_file()
            && std::process::Command::new(&java)
                .arg("--list-modules")
                .output()
                .ok()
                .filter(|o| o.status.success())
                .is_some_and(|o| {
                    String::from_utf8_lossy(&o.stdout)
                        .lines()
                        .any(|l| l.starts_with("jdk.jdi@"))
                })
    })
}

/// 디버거가 읽을 표(탭) — S 절대 경로 시작 끝 열쇠 · R 열쇠 메서드 경로 · P 패키지 · H 주소 종류 · N 열쇠 이름
pub fn table_lines(table: &SpanTable) -> Vec<String> {
    let package = Regex::new(r"(?m)^\s*package\s+([\w.]+)\s*;").expect("package");
    let java_key = |k: &str| {
        k.rsplit_once(':')
            .is_some_and(|(f, _)| f.ends_with(".java"))
    };
    let mut lines = Vec::new();
    let mut packages: Vec<String> = Vec::new();
    for (file, spans) in &table.files {
        if !file.to_string_lossy().ends_with(".java") {
            continue;
        }
        for (a, b, id) in spans {
            lines.push(format!("S\t{}\t{a}\t{b}\t{id}", file.to_string_lossy()));
        }
        if let Ok(text) = std::fs::read_to_string(file)
            && let Some(m) = package.captures(&text)
            && !packages.contains(&m[1].to_string())
        {
            packages.push(m[1].to_string());
        }
    }
    for (id, method, path) in &table.routes {
        if java_key(id) {
            lines.push(format!("R\t{id}\t{method}\t{path}"));
        }
    }
    for p in &packages {
        lines.push(format!("P\t{p}"));
    }
    if let Some(hosts) = table.json["hosts"].as_object() {
        for (host, kind) in hosts {
            lines.push(format!("H\t{host}\t{}", kind.as_str().unwrap_or("http")));
        }
    }
    for (id, name) in &table.names {
        if java_key(id) {
            lines.push(format!("N\t{id}\t{name}"));
        }
    }
    lines
}

/// SYNC-MS-027#trace.java_setup
///
/// JDK를 찾고 범위 표를 쓰고 디버거를 빈 포트에 띄워 `LISTENING`을 30초까지 기다린다 → 대상에 줄 `JAVA_TOOL_OPTIONS`
pub async fn java_setup(
    kit: &Kit,
    table: &SpanTable,
    work: &Path,
    out: &Path,
    job: bool,
) -> Result<JavaSetup, String> {
    let Some(jdk) = find_jdk() else {
        return Err(
            "Java 실행 기록에는 JDK 11 이상(jdk.jdi 모듈 포함)이 필요하다 — JAVA_HOME을 그 폴더로 두거나 SYNCDOC_JAVA_HOME=<JDK 경로>를 주세요(JRE만으로는 안 된다)"
                .into(),
        );
    };
    let lines = table_lines(table);
    if !lines.iter().any(|l| l.starts_with("P\t")) {
        return Err(
            "기록할 Java 클래스를 그래프에서 찾지 못했다 — 코드를 push해 그래프를 다시 만드세요"
                .into(),
        );
    }
    let table_path = work.join("jdi.txt");
    std::fs::write(&table_path, lines.join("\n") + "\n").map_err(|e| e.to_string())?;
    let port = std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .map_err(|e| format!("빈 포트를 찾지 못했다: {e}"))?;
    let mut child = tokio::process::Command::new(java_bin(&jdk))
        .arg(kit.dir.join("java").join("SyncdocJdi.java"))
        .arg(port.to_string())
        .arg(&table_path)
        .arg(out)
        .arg(if job { "1" } else { "0" })
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("Java 디버거를 띄우지 못했다: {e}"))?;
    let stdout = child.stdout.take().ok_or("디버거 출력을 못 읽었다")?;
    let mut reader = BufReader::new(stdout).lines();
    let ready = tokio::time::timeout(Duration::from_secs(30), async {
        while let Ok(Some(line)) = reader.next_line().await {
            if line.starts_with("LISTENING ") {
                return true;
            }
        }
        false
    })
    .await
    .unwrap_or(false);
    if !ready {
        let _ = child.kill().await;
        return Err(format!(
            "Java 디버거를 띄우지 못했다 — {}가 JDK인지 확인하세요",
            jdk.display()
        ));
    }
    // 디버거는 더 쓰지 않지만 파이프가 차지 않게 비운다
    tokio::spawn(async move { while let Ok(Some(_)) = reader.next_line().await {} });
    let agent =
        format!("-agentlib:jdwp=transport=dt_socket,server=n,address=127.0.0.1:{port},suspend=y");
    let options = match std::env::var("JAVA_TOOL_OPTIONS") {
        Ok(old) if !old.trim().is_empty() => format!("{agent} {old}"),
        _ => agent,
    };
    Ok(JavaSetup {
        child,
        env: vec![("JAVA_TOOL_OPTIONS".into(), options)],
        port,
    })
}
