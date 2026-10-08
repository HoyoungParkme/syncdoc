//! spec — 문서·항목·버전과 명세 엔진 (SYNC-DOM-004 4.3 · SYNC-MS-014)

pub mod model;
pub mod repo;
pub mod service;

pub use model::{DocumentRow, ItemRow, VersionRow};
pub use service::{DIFF_CONTEXT_LINES, SUBTYPES, SpecService, TYPES};
