//! 함께 담은 PostgreSQL 16 — 앱이 직접 띄우고 멈춘다 (SYNC-INFRA-001 9.1·9.2·9.4, 사용자 결정 2026-10-07).
//! 시험용 라이브러리(postgresql_embedded)는 fsync를 끄고 멈출 때 데이터 폴더를 지워 쓰지 않는다.
//! 데이터 자리의 `pgdata/` · 127.0.0.1 임의 포트 · 켤 때마다 바뀌는 암호 · 역할·DB `syncdoc`(Docker 판과 같다).

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Output, Stdio};

use rand::RngExt;
use rand::distr::Alphanumeric;
use sqlx::postgres::PgConnectOptions;
use sqlx::{Connection, PgConnection};
use syncdoc_core::errors::Problem;
use tokio::io::AsyncWriteExt;
use tokio::process::Command;

/// 역할과 DB — Docker 판과 같은 이름이라 한 판의 덤프가 다른 판에 그대로 들어간다
const ROLE: &str = "syncdoc";
const DB: &str = "syncdoc";

/// 켤 때마다 `ALTER SYSTEM`으로 두는 설정 — 연결 수·메모리는 기본값(사용자 결정 2026-10-07).
/// 유닉스 소켓은 여기서 끄지 않는다 — `ALTER SYSTEM`은 빈 목록을 빈 이름 하나(`'""'`)로 저장해
/// 루트에 소켓을 만들려 한다. 띄울 때 `-k ''`로 끈다(`ctl_start`)
const SETTINGS: [(&str, &str); 6] = [
    ("listen_addresses", "127.0.0.1"),
    ("timezone", "UTC"),
    ("log_timezone", "UTC"),
    ("logging_collector", "on"),
    ("log_directory", "../logs"),
    ("log_filename", "postgresql-%Y-%m-%d.log"),
];

/// 띄운 PostgreSQL — 놓이면(패닉 등) 한 번 멈춰 본다
pub struct PgServer {
    /// 127.0.0.1 · 포트 · `syncdoc` · 이번 암호 · DB `syncdoc`
    pub options: PgConnectOptions,
    pub port: u16,
    pub pgdata: PathBuf,
    pub bin: PathBuf,
    stopped: bool,
}

/// SYNC-MS-012#pg.start
pub async fn start(pg_dir: &Path, data_dir: &Path) -> Result<PgServer, Problem> {
    let bin = pg_dir.join("bin");
    for name in ["initdb", "postgres", "pg_ctl"] {
        let path = exe(&bin, name);
        if !path.is_file() {
            return Err(Problem::Internal {
                log: format!("PostgreSQL 바이너리가 없다 — {}", path.display()),
            });
        }
    }
    let pgdata = data_dir.join("pgdata");
    let logs = data_dir.join("logs");
    fs::create_dir_all(&logs)?;
    let pw = password();
    if !pgdata.exists() {
        initdb(&bin, data_dir, &pgdata, &pw).await?;
    }
    if pgdata.join("postmaster.pid").exists() && ctl_running(&bin, &pgdata).await {
        ctl_stop(&bin, &pgdata).await?; // 지난번 비정상 종료로 남은 서버
    }
    configure(&bin, &pgdata, &pw).await?;
    let mut last = None;
    for _ in 0..3 {
        let port = free_port()?;
        match ctl_start(&bin, &pgdata, &logs, port).await {
            Ok(()) => {
                if let Err(p) = create_db(port, &pw).await {
                    let _ = ctl_stop(&bin, &pgdata).await;
                    return Err(p);
                }
                return Ok(PgServer {
                    options: options(port, &pw, DB),
                    port,
                    pgdata,
                    bin,
                    stopped: false,
                });
            }
            Err(p) => last = Some(p),
        }
    }
    Err(last.unwrap_or_else(|| Problem::Internal {
        log: "PostgreSQL을 띄우지 못했다".into(),
    }))
}

/// SYNC-MS-012#pg.stop
pub async fn stop(server: PgServer) -> Result<(), Problem> {
    let mut server = server;
    if server.pgdata.join("postmaster.pid").exists() {
        ctl_stop(&server.bin, &server.pgdata).await?;
    }
    server.stopped = true;
    Ok(())
}

impl Drop for PgServer {
    fn drop(&mut self) {
        if !self.stopped && self.pgdata.join("postmaster.pid").exists() {
            let _ = std::process::Command::new(exe(&self.bin, "pg_ctl"))
                .arg("stop")
                .arg("-D")
                .arg(&self.pgdata)
                .args(["-m", "fast", "-w", "-t", "30"])
                .output();
        }
    }
}

/// 처음 — `pgdata.init`에 만들고 다 되면 이름을 바꾼다. 반쯤 만든 것을 완성본으로 읽지 않게
async fn initdb(bin: &Path, data_dir: &Path, pgdata: &Path, pw: &str) -> Result<(), Problem> {
    let staging = data_dir.join("pgdata.init");
    if staging.exists() {
        fs::remove_dir_all(&staging)?;
    }
    let pwfile = data_dir.join("pgdata.pw");
    write_private(&pwfile, pw)?;
    let out = Command::new(exe(bin, "initdb"))
        .arg("-D")
        .arg(&staging)
        .args([
            "-U",
            ROLE,
            "-A",
            "scram-sha-256",
            "-E",
            "UTF8",
            "--locale=C",
            "--no-instructions",
        ])
        .arg(format!("--pwfile={}", pwfile.display()))
        .output()
        .await;
    let _ = fs::remove_file(&pwfile);
    checked(out, "initdb", None)?;
    fs::rename(&staging, pgdata)?;
    Ok(())
}

/// 단일 사용자 모드로 암호를 바꾸고 설정을 둔다 — 암호는 표준 입력으로만 간다
async fn configure(bin: &Path, pgdata: &Path, pw: &str) -> Result<(), Problem> {
    let mut sql =
        format!("ALTER ROLE {ROLE} PASSWORD '{pw}'\nALTER SYSTEM RESET unix_socket_directories\n");
    for (k, v) in SETTINGS {
        sql += &format!("ALTER SYSTEM SET {k} = '{v}'\n");
    }
    let mut child = Command::new(exe(bin, "postgres"))
        .arg("--single")
        .arg("-D")
        .arg(pgdata)
        .args(["-c", "exit_on_error=on", "postgres"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(sql.as_bytes()).await?;
    }
    let out = child.wait_with_output().await;
    checked(out, "postgres --single", Some(pw))
}

/// `pg_ctl start` — 따로 프로세스 묶음으로. 터미널 Ctrl+C가 먼저 닿지 않고 멈추는 순서를 앱이 쥔다.
/// 표준 출력·오류는 파이프가 아니라 `logs/pg_ctl.log`로 — 윈도의 `pg_ctl`은 핸들을 물려주며 서버를 띄워,
/// 파이프로 받으면 서버가 끝날 때까지 읽기가 끝나지 않는다
async fn ctl_start(bin: &Path, pgdata: &Path, logs: &Path, port: u16) -> Result<(), Problem> {
    let out_path = logs.join("pg_ctl.log");
    let out = fs::File::create(&out_path)?;
    let err = out.try_clone()?;
    let mut cmd = Command::new(exe(bin, "pg_ctl"));
    cmd.arg("start")
        .arg("-D")
        .arg(pgdata)
        .args(["-w", "-t", "60", "-l"])
        .arg(logs.join("postgresql-boot.log"))
        .arg("-o")
        .arg(if cfg!(unix) {
            format!("-p {port} -k ''") // 유닉스 소켓을 끈다 — 127.0.0.1 TCP만
        } else {
            format!("-p {port}")
        });
    #[cfg(unix)]
    cmd.process_group(0);
    #[cfg(windows)]
    cmd.creation_flags(0x0000_0200); // CREATE_NEW_PROCESS_GROUP
    cmd.stdin(Stdio::null()).stdout(out).stderr(err);
    let status = cmd.status().await.map_err(|e| Problem::Internal {
        log: format!("pg_ctl start을 못 돌렸다 — {e}"),
    })?;
    if status.success() {
        return Ok(());
    }
    let text = fs::read_to_string(&out_path).unwrap_or_default();
    Err(Problem::Internal {
        log: format!(
            "pg_ctl start 실패({status}) — {} · {}",
            tail(&text),
            logs.join("postgresql-boot.log").display()
        ),
    })
}

async fn ctl_running(bin: &Path, pgdata: &Path) -> bool {
    Command::new(exe(bin, "pg_ctl"))
        .arg("status")
        .arg("-D")
        .arg(pgdata)
        .output()
        .await
        .is_ok_and(|o| o.status.success())
}

async fn ctl_stop(bin: &Path, pgdata: &Path) -> Result<(), Problem> {
    let out = Command::new(exe(bin, "pg_ctl"))
        .arg("stop")
        .arg("-D")
        .arg(pgdata)
        .args(["-m", "fast", "-w", "-t", "30"])
        .output()
        .await;
    match checked(out, "pg_ctl stop", None) {
        Err(_) if !ctl_running(bin, pgdata).await => Ok(()), // 이미 멈춰 있었다
        r => r,
    }
}

/// `syncdoc` DB가 없으면 만든다
async fn create_db(port: u16, pw: &str) -> Result<(), Problem> {
    let mut conn = PgConnection::connect_with(&options(port, pw, "postgres")).await?;
    let exists: bool =
        sqlx::query_scalar("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1)")
            .bind(DB)
            .fetch_one(&mut conn)
            .await?;
    if !exists {
        sqlx::raw_sql("CREATE DATABASE syncdoc")
            .execute(&mut conn)
            .await?;
    }
    conn.close().await?;
    Ok(())
}

fn options(port: u16, pw: &str, db: &str) -> PgConnectOptions {
    PgConnectOptions::new()
        .host("127.0.0.1")
        .port(port)
        .username(ROLE)
        .password(pw)
        .database(db)
}

/// 127.0.0.1에 잠깐 묶어 빈 포트를 얻는다
fn free_port() -> Result<u16, Problem> {
    let l = std::net::TcpListener::bind(("127.0.0.1", 0))?;
    Ok(l.local_addr()?.port())
}

fn password() -> String {
    rand::rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect()
}

fn write_private(path: &Path, text: &str) -> Result<(), Problem> {
    fs::write(path, text)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

/// 실행 파일 이름 — 윈도는 `.exe`
fn exe(bin: &Path, name: &str) -> PathBuf {
    if cfg!(windows) {
        bin.join(format!("{name}.exe"))
    } else {
        bin.join(name)
    }
}

/// 실패면 끝 코드와 표준 오류 마지막 줄들 — 암호가 든 출력은 가린다
fn checked(out: std::io::Result<Output>, what: &str, secret: Option<&str>) -> Result<(), Problem> {
    let out = out.map_err(|e| Problem::Internal {
        log: format!("{what}을 못 돌렸다 — {e}"),
    })?;
    if out.status.success() {
        return Ok(());
    }
    let mut err = String::from_utf8_lossy(&out.stderr).into_owned();
    if let Some(s) = secret {
        err = err.replace(s, "***");
    }
    Err(Problem::Internal {
        log: format!("{what} 실패({}) — {}", out.status, tail(&err)),
    })
}

/// 마지막 다섯 줄을 한 줄로
fn tail(text: &str) -> String {
    let lines: Vec<&str> = text.lines().rev().take(5).collect();
    lines.into_iter().rev().collect::<Vec<_>>().join(" / ")
}
