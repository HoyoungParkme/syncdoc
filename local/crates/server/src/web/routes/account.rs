//! 내 계정 — 파이썬 판 `web/routers/account.py`의 `/api/me`

use axum::Json;
use axum::extract::State;
use syncdoc_core::errors::Problem;
use syncdoc_core::types::iso_utc;

use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::Me;

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
