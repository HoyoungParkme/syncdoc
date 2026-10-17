//! 실행 기록 — 파이썬 판 `web/routers/traces.py`(카드 L28). 화면 UI-19와 기록 도구(SEQ-36)가 부른다.
//! 소유를 `ProjectService.get_owned`로 먼저 보고 `TraceService`를 바로 부른다. 올리기만 개인 토큰으로도 된다.
//! 차례는 파이썬 판(FastAPI)과 같다 — 본문 JSON 읽기 → 사람(토큰·로컬) → 4MB → 꼴 검증 → 소유 → 받기

use std::sync::LazyLock;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use num_bigint::BigInt;
use syncdoc_core::errors::Problem;
use syncdoc_core::project::service::ProjectService;
use syncdoc_core::trace::TraceService;
use syncdoc_core::trace::service::{KEEP, MAX_BYTES};

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::state::AppState;
use crate::web::auth::{current_user, token_or_session_user};
use crate::web::problem::ApiProblem;
use crate::web::schemas::{Deleted, TraceBrief, TraceCoverage, TraceView};

static TRACE_RECORD: LazyLock<Validator> = LazyLock::new(schemas::trace_record);
static INT: LazyLock<Validator> = LazyLock::new(schemas::int);

/// SYNC-API-001#POST/api/projects/{code}/traces
pub async fn upload_trace(
    State(state): State<AppState>,
    Path(code): Path<String>,
    headers: HeaderMap,
    bytes: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &bytes)?;
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = token_or_session_user(&mut tx, &state, &headers).await?;
    // 토큰이 통과했으면 뒤가 실패해도 last_used_at은 남는다 (파이썬 의존성의 커밋)
    tx.commit().await.map_err(Problem::from)?;
    if bytes.len() > MAX_BYTES {
        return Err(Problem::TraceInvalid {
            reason: "본문이 4MB를 넘는다".into(),
            status: 413,
        }
        .into());
    }
    fastapi::body_model(&body, &TRACE_RECORD)?;
    let record: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|e| Problem::Internal {
            log: format!("검증한 본문을 못 읽었다: {e}"),
        })?;
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let (project, _) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&code, &user)
    .await?;
    let (brief, new) = TraceService { db: &mut tx }
        .save(project.id, user.id, &record)
        .await?;
    tx.commit().await.map_err(Problem::from)?;
    let status = if new {
        StatusCode::CREATED
    } else {
        StatusCode::OK
    };
    Ok((status, Json(TraceBrief::from(&brief))).into_response())
}

/// SYNC-API-001#GET/api/projects/{code}/traces
pub async fn list_traces(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<Vec<TraceBrief>>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let (project, _) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&code, &user)
    .await?;
    let list = TraceService { db: &mut tx }
        .list_recent(project.id, KEEP)
        .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(list.iter().map(TraceBrief::from).collect()))
}

/// SYNC-API-001#DELETE/api/projects/{code}/traces
pub async fn delete_traces(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<Deleted>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let (project, _) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&code, &user)
    .await?;
    let n = TraceService { db: &mut tx }
        .delete(project.id, None)
        .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(Deleted { deleted: n }))
}

/// SYNC-API-001#GET/api/projects/{code}/traces/coverage
pub async fn trace_coverage(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<TraceCoverage>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let (project, _) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&code, &user)
    .await?;
    let c = TraceService { db: &mut tx }.coverage(project.id).await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(TraceCoverage::from(&c)))
}

/// 경로의 기록 번호 — 파이썬 정수라 아무리 커도 받는다. i64를 넘으면 그런 행은 없다
fn trace_id(raw: &str) -> Result<Result<i64, BigInt>, Problem> {
    let n = fastapi::path_int("trace_id", raw, &INT)?;
    Ok(i64::try_from(&n).map_err(|_| n))
}

fn no_trace(n: &BigInt) -> Problem {
    Problem::NotFound {
        resource: "trace".into(),
        id: n.to_string().into(),
    }
}

/// SYNC-API-001#GET/api/projects/{code}/traces/{id}
pub async fn get_trace(
    State(state): State<AppState>,
    Path((code, raw)): Path<(String, String)>,
) -> Result<Json<TraceView>, ApiProblem> {
    let id = trace_id(&raw)?;
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let (project, _) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&code, &user)
    .await?;
    let id = id.map_err(|n| no_trace(&n))?;
    let v = TraceService { db: &mut tx }.get(project.id, id).await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(TraceView::from(&v)))
}

/// SYNC-API-001#DELETE/api/projects/{code}/traces/{id}
pub async fn delete_trace(
    State(state): State<AppState>,
    Path((code, raw)): Path<(String, String)>,
) -> Result<Response, ApiProblem> {
    let id = trace_id(&raw)?;
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let (project, _) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&code, &user)
    .await?;
    let id = id.map_err(|n| no_trace(&n))?;
    TraceService { db: &mut tx }
        .delete(project.id, Some(id))
        .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(StatusCode::NO_CONTENT.into_response())
}
