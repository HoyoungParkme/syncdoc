//! SYNC-MS-016 테스트 관점 — 파이썬 판 SYNC-MS-006과 같은 경우들

mod support;

use sqlx::PgConnection;
use syncdoc_core::account::service::AccountService;

async fn count_local(c: &mut PgConnection) -> i64 {
    sqlx::query_scalar("SELECT count(*) FROM users WHERE kind = 'local'")
        .fetch_one(c)
        .await
        .expect("수")
}

#[tokio::test]
async fn ensure_local_user_makes_one_row_and_renames_it() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let first = AccountService { db: &mut c }
        .ensure_local_user("local", "로컬")
        .await
        .expect("처음");
    assert_eq!(
        (first.github_login.as_str(), first.kind.as_str()),
        ("local", "local")
    );
    assert_eq!(first.github_user_id, None);
    let again = AccountService { db: &mut c }
        .ensure_local_user("local", "로컬")
        .await
        .expect("다시");
    assert_eq!(again.id, first.id);
    assert_eq!(count_local(&mut c).await, 1);
    let renamed = AccountService { db: &mut c }
        .ensure_local_user("hoyoung", "호영")
        .await
        .expect("이름");
    assert_eq!(renamed.id, first.id);
    assert_eq!(
        (renamed.github_login.as_str(), renamed.display_name.as_str()),
        ("hoyoung", "호영")
    );
    assert_eq!(count_local(&mut c).await, 1);
}

#[tokio::test]
async fn ensure_local_user_refuses_someone_elses_login() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    for (login, kind) in [("gh", "github"), ("ph", "placeholder")] {
        sqlx::query("INSERT INTO users (github_login, display_name, kind) VALUES ($1, $1, $2)")
            .bind(login)
            .bind(kind)
            .execute(&mut *c)
            .await
            .expect("다른 사용자");
        let err = AccountService { db: &mut c }
            .ensure_local_user(login, "나")
            .await
            .expect_err("남의 아이디");
        assert!(err.to_string().contains("이미 다른 사용자다"), "{err}");
        let kind_now: String = sqlx::query_scalar("SELECT kind FROM users WHERE github_login = $1")
            .bind(login)
            .fetch_one(&mut *c)
            .await
            .expect("그 행");
        assert_eq!(kind_now, kind);
    }
    // 로컬 사용자가 있는데 아이디를 남의 것으로 바꾸려 하면
    AccountService { db: &mut c }
        .ensure_local_user("local", "나")
        .await
        .expect("로컬");
    let err = AccountService { db: &mut c }
        .ensure_local_user("gh", "나")
        .await
        .expect_err("남의 아이디로 바꿈");
    assert!(err.to_string().contains("이미 다른 사용자다"));
    assert_eq!(count_local(&mut c).await, 1);
}

#[tokio::test]
async fn local_user_returns_existing_or_creates() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let made = AccountService { db: &mut c }
        .local_user("local", "로컬")
        .await
        .expect("없으면 만든다");
    assert_eq!(made.github_login, "local");
    let same = AccountService { db: &mut c }
        .local_user("다른", "다른 이름")
        .await
        .expect("있으면 그 행");
    assert_eq!(
        (
            same.id,
            same.github_login.as_str(),
            same.display_name.as_str()
        ),
        (made.id, "local", "로컬")
    );
}
