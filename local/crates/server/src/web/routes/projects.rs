//! 프로젝트 — 파이썬 판 `web/routers/projects.py`의 목록·만들기·지우기 (카드 L6)

use std::sync::LazyLock;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use syncdoc_core::errors::Problem;
use syncdoc_core::project::service::ProjectService;
use syncdoc_core::queries;
use syncdoc_core::types::Storage;

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::ProjectSummary;

static INIT_PROJECT: LazyLock<Validator> = LazyLock::new(schemas::init_project);

/// SYNC-API-001#GET/api/projects
pub async fn list_projects(
    State(state): State<AppState>,
) -> Result<Json<Vec<ProjectSummary>>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let all = queries::project_summary(&mut tx, &state.repos, &user).await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(all.iter().map(ProjectSummary::from).collect()))
}

fn field<'a>(v: &'a PyValue, name: &str) -> Option<&'a PyValue> {
    v.as_dict().and_then(|d| d.get(&PyStr::from(name)))
}

fn text(v: &PyValue, name: &str) -> String {
    match field(v, name) {
        Some(PyValue::Str(PyStr::Utf8(s))) => s.clone(),
        _ => String::new(),
    }
}

/// SYNC-API-001#POST/api/projects
pub async fn init_project(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let req = fastapi::body_model(&body, &INIT_PROJECT)?;
    let code = text(&req, "code");
    let storage = Storage::parse(&text(&req, "storage")).unwrap_or(Storage::Github);
    let import_existing = matches!(field(&req, "import_existing"), Some(PyValue::Bool(true)));
    ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .init_project(&code, &text(&req, "name"), &user, import_existing, storage)
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let summary = queries::project_summary(&mut c, &state.repos, &user)
        .await?
        .into_iter()
        .find(|p| p.code == code)
        .ok_or_else(|| Problem::Internal {
            log: format!("만든 프로젝트 {code}의 요약이 없다"),
        })?;
    Ok((StatusCode::CREATED, Json(ProjectSummary::from(&summary))).into_response())
}

/// SYNC-API-001#DELETE/api/projects/{code}
pub async fn delete_project(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<StatusCode, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .delete_project(&code, &user)
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(StatusCode::NO_CONTENT)
}
