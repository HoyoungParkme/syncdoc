//! 응답 형태 — SYNC-API-001 4장. 키 순서는 파이썬 판 `web/schemas`와 같다

use indexmap::IndexMap;
use serde::Serialize;
use syncdoc_core::account::model::AccessTokenRow;
use syncdoc_core::types::{
    DocumentSummary as DocumentSummaryDto, ProjectSummary as ProjectSummaryDto, StageSummary,
    iso_utc,
};

/// `Me` — `User`(id·github_login·display_name·created_at)에 판·모델·저장 방식을 더한 것
#[derive(Debug, Serialize)]
pub struct Me {
    pub id: i32,
    pub github_login: String,
    pub display_name: String,
    pub created_at: String,
    pub llm_enabled: bool,
    pub storage_modes: Vec<&'static str>,
    pub edition: &'static str,
    pub repo_private: bool,
}

/// `AccessToken` — 원문·해시 없음 (`web/schemas/account.py`)
#[derive(Debug, Serialize)]
pub struct AccessToken {
    pub id: i32,
    pub label: String,
    pub issued_at: String,
    pub expires_at: Option<String>,
    pub revoked_at: Option<String>,
    pub last_used_at: Option<String>,
}

impl From<AccessTokenRow> for AccessToken {
    fn from(t: AccessTokenRow) -> Self {
        AccessToken {
            id: t.id,
            label: t.label,
            issued_at: iso_utc(t.issued_at),
            expires_at: t.expires_at.map(iso_utc),
            revoked_at: t.revoked_at.map(iso_utc),
            last_used_at: t.last_used_at.map(iso_utc),
        }
    }
}

/// `IssuedToken` — `AccessToken` + 원문 `token`(이 응답에서만)
#[derive(Debug, Serialize)]
pub struct IssuedToken {
    #[serde(flatten)]
    pub token: AccessToken,
    #[serde(rename = "token")]
    pub raw: String,
}

/// `DocumentSummary` — `web/schemas/documents.py` (판별 필드 `type`이 맨 앞). 요약 경로의 작성자 이름은 없다
#[derive(Debug, Serialize)]
pub struct DocumentSummary {
    #[serde(rename = "type")]
    pub kind: &'static str,
    pub doc_id: String,
    pub doc_type: String,
    pub stage: Option<i32>,
    pub status: String,
    pub current_version_no: i32,
    pub has_convention_error: bool,
    pub incomplete_warnings: Vec<String>,
    pub updated_at: String,
    pub last_author: Option<()>,
    pub counts: IndexMap<String, i64>,
    pub trashed_at: Option<String>,
}

impl From<&DocumentSummaryDto> for DocumentSummary {
    fn from(d: &DocumentSummaryDto) -> Self {
        DocumentSummary {
            kind: "document",
            doc_id: d.doc_id.clone(),
            doc_type: d.doc_type.clone(),
            stage: d.stage,
            status: d.status.clone(),
            current_version_no: d.current_version_no,
            has_convention_error: d.has_convention_error,
            incomplete_warnings: d.incomplete_warnings.clone(),
            updated_at: iso_utc(d.updated_at),
            last_author: None,
            counts: d.counts.clone(),
            trashed_at: d.trashed_at.map(iso_utc),
        }
    }
}

/// `ProjectSummary` — `web/schemas/projects.py`
#[derive(Debug, Serialize)]
pub struct ProjectSummary {
    pub code: String,
    pub name: String,
    pub storage: &'static str,
    pub remote_url: Option<String>,
    pub stages: Vec<StageSummary>,
    pub std_docs: Vec<DocumentSummary>,
    pub counts: IndexMap<String, i64>,
    pub updated_at: Option<String>,
}

impl From<&ProjectSummaryDto> for ProjectSummary {
    fn from(p: &ProjectSummaryDto) -> Self {
        ProjectSummary {
            code: p.code.clone(),
            name: p.name.clone(),
            storage: p.storage.as_str(),
            remote_url: p.remote_url.clone(),
            stages: p.stages.clone(),
            std_docs: p.std_docs.iter().map(DocumentSummary::from).collect(),
            counts: p.counts.clone(),
            updated_at: p.updated_at.map(iso_utc),
        }
    }
}
