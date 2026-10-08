//! `/mcp` — 에이전트 입구 (SYNC-API-002 · SYNC-DOM-004 1장 mcp/).
//! 파이썬 mcp SDK 2.2.0의 핸드셰이크 경로를 옮겼다 — 세션 없는 streamable HTTP, 서버 이름 `syncdoc_local`.
//! 2026-07-28 새 프로토콜은 카드 L18.

pub mod auth;
pub mod decl;
pub mod dispatch;
pub mod tools;
pub mod transport;

use axum::Router;
use axum::extract::DefaultBodyLimit;
use axum::middleware;
use axum::routing::get;

use crate::state::AppState;
use auth::bearer;
use transport::handle;

/// `/mcp` 라우터 — 메서드(GET·POST·DELETE)를 먼저 가르고 인증한다(파이썬 `Route(methods=…)` 뒤 `BearerAuth`)
pub fn router(state: AppState) -> Router<AppState> {
    let _ = decl::decl();
    Router::new()
        .route("/mcp", get(handle).post(handle).delete(handle))
        .route_layer(middleware::from_fn_with_state(state, bearer))
        .layer(DefaultBodyLimit::disable())
}
