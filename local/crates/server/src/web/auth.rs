//! 현재 사용자 — 폐쇄망판은 로그인이 없어 로컬 사용자다 (SYNC-SEQ-001#SEQ-C3 · SYNC-INFRA-001 5장)

use axum::http::{HeaderMap, header};
use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::pycompat::chars::strip;

use crate::state::AppState;

/// 요청의 사용자 — 로컬 사용자, 없으면 설정대로 만든다. 트랜잭션은 처리기가 쥔다
pub async fn current_user(db: &mut PgConnection, state: &AppState) -> Result<UserRow, Problem> {
    let mut svc = AccountService { db };
    svc.local_user(&state.local_login, &state.local_name).await
}

/// 기록 도구의 두 경로(trace-spans·traces 올리기)의 사용자 — API-001 1장 · SEQ-36 (카드 L28).
/// `Authorization: Bearer`가 있으면 개인 토큰이 사람을 정한다(틀리면 401). 없으면 로컬 사용자.
/// 머리는 Starlette처럼 latin-1로 읽고 첫 값을 쓴다. 토큰이 통과하면 처리기의 트랜잭션이 커밋한다
pub async fn token_or_session_user(
    db: &mut PgConnection,
    state: &AppState,
    headers: &HeaderMap,
) -> Result<UserRow, Problem> {
    let raw: String = headers
        .get(header::AUTHORIZATION)
        .map(|v| v.as_bytes().iter().map(|b| char::from(*b)).collect())
        .unwrap_or_default();
    let Some(token) = raw.strip_prefix("Bearer ") else {
        return current_user(db, state).await;
    };
    AccountService { db }
        .authenticate_token(strip(token))
        .await?
        .ok_or_else(|| Problem::Unauthorized {
            detail: "토큰 없음·폐기·만료".into(),
        })
}
