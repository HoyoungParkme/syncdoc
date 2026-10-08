//! users·access_tokens 행 — 속성은 SYNC-DOM-003 그대로 (SYNC-DOM-004 2.4)

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

/// `access_tokens` 한 행 — 원문은 없다, 해시만 (SYNC-INFRA-001 5장)
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct AccessTokenRow {
    pub id: i32,
    pub user_id: i32,
    pub token_hash: String,
    pub label: String,
    pub issued_at: OffsetDateTime,
    pub expires_at: Option<OffsetDateTime>,
    pub revoked_at: Option<OffsetDateTime>,
    pub last_used_at: Option<OffsetDateTime>,
}
