//! 프로젝트 — 파이썬 판 `web/routers/projects.py`의 목록·만들기·지우기(카드 L6)와 상세·문서·문제 목록·관계도·첨부(카드 L8)

use std::sync::LazyLock;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, RawQuery, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{IntoResponse, Response};
use syncdoc_core::errors::Problem;
use syncdoc_core::project::service::ProjectService;
use syncdoc_core::queries;
use syncdoc_core::types::{GraphScope, Storage};

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{DocumentSummary, Graph, ProjectDetail, ProjectItemOut, ProjectSummary};

static INIT_PROJECT: LazyLock<Validator> = LazyLock::new(schemas::init_project);
static STAGE: LazyLock<Validator> = LazyLock::new(schemas::stage);
static DOC_STATUS: LazyLock<Validator> = LazyLock::new(schemas::doc_status);
static FLAG_KIND: LazyLock<Validator> = LazyLock::new(schemas::flag_kind);
static GRAPH_SCOPE: LazyLock<Validator> = LazyLock::new(schemas::graph_scope);

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
) -> Result<Response, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .delete_project(&code, &user)
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    // FastAPI `status_code=204`에 처리기가 None을 돌려주면 JSONResponse의 머리가 남는다 — 파이썬 판과 같게
    Ok((
        StatusCode::NO_CONTENT,
        [(header::CONTENT_TYPE, "application/json")],
    )
        .into_response())
}

/// SYNC-API-001#GET/api/projects/{code}
pub async fn get_project(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<ProjectDetail>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let d = queries::project_detail(&mut c, &state.repos, &code, &user).await?;
    Ok(Json(ProjectDetail::from(&d)))
}

/// SYNC-API-001#GET/api/projects/{code}/docs
///
/// 질의 `stage`(1~11)·`status`(draft·approved) — 틀리면 422, 둘 다 틀리면 둘 다 싣는다
pub async fn list_docs(
    State(state): State<AppState>,
    Path(code): Path<String>,
    RawQuery(raw): RawQuery,
) -> Result<Json<Vec<DocumentSummary>>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let q = fastapi::query_params(raw.as_deref());
    let mut errors = Vec::new();
    let stage = fastapi::query_field(&q, "stage", &STAGE, false, &mut errors);
    let status = fastapi::query_field(&q, "status", &DOC_STATUS, false, &mut errors);
    fastapi::check_errors(errors)?;
    let stage = match stage {
        Some(PyValue::Int(i)) => i32::try_from(&i).ok(),
        _ => None,
    };
    let status = match status {
        Some(PyValue::Str(PyStr::Utf8(s))) => Some(s),
        _ => None,
    };
    let docs = queries::document_list(&mut c, &state.repos, &code, &user, stage, status.as_deref())
        .await?;
    Ok(Json(docs.iter().map(DocumentSummary::from).collect()))
}

/// SYNC-API-001#GET/api/projects/{code}/flags
///
/// 경로 이름은 flags로 남았다 — 끊어진 참조는 `references.is_missing`. `kind`는 필수
pub async fn list_items(
    State(state): State<AppState>,
    Path(code): Path<String>,
    RawQuery(raw): RawQuery,
) -> Result<Json<Vec<ProjectItemOut>>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let q = fastapi::query_params(raw.as_deref());
    let mut errors = Vec::new();
    let kind = fastapi::query_field(&q, "kind", &FLAG_KIND, true, &mut errors);
    fastapi::check_errors(errors)?;
    let kind = match kind {
        Some(PyValue::Str(PyStr::Utf8(s))) => s,
        _ => String::new(),
    };
    let items = queries::project_items(&mut c, &state.repos, &code, &kind, &user).await?;
    Ok(Json(items.iter().map(ProjectItemOut::from).collect()))
}

/// SYNC-API-001#GET/api/projects/{code}/graph
///
/// 질의 `scope` — `all`(기본)·`approved`
pub async fn graph(
    State(state): State<AppState>,
    Path(code): Path<String>,
    RawQuery(raw): RawQuery,
) -> Result<Json<Graph>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let q = fastapi::query_params(raw.as_deref());
    let mut errors = Vec::new();
    let scope = fastapi::query_field(&q, "scope", &GRAPH_SCOPE, false, &mut errors);
    fastapi::check_errors(errors)?;
    let scope = match scope {
        Some(PyValue::Str(PyStr::Utf8(s))) if s == "approved" => GraphScope::Approved,
        _ => GraphScope::All,
    };
    let g = queries::graph_view(&mut c, &state.repos, &code, &user, scope).await?;
    Ok(Json(Graph::from(&g)))
}

/// 첨부의 content-type — 파이썬 판 컨테이너의 `mimetypes.guess_type`(/etc/mime.types 없음)이 내는 그대로.
/// 표에 없는 것(webp·woff·woff2·ttf)은 starlette 기본값 `application/octet-stream`, `text/*`에는 charset
fn asset_content_type(path: &std::path::Path) -> &'static str {
    let ext = path
        .extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default();
    match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "svg" => "image/svg+xml",
        "css" => "text/css; charset=utf-8",
        _ => "application/octet-stream",
    }
}

/// 파이썬 `str(float)` — 정수면 `.0`을 붙인다(ETag 재료)
fn py_float(x: f64) -> String {
    let s = format!("{x}");
    if s.contains('.') || s.contains('e') || s.contains("inf") || s.contains("NaN") {
        s
    } else {
        format!("{s}.0")
    }
}

/// SYNC-API-001#GET/api/projects/{code}/files/{path}
///
/// 첨부(이미지·폰트·css)를 작업 사본에서 — starlette `FileResponse`와 같은 머리(차례까지). svg는 직접 열어도
/// 스크립트가 앱 출처에서 못 돌게 `sandbox`. Range는 계약 밖이라 받지 않는다(늘 전체)
pub async fn get_file(
    State(state): State<AppState>,
    Path(params): Path<std::collections::HashMap<String, String>>,
) -> Result<Response, ApiProblem> {
    // `/files/`도 같은 처리기 — 파이썬 `{path:path}`는 빈 것도 받는다
    let code = params.get("code").cloned().unwrap_or_default();
    let path = params.get("path").cloned().unwrap_or_default();
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let target = ProjectService {
        db: &mut c,
        repos: &state.repos,
    }
    .asset_path(&code, &path, &user)
    .await?;
    drop(c);
    let meta = tokio::fs::metadata(&target).await.map_err(Problem::from)?;
    let bytes = tokio::fs::read(&target).await.map_err(Problem::from)?;
    let mtime = meta.modified().map_err(Problem::from)?;
    let secs = mtime
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    let etag = {
        use md5::Digest;
        let digest = md5::Md5::digest(format!("{}-{}", py_float(secs), meta.len()).as_bytes());
        let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
        format!("\"{hex}\"")
    };
    let mut resp = Response::new(axum::body::Body::from(bytes));
    let h = resp.headers_mut();
    let set = |h: &mut HeaderMap, k: header::HeaderName, v: &str| {
        if let Ok(v) = header::HeaderValue::from_str(v) {
            h.insert(k, v);
        }
    };
    set(h, header::CACHE_CONTROL, "private, max-age=60");
    if target
        .extension()
        .is_some_and(|e| e.to_string_lossy().to_lowercase() == "svg")
    {
        set(h, header::CONTENT_SECURITY_POLICY, "sandbox");
    }
    set(h, header::CONTENT_TYPE, asset_content_type(&target));
    set(h, header::ACCEPT_RANGES, "bytes");
    set(h, header::CONTENT_LENGTH, &meta.len().to_string());
    set(h, header::LAST_MODIFIED, &httpdate::fmt_http_date(mtime));
    set(h, header::ETAG, &etag);
    Ok(resp)
}

/// SYNC-API-001#GET/api/projects/{code}/trash
pub async fn trash_list(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<Vec<DocumentSummary>>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let docs = queries::trash_list(&mut c, &state.repos, &code, &user).await?;
    Ok(Json(docs.iter().map(DocumentSummary::from).collect()))
}
