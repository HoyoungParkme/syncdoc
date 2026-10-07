//! 두 판의 스키마가 같은지 — SYNC-STD-004#DEV-7.
//! 시험 서버에 Alembic(온라인)이 올린 DB와 Rust 판(`migrate::apply`)이 올린 DB를 만들어
//! `pg_dump --schema-only`와 `alembic_version`을 비교하고 지운다. 이름에 test가 없는 서버면 시작하지 않는다.

use std::process::Command;

use sqlx::{Connection, PgConnection};
use syncdoc_core::migrate;

use crate::pg_fetch::VERSION;
use crate::testdb::{TestServer, create_db, drop_db};
use crate::{local_root, repo_root};

const ALEMBIC_DB: &str = "syncdoc_local_test_schema_alembic";
const RUST_DB: &str = "syncdoc_local_test_schema_rust";

pub async fn run() -> Result<(), String> {
    let server = TestServer::from_env()?;
    let result = compare(&server).await;
    if let Ok(mut admin) = PgConnection::connect_with(&server.options("postgres")?).await {
        for db in [ALEMBIC_DB, RUST_DB] {
            let _ = drop_db(&mut admin, db).await;
        }
    }
    result
}

async fn compare(server: &TestServer) -> Result<(), String> {
    let mut admin = PgConnection::connect_with(&server.options("postgres")?)
        .await
        .map_err(|e| e.to_string())?;
    for db in [ALEMBIC_DB, RUST_DB] {
        drop_db(&mut admin, db).await?;
        create_db(&mut admin, db).await?;
    }
    // Alembic — 온라인으로. DATABASE_URL을 시험 서버의 시험 DB로 덮어쓴다(운영 DB에 닿지 않게)
    let (user, pw) = server.credentials();
    let url = format!(
        "postgresql+psycopg://{user}:{pw}@{}",
        server.rest_for(ALEMBIC_DB)
    );
    let out = Command::new("uv")
        .args(["run", "--quiet", "alembic", "upgrade", "head"])
        .current_dir(repo_root().join("backend"))
        .env("DATABASE_URL", &url)
        .output()
        .map_err(|e| format!("uv를 못 돌렸다 — {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "alembic upgrade head 실패 — {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    // Rust 판
    let mut conn = PgConnection::connect_with(&server.options(RUST_DB)?)
        .await
        .map_err(|e| e.to_string())?;
    migrate::apply(&mut conn).await.map_err(|e| e.to_string())?;
    conn.close().await.map_err(|e| e.to_string())?;

    let (a, b) = (dump(server, ALEMBIC_DB)?, dump(server, RUST_DB)?);
    let (va, vb) = (
        version(server, ALEMBIC_DB).await?,
        version(server, RUST_DB).await?,
    );
    if a != b || va != vb {
        let only_a: Vec<&String> = a.iter().filter(|l| !b.contains(l)).collect();
        let only_b: Vec<&String> = b.iter().filter(|l| !a.contains(l)).collect();
        return Err(format!(
            "스키마가 다르다 — alembic_version {va} / {vb}\n  Alembic에만: {only_a:?}\n  Rust 판에만: {only_b:?}"
        ));
    }
    println!("스키마가 같다 — 덤프 {}줄 · alembic_version {va}", a.len());
    Ok(())
}

/// `pg_dump --schema-only` — 주석·SET·빈 줄과 실행마다 바뀌는 `\restrict` 줄을 뺀 줄들
fn dump(server: &TestServer, db: &str) -> Result<Vec<String>, String> {
    let pg_dump = local_root()
        .join("target")
        .join("pg")
        .join(VERSION)
        .join("bin")
        .join("pg_dump");
    let (user, pw) = server.credentials();
    let opts = server.options(db)?;
    let out = Command::new(&pg_dump)
        .args(["--schema-only", "--no-owner", "--no-privileges"])
        .args([
            "-h",
            opts.get_host(),
            "-p",
            &opts.get_port().to_string(),
            "-U",
            &user,
            "-d",
            db,
        ])
        .env("PGPASSWORD", pw)
        .output()
        .map_err(|e| {
            format!(
                "{}을 못 돌렸다(cargo xtask pg-fetch) — {e}",
                pg_dump.display()
            )
        })?;
    if !out.status.success() {
        return Err(format!(
            "pg_dump {db} 실패 — {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout)
        .lines()
        .filter(|l| {
            let t = l.trim();
            !t.is_empty()
                && !t.starts_with("--")
                && !t.starts_with("SET ")
                && !t.starts_with("SELECT pg_catalog.set_config")
                && !t.starts_with("\\restrict")
                && !t.starts_with("\\unrestrict")
        })
        .map(str::to_string)
        .collect())
}

async fn version(server: &TestServer, db: &str) -> Result<String, String> {
    let mut conn = PgConnection::connect_with(&server.options(db)?)
        .await
        .map_err(|e| e.to_string())?;
    let v: String = sqlx::query_scalar("SELECT version_num FROM alembic_version")
        .fetch_one(&mut conn)
        .await
        .map_err(|e| e.to_string())?;
    conn.close().await.map_err(|e| e.to_string())?;
    Ok(v)
}
