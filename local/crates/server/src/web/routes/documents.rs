//! 문서 — 파이썬 판 `web/routers/documents.py`의 읽기(카드 L8): 문서·이력·diff·추적표.
//! 카드 L9가 상태·되돌리기·휴지통 넣기·되살리기·완전 삭제를 더했다. 묻기(L14)는 그 카드가 더한다

use std::sync::LazyLock;

use axum::Json;
use axum::extract::{Path, RawQuery, State};
use num_bigint::BigInt;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline;
use syncdoc_core::project::service::ProjectService;
use syncdoc_core::queries;
use syncdoc_core::spec::SpecService;
use syncdoc_core::types::{ApiAuthor, Author, AuthorKind, Entry};

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::PyValue;
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{Diff, Document, DownstreamView, TrashResult, Version};

static VERSION_NO: LazyLock<Validator> = LazyLock::new(schemas::version_no);
static FLAG: LazyLock<Validator> = LazyLock::new(schemas::flag);

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

/// SYNC-API-001#GET/api/docs/{docId}/diff
///
/// 질의 `from`·`to` — 1 이상 정수, 둘 다 필수. 판은 int4 — 그 밖의 수는 파이썬 판처럼 소유·문서를 본 뒤 500
pub async fn diff(
    State(state): State<AppState>,
    Path(doc_id): Path<String>,
    RawQuery(raw): RawQuery,
) -> Result<Json<Diff>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let q = fastapi::query_params(raw.as_deref());
    let mut errors = Vec::new();
    let from = fastapi::query_field(&q, "from", &VERSION_NO, true, &mut errors);
    let to = fastapi::query_field(&q, "to", &VERSION_NO, true, &mut errors);
    fastapi::check_errors(errors)?;
    let big = |v: Option<PyValue>| match v {
        Some(PyValue::Int(i)) => i,
        _ => BigInt::from(0),
    };
    let (from, to) = (big(from), big(to));
    match (i32::try_from(&from), i32::try_from(&to)) {
        (Ok(f), Ok(t)) => {
            let d = queries::diff_with_impact(&mut c, &state.repos, &doc_id, f, t, &user).await?;
            Ok(Json(Diff::from(&d)))
        }
        _ => {
            // 파이썬 판은 int4 밖의 수를 판 조회에 묶다가 DB가 거절해 500이다 — 소유·문서는 그 앞에서 본다
            ProjectService {
                db: &mut c,
                repos: &state.repos,
            }
            .get_owned(doc_id.split('-').next().unwrap_or(""), &user)
            .await?;
            SpecService { db: &mut c }.get_document(&doc_id).await?;
            Err(ApiProblem(Problem::Internal {
                log: format!("판 번호가 int4 밖이다 — {from}, {to}"),
            }))
        }
    }
}

/// SYNC-API-001#GET/api/docs/{docId}/versions
///
/// 파이썬 경로처럼 queries를 거치지 않는다(이력의 작성자 이름은 users_by_ids로, API-001 3.1 예외) — 소유 검사도 없다
pub async fn versions(
    State(state): State<AppState>,
    Path(doc_id): Path<String>,
) -> Result<Json<Vec<Version>>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    current_user(&mut c, &state).await?;
    let mut rows = SpecService { db: &mut c }.list_versions(&doc_id).await?;
    let ids: Vec<i32> = rows
        .iter()
        .map(|v| v.author.user_id)
        .chain(rows.iter().filter_map(|v| v.author.instructed_by_id))
        .collect();
    let names = AccountService { db: &mut c }.users_by_ids(&ids).await?;
    for v in &mut rows {
        v.author_view = Some(ApiAuthor {
            kind: v.author.kind.clone(),
            user: names.get(&v.author.user_id).cloned(),
            instructed_by: v
                .author
                .instructed_by_id
                .and_then(|i| names.get(&i).cloned()),
            via: v.author.via.clone(),
        });
    }
    Ok(Json(rows.iter().map(Version::from).collect()))
}

/// SYNC-API-001#GET/api/docs/{docId}/downstream
pub async fn downstream(
    State(state): State<AppState>,
    Path(doc_id): Path<String>,
) -> Result<Json<DownstreamView>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let d = queries::downstream_view(&mut c, &state.repos, &doc_id, &user).await?;
    Ok(Json(DownstreamView::from(&d)))
}

/// 웹의 사람 작성자 — `human`·사람·없음·`via` (파이썬 `_human`은 `web_status`, 되살리기는 `web_revert`)
fn human(user: &UserRow, via: Entry) -> Author {
    Author {
        kind: AuthorKind::Human,
        user: user.clone(),
        instructed_by: None,
        via,
    }
}

/// SYNC-API-001#DELETE/api/docs/{docId}
///
/// `confirm` 없이 부르면 끊어질 것을 담은 `document-deletion-needs-confirm` — 화면(UI-5 13.2)이 보여주고 `confirm=true`로 다시 부른다
pub async fn trash_document(
    State(state): State<AppState>,
    Path(doc_id): Path<String>,
    RawQuery(raw): RawQuery,
) -> Result<Json<TrashResult>, ApiProblem> {
    let user = {
        let mut c = state.pool.acquire().await.map_err(Problem::from)?;
        current_user(&mut c, &state).await?
    };
    let q = fastapi::query_params(raw.as_deref());
    let mut errors = Vec::new();
    let confirm = fastapi::query_field(&q, "confirm", &FLAG, false, &mut errors);
    fastapi::check_errors(errors)?;
    let confirm = matches!(confirm, Some(PyValue::Bool(true)));
    let r = pipeline::trash_document(
        &state.pool,
        &state.repos,
        &doc_id,
        &human(&user, Entry::WebStatus),
        confirm,
    )
    .await?;
    Ok(Json(TrashResult::from(&r)))
}
