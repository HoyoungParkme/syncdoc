//! references 행 — 속성은 SYNC-DOM-003 그대로 (SYNC-DOM-004 2.3)

/// `references` 한 행 — 끊어진 참조는 `is_missing`이고 `to_*`가 비며 `raw_target`이 남는다
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct ReferenceRow {
    pub id: i32,
    pub from_item_id: Option<i32>,
    pub from_document_id: i32,
    pub to_item_id: Option<i32>,
    pub to_document_id: Option<i32>,
    pub raw_target: String,
    pub is_missing: bool,
    pub extracted_version_id: i32,
}
