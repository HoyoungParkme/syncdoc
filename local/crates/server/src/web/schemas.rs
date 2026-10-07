//! 응답 형태 — SYNC-API-001 4장. 키 순서는 파이썬 판 `web/schemas/common.py`와 같다

use serde::Serialize;

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
