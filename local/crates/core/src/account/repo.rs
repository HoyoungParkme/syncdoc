//! users·access_tokens 조회·저장 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use sqlx::{AssertSqlSafe, PgConnection};
use time::OffsetDateTime;

use super::model::{AccessTokenRow, UserRow};
use crate::types::UserKind;

/// `kind=local` 행 — 하나뿐이다. id 순 첫 행
pub async fn local_user(db: &mut PgConnection) -> Result<Option<UserRow>, sqlx::Error> {
    sqlx::query_as::<_, UserRow>(
        "SELECT id, github_login, github_user_id, display_name, github_token_encrypted, \
         created_at, kind FROM users WHERE kind = $1 ORDER BY id LIMIT 1",
    )
    .bind(UserKind::Local.as_str())
    .fetch_optional(db)
    .await
}

/// 아이디로 — 대소문자 그대로
pub async fn user_by_login(
    db: &mut PgConnection,
    login: &str,
) -> Result<Option<UserRow>, sqlx::Error> {
    sqlx::query_as::<_, UserRow>(
        "SELECT id, github_login, github_user_id, display_name, github_token_encrypted, \
         created_at, kind FROM users WHERE github_login = $1",
    )
    .bind(login)
    .fetch_optional(db)
    .await
}

/// 로컬 사용자를 넣는다 — GitHub 아이디·토큰 없음
pub async fn add_local_user(
    db: &mut PgConnection,
    login: &str,
    display_name: &str,
) -> Result<UserRow, sqlx::Error> {
    sqlx::query_as::<_, UserRow>(
        "INSERT INTO users (github_login, github_user_id, kind, display_name, \
         github_token_encrypted) VALUES ($1, NULL, $2, $3, NULL) \
         RETURNING id, github_login, github_user_id, display_name, github_token_encrypted, \
         created_at, kind",
    )
    .bind(login)
    .bind(UserKind::Local.as_str())
    .bind(display_name)
    .fetch_one(db)
    .await
}

/// 아이디·이름을 고친다
pub async fn rename(
    db: &mut PgConnection,
    id: i32,
    login: &str,
    display_name: &str,
) -> Result<UserRow, sqlx::Error> {
    sqlx::query_as::<_, UserRow>(
        "UPDATE users SET github_login = $2, display_name = $3 WHERE id = $1 \
         RETURNING id, github_login, github_user_id, display_name, github_token_encrypted, \
         created_at, kind",
    )
    .bind(id)
    .bind(login)
    .bind(display_name)
    .fetch_one(db)
    .await
}

const TOKEN_COLS: &str =
    "id, user_id, token_hash, label, issued_at, expires_at, revoked_at, last_used_at";

/// 사용자의 토큰 — 새것이 앞 (파이썬 `tokens_of`)
pub async fn tokens_of(
    db: &mut PgConnection,
    user_id: i32,
) -> Result<Vec<AccessTokenRow>, sqlx::Error> {
    sqlx::query_as::<_, AccessTokenRow>(AssertSqlSafe(format!(
        "SELECT {TOKEN_COLS} FROM access_tokens WHERE user_id = $1 ORDER BY issued_at DESC"
    )))
    .bind(user_id)
    .fetch_all(db)
    .await
}

/// 해시로 토큰 하나
pub async fn token_by_hash(
    db: &mut PgConnection,
    token_hash: &str,
) -> Result<Option<AccessTokenRow>, sqlx::Error> {
    sqlx::query_as::<_, AccessTokenRow>(AssertSqlSafe(format!(
        "SELECT {TOKEN_COLS} FROM access_tokens WHERE token_hash = $1"
    )))
    .bind(token_hash)
    .fetch_optional(db)
    .await
}

/// 그 사용자의 토큰 하나 — 남의 것은 없는 것과 같다
pub async fn token_of_user(
    db: &mut PgConnection,
    token_id: i32,
    user_id: i32,
) -> Result<Option<AccessTokenRow>, sqlx::Error> {
    sqlx::query_as::<_, AccessTokenRow>(AssertSqlSafe(format!(
        "SELECT {TOKEN_COLS} FROM access_tokens WHERE id = $1 AND user_id = $2"
    )))
    .bind(token_id)
    .bind(user_id)
    .fetch_optional(db)
    .await
}

/// 토큰을 넣는다 — 만료·사용 흔적 없음
pub async fn add_token(
    db: &mut PgConnection,
    user_id: i32,
    token_hash: &str,
    label: &str,
    issued_at: OffsetDateTime,
) -> Result<AccessTokenRow, sqlx::Error> {
    sqlx::query_as::<_, AccessTokenRow>(AssertSqlSafe(format!(
        "INSERT INTO access_tokens (user_id, token_hash, label, issued_at, expires_at, \
         revoked_at, last_used_at) VALUES ($1, $2, $3, $4, NULL, NULL, NULL) RETURNING {TOKEN_COLS}"
    )))
    .bind(user_id)
    .bind(token_hash)
    .bind(label)
    .bind(issued_at)
    .fetch_one(db)
    .await
}

/// 폐기 시각을 적는다
pub async fn set_revoked(
    db: &mut PgConnection,
    id: i32,
    at: OffsetDateTime,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE access_tokens SET revoked_at = $2 WHERE id = $1")
        .bind(id)
        .bind(at)
        .execute(db)
        .await
        .map(|_| ())
}

/// 마지막 사용 시각을 적는다
pub async fn set_last_used(
    db: &mut PgConnection,
    id: i32,
    at: OffsetDateTime,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE access_tokens SET last_used_at = $2 WHERE id = $1")
        .bind(id)
        .bind(at)
        .execute(db)
        .await
        .map(|_| ())
}

/// id로 사용자
pub async fn user_by_id(db: &mut PgConnection, id: i32) -> Result<Option<UserRow>, sqlx::Error> {
    sqlx::query_as::<_, UserRow>(
        "SELECT id, github_login, github_user_id, display_name, github_token_encrypted, \
         created_at, kind FROM users WHERE id = $1",
    )
    .bind(id)
    .fetch_optional(db)
    .await
}

/// id 여럿으로 사용자 — 쿼리 한 번, 차례 없음
pub async fn users_by_ids(db: &mut PgConnection, ids: &[i32]) -> Result<Vec<UserRow>, sqlx::Error> {
    sqlx::query_as::<_, UserRow>(
        "SELECT id, github_login, github_user_id, display_name, github_token_encrypted, \
         created_at, kind FROM users WHERE id = ANY($1)",
    )
    .bind(ids)
    .fetch_all(db)
    .await
}
