//! 대화·첨부 — 파이썬 판 `web/routers/conversations.py`(카드 L14): 내 대화 목록·새 대화·대화 하나·지우기,
//! 아직 안 보낸 첨부 올리기·받기·빼기. 질문(ask)은 documents·code 경로에 있다

use std::sync::LazyLock;

use axum::Json;
use axum::body::Bytes;
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{IntoResponse, Response};
use num_bigint::BigInt;
use percent_encoding::{AsciiSet, NON_ALPHANUMERIC, utf8_percent_encode};
use sqlx::Connection;
use syncdoc_core::conversation::ConversationService;
use syncdoc_core::errors::Problem;
use syncdoc_core::queries;
use syncdoc_core::types::ConversationBrief as BriefDto;

use crate::compat::fastapi::{self, schemas};
use crate::compat::pydantic::Validator;
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;
use crate::web::auth::current_user;
use crate::web::problem::ApiProblem;
use crate::web::schemas::{AttachmentMeta, Conversation, ConversationBrief};

static CREATE: LazyLock<Validator> = LazyLock::new(schemas::create_conversation);
static INT: LazyLock<Validator> = LazyLock::new(schemas::int);

/// 파이썬 `urllib.parse.quote(name)` — 안전 글자는 영문·숫자·`_.-~`와 `/`
const QUOTE: &AsciiSet = &NON_ALPHANUMERIC
    .remove(b'_')
    .remove(b'.')
    .remove(b'-')
    .remove(b'~')
    .remove(b'/');

/// 경로의 `{id}` — 파이썬 `int`. int4 밖이면 DB가 거절한다(500, 파이썬 판도 같다)
fn path_id(raw: &str) -> Result<i32, Problem> {
    let n: BigInt = fastapi::path_int("id", raw, &INT)?;
    i32::try_from(&n).map_err(|_| Problem::Internal {
        log: format!("id가 int4 밖이다 — {n}"),
    })
}

/// SYNC-API-001#GET/api/projects/{code}/conversations
///
/// 내 대화, 최근순 (UI-5 8.11)
pub async fn list_conversations(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<Vec<ConversationBrief>>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let briefs = ConversationService {
        db: &mut c,
        repos: &state.repos,
    }
    .list(&code, &user)
    .await?;
    Ok(Json(briefs.iter().map(ConversationBrief::from).collect()))
}

/// SYNC-API-001#GET/api/projects/{code}/conversations post
///
/// 새 대화 (UI-5 8.12) — 본문이 없거나 제목이 비면 「새 대화」
pub async fn create_conversation(
    State(state): State<AppState>,
    Path(code): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let body = fastapi::read_body(&headers, &body)?;
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let req = fastapi::body_model_optional(&body, &CREATE)?;
    let title = match req
        .as_ref()
        .and_then(|r| r.as_dict())
        .and_then(|d| d.get(&PyStr::from("title")))
    {
        Some(PyValue::Str(PyStr::Utf8(s))) => Some(s.clone()),
        Some(PyValue::Str(s)) => Some(s.repr()),
        _ => None,
    };
    let mut tx = c.begin().await.map_err(Problem::from)?;
    let conv = ConversationService {
        db: &mut tx,
        repos: &state.repos,
    }
    .create(&code, &user, title.as_deref())
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    let brief = BriefDto {
        id: conv.id,
        title: conv.title,
        turn_count: 0,
        updated_at: conv.updated_at,
    };
    Ok((StatusCode::CREATED, Json(ConversationBrief::from(&brief))).into_response())
}

/// SYNC-API-001#GET/api/conversations/{id}
///
/// 턴 전부 + 첨부 메타 (UI-5 8.7) — 답 속 참조는 실제 항목과 맞춘 링크로
pub async fn get_conversation(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Conversation>, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let id = path_id(&id)?;
    let v = queries::conversation_view(&mut c, &state.repos, id, &user).await?;
    Ok(Json(Conversation::from(&v)))
}

/// SYNC-API-001#GET/api/conversations/{id} delete
///
/// 턴·첨부까지 (UI-5 8.13)
pub async fn delete_conversation(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Response, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let id = path_id(&id)?;
    let mut tx = c.begin().await.map_err(Problem::from)?;
    ConversationService {
        db: &mut tx,
        repos: &state.repos,
    }
    .delete(id, &user)
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(StatusCode::NO_CONTENT.into_response())
}

/// SYNC-API-001#POST/api/conversations/{id}/attachments
///
/// 아직 안 보낸 첨부 (UI-5 8.14~8.16) — multipart의 `file` 하나
pub async fn upload_attachment(
    State(state): State<AppState>,
    Path(id): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    // 폼 해석은 의존성보다 먼저 — 깨진 multipart는 400 (FastAPI `get_request_handler`)
    let file = fastapi::form_file(&headers, &body, "file").await;
    if let Err(p @ Problem::Blank { .. }) = file {
        return Err(ApiProblem(p));
    }
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    // 경로 값 오류와 본문 오류는 한 번에(경로가 먼저)
    let (n, file) = match (fastapi::path_int("id", &id, &INT), file) {
        (Ok(n), Ok(f)) => (n, f),
        (
            Err(Problem::InvalidRequest { mut errors }),
            Err(Problem::InvalidRequest { errors: more }),
        ) => {
            errors.extend(more);
            return Err(ApiProblem(Problem::InvalidRequest { errors }));
        }
        (Err(p), _) | (_, Err(p)) => return Err(ApiProblem(p)),
    };
    let id = i32::try_from(&n).map_err(|_| Problem::Internal {
        log: format!("id가 int4 밖이다 — {n}"),
    })?;
    let mut tx = c.begin().await.map_err(Problem::from)?;
    let meta = ConversationService {
        db: &mut tx,
        repos: &state.repos,
    }
    .add_attachment(
        id,
        &user,
        file.filename
            .as_deref()
            .filter(|n| !n.is_empty())
            .unwrap_or("file"),
        file.content_type.as_deref().unwrap_or(""),
        &file.data,
    )
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok((StatusCode::CREATED, Json(AttachmentMeta::from(&meta))).into_response())
}

/// SYNC-API-001#GET/api/attachments/{id}
///
/// 파일 그대로 — 썸네일·미리보기·다운로드. 글자 종류는 starlette처럼 `; charset=utf-8`을 붙인다
pub async fn get_attachment(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Response, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let id = path_id(&id)?;
    let (name, mime, data) = ConversationService {
        db: &mut c,
        repos: &state.repos,
    }
    .attachment_bytes(id, &user)
    .await?;
    let content_type = if mime.starts_with("text/") && !mime.to_lowercase().contains("charset=") {
        format!("{mime}; charset=utf-8")
    } else {
        mime
    };
    let disposition = format!(
        "inline; filename*=UTF-8''{}",
        utf8_percent_encode(&name, QUOTE)
    );
    Ok((
        StatusCode::OK,
        [
            (header::CONTENT_TYPE, content_type),
            (header::CONTENT_DISPOSITION, disposition),
            (header::CACHE_CONTROL, "private, max-age=3600".to_string()),
        ],
        data,
    )
        .into_response())
}

/// SYNC-API-001#GET/api/attachments/{id} delete
///
/// 아직 안 보낸 첨부를 뺀다 (UI-5 8.14 ✕)
pub async fn delete_attachment(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Response, ApiProblem> {
    let mut c = state.pool.acquire().await.map_err(Problem::from)?;
    let user = current_user(&mut c, &state).await?;
    let id = path_id(&id)?;
    let mut tx = c.begin().await.map_err(Problem::from)?;
    ConversationService {
        db: &mut tx,
        repos: &state.repos,
    }
    .remove_attachment(id, &user)
    .await?;
    tx.commit().await.map_err(Problem::from)?;
    Ok(StatusCode::NO_CONTENT.into_response())
}
