//! 응답 형태 — SYNC-API-001 4장. 키 순서는 파이썬 판 `web/schemas`와 같다

use serde::Serialize;
use syncdoc_core::account::model::AccessTokenRow;
use syncdoc_core::types::iso_utc;

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
