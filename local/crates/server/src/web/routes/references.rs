//! 항목 — 파이썬 판 `web/routers/references.py`(카드 L8): 항목 블록·위아래 참조·11단계 체인.
//! 경로에 `/`를 못 싣는 항목 ID(`GET/api/me`)는 `~`로 온다 — 여기서 `/`로 바꾼다

use axum::Json;
use axum::extract::{Path, State};
use syncdoc_core::errors::Problem;
use syncdoc_core::queries;

use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{ItemReferences, ItemView};

/// SYNC-API-001#GET/api/docs/{docId}/items/{itemId}
pub async fn item_view(
    State(state): State<AppState>,
    Path((doc_id, item_id)): Path<(String, String)>,
) -> Result<Json<ItemView>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let v = queries::item_view(
        &mut c,
        &state.repos,
        &doc_id,
        &item_id.replace('~', "/"),
        &user,
    )
    .await?;
    Ok(Json(ItemView::from(&v)))
}

/// SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/references
pub async fn item_references(
    State(state): State<AppState>,
    Path((doc_id, item_id)): Path<(String, String)>,
) -> Result<Json<ItemReferences>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let r = queries::item_references_view(
        &mut c,
        &state.repos,
        &doc_id,
        &item_id.replace('~', "/"),
        &user,
    )
    .await?;
    Ok(Json(ItemReferences::from(&r)))
}
