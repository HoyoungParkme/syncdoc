//! 문서 — 파이썬 판 `web/routers/documents.py`의 읽기(카드 L8): 문서·이력·diff·추적표.
//! 상태·되돌리기·휴지통(L9)과 묻기(L14)는 그 카드가 더한다

use axum::Json;
use axum::extract::{Path, State};
use syncdoc_core::errors::Problem;
use syncdoc_core::queries;

use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::Document;

/// SYNC-API-001#GET/api/docs/{docId}
pub async fn get_document(
    State(state): State<AppState>,
    Path(doc_id): Path<String>,
) -> Result<Json<Document>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let d = queries::document_view(&mut c, &state.repos, &doc_id, &user).await?;
    Ok(Json(Document::from(&d)))
}
