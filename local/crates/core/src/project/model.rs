//! projects·repositories 행 — 속성은 SYNC-DOM-003 그대로 (SYNC-DOM-004 2.1)

use time::OffsetDateTime;

/// `projects` 한 행
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct ProjectRow {
    pub id: i32,
    pub code: String,
    pub name: String,
    pub created_at: OffsetDateTime,
    pub owner_user_id: i32,
}

/// `repositories` 한 행 — 프로젝트마다 하나. 서버 저장이면 `remote_url`이 서버 저장소의 절대 경로다
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct RepositoryRow {
    pub id: i32,
    pub project_id: i32,
    pub remote_url: String,
    pub workdir_path: String,
    pub last_processed_commit: Option<String>,
    pub synced_at: Option<OffsetDateTime>,
    pub registered_by_user_id: i32,
    pub storage: String,
    pub hook_id: Option<i32>,
    pub hook_error: Option<String>,
    pub fetch_error: Option<String>,
    pub behind_by: Option<i32>,
    pub fetched_at: Option<OffsetDateTime>,
}
