//! 관리 — 파이썬 판 `web/routers/admin.py`(SYNC-API-001 3.8, 카드 L11). 동기화 상태·재구축·통지·지금 가져오기·옮기기.
//! 싱크독_로컬은 서버 저장뿐이라 통지는 늘 `none`이고 옮기기 둘은 늘 거절이다

use std::sync::LazyLock;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, State};
use axum::http::HeaderMap;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline;
use syncdoc_core::project::service::ProjectService;

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{HookStatus, RebuildResult, RepoStatus, SyncResult};

static MOVE_TO_GITHUB: LazyLock<Validator> = LazyLock::new(schemas::move_to_github);

/// SYNC-API-001#GET/api/admin/repos
pub async fn repos(State(state): State<AppState>) -> Result<Json<Vec<RepoStatus>>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let rows = ProjectService {
        db: &mut c,
        repos: &state.repos,
    }
    .repo_status(&user)
    .await?;
    Ok(Json(rows.iter().map(RepoStatus::from).collect()))
}

/// SYNC-API-001#POST/api/admin/repos/{code}/rebuild
pub async fn rebuild(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<RebuildResult>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let r = ProjectService {
        db: &mut c,
        repos: &state.repos,
    }
    .rebuild_index(&code, &user)
    .await?;
    Ok(Json(RebuildResult::from(&r)))
}

/// SYNC-API-001#POST/api/admin/repos/{code}/hook
pub async fn hook(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<HookStatus>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let h = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .ensure_hook(&code, &user)
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(HookStatus::from(&h)))
}

/// SYNC-API-001#POST/api/admin/repos/{code}/sync
pub async fn sync(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<SyncResult>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let r = ProjectService {
        db: &mut c,
        repos: &state.repos,
    }
    .sync_now(&state.pool, &code, &user)
    .await?;
    Ok(Json(SyncResult::from(&r)))
}

/// SYNC-API-001#POST/api/admin/repos/{code}/move-to-server
pub async fn move_to_server(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<()>, ApiProblem> {
    let user = {
        let mut c = state.pool.acquire().await.map_err(Problem::from)?;
        current_user(&mut c, &state).await?
    };
    pipeline::move_to_server(&state.pool, &state.repos, &code, &user).await?;
    Err(ApiProblem(Problem::Internal {
        log: "싱크독_로컬은 옮길 수 없다".into(),
    }))
}

/// SYNC-API-001#POST/api/admin/repos/{code}/move-to-github
///
/// 본문 `MoveToGithub { remote_url (1글자 이상) }`
pub async fn move_to_github(
    State(state): State<AppState>,
    Path(code): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Json<()>, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let user = {
        let mut c = state.pool.acquire().await.map_err(Problem::from)?;
        current_user(&mut c, &state).await?
    };
    let req = fastapi::body_model(&body, &MOVE_TO_GITHUB)?;
    let remote_url = match req
        .as_dict()
        .and_then(|d| d.get(&PyStr::from("remote_url")))
    {
        Some(PyValue::Str(PyStr::Utf8(s))) => s.clone(),
        _ => String::new(),
    };
    pipeline::move_to_github(&state.pool, &state.repos, &code, &user, &remote_url).await?;
    Err(ApiProblem(Problem::Internal {
        log: "싱크독_로컬은 옮길 수 없다".into(),
    }))
}
