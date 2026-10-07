//! users 행 — 속성은 SYNC-DOM-003 `users` 그대로 (SYNC-DOM-004 2.4)

use time::OffsetDateTime;

/// `users` 한 행
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct UserRow {
    pub id: i32,
    pub github_login: String,
    pub github_user_id: Option<i64>,
    pub display_name: String,
    pub github_token_encrypted: Option<Vec<u8>>,
    pub created_at: OffsetDateTime,
    pub kind: String,
}
