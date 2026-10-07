//! 싱크독_로컬 서버 조립 — SYNC-DOM-004 1장 server · SYNC-INFRA-001 4.1·9.1.
//! 처리기는 가져온 맨 이름으로 등록한다 — 경로로 적으면 코드 그래프가 조립에서 처리기로 선을 긋는다.

pub mod state;
pub mod web;

use axum::routing::get;
use axum::{Json, Router, middleware};
use serde_json::{Value, json};
use tower_http::catch_panic::CatchPanicLayer;

use crate::state::AppState;
use crate::web::guard::guard;
use crate::web::problem::{method_not_allowed, panic_response};
use crate::web::routes::account::me;
use crate::web::routes::specs::spec_copy;
use crate::web::static_files::fallback;

/// 라우터 — 가드가 라우팅 바깥에서 모든 요청을 덮는다(404·405·정적 파일까지, SEQ-C3)
pub fn app(state: AppState) -> Router {
    let inner = Router::new()
        .route("/health", get(health))
        .route("/api/me", get(me))
        .route("/specs/", get(spec_copy))
        .route("/specs/{*path}", get(spec_copy))
        .fallback(fallback)
        .with_state(state.clone());
    // 405 변환은 라우터 바깥에서 — axum은 Allow 머리를 경로 처리기 바깥에서 붙인다
    Router::new()
        .fallback_service(inner)
        .layer(middleware::from_fn(method_not_allowed))
        .layer(middleware::from_fn_with_state(state, guard))
        .layer(CatchPanicLayer::custom(panic_response))
}

/// `/health` — 살아 있다 (INFRA 8.1, 파이썬 판 main.py와 같은 본문)
async fn health() -> Json<Value> {
    Json(json!({"status": "ok"}))
}
