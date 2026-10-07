//! users 조회·저장 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use sqlx::PgConnection;

use super::model::UserRow;
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
