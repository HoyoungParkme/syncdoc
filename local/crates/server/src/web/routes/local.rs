//! 이 PC — `/api/local*` (SYNC-API-001 3.11, 카드 L16). 싱크독_로컬 설치형만 — 파이썬 판에는 없는 경로다.
//! 다시 켜기(설정 저장·되살리기·옮기기)는 검사가 끝나면 202 — 서버가 내려가 그 일을 하고 다시 뜬다

use std::path::Path as FsPath;
use std::sync::{Arc, LazyLock};

use axum::Json;
use axum::body::Bytes;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use serde_json::json;
use syncdoc_core::errors::Problem;

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::local::{LocalOps, SettingsChange};
use crate::state::AppState;
use crate::web::problem::ApiProblem;

static SETTINGS: LazyLock<Validator> = LazyLock::new(schemas::local_settings);
static AUTOSTART: LazyLock<Validator> = LazyLock::new(schemas::local_autostart);
static RESTORE: LazyLock<Validator> = LazyLock::new(schemas::local_restore);
static MOVE: LazyLock<Validator> = LazyLock::new(schemas::local_move);
static REQUEST: LazyLock<Validator> = LazyLock::new(schemas::local_request);

/// 이 PC의 문 — 경로는 이것이 있을 때만 걸린다
fn ops(state: &AppState) -> Result<Arc<dyn LocalOps>, Problem> {
    state.local.clone().ok_or_else(|| Problem::Internal {
        log: "이 PC가 없는 조립에서 /api/local을 불렀다".into(),
    })
}

/// 모델의 글자 칸 — 없거나 `null`이면 없음
fn opt_text(v: &PyValue, name: &str) -> Option<String> {
    match v.as_dict().and_then(|d| d.get(&PyStr::from(name))) {
        Some(PyValue::Str(s)) => s.as_str().map(str::to_string),
        _ => None,
    }
}

fn restarting() -> Response {
    (StatusCode::ACCEPTED, Json(json!({"restarting": true}))).into_response()
}

/// SYNC-API-001#GET/api/local
pub async fn get_local(State(state): State<AppState>) -> Result<Response, ApiProblem> {
    Ok(Json(ops(&state)?.info().await?).into_response())
}

/// SYNC-API-001#PUT/api/local/settings
pub async fn put_settings(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let req = fastapi::body_model(&body, &SETTINGS)?;
    let change = SettingsChange {
        name: opt_text(&req, "name"),
        llm_api_url: opt_text(&req, "llm_api_url").map(|s| s.trim().to_string()),
        llm_api_key: opt_text(&req, "llm_api_key"),
        llm_model: opt_text(&req, "llm_model"),
        backup_dir: opt_text(&req, "backup_dir").map(|s| s.trim().to_string()),
        backup_password: opt_text(&req, "backup_password"),
    };
    // 켤 때 settings.load가 받지 않을 값은 여기서 막는다 — 다시 켜다 멈추지 않게
    let mut errors = Vec::new();
    if let Some(u) = &change.llm_api_url
        && !(u.is_empty() || u.starts_with("http://") || u.starts_with("https://"))
    {
        errors.push((
            "body.llm_api_url".to_string(),
            "Value error, 비었거나 http:// 또는 https://로 시작해야 한다".to_string(),
        ));
    }
    if let Some(d) = &change.backup_dir
        && !(d.is_empty() || FsPath::new(d).is_absolute())
    {
        errors.push((
            "body.backup_dir".to_string(),
            "Value error, 비었거나 절대 경로여야 한다".to_string(),
        ));
    }
    fastapi::check_errors(errors)?;
    ops(&state)?.save_settings(change).await?;
    Ok(restarting())
}

/// SYNC-API-001#PUT/api/local/autostart
pub async fn put_autostart(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let req = fastapi::body_model(&body, &AUTOSTART)?;
    let on = matches!(
        req.as_dict().and_then(|d| d.get(&PyStr::from("on"))),
        Some(PyValue::Bool(true))
    );
    let local = ops(&state)?;
    local.set_autostart(on).await?;
    Ok(Json(local.info().await?).into_response())
}

/// SYNC-API-001#POST/api/local/backups
pub async fn post_backup(State(state): State<AppState>) -> Result<Response, ApiProblem> {
    let file = ops(&state)?.backup_now().await?;
    Ok((StatusCode::CREATED, Json(file)).into_response())
}

/// SYNC-API-001#POST/api/local/restore
pub async fn post_restore(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let req = fastapi::body_model(&body, &RESTORE)?;
    let name = opt_text(&req, "name").unwrap_or_default();
    let password = opt_text(&req, "password");
    ops(&state)?
        .restore(&name, password.as_deref().filter(|p| !p.is_empty()))
        .await?;
    Ok(restarting())
}

/// SYNC-API-001#POST/api/local/request
///
/// 이 PC의 개발 서버로 요청을 대신 보낸다(UI-19 6.2·6.6, 카드 L30). 설치형이 아니어도(시험 서버) 된다
pub async fn post_request(headers: HeaderMap, body: Bytes) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let req = fastapi::body_model(&body, &REQUEST)?;
    let reply = crate::local::request(
        &opt_text(&req, "method").unwrap_or_default(),
        &opt_text(&req, "url").unwrap_or_default(),
        opt_text(&req, "body").as_deref(),
    )
    .await?;
    Ok(Json(reply).into_response())
}

/// SYNC-API-001#POST/api/local/move
pub async fn post_move(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let req = fastapi::body_model(&body, &MOVE)?;
    ops(&state)?
        .move_to(&opt_text(&req, "dir").unwrap_or_default())
        .await?;
    Ok(restarting())
}
