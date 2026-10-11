//! 싱크독_로컬 서버 조립 — SYNC-DOM-004 1장 server · SYNC-INFRA-001 4.1·9.1.
//! 처리기는 가져온 맨 이름으로 등록한다 — 경로로 적으면 코드 그래프가 조립에서 처리기로 선을 긋는다.

pub mod compat;
pub mod mcp;
pub mod state;
pub mod web;

use axum::extract::DefaultBodyLimit;
use axum::routing::{delete, get};
use axum::{Json, Router, middleware};
use serde_json::{Value, json};
use tower_http::catch_panic::CatchPanicLayer;

use crate::compat::uvicorn::decode_path;
use crate::state::AppState;
use crate::web::guard::guard;
use crate::web::problem::{method_not_allowed, panic_response};
use crate::web::routes::account::{issue_token, list_tokens, me, revoke_token};
use crate::web::routes::documents::diff;
use crate::web::routes::documents::downstream;
use crate::web::routes::documents::get_document;
use crate::web::routes::documents::trash_document;
use crate::web::routes::documents::versions;
use crate::web::routes::projects::{
    delete_project, get_file, get_project, graph, init_project, list_docs, list_items,
    list_projects, trash_list,
};
use crate::web::routes::references::item_chain;
use crate::web::routes::references::item_references;
use crate::web::routes::references::item_view;
use crate::web::routes::specs::spec_copy;
use crate::web::static_files::fallback;

/// 라우터 — 가드가 라우팅 바깥에서 모든 요청을 덮는다(404·405·정적 파일까지, SEQ-C3)
pub fn app(state: AppState) -> Router {
    let inner = Router::new()
        .route("/health", get(health))
        .route("/api/me", get(me))
        .route("/api/me/tokens", get(list_tokens).post(issue_token))
        .route("/api/me/tokens/{token_id}", delete(revoke_token))
        .route("/api/projects", get(list_projects).post(init_project))
        .route(
            "/api/projects/{code}",
            get(get_project).delete(delete_project),
        )
        .route("/api/projects/{code}/docs", get(list_docs))
        .route("/api/projects/{code}/flags", get(list_items))
        .route("/api/projects/{code}/graph", get(graph))
        .route("/api/projects/{code}/files/{*path}", get(get_file))
        .route("/api/projects/{code}/files/", get(get_file))
        .route("/api/docs/{doc_id}/diff", get(diff))
        .route("/api/docs/{doc_id}/versions", get(versions))
        .route("/api/docs/{doc_id}/downstream", get(downstream))
        .route("/api/docs/{doc_id}/items/{item_id}", get(item_view))
        .route(
            "/api/docs/{doc_id}/items/{item_id}/references",
            get(item_references),
        )
        .route("/api/docs/{doc_id}/items/{item_id}/chain", get(item_chain))
        .route("/api/projects/{code}/trash", get(trash_list))
        .route(
            "/api/docs/{doc_id}",
            get(get_document).delete(trash_document),
        )
        .merge(mcp::router(state.clone()))
        .route("/specs/", get(spec_copy))
        .route("/specs/{*path}", get(spec_copy))
        .fallback(fallback)
        // 파이썬 판(FastAPI)은 본문 크기를 막지 않는다 — /mcp만 4MiB(MCP SDK)
        .layer(DefaultBodyLimit::disable())
        .with_state(state.clone());
    // 405 변환은 라우터 바깥에서 — axum은 Allow 머리를 경로 처리기 바깥에서 붙인다
    Router::new()
        .fallback_service(inner)
        .layer(middleware::from_fn(method_not_allowed))
        .layer(middleware::from_fn_with_state(state, guard))
        .layer(middleware::from_fn(decode_path))
        .layer(CatchPanicLayer::custom(panic_response))
}

/// `/health` — 살아 있다 (INFRA 8.1, 파이썬 판 main.py와 같은 본문)
async fn health() -> Json<Value> {
    Json(json!({"status": "ok"}))
}
