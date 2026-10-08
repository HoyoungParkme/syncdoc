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

// ---- 토큰 (카드 L3) ----

async fn local(c: &mut PgConnection) -> syncdoc_core::account::model::UserRow {
    AccountService { db: c }
        .ensure_local_user("local", "local")
        .await
        .expect("로컬 사용자")
}

#[tokio::test]
async fn issue_token_keeps_only_the_hash() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let u = local(&mut c).await;
    let issued = AccountService { db: &mut c }
        .issue_token(&u, "노트북")
        .await
        .expect("발급");
    assert!(issued.raw.starts_with("syncdoc_pat_"));
    assert_eq!(issued.raw.len(), "syncdoc_pat_".len() + 43);
    assert_eq!(
        issued.token.token_hash,
        syncdoc_core::account::service::sha256_hex(&issued.raw)
    );
    let raw_in_db: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM access_tokens WHERE token_hash = $1 OR label = $1",
    )
    .bind(&issued.raw)
    .fetch_one(&mut *c)
    .await
    .expect("수");
    assert_eq!(raw_in_db, 0);
    let t = &issued.token;
    assert!(t.last_used_at.is_none() && t.revoked_at.is_none() && t.expires_at.is_none());
    assert_eq!(t.label, "노트북");
}

#[tokio::test]
async fn authenticate_token_marks_use_only_when_it_passes() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let u = local(&mut c).await;
    let issued = AccountService { db: &mut c }
        .issue_token(&u, "a")
        .await
        .expect("발급");
    let typo = AccountService { db: &mut c }
        .authenticate_token(&format!("{}x", issued.raw))
        .await
        .expect("오타");
    assert!(typo.is_none());
    let before = AccountService { db: &mut c }
        .list_tokens(&u)
        .await
        .expect("목록");
    assert!(before[0].last_used_at.is_none());
    let who = AccountService { db: &mut c }
        .authenticate_token(&issued.raw)
        .await
        .expect("인증")
        .expect("통과");
    assert_eq!(who.id, u.id);
    let after = AccountService { db: &mut c }
        .list_tokens(&u)
        .await
        .expect("목록");
    assert!(after[0].last_used_at.is_some());
    AccountService { db: &mut c }
        .revoke_token(&u, i64::from(issued.token.id))
        .await
        .expect("폐기");
    let revoked = AccountService { db: &mut c }
        .authenticate_token(&issued.raw)
        .await
        .expect("폐기 뒤");
    assert!(revoked.is_none());
}

#[tokio::test]
async fn list_tokens_newest_first_including_revoked() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let u = local(&mut c).await;
    let a = AccountService { db: &mut c }
        .issue_token(&u, "a")
        .await
        .expect("a");
    let b = AccountService { db: &mut c }
        .issue_token(&u, "b")
        .await
        .expect("b");
    AccountService { db: &mut c }
        .revoke_token(&u, i64::from(a.token.id))
        .await
        .expect("폐기");
    let list = AccountService { db: &mut c }
        .list_tokens(&u)
        .await
        .expect("목록");
    assert_eq!(
        list.iter().map(|t| t.id).collect::<Vec<_>>(),
        vec![b.token.id, a.token.id]
    );
    assert!(list[1].revoked_at.is_some());
}

#[tokio::test]
async fn revoke_token_of_someone_else_is_not_found() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let u = local(&mut c).await;
    let other: syncdoc_core::account::model::UserRow = sqlx::query_as(
        "INSERT INTO users (github_login, github_user_id, kind, display_name) \
         VALUES ('other', 7, 'github', 'other') RETURNING id, github_login, github_user_id, \
         display_name, github_token_encrypted, created_at, kind",
    )
    .fetch_one(&mut *c)
    .await
    .expect("남");
    let theirs = AccountService { db: &mut c }
        .issue_token(&other, "x")
        .await
        .expect("남의 토큰");
    let e = AccountService { db: &mut c }
        .revoke_token(&u, i64::from(theirs.token.id))
        .await
        .expect_err("남의 것");
    assert_eq!(e.kind(), Some("not-found"));
    assert_eq!(
        e.to_string(),
        format!("access_token {} 없음", theirs.token.id)
    );
    let still = AccountService { db: &mut c }
        .list_tokens(&other)
        .await
        .expect("목록");
    assert!(still[0].revoked_at.is_none());
    let missing = AccountService { db: &mut c }
        .revoke_token(&u, 999_999)
        .await
        .expect_err("없는 id");
    assert_eq!(missing.to_string(), "access_token 999999 없음");
    let out_of_range = AccountService { db: &mut c }
        .revoke_token(&u, i64::from(i32::MAX) + 1)
        .await
        .expect_err("int4 밖");
    assert_eq!(out_of_range.kind(), Some("internal"));
}
