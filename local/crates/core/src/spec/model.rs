//! documents·items·versions 행 — 속성은 SYNC-DOM-003 그대로 (SYNC-DOM-004 2.2)

use time::OffsetDateTime;

/// `documents` 한 행
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct DocumentRow {
    pub id: i32,
    pub project_id: i32,
    pub doc_id: String,
    pub doc_type: String,
    pub status: String,
    pub current_body: String,
    pub current_version_no: i32,
    pub has_convention_error: bool,
    pub convention_error_detail: Option<String>,
    pub incomplete_warnings: Option<String>,
    pub trashed_at: Option<OffsetDateTime>,
    pub trashed_by_user_id: Option<i32>,
    pub updated_at: OffsetDateTime,
}

/// `items` 한 행 — 지운 항목도 행은 남는다(`is_deleted`)
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct ItemRow {
    pub id: i32,
    pub document_id: i32,
    pub item_id: String,
    pub display_name: Option<String>,
    pub is_deleted: bool,
    pub deleted_at: Option<OffsetDateTime>,
}

/// `versions` 한 행 — 본문 사본과 작성자
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct VersionRow {
    pub id: i32,
    pub document_id: i32,
    pub version_no: i32,
    pub commit_hash: String,
    pub body: String,
    pub author_kind: String,
    pub author_user_id: i32,
    pub instructed_by_user_id: Option<i32>,
    pub via: String,
    pub message: String,
    pub created_at: OffsetDateTime,
}
