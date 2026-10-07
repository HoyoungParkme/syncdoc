//! AppState — 처리기가 함께 쓰는 것 (SYNC-DOM-004 1장 server)

use sqlx::PgPool;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    /// 설정의 `LOCAL_LOGIN` — 로컬 사용자가 없을 때 만들 아이디 (SYNC-MS-016#AccountService.local_user)
    pub local_login: String,
    /// 설정의 `LOCAL_NAME`(비면 아이디)
    pub local_name: String,
    /// 모델 주소와 키가 다 있다 (INFRA 5.2 `llm_enabled`)
    pub llm_enabled: bool,
    /// 공개 주소의 host:port — 같은 망 열기(L16) 전에는 `127.0.0.1:{실제 포트}` (INFRA 9.4)
    pub public_netloc: String,
}
