//! codegraph — 코드 그래프 행 (SYNC-DOM-004 4.11 · SYNC-MS-022). 프로젝트마다 최신 하나.
//! 추출·줄이기·보강·대조는 `syncdoc_codegraph`(DB를 모른다)가 한다

pub mod model;
pub mod repo;
pub mod service;

pub use model::CodeGraphRow;
pub use service::CodeGraphService;
