//! 시험 서버(5434) — `SYNCDOC_LOCAL_TEST_DATABASE_URL`. 이름에 test가 없으면 쓰지 않는다 (SYNC-STD-004#DEV-14)

use sqlx::postgres::PgConnectOptions;
use sqlx::{AssertSqlSafe, Connection, PgConnection};

pub const DEFAULT_URL: &str = "postgres://syncdoc:syncdoc@127.0.0.1:5434/syncdoc_local_test";

/// 시험 서버 주소 — `scheme://user:pw@host:port/db`
pub struct TestServer {
    url: String,
}

impl TestServer {
    pub fn from_env() -> Result<Self, String> {
        let url =
            std::env::var("SYNCDOC_LOCAL_TEST_DATABASE_URL").unwrap_or_else(|_| DEFAULT_URL.into());
        let name = url.rsplit('/').next().unwrap_or("");
        if !name.contains("test") {
            return Err(format!("시험 DB가 아니다 — 이름에 test가 없다: {name}"));
        }
        Ok(Self { url })
    }

    /// 같은 서버의 다른 DB 주소
    pub fn url_for(&self, db: &str) -> String {
        let base = self
            .url
            .rsplit_once('/')
            .map_or(self.url.as_str(), |(b, _)| b);
        format!("{base}/{db}")
    }

    pub fn options(&self, db: &str) -> Result<PgConnectOptions, String> {
        self.url_for(db).parse().map_err(|e| format!("{e}"))
    }

    /// 주소의 사용자 정보 뒤 — `user:pw@` 빼고 (`host:port/db`)
    pub fn rest_for(&self, db: &str) -> String {
        let url = self.url_for(db);
        let after = url.split_once("://").map_or(url.as_str(), |(_, r)| r);
        after.rsplit_once('@').map_or(after, |(_, r)| r).to_string()
    }

    /// 주소의 사용자와 암호 — 명령줄에 싣지 않고 환경 변수로 넘긴다
    pub fn credentials(&self) -> (String, String) {
        let after = self
            .url
            .split_once("://")
            .map_or(self.url.as_str(), |(_, r)| r);
        let info = after.rsplit_once('@').map_or("", |(i, _)| i);
        let (user, pw) = info.split_once(':').unwrap_or((info, ""));
        (user.to_string(), pw.to_string())
    }
}

/// 시험이 남긴 `syncdoc_local_test_*` DB를 지운다
pub async fn clean() -> Result<(), String> {
    let server = TestServer::from_env()?;
    let mut conn = PgConnection::connect_with(&server.options("postgres")?)
        .await
        .map_err(|e| e.to_string())?;
    let names: Vec<String> = sqlx::query_scalar(
        "SELECT datname FROM pg_database WHERE datname LIKE 'syncdoc\\_local\\_test\\_%'",
    )
    .fetch_all(&mut conn)
    .await
    .map_err(|e| e.to_string())?;
    for n in &names {
        drop_db(&mut conn, n).await?;
    }
    println!("시험 DB {}개를 지웠다", names.len());
    Ok(())
}

pub async fn drop_db(conn: &mut PgConnection, db: &str) -> Result<(), String> {
    sqlx::raw_sql(AssertSqlSafe(format!(
        "DROP DATABASE IF EXISTS \"{db}\" WITH (FORCE)"
    )))
    .execute(conn)
    .await
    .map(|_| ())
    .map_err(|e| e.to_string())
}

pub async fn create_db(conn: &mut PgConnection, db: &str) -> Result<(), String> {
    sqlx::raw_sql(AssertSqlSafe(format!("CREATE DATABASE \"{db}\"")))
        .execute(conn)
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())
}
