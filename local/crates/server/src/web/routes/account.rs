//! 내 계정 — 파이썬 판 `web/routers/account.py`의 `/api/me`·`/api/me/tokens`

use std::sync::LazyLock;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use num_traits::ToPrimitive;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::types::iso_utc;

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{AccessToken, IssuedToken, Me};

static ISSUE_TOKEN: LazyLock<Validator> = LazyLock::new(schemas::issue_token);
static INT: LazyLock<Validator> = LazyLock::new(schemas::int);

/// SYNC-API-001#GET/api/me
pub async fn me(State(state): State<AppState>) -> Result<Json<Me>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(Me {
        id: user.id,
        github_login: user.github_login,
        display_name: user.display_name,
        created_at: iso_utc(user.created_at),
        llm_enabled: state.llm_enabled,
        storage_modes: vec!["server"],
        edition: "closed",
        repo_private: true,
    }))
}

/// SYNC-API-001#GET/api/me/tokens
pub async fn list_tokens(
    State(state): State<AppState>,
) -> Result<Json<Vec<AccessToken>>, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let tokens = AccountService { db: &mut tx }.list_tokens(&user).await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(Json(tokens.into_iter().map(AccessToken::from).collect()))
}

/// SYNC-API-001#POST/api/me/tokens
pub async fn issue_token(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let req = fastapi::body_model(&body, &ISSUE_TOKEN)?;
    let label = match req.as_dict().and_then(|d| d.get(&PyStr::from("label"))) {
        Some(PyValue::Str(PyStr::Utf8(s))) => s.clone(),
        // 서로게이트가 든 문자열은 max_length 검증이 string_unicode로 막는다 — 여기 오지 않는다
        _ => {
            return Err(Problem::Internal {
                log: "label이 문자열이 아니다".into(),
            }
            .into());
        }
    };
    let issued = AccountService { db: &mut tx }
        .issue_token(&user, &label)
        .await?;
    tx.commit().await.map_err(Problem::from)?;
    let body = IssuedToken {
        token: AccessToken::from(issued.token),
        raw: issued.raw,
    };
    Ok((StatusCode::CREATED, Json(body)).into_response())
}

/// SYNC-API-001#DELETE/api/me/tokens/{id}
pub async fn revoke_token(
    State(state): State<AppState>,
    Path(token_id): Path<String>,
) -> Result<StatusCode, ApiProblem> {
    let mut tx = state.pool.begin().await.map_err(Problem::from)?;
    let user = current_user(&mut tx, &state).await?;
    let id = fastapi::path_int("token_id", &token_id, &INT)?;
    // 파이썬 int는 크기가 없다 — i64 밖이면 DB에 넘기지 못한다(500 internal, MS-016 revoke_token 다른 점)
    let Some(i) = id.to_i64() else {
        return Err(Problem::Internal {
            log: format!("access_tokens.id {id}: integer out of range"),
        }
        .into());
    };
    AccountService { db: &mut tx }
        .revoke_token(&user, i)
        .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(StatusCode::NO_CONTENT)
}
