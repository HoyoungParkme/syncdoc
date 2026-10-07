//! SYNC-MS-012#migrate.apply 테스트 관점

mod support;

use std::fs;
use std::path::PathBuf;

use sqlx::{AssertSqlSafe, PgConnection};
use syncdoc_core::migrate;

fn migrations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../migrations")
}

fn files() -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = fs::read_dir(migrations_dir())
        .expect("local/migrations")
        .map(|e| e.expect("항목").path())
        .filter(|p| p.extension().is_some_and(|x| x == "sql"))
        .collect();
    v.sort();
    v
}

async fn version(c: &mut PgConnection) -> String {
    sqlx::query_scalar("SELECT version_num FROM alembic_version")
        .fetch_one(c)
        .await
        .expect("alembic_version")
}

#[tokio::test]
async fn empty_db_gets_every_revision() {
    let db = support::empty_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let applied = migrate::apply(&mut c).await.expect("이전");
    let names: Vec<String> = files()
        .iter()
        .map(|p| p.file_name().unwrap().to_string_lossy()[..4].to_string())
        .collect();
    assert_eq!(applied, names);
    assert_eq!(applied.first().copied(), Some("0001"));
    assert_eq!(version(&mut c).await, *applied.last().unwrap());
    let tables: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' \
         AND table_name <> 'alembic_version'",
    )
    .fetch_one(&mut *c)
    .await
    .expect("표 수");
    assert_eq!(tables, 14);
    // 다시 → 올릴 것이 없다
    assert!(migrate::apply(&mut c).await.expect("다시").is_empty());
}

#[tokio::test]
async fn half_migrated_db_gets_the_rest() {
    let db = support::empty_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let all = files();
    for f in &all[..10] {
        sqlx::raw_sql(AssertSqlSafe(fs::read_to_string(f).expect("SQL")))
            .execute(&mut *c)
            .await
            .expect("0001~0010");
    }
    assert_eq!(version(&mut c).await, "0010");
    let applied = migrate::apply(&mut c).await.expect("나머지");
    assert_eq!(applied.first().copied(), Some("0011"));
    assert_eq!(applied.len(), all.len() - 10);
}

#[tokio::test]
async fn unknown_revision_refuses_and_changes_nothing() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    sqlx::raw_sql("UPDATE alembic_version SET version_num = '9999'")
        .execute(&mut *c)
        .await
        .expect("새 판인 척");
    let err = migrate::apply(&mut c).await.expect_err("새 판 DB");
    assert!(err.to_string().contains("이 프로그램보다 새 판"), "{err}");
    assert_eq!(version(&mut c).await, "9999");
}

#[test]
fn each_file_moves_alembic_version_from_previous_to_itself() {
    let mut prev: Option<String> = None;
    for f in files() {
        let rev = f.file_name().unwrap().to_string_lossy()[..4].to_string();
        let sql = fs::read_to_string(&f).expect("SQL");
        let stamp = match &prev {
            None => format!("INSERT INTO alembic_version (version_num) VALUES ('{rev}')"),
            Some(p) => format!(
                "UPDATE alembic_version SET version_num='{rev}' WHERE alembic_version.version_num = '{p}'"
            ),
        };
        assert!(sql.contains(&stamp), "{}에 `{stamp}`이 없다", f.display());
        assert!(
            sql.trim_start().starts_with("BEGIN;") || sql.contains("\nBEGIN;"),
            "{} BEGIN",
            f.display()
        );
        assert!(
            sql.trim_end().ends_with("COMMIT;"),
            "{} COMMIT",
            f.display()
        );
        prev = Some(rev);
    }
    assert!(prev.is_some(), "이전 SQL이 없다 — cargo xtask migrations");
}
