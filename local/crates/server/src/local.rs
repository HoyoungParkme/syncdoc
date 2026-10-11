//! 이 PC — 설치형(app crate)이 쥔 일의 문 (SYNC-DOM-004 4.12 · SYNC-API-001 3.11, 카드 L16).
//! crate 의존이 `app → server` 한 방향이라 server가 문(`LocalOps`)을 두고 app이 채워 서버 상태에 넣는다.
//! 파이썬 판에는 없다 — 비어 있으면 `/api/local*`이 없는 경로다

use async_trait::async_trait;
use serde::Serialize;
use syncdoc_core::errors::Problem;

/// 백업 파일 하나 (API-001 `BackupFile`)
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub struct BackupFile {
    pub name: String,
    pub size: u64,
    pub encrypted: bool,
}

/// 켠 뒤 마지막 백업 시도
#[derive(Serialize, Clone, Debug)]
pub struct LastBackup {
    pub at: String,
    pub name: Option<String>,
    pub error: Option<String>,
}

/// 켠 뒤 마지막 다시 켜기 — `settings`·`restore`·`move`
#[derive(Serialize, Clone, Debug)]
pub struct LastOp {
    pub kind: &'static str,
    pub ok: bool,
    pub message: String,
    pub at: String,
}

/// 「백업」 카드
#[derive(Serialize, Clone, Debug)]
pub struct BackupInfo {
    pub dir: String,
    pub encrypted: bool,
    pub keep: usize,
    pub files: Vec<BackupFile>,
    pub last: Option<LastBackup>,
}

/// `GET /api/local` — 「이 PC」·「백업」 카드가 그리는 것. 키·암호 원문은 없다
#[derive(Serialize, Clone, Debug)]
pub struct LocalInfo {
    pub login: String,
    pub name: String,
    pub llm_api_url: String,
    pub llm_api_key_set: bool,
    pub llm_model: String,
    pub public_base_url: String,
    pub autostart: bool,
    pub data_dir: String,
    pub backup: BackupInfo,
    pub last_op: Option<LastOp>,
}

/// 설정 저장 — 준 칸만 바꾼다(없으면 그대로)
#[derive(Clone, Debug, Default)]
pub struct SettingsChange {
    pub name: Option<String>,
    pub llm_api_url: Option<String>,
    pub llm_api_key: Option<String>,
    pub llm_model: Option<String>,
    pub backup_dir: Option<String>,
    pub backup_password: Option<String>,
}

/// 이 PC의 일 — 처리기가 부른다. 다시 켜기(설정 저장·되살리기·옮기기)는 검사만 하고 runtime에 넘긴다
#[async_trait]
pub trait LocalOps: Send + Sync {
    /// 「이 PC」·「백업」 카드가 그리는 것
    async fn info(&self) -> Result<LocalInfo, Problem>;
    /// 설정 값만 바꾸고 다시 켜기를 건다
    async fn save_settings(&self, change: SettingsChange) -> Result<(), Problem>;
    /// 자동 시작 켜고 끄기
    async fn set_autostart(&self, on: bool) -> Result<(), Problem>;
    /// 지금 백업
    async fn backup_now(&self) -> Result<BackupFile, Problem>;
    /// 백업을 풀어 보고 되살리기를 건다
    async fn restore(&self, name: &str, password: Option<&str>) -> Result<(), Problem>;
    /// 옮길 자리를 보고 옮기기를 건다
    async fn move_to(&self, dir: &str) -> Result<(), Problem>;
}
