//! 현재 사용자 — 폐쇄망판은 로그인이 없어 로컬 사용자다 (SYNC-SEQ-001#SEQ-C3 · SYNC-INFRA-001 5장)

use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;

use crate::state::AppState;

/// 요청의 사용자 — 로컬 사용자, 없으면 설정대로 만든다. 트랜잭션은 처리기가 쥔다
pub async fn current_user(db: &mut PgConnection, state: &AppState) -> Result<UserRow, Problem> {
    let mut svc = AccountService { db };
    svc.local_user(&state.local_login, &state.local_name).await
}
