//! code_graphs 행 — 속성은 SYNC-DOM-003 그대로 (SYNC-DOM-004 2장 · 파이썬 판 `CodeGraph`)

use syncdoc_codegraph::Graph;
use time::OffsetDateTime;

/// `code_graphs` 한 행 — PK가 곧 `project_id`라 프로젝트마다 하나. 항목 ID는 `graph` 안의 글자다
#[derive(Clone, Debug)]
pub struct CodeGraphRow {
    pub project_id: i32,
    pub commit_hash: Option<String>,
    /// `repo`(커밋된 graph.json) · `server`(뽑았다)
    pub source: Option<String>,
    pub graph: Graph,
    pub function_count: i32,
    pub call_count: i32,
    pub built_at: OffsetDateTime,
    pub error: Option<String>,
}
