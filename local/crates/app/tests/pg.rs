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

/// 첫 켜기는 디스크에 내리기를 뒤로 미룬다(카드 L19) — 표식이 생겼다가 뒤에서 지워지고,
/// 표식을 남겨 두고 켜면 서버를 띄우기 전에 마친다
#[tokio::test]
async fn first_start_defers_sync_behind_a_mark() {
    let bins = pg_dir().expect("cargo xtask pg-fetch로 받은 PostgreSQL");
    let dir = tempfile::tempdir().unwrap();
    let mark = dir.path().join(syncdoc_app::pg::SYNC_MARK);
    let first = start(&bins, dir.path()).await.expect("처음 띄운다");
    // 뒤에서 `initdb --sync-only`가 끝나면 표식이 없어진다
    let mut waited = 0;
    while mark.exists() && waited < 600 {
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        waited += 1;
    }
    assert!(!mark.exists(), "뒤의 동기화가 표식을 지운다");
    stop(first).await.expect("멈춘다");
    // 지난번에 마치지 못한 것처럼 표식을 두고 켠다 — 서버가 뜨기 전에 지워진다
    std::fs::write(&mark, "").unwrap();
    let again = start(&bins, dir.path()).await.expect("다시 띄운다");
    assert!(!mark.exists(), "켜기 전에 마친다");
    let mut c = PgConnection::connect_with(&again.options)
        .await
        .expect("붙는다");
    assert_eq!(show(&mut c, "fsync").await, "on");
    c.close().await.unwrap();
    stop(again).await.expect("멈춘다");
}
