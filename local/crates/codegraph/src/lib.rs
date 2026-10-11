//! 코드 그래프의 순수 부분 — 추출·줄이기·보강·대조·층 (SYNC-DOM-004 1장 crates/codegraph, SYNC-MS-022).
//! DB·git을 모르고 파일만 읽는다. 파이썬 판 `core/codegraph/graph.py`와 같은 이름·같은 처리·같은 그래프 모양이다 —
//! 같은 원형이면 바이트까지 같은 그래프를 낸다(정답 파일 `tests/golden/codegraph.json`, `cargo xtask codegraph-golden`).

pub mod community;
pub mod enrich;
mod extract;
pub mod graph;
mod python;
mod rust;
mod ts;

use serde::{Deserialize, Serialize};

pub use community::communities;
pub use enrich::enrich;
pub use extract::extract;
pub use graph::{
    compare, item_function, item_neighbors, layer_table, layers, load, reduce, spec_calls,
    touches_code,
};

/// 함수·메서드 하나 — `key`는 `파일:줄` (SYNC-MS-011 0장 그래프 모양)
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Function {
    pub key: String,
    pub name: String,
    pub qual: String,
    pub file: String,
    pub line: i64,
    #[serde(default)]
    pub end: Option<i64>,
    /// 속한 명세 항목 — 2026-10-02 이전 그래프에는 없다
    #[serde(default)]
    pub item: Option<String>,
    #[serde(default)]
    pub ms: Option<String>,
    /// 든 커뮤니티 — 커뮤니티를 나눈 그래프에만(카드 L13)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub community: Option<i64>,
}

/// 호출 선 `[from, to, via]` — via는 `graphify` 또는 `enrich`
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Call(pub String, pub String, pub String);

/// 커뮤니티 하나 (카드 L13)
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Community {
    pub id: i64,
    pub label: String,
    pub size: i64,
}

/// 그래프 — `code_graphs.graph`에 그대로 들어가는 것. `files`는 줄이기가 주고 보강이 쓰고 비운다
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Graph {
    #[serde(default)]
    pub functions: Vec<Function>,
    #[serde(default)]
    pub calls: Vec<Call>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub communities: Option<Vec<Community>>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub files: Vec<String>,
}

/// 명세 호출과 코드 호출의 대조 한 줄 (DOM-002 2.8 `CallDiff`)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CallDiff {
    pub ms_id: String,
    pub function: Option<String>,
    pub same: Vec<String>,
    pub code_only: Vec<String>,
    pub spec_only: Vec<String>,
}

/// 층 표의 명세 칸 조각 — `[[…]]` 안(없으면 없음)과 나머지 글자
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LayerSpec {
    #[serde(rename = "ref")]
    pub ref_: Option<String>,
    pub note: String,
}

/// 층 표의 한 줄 — 경로 꼴들·층 이름·명세 조각·본문 줄 번호
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LayerRow {
    pub patterns: Vec<String>,
    pub name: String,
    pub specs: Vec<LayerSpec>,
    pub line: i64,
}

/// 함수 하나의 층 — 이름과 명세 조각
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Layer {
    pub name: String,
    pub specs: Vec<LayerSpec>,
}

/// 코드 그래프를 못 만들었다 — 문장 하나. 그래프 만들기가 그래프 행의 `error`로 남긴다(HTTP로 나가지 않는다)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodeGraphFailed(pub String);

impl std::fmt::Display for CodeGraphFailed {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for CodeGraphFailed {}
