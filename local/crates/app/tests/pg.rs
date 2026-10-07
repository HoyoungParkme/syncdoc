//! SYNC-MS-012#pg.start·pg.stop 테스트 관점 — 진짜 바이너리(`cargo xtask pg-fetch`), 임시 데이터 자리

use std::mem;

use sqlx::{Connection, PgConnection};
use syncdoc_app::paths::pg_dir;
use syncdoc_app::pg::{start, stop};

async fn show(c: &mut PgConnection, name: &str) -> String {
    sqlx::query_scalar(sqlx::AssertSqlSafe(format!("SHOW {name}")))
        .fetch_one(c)
        .await
        .expect(name)
}

#[tokio::test]
async fn start_stop_and_restart_with_new_password() {
    let bins = pg_dir().expect("cargo xtask pg-fetch로 받은 PostgreSQL");
    let dir = tempfile::tempdir().unwrap();

    // 처음 — initdb부터
    let first = start(&bins, dir.path()).await.expect("처음 띄운다");
    let mut c = PgConnection::connect_with(&first.options)
        .await
        .expect("붙는다");
    assert_eq!(show(&mut c, "listen_addresses").await, "127.0.0.1");
    assert_eq!(show(&mut c, "fsync").await, "on");
    assert_eq!(show(&mut c, "server_encoding").await, "UTF8");
    // PostgreSQL 16은 lc_collate 변수를 없앴다 — DB의 정렬로 본다
    let collate: String =
        sqlx::query_scalar("SELECT datcollate FROM pg_database WHERE datname = current_database()")
            .fetch_one(&mut c)
            .await
            .unwrap();
    assert_eq!(collate, "C");
    let user: String = sqlx::query_scalar("SELECT current_user")
        .fetch_one(&mut c)
        .await
        .unwrap();
    let db: String = sqlx::query_scalar("SELECT current_database()")
        .fetch_one(&mut c)
        .await
        .unwrap();
    assert_eq!((user.as_str(), db.as_str()), ("syncdoc", "syncdoc"));
    sqlx::raw_sql("CREATE TABLE kept (x int); INSERT INTO kept VALUES (7)")
        .execute(&mut c)
        .await
        .unwrap();
    c.close().await.unwrap();
    assert!(
        !dir.path().join("pgdata.pw").exists(),
        "암호 파일이 남지 않는다"
    );
    let old = first.options.clone();

    // 멈추지 않고 버려도(비정상 종료) 다음 start가 된다
    mem::forget(first);
    let second = start(&bins, dir.path())
        .await
        .expect("남은 서버를 정리하고 다시 띄운다");
    let mut c = PgConnection::connect_with(&second.options)
        .await
        .expect("새 암호로 붙는다");
    let x: i32 = sqlx::query_scalar("SELECT x FROM kept")
        .fetch_one(&mut c)
        .await
        .expect("데이터가 그대로");
    assert_eq!(x, 7);
    c.close().await.unwrap();
    let stale = old.port(second.port);
    assert!(
        PgConnection::connect_with(&stale).await.is_err(),
        "옛 암호는 안 된다"
    );

    let pgdata = second.pgdata.clone();
    let options = second.options.clone();
    stop(second).await.expect("멈춘다");
    assert!(!pgdata.join("postmaster.pid").exists());
    assert!(
        PgConnection::connect_with(&options).await.is_err(),
        "멈춘 뒤에는 붙을 수 없다"
    );
}
