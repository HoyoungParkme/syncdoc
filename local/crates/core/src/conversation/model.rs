//! conversations·turns·attachments 행 — 속성은 SYNC-DOM-003 그대로 (SYNC-DOM-004 2.5)

use serde_json::Value;
use time::OffsetDateTime;

/// `conversations` 한 행
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct ConversationRow {
    pub id: i32,
    pub project_id: i32,
    pub user_id: i32,
    pub title: String,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
}

/// `turns` 한 행 — 질문 하나와 그 답. `progress`·`context_item_ids`는 JSON 배열
#[derive(Clone, Debug)]
pub struct TurnRow {
    pub id: i32,
    pub conversation_id: i32,
    pub seq: i32,
    pub question: String,
    pub answer: Option<String>,
    pub progress: Value,
    pub context_item_ids: Value,
    pub error: Option<String>,
    pub created_at: OffsetDateTime,
}

/// `attachments` 한 행 — 바이트까지. `turn_id`가 없으면 아직 안 보낸 것
#[derive(Clone, Debug, sqlx::FromRow)]
pub struct AttachmentRow {
    pub id: i32,
    pub conversation_id: i32,
    pub turn_id: Option<i32>,
    pub user_id: i32,
    pub name: String,
    pub mime: String,
    pub size: i32,
    pub bytes: Vec<u8>,
    pub text_cache: Option<String>,
    pub created_at: OffsetDateTime,
}
