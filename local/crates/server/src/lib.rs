//! 싱크독_로컬 서버 조립 — SYNC-DOM-004 1장 server · SYNC-INFRA-001 4.1·9.1.
//! 처리기는 가져온 맨 이름으로 등록한다 — 경로로 적으면 코드 그래프가 조립에서 처리기로 선을 긋는다.

pub mod compat;
pub mod local;
pub mod mcp;
pub mod state;
pub mod web;

use axum::extract::DefaultBodyLimit;
use axum::routing::{any, delete, get, post, put};
use axum::{Json, Router, middleware};
use serde_json::{Value, json};
use tower_http::catch_panic::CatchPanicLayer;

use crate::compat::uvicorn::decode_path;
use crate::state::AppState;
use crate::web::guard::guard;
use crate::web::problem::{method_not_allowed, panic_response};
use crate::web::routes::account::{issue_token, list_tokens, me, revoke_token};
use crate::web::routes::admin::{hook, move_to_github, move_to_server, rebuild, repos, sync};
use crate::web::routes::code::{
    ask_code, code_calls, code_nodes, code_text, doc_code, flow_view, item_code, item_code_source,
    trace_spans,
};
use crate::web::routes::conversations::{
    create_conversation, delete_attachment, delete_conversation, get_attachment, get_conversation,
    list_conversations, upload_attachment,
};
use crate::web::routes::documents::ask;
use crate::web::routes::documents::change_status;
use crate::web::routes::documents::diff;
use crate::web::routes::documents::downstream;
use crate::web::routes::documents::get_document;
use crate::web::routes::documents::purge_document;
use crate::web::routes::documents::restore_document;
use crate::web::routes::documents::revert;
use crate::web::routes::documents::trash_document;
use crate::web::routes::documents::versions;
use crate::web::routes::git::git_entrance;
use crate::web::routes::local::{
    get_local, post_backup, post_move, post_restore, put_autostart, put_settings,
};
use crate::web::routes::projects::{
    delete_project, get_file, get_project, graph, import_bundle, init_project, list_docs,
    list_items, list_projects, project_methods, trash_list,
};
use crate::web::routes::references::item_chain;
use crate::web::routes::references::item_references;
use crate::web::routes::references::item_view;
use crate::web::routes::specs::spec_copy;
use crate::web::routes::traces::{
    delete_trace, delete_traces, get_trace, list_traces, trace_coverage, upload_trace,
};
use crate::web::static_files::fallback;

/// 라우터 — 가드가 라우팅 바깥에서 모든 요청을 덮는다(404·405·정적 파일까지, SEQ-C3)
pub fn app(state: AppState) -> Router {
    let mut routes = Router::new()
        .route("/health", get(health))
        .route("/api/me", get(me))
        .route("/api/me/tokens", get(list_tokens).post(issue_token))
        .route("/api/me/tokens/{token_id}", delete(revoke_token))
        .route("/api/projects", get(list_projects).post(init_project))
        .route(
            "/api/projects/{code}",
            get(get_project)
                .delete(delete_project)
                .post(import_bundle)
                .fallback(project_methods),
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
        .route("/api/docs/{doc_id}/code", get(doc_code))
        .route("/api/docs/{doc_id}/items/{item_id}/code", get(item_code))
        .route(
            "/api/docs/{doc_id}/items/{item_id}/code/source",
            get(item_code_source),
        )
        .route("/api/projects/{code}/code-calls", get(code_calls))
        .route("/api/projects/{code}/code-graph", get(code_nodes))
        .route("/api/projects/{code}/flow", get(flow_view))
        .route("/api/projects/{code}/trace-spans", get(trace_spans))
        .route(
            "/api/projects/{code}/traces",
            post(upload_trace).get(list_traces).delete(delete_traces),
        )
        .route("/api/projects/{code}/traces/coverage", get(trace_coverage))
        .route(
            "/api/projects/{code}/traces/{trace_id}",
            get(get_trace).delete(delete_trace),
        )
        .route("/api/projects/{code}/code/ask", post(ask_code))
        .route(
            "/api/projects/{code}/conversations",
            get(list_conversations).post(create_conversation),
        )
        .route(
            "/api/conversations/{id}",
            get(get_conversation).delete(delete_conversation),
        )
        .route(
            "/api/conversations/{id}/attachments",
            post(upload_attachment),
        )
        .route(
            "/api/attachments/{id}",
            get(get_attachment).delete(delete_attachment),
        )
        .route("/api/docs/{doc_id}/ask", post(ask))
        .route("/api/projects/{code}/code/source", get(code_text))
        .route("/api/projects/{code}/trash", get(trash_list))
        .route(
            "/api/docs/{doc_id}",
            get(get_document).delete(trash_document),
        )
        .route("/api/docs/{doc_id}/restore", post(restore_document))
        .route("/api/docs/{doc_id}/purge", post(purge_document))
        .route("/api/docs/{doc_id}/status", post(change_status))
        .route("/api/docs/{doc_id}/revert", post(revert))
        .route("/git/{*rest}", any(git_entrance))
        .route("/api/admin/repos", get(repos))
        .route("/api/admin/repos/{code}/rebuild", post(rebuild))
        .route("/api/admin/repos/{code}/hook", post(hook))
        .route("/api/admin/repos/{code}/sync", post(sync))
        .route(
            "/api/admin/repos/{code}/move-to-server",
            post(move_to_server),
        )
        .route(
            "/api/admin/repos/{code}/move-to-github",
            post(move_to_github),
        )
        .merge(mcp::router(state.clone()))
        .route("/specs/", get(spec_copy))
        .route("/specs/{*path}", get(spec_copy));
    // 이 PC — 설치형만(카드 L16). 비어 있으면 없는 경로(파이썬 판과 같다)
    if state.local.is_some() {
        routes = routes
            .route("/api/local", get(get_local))
            .route("/api/local/settings", put(put_settings))
            .route("/api/local/autostart", put(put_autostart))
            .route("/api/local/backups", post(post_backup))
            .route("/api/local/restore", post(post_restore))
            .route("/api/local/move", post(post_move));
    }
    let inner = routes
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
