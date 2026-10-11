//! conversation — 읽는 중 질의의 보관 (SYNC-DOM-004 4.10 · SYNC-MS-021). 대화·턴·첨부.
//! 명세 묶음과 선이 없다 — 문서·항목 표를 읽지도 쓰지도 않고 프로젝트·사용자를 ID로만 가리킨다

pub mod model;
pub mod repo;
pub mod service;

pub use model::{AttachmentRow, ConversationRow, TurnRow};
pub use service::ConversationService;
