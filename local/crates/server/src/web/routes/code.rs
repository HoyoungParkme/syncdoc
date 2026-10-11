//! 코드 그래프 — 파이썬 판 `web/routers/code.py`(카드 L12): 코드 탭·코드 보기·관계도 코드 호출·코드 그래프의 코드.
//! 대조는 부를 때 계산한다 — 그래프는 code_graphs에서, 「호출하는 것」은 명세에서. itemId의 `~`는 `/`.
//! 카드 L13이 노드 전부(`code-graph`)를, 카드 L14가 묻기(`code/ask`, SSE)를 더했다

use std::sync::LazyLock;

use axum::Json;
use axum::extract::{Path, RawQuery, State};
use num_bigint::BigInt;
use syncdoc_core::errors::Problem;
use syncdoc_core::queries;

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{CodeCalls, CodeNodes, CodeText, CodeView};

static CODE_FILE: LazyLock<Validator> = LazyLock::new(schemas::code_file);
static LINE: LazyLock<Validator> = LazyLock::new(schemas::version_no);
static ASK_CODE: LazyLock<Validator> = LazyLock::new(schemas::ask_code_request);

/// SYNC-API-001#GET/api/docs/{docId}/code
pub async fn doc_code(
    State(state): State<AppState>,
    Path(doc_id): Path<String>,
) -> Result<Json<CodeView>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let v = queries::code_view(&mut c, &state.repos, &doc_id, None, &user).await?;
    Ok(Json(CodeView::from(&v)))
}

/// SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code
pub async fn item_code(
    State(state): State<AppState>,
    Path((doc_id, item_id)): Path<(String, String)>,
) -> Result<Json<CodeView>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let item = item_id.replace('~', "/");
    let v = queries::code_view(&mut c, &state.repos, &doc_id, Some(&item), &user).await?;
    Ok(Json(CodeView::from(&v)))
}

/// SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code/source
pub async fn item_code_source(
    State(state): State<AppState>,
    Path((doc_id, item_id)): Path<(String, String)>,
) -> Result<Json<CodeText>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let t = queries::code_source(
        &mut c,
        &state.repos,
        &doc_id,
        &item_id.replace('~', "/"),
        &user,
    )
    .await?;
    Ok(Json(CodeText::from(&t)))
}

/// SYNC-API-001#GET/api/projects/{code}/code-calls
pub async fn code_calls(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<CodeCalls>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let v = queries::code_calls(&mut c, &state.repos, &code, &user).await?;
    Ok(Json(CodeCalls::from(&v)))
}

/// SYNC-API-001#GET/api/projects/{code}/code-graph
pub async fn code_nodes(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<CodeNodes>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let v = queries::code_nodes(&mut c, &state.repos, &code, &user).await?;
    Ok(Json(CodeNodes::from(&v)))
}

/// SYNC-API-001#GET/api/projects/{code}/code/source
///
/// 질의 `file`(1자 이상)·`line`(1 이상 정수) 둘 다 필수. 파이썬 정수라 아무리 커도 받는다 — 그런 줄의 함수는 없다
pub async fn code_text(
    State(state): State<AppState>,
    Path(code): Path<String>,
    RawQuery(raw): RawQuery,
) -> Result<Json<CodeText>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let q = fastapi::query_params(raw.as_deref());
    let mut errors = Vec::new();
    let file = fastapi::query_field(&q, "file", &CODE_FILE, true, &mut errors);
    let line = fastapi::query_field(&q, "line", &LINE, true, &mut errors);
    fastapi::check_errors(errors)?;
    let file = match file {
        Some(PyValue::Str(PyStr::Utf8(s))) => s,
        Some(PyValue::Str(s)) => s.repr(),
        _ => String::new(),
    };
    let line = match line {
        Some(PyValue::Int(i)) => i,
        _ => BigInt::from(0),
    };
    // i64 밖의 줄은 어느 함수와도 같지 않다 — 소유·그래프는 그대로 보고, 없는 함수의 이름은 받은 수 그대로
    let (n, big) = match i64::try_from(&line) {
        Ok(n) => (n, false),
        Err(_) => (-1, true),
    };
    match queries::code_text(&mut c, &state.repos, &code, &file, n, &user).await {
        Ok(t) => Ok(Json(CodeText::from(&t))),
        Err(Problem::NotFound { resource, .. }) if big && resource == "function" => {
            Err(ApiProblem(Problem::NotFound {
                resource,
                id: format!("{file}:{line}").into(),
            }))
        }
        Err(p) => Err(ApiProblem(p)),
    }
}

/// SYNC-API-001#POST/api/projects/{code}/code/ask
///
/// 코드 그래프에서 묻는다(UI-17 질문 탭) — 고른 함수(key)가 시작 맥락, 없으면 그래프 전체. 스트림은 문서에 묻기와 같다
pub async fn ask_code(
    State(state): State<AppState>,
    Path(code): Path<String>,
    headers: axum::http::HeaderMap,
    body: axum::body::Bytes,
) -> Result<axum::response::Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let user = {
        let mut c = state.pool.acquire().await.map_err(Problem::from)?;
        current_user(&mut c, &state).await?
    };
    let req = fastapi::body_model(&body, &ASK_CODE)?;
    let b = crate::web::sse::ask_body(&req, "key");
    let rx = queries::ask_code(
        &state.pool,
        &state.repos,
        &state.llm,
        &code,
        b.hint.as_deref(),
        b.conversation_id,
        &b.question,
        &b.attachment_ids,
        &user,
    )
    .await?;
    Ok(crate::web::sse::stream(rx))
}
