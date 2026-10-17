//! trace — 실행 기록 (SYNC-DOM-004 2.6a·4.14 · SYNC-MS-027). 받은 기록을 고치지 않고 최근 300개를 둔다

pub mod service;

pub use service::TraceService;
