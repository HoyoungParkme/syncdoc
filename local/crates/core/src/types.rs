//! 열거형·DTO — SYNC-DOM-002 2.7·2.8 그대로 (Rust는 `syncdoc_core::types`).
//! 직렬화 이름(JSON 키·열거형 값)도 파이썬 판과 같다.

use std::fmt;

use indexmap::IndexMap;
use serde::Serialize;
use time::OffsetDateTime;

use crate::account::model::{AccessTokenRow, UserRow};

/// 문서 타입 — 11단계 코드와 `STD` (SYNC-STD-001 1.1)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize)]
pub enum DocType {
    #[serde(rename = "RFQ")]
    Rfq,
    #[serde(rename = "PRD")]
    Prd,
    #[serde(rename = "SCN")]
    Scn,
    #[serde(rename = "UC")]
    Uc,
    #[serde(rename = "INFRA")]
    Infra,
    #[serde(rename = "DOM")]
    Dom,
    #[serde(rename = "UI")]
    Ui,
    #[serde(rename = "API")]
    Api,
    #[serde(rename = "SEQ")]
    Seq,
    #[serde(rename = "MS")]
    Ms,
    #[serde(rename = "CODE")]
    Code,
    #[serde(rename = "STD")]
    Std,
}

impl DocType {
    pub const ALL: [DocType; 12] = [
        DocType::Rfq,
        DocType::Prd,
        DocType::Scn,
        DocType::Uc,
        DocType::Infra,
        DocType::Dom,
        DocType::Ui,
        DocType::Api,
        DocType::Seq,
        DocType::Ms,
        DocType::Code,
        DocType::Std,
    ];

    pub fn as_str(self) -> &'static str {
        match self {
            DocType::Rfq => "RFQ",
            DocType::Prd => "PRD",
            DocType::Scn => "SCN",
            DocType::Uc => "UC",
            DocType::Infra => "INFRA",
            DocType::Dom => "DOM",
            DocType::Ui => "UI",
            DocType::Api => "API",
            DocType::Seq => "SEQ",
            DocType::Ms => "MS",
            DocType::Code => "CODE",
            DocType::Std => "STD",
        }
    }

    /// 글자 → 타입 — 없는 이름이면 None
    pub fn parse(s: &str) -> Option<DocType> {
        DocType::ALL.into_iter().find(|t| t.as_str() == s)
    }
}

/// 문서 상태 — 둘뿐이다 (DOM-002 2.7, 라벨 「완료」는 approved)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum DocStatus {
    Draft,
    Approved,
}

impl DocStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            DocStatus::Draft => "draft",
            DocStatus::Approved => "approved",
        }
    }

    pub fn parse(s: &str) -> Option<DocStatus> {
        [DocStatus::Draft, DocStatus::Approved]
            .into_iter()
            .find(|t| t.as_str() == s)
    }
}

/// 저장이 들어온 입구 (DOM-002 2.7 `Entry`) — 규약 검증이 입구마다 다르다
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Entry {
    Mcp,
    WebRevert,
    WebStatus,
    Github,
}

impl Entry {
    pub fn as_str(self) -> &'static str {
        match self {
            Entry::Mcp => "mcp",
            Entry::WebRevert => "web_revert",
            Entry::WebStatus => "web_status",
            Entry::Github => "github",
        }
    }

    pub fn parse(s: &str) -> Option<Entry> {
        [
            Entry::Mcp,
            Entry::WebRevert,
            Entry::WebStatus,
            Entry::Github,
        ]
        .into_iter()
        .find(|t| t.as_str() == s)
    }
}

/// 규약 위반 — 저장을 막는다 (DOM-002 2.8 `Violation`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Violation {
    pub line: usize,
    pub rule: String,
    pub message: String,
}

/// 미완성 경고 — 저장은 된다 (DOM-002 2.8 `Warning`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Warning {
    pub rule: String,
    pub message: String,
}

/// 파이썬 `str(Warning)` — `rule: message`, message가 비면 `rule`
impl fmt::Display for Warning {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.message.is_empty() {
            write!(f, "{}", self.rule)
        } else {
            write!(f, "{}: {}", self.rule, self.message)
        }
    }
}

/// 규약 검증 결과 — 위반이 비면 통과 (DOM-002 2.8 `ValidateResult`)
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct ValidateResult {
    pub violations: Vec<Violation>,
    pub warnings: Vec<Warning>,
}

/// 항목 블록 — 줄은 1부터, 끝 포함. `text`는 원본 줄 (DOM-002 2.8 `ItemBlock`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ItemBlock {
    pub item_id: String,
    pub display_name: String,
    pub level: usize,
    pub start_line: usize,
    pub end_line: usize,
    pub text: String,
}

/// diff 줄의 종류
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum DiffOp {
    Add,
    Del,
    Ctx,
}

/// diff 줄 (DOM-002 2.8 `DiffLine`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct DiffLine {
    pub op: DiffOp,
    pub text: String,
}

/// 항목 하나의 바뀐 줄들 — `item_id`가 None이면 항목 밖 글. `downstream_count`는 읽기 조합이 채운다
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Hunk {
    pub item_id: Option<String>,
    pub lines: Vec<DiffLine>,
    pub downstream_count: i64,
}

/// 두 버전 diff (API-001 `Diff`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Diff {
    pub from_version: i32,
    pub to_version: i32,
    pub hunks: Vec<Hunk>,
}

/// 사용자 종류 — `users.kind`. DB enum이 아니라 varchar + 앱 검증 (SYNC-DOM-003)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UserKind {
    Github,
    Local,
    Placeholder,
}

impl UserKind {
    pub fn as_str(self) -> &'static str {
        match self {
            UserKind::Github => "github",
            UserKind::Local => "local",
            UserKind::Placeholder => "placeholder",
        }
    }
}

/// 저장 방식 — `repositories.storage` (DOM-002 2.7 `Storage`). 싱크독_로컬은 서버 저장뿐이다
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Storage {
    Github,
    Server,
}

impl Storage {
    pub fn as_str(self) -> &'static str {
        match self {
            Storage::Github => "github",
            Storage::Server => "server",
        }
    }

    pub fn parse(s: &str) -> Option<Storage> {
        [Storage::Github, Storage::Server]
            .into_iter()
            .find(|t| t.as_str() == s)
    }
}

/// 단계 번호 — `RFQ` 1 … `CODE` 11. `STD`는 단계 밖 (DOM-002 `STAGE_OF`)
pub const STAGES: [&str; 11] = [
    "RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE",
];

/// 타입 → 단계 번호 — 없으면 None(`STD`·모르는 타입)
pub fn stage_of(doc_type: &str) -> Option<i32> {
    STAGES
        .iter()
        .position(|t| *t == doc_type)
        .map(|i| i as i32 + 1)
}

/// 작성 주체의 종류 (DOM-002 2.7 `AuthorKind`)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum AuthorKind {
    Human,
    Agent,
}

impl AuthorKind {
    pub fn as_str(self) -> &'static str {
        match self {
            AuthorKind::Human => "human",
            AuthorKind::Agent => "agent",
        }
    }
}

/// 쓰는 사람 (DOM-002 2.8 `Author`) — 에이전트는 `agent`·발급자·발급자·`mcp` (SEQ-C2)
#[derive(Clone, Debug)]
pub struct Author {
    pub kind: AuthorKind,
    pub user: UserRow,
    pub instructed_by: Option<UserRow>,
    pub via: Entry,
}

/// 입구 → `versions.via` — `web_revert`·`web_status`는 `web`으로 접는다 (파이썬 `fold_via`)
pub fn fold_via(entry: Entry) -> &'static str {
    match entry {
        Entry::WebRevert | Entry::WebStatus => "web",
        other => other.as_str(),
    }
}

/// 타입 → 저장소 디렉터리 `{NN-TYPE}` — 단계 밖(`STD`)은 번호 없이 (파이썬 `spec_dir`, STD-001 1.1)
pub fn spec_dir(doc_type: &str) -> String {
    match stage_of(doc_type) {
        Some(n) => format!("{n:02}-{doc_type}"),
        None => doc_type.to_string(),
    }
}

/// 작성자 — id만(이름은 읽기 조합이 붙인다) (DOM-002 2.8 `AuthorRef`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct AuthorRef {
    pub kind: String,
    pub user_id: i32,
    pub instructed_by_id: Option<i32>,
    pub via: String,
}

/// 사용자 표시 정보 (API-001 `UserRef`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct UserRef {
    pub id: i32,
    pub github_login: String,
    pub display_name: String,
}

/// 이름 붙은 작성자 (API-001 `Author`) — 읽기 조합이 `AuthorRef`를 `users_by_ids`로 채운 것
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ApiAuthor {
    pub kind: String,
    pub user: Option<UserRef>,
    pub instructed_by: Option<UserRef>,
    pub via: String,
}

/// 문서 요약 (API-001 `DocumentSummary`) — `counts`·`author`는 읽기 조합이 채운다
#[derive(Clone, Debug, PartialEq)]
pub struct DocumentSummary {
    pub id: i32,
    pub doc_id: String,
    pub doc_type: String,
    pub stage: Option<i32>,
    pub status: String,
    pub current_version_no: i32,
    pub has_convention_error: bool,
    pub incomplete_warnings: Vec<String>,
    pub updated_at: OffsetDateTime,
    pub last_author: Option<AuthorRef>,
    pub author: Option<ApiAuthor>,
    pub counts: IndexMap<String, i64>,
    pub trashed_at: Option<OffsetDateTime>,
}

/// 문서의 항목 하나 (API-001 `Document.items[]`) — `missing_refs`는 읽기 조합이 채운다
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DocItem {
    pub pk: i32,
    pub item_id: String,
    pub display_name: Option<String>,
    pub missing_refs: Vec<String>,
}

/// 문서 (API-001 `Document`) — 요약 + 본문·해시·항목. 이웃·미존재 참조·프로젝트 이름은 `queries.document_view`가 붙인다
#[derive(Clone, Debug, PartialEq)]
pub struct Document {
    pub summary: DocumentSummary,
    pub body: String,
    pub commit_hash: Option<String>,
    pub current_version_id: Option<i32>,
    pub missing_refs: Vec<String>,
    pub convention_error_detail: Option<String>,
    pub items: Vec<DocItem>,
    pub prev_doc_id: Option<String>,
    pub next_doc_id: Option<String>,
    pub project_name: String,
}

/// 항목 블록 조회 (API-002 `get_item`)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ItemView {
    pub pk: i32,
    pub doc_id: String,
    pub item_id: String,
    pub display_name: Option<String>,
    pub body: String,
    pub doc_status: String,
    pub doc_version_no: i32,
}

/// 참조 대상 표시 (API-001 `ItemRef`) — 문서 전체 참조면 `item_id`가 없다. `is_deleted`·`deleted_at`은 안쪽 것
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ItemRef {
    pub doc_id: Option<String>,
    pub item_id: Option<String>,
    pub display_name: Option<String>,
    pub raw_target: String,
    pub is_missing: bool,
    pub is_deleted: bool,
    pub deleted_at: Option<OffsetDateTime>,
}

/// 문서 pk → 표시 정보 (DOM-002 2.8 `DocRef`)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DocRef {
    pub document_id: i32,
    pub doc_id: String,
    pub title: String,
    pub stage: Option<i32>,
    pub status: String,
}

/// 항목의 상위·하위 참조 (API-002 `get_references`)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ItemReferences {
    pub doc_id: String,
    pub item_id: String,
    pub upstream: Vec<ItemRef>,
    pub downstream: Vec<ItemRef>,
}

/// 참조 간선 — pk만 (DOM-002 2.8 `RefEdge`). 파이썬 `_edge`와 같은 꼴
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RefEdge {
    pub from_item_pk: Option<i32>,
    pub to_item_pk: Option<i32>,
    pub to_document_id: Option<i32>,
    pub raw_target: String,
    pub is_missing: bool,
    pub from_document_id: i32,
}

/// 참조 추출 결과 (DOM-002 2.8 `ExtractResult`)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ExtractResult {
    pub added: i64,
    pub removed: i64,
    pub missing: i64,
}

/// 저장 결과 (API-002 `create_document`·`update_document`) — `next_step`은 `mcp`만
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SaveResult {
    pub doc_id: String,
    pub version_no: i32,
    pub commit_hash: String,
    pub status: String,
    pub warnings: Vec<String>,
    pub next_step: Option<String>,
}

/// 하위 참조가 있는 지운 항목 — `item-deletion-needs-confirm`의 한 칸. 하위는 출발 항목의 이름으로
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeletedItem {
    pub item_id: String,
    pub downstream: Vec<ItemRef>,
}

/// 단계 한 칸 (API-001 `StageSummary`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct StageSummary {
    pub stage: i32,
    pub doc_type: String,
    pub status: Option<String>,
    pub doc_count: i64,
    pub gate_warning: bool,
    pub broken_count: i64,
}

/// 프로젝트 요약 (API-001 `ProjectSummary`) — 단계는 늘 11칸
#[derive(Clone, Debug, PartialEq)]
pub struct ProjectSummary {
    pub code: String,
    pub name: String,
    pub storage: Storage,
    pub remote_url: Option<String>,
    pub stages: Vec<StageSummary>,
    pub std_docs: Vec<DocumentSummary>,
    pub counts: IndexMap<String, i64>,
    pub updated_at: Option<OffsetDateTime>,
}

/// 토큰 발급 결과 — 원문(`raw`)은 이 값에만 있다 (SYNC-DOM-002 2.8 `IssuedToken`)
#[derive(Clone, Debug)]
pub struct IssuedToken {
    pub token: AccessTokenRow,
    pub raw: String,
}

/// API의 시각 — ISO 8601 UTC. 마이크로초 여섯 자리(0이면 뺀다), 끝은 `Z`.
/// 파이썬 판(pydantic)이 내는 바이트와 같다 — `2026-10-07T03:00:00.123456Z`
pub fn iso_utc(t: OffsetDateTime) -> String {
    let t = t.to_offset(time::UtcOffset::UTC);
    let micro = t.microsecond();
    let frac = if micro == 0 {
        String::new()
    } else {
        format!(".{micro:06}")
    };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}{frac}Z",
        t.year(),
        u8::from(t.month()),
        t.day(),
        t.hour(),
        t.minute(),
        t.second()
    )
}

/// 파이썬 `datetime.isoformat()`(UTC) — 마이크로초가 0이면 뺀다, 끝은 `+00:00`. MCP 응답이 이 꼴이다
pub fn py_isoformat(t: OffsetDateTime) -> String {
    let z = iso_utc(t);
    format!("{}+00:00", z.trim_end_matches('Z'))
}

#[cfg(test)]
mod tests {
    use super::*;
    use time::macros::datetime;

    #[test]
    fn warning_text_and_spec_dir_like_python() {
        let w = |r: &str, m: &str| Warning {
            rule: r.into(),
            message: m.into(),
        };
        assert_eq!(
            w("section.missing", "1. 목적").to_string(),
            "section.missing: 1. 목적"
        );
        assert_eq!(w("item.none", "").to_string(), "item.none");
        assert_eq!(spec_dir("DOM"), "06-DOM");
        assert_eq!(spec_dir("CODE"), "11-CODE");
        assert_eq!(spec_dir("STD"), "STD");
        assert_eq!(fold_via(Entry::WebStatus), "web");
        assert_eq!(fold_via(Entry::Mcp), "mcp");
    }

    #[test]
    fn iso_utc_like_pydantic() {
        assert_eq!(
            iso_utc(datetime!(2026-10-07 03:00:00.123456 UTC)),
            "2026-10-07T03:00:00.123456Z"
        );
        assert_eq!(
            iso_utc(datetime!(2026-10-07 03:00:00 UTC)),
            "2026-10-07T03:00:00Z"
        );
        assert_eq!(
            iso_utc(datetime!(2026-10-07 12:00:00.000010 +09:00)),
            "2026-10-07T03:00:00.000010Z"
        );
    }
}
