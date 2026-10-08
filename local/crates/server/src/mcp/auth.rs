//! MCP 인증 — SYNC-SEQ-001#SEQ-C2 (파이썬 판 `mcp/auth.py`의 `BearerAuth`).
//! `Authorization: Bearer {원문}` → `AccountService.authenticate_token`. 통과하면 응답 전에 곧바로 커밋한다 —
//! 사용 흔적(`last_used_at`)이 남고, 응답을 흘리는 동안 토큰 행을 잠그지 않는다(#49·#318).
//! 없음·폐기·만료는 401 problem — 무엇이 틀렸는지 알리지 않는다. 원문은 로그에 남기지 않는다.

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::{StatusCode, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use syncdoc_core::account::model::UserRow;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;

use crate::state::AppState;
use crate::web::problem::render;

/// 파이썬 `json.dumps(Unauthorized(…).to_dict(), ensure_ascii=False)` — 기본 구분자(`, `·`: `)
const UNAUTHORIZED: &str = "{\"type\": \"urn:syncdoc:unauthorized\", \"title\": \"unauthorized\", \"status\": 401, \"detail\": \"토큰 없음·폐기·만료\"}";

/// 파이썬 `str.isspace()`가 참인 글자 — `str.strip()`이 벗긴다
fn py_space(c: char) -> bool {
    matches!(
        c,
        '\t' | '\n'
            | '\u{0b}'
            | '\u{0c}'
            | '\r'
            | '\u{1c}'..='\u{1f}'
            | ' '
            | '\u{85}'
            | '\u{a0}'
            | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'
            | '\u{2029}'
            | '\u{202f}'
            | '\u{205f}'
            | '\u{3000}'
    )
}

/// 원문 꺼내기 — ASGI 머리 목록을 dict로 만들었다(같은 이름이면 마지막). `Bearer `로 시작해야 한다
fn raw_token(req: &Request) -> Result<String, ()> {
    let Some(v) = req
        .headers()
        .get_all(header::AUTHORIZATION)
        .iter()
        .next_back()
    else {
        return Ok(String::new());
    };
    let s = std::str::from_utf8(v.as_bytes()).map_err(|_| ())?;
    Ok(match s.strip_prefix("Bearer ") {
        Some(rest) => rest.trim_matches(py_space).to_string(),
        None => String::new(),
    })
}

pub async fn bearer(State(state): State<AppState>, req: Request, next: Next) -> Response {
    let raw = match raw_token(&req) {
        Ok(r) => r,
        // 파이썬은 UTF-8이 아닌 머리를 풀다 예외 — 처리하지 못한 오류(500 internal)
        Err(()) => {
            return render(&Problem::Internal {
                log: "Authorization 머리가 UTF-8이 아니다".into(),
            });
        }
    };
    let mut user = None;
    if !raw.is_empty() {
        match authenticate(&state, &raw).await {
            Ok(u) => user = u,
            Err(p) => return render(&p),
        }
    }
    let Some(user) = user else {
        return (
            StatusCode::UNAUTHORIZED,
            [(header::CONTENT_TYPE, "application/problem+json")],
            Body::from(UNAUTHORIZED),
        )
            .into_response();
    };
    // 토큰 발급자 — 도구가 「나」로 쓴다 (파이썬 `current_user_id`, API-002 1장)
    let mut req = req;
    req.extensions_mut().insert(user);
    next.run(req).await
}

async fn authenticate(state: &AppState, raw: &str) -> Result<Option<UserRow>, Problem> {
    let mut tx = state.pool.begin().await?;
    let user = AccountService { db: &mut tx }
        .authenticate_token(raw)
        .await?;
    if user.is_some() {
        tx.commit().await?;
    }
    Ok(user)
}
