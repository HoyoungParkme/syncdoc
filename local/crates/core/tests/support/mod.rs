//! 시험 DB — 시험 컨테이너(5434)에 시험마다 DB 하나 (SYNC-STD-004#DEV-14 Rust).
//! 이름은 `syncdoc_local_test_{pid}_{n}`, 이전 SQL을 올려 둔다. 놓이면 지운다 — 남은 것은 `cargo xtask test-db-clean`.
//! 다른 서버는 `SYNCDOC_LOCAL_TEST_DATABASE_URL` — 이름에 test가 없으면 시작하지 않는다.

#![allow(dead_code)]

use std::sync::atomic::{AtomicUsize, Ordering};

use sqlx::postgres::{PgConnectOptions, PgPoolOptions};
use sqlx::{AssertSqlSafe, Connection, PgConnection, PgPool};
use syncdoc_core::migrate;

const DEFAULT_URL: &str = "postgres://syncdoc:syncdoc@127.0.0.1:5434/syncdoc_local_test";
static NEXT: AtomicUsize = AtomicUsize::new(0);

pub struct TestDb {
    pub pool: PgPool,
    pub name: String,
    admin: PgConnectOptions,
}

/// 시험 서버의 관리 연결(DB `postgres`)
pub fn admin_options() -> PgConnectOptions {
    let url =
        std::env::var("SYNCDOC_LOCAL_TEST_DATABASE_URL").unwrap_or_else(|_| DEFAULT_URL.into());
    let name = url.rsplit('/').next().unwrap_or("");
    assert!(
        name.contains("test"),
        "시험 DB가 아니다 — 이름에 test가 없다: {name}"
    );
    url.parse::<PgConnectOptions>()
        .expect("시험 DB 주소")
        .database("postgres")
}

/// 빈 DB — 이전을 올리지 않는다
pub async fn empty_db() -> TestDb {
    let admin = admin_options();
    let name = format!(
        "syncdoc_local_test_{}_{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    );
    let mut conn = PgConnection::connect_with(&admin)
        .await
        .expect("시험 서버(5434)에 붙는다");
    sqlx::raw_sql(AssertSqlSafe(format!(
        "DROP DATABASE IF EXISTS \"{name}\" WITH (FORCE)"
    )))
    .execute(&mut conn)
    .await
    .expect("지난 시험 DB를 지운다");
    sqlx::raw_sql(AssertSqlSafe(format!("CREATE DATABASE \"{name}\"")))
        .execute(&mut conn)
        .await
        .expect("시험 DB를 만든다");
    conn.close().await.expect("관리 연결을 닫는다");
    let pool = PgPoolOptions::new()
        .max_connections(4)
        .connect_with(admin.clone().database(&name))
        .await
        .expect("시험 DB 풀");
    TestDb { pool, name, admin }
}

/// 이전 SQL을 다 올린 DB
pub async fn test_db() -> TestDb {
    let db = empty_db().await;
    let mut conn = db.pool.acquire().await.expect("연결");
    migrate::apply(&mut conn).await.expect("이전 SQL");
    drop(conn);
    db
}

impl Drop for TestDb {
    fn drop(&mut self) {
        let (admin, name) = (self.admin.clone(), self.name.clone());
        // 시험의 런타임 밖에서 — 패닉 뒤에도 지운다
        let _ = std::thread::spawn(move || {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build();
            if let Ok(rt) = rt {
                rt.block_on(async move {
                    if let Ok(mut c) = PgConnection::connect_with(&admin).await {
                        let _ = sqlx::raw_sql(AssertSqlSafe(format!(
                            "DROP DATABASE IF EXISTS \"{name}\" WITH (FORCE)"
                        )))
                        .execute(&mut c)
                        .await;
                    }
                });
            }
        })
        .join();
    }
}

/// 임시 자리의 서버 저장소 자리 — git은 PATH의 것, 전역 설정은 그 자리의 빈 파일 (SYNC-MS-013 0장)
pub fn server_repos(root: &std::path::Path) -> syncdoc_core::project::service::ServerRepos {
    for d in ["origins", "repos"] {
        let _ = std::fs::create_dir_all(root.join(d));
    }
    let global = root.join("gitconfig");
    let _ = std::fs::write(&global, "");
    syncdoc_core::project::service::ServerRepos {
        git: syncdoc_core::infra::git::Git {
            exe: "git".into(),
            global_config: global,
        },
        origins: root.join("origins"),
        repos: root.join("repos"),
        specs_url: "http://127.0.0.1:8010/specs".into(),
    }
}
