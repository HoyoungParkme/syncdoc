//! 열거형·DTO — SYNC-DOM-002 2.7·2.8 그대로 (Rust는 `syncdoc_core::types`).
//! 직렬화 이름(JSON 키·열거형 값)도 파이썬 판과 같다.

use indexmap::IndexMap;
use serde::Serialize;
use time::OffsetDateTime;

use crate::account::model::AccessTokenRow;

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

/// 작성자 — id만(이름은 읽기 조합이 붙인다) (DOM-002 2.8 `AuthorRef`)
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct AuthorRef {
    pub kind: String,
    pub user_id: i32,
    pub instructed_by_id: Option<i32>,
    pub via: String,
}

/// 문서 요약 (API-001 `DocumentSummary`) — `counts`는 읽기 조합이 채운다
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
    pub counts: IndexMap<String, i64>,
    pub trashed_at: Option<OffsetDateTime>,
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
