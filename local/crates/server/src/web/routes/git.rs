//! git 입구 — 파이썬 판 `web/routers/git.py`(카드 L10). 서버 저장소의 git 스마트 HTTP.
//! 파이썬 판은 `git http-backend`를 CGI로 돌린다 — Rust는 `upload-pack`·`receive-pack --stateless-rpc`를 직접 부르고
//! http-backend가 내는 머리(`Expires`·`Pragma`·`Cache-Control`·`Content-Type`)와 415 문장을 그대로 낸다(INFRA 9.1).
//! 인증은 HTTP Basic — 비밀번호 칸이 개인 토큰(MCP와 같은 것), 아이디 칸은 보지 않는다

use std::io::Read;
use std::sync::LazyLock;

use axum::body::{Body, Bytes};
use axum::extract::{Path, RawQuery, State};
use axum::http::{HeaderMap, HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use base64::Engine;
use regex::Regex;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline;
use syncdoc_core::project::service::ProjectService;

use crate::compat::fastapi;
use crate::state::AppState;
use crate::web::problem::{ApiProblem, render};

/// starlette가 `/git/{code}.git/…`를 맞추는 정규식 그대로 — 코드는 `[^/]+`(탐욕)
static GIT_PATH: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^([^/]+)\.git/(info/refs|git-upload-pack|git-receive-pack)$").expect("git 경로")
});

/// 파이썬 `_SERVICES` — 옛 「dumb」 프로토콜은 받지 않는다
const SERVICES: [&str; 2] = ["git-upload-pack", "git-receive-pack"];

/// http-backend `hdr_nocache` — 캐시하지 말라는 머리 셋
fn nocache(h: &mut HeaderMap) {
    h.insert(
        header::EXPIRES,
        HeaderValue::from_static("Fri, 01 Jan 1980 00:00:00 GMT"),
    );
    h.insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
    h.insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-cache, max-age=0, must-revalidate"),
    );
}

/// 401 + WWW-Authenticate — 없으면 git이 비밀번호를 묻지 않고 실패한다 (파이썬 `_challenge` — `Unauthorized.to_dict()`)
fn challenge() -> Response {
    let body = r#"{"type":"urn:syncdoc:unauthorized","title":"unauthorized","status":401,"detail":"git 입구 — 비밀번호 칸에 개인 토큰"}"#;
    let mut resp = Response::new(Body::from(body));
    *resp.status_mut() = StatusCode::UNAUTHORIZED;
    let h = resp.headers_mut();
    h.insert(
        header::WWW_AUTHENTICATE,
        HeaderValue::from_static("Basic realm=\"SyncDoc\""),
    );
    h.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/problem+json"),
    );
    resp
}

/// Basic의 비밀번호 칸이 개인 토큰 — 통과하면 곧바로 커밋한다(사용 흔적·토큰 행 잠금, #318) (파이썬 `_token_user`)
async fn token_user(state: &AppState, headers: &HeaderMap) -> Result<Option<UserRow>, Problem> {
    let value = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if !value
        .get(..6)
        .is_some_and(|p| p.eq_ignore_ascii_case("basic "))
    {
        return Ok(None);
    }
    let engine = base64::engine::GeneralPurpose::new(
        &base64::alphabet::STANDARD,
        base64::engine::GeneralPurposeConfig::new().with_decode_allow_trailing_bits(true),
    );
    let Ok(raw) = engine.decode(value[6..].trim()) else {
        return Ok(None);
    };
    let Ok(decoded) = String::from_utf8(raw) else {
        return Ok(None);
    };
    let token = decoded.split_once(':').map_or("", |(_, t)| t);
    if token.is_empty() {
        return Ok(None);
    }
    let mut tx = state.pool.begin().await?;
    let user = AccountService { db: &mut tx }
        .authenticate_token(token)
        .await?;
    tx.commit().await?;
    Ok(user)
}

/// 인증 → 원본 → 서비스 — 파이썬 `_serve`. `rpc`면 본문을 넘기고, 아니면 광고
async fn serve(
    state: &AppState,
    code: &str,
    service: &str,
    rpc: bool,
    headers: &HeaderMap,
    body: Bytes,
) -> Result<Response, Problem> {
    let Some(user) = token_user(state, headers).await? else {
        return Ok(challenge());
    };
    let origin = {
        let mut c = state.pool.acquire().await?;
        ProjectService {
            db: &mut c,
            repos: &state.repos,
        }
        .server_origin(code, &user)
        .await?
    };
    let protocol = headers
        .get("git-protocol")
        .and_then(|v| v.to_str().ok())
        .filter(|v| !v.is_empty());
    let mut resp = Response::default();
    nocache(resp.headers_mut());
    if !rpc {
        let out = state
            .repos
            .git
            .advertise_refs(&origin, service, protocol)
            .await?;
        set_type(&mut resp, &format!("application/x-{service}-advertisement"));
        *resp.body_mut() = Body::from(out);
        return Ok(resp);
    }
    // http-backend `check_content_type` — 다르면 415와 문장
    let want = format!("application/x-{service}-request");
    let got = headers
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if got != want {
        *resp.status_mut() = StatusCode::UNSUPPORTED_MEDIA_TYPE;
        *resp.body_mut() = Body::from(format!(
            "Expected POST with Content-Type '{want}', but received '{got}' instead.\n"
        ));
        return Ok(resp);
    }
    let encoding = headers
        .get(header::CONTENT_ENCODING)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let input = if matches!(encoding, "gzip" | "x-gzip") {
        let mut out = Vec::new();
        flate2::read::GzDecoder::new(&body[..])
            .read_to_end(&mut out)
            .map_err(|e| Problem::Internal {
                log: format!("git 입구 gzip 본문을 못 풀었다 — {e}"),
            })?;
        out
    } else {
        body.to_vec()
    };
    let out = state
        .repos
        .git
        .service_rpc(&origin, service, input, protocol)
        .await?;
    set_type(&mut resp, &format!("application/x-{service}-result"));
    *resp.body_mut() = Body::from(out);
    if service == "git-receive-pack" {
        // push를 받은 뒤 밀린 커밋을 곧바로 읽는다(SEQ-29) — 배치다, 실패는 폴링이 메운다
        let (state, code) = (state.clone(), code.to_string());
        tokio::spawn(async move {
            if let Err(e) = pipeline::read_pending(&state.pool, &state.repos, &code, &user).await {
                tracing::warn!("git push 처리 실패 code={code} — 폴링이 메운다: {e}");
            }
        });
    }
    Ok(resp)
}

fn set_type(resp: &mut Response, value: &str) {
    if let Ok(v) = HeaderValue::from_str(value) {
        resp.headers_mut().insert(header::CONTENT_TYPE, v);
    }
}

/// SYNC-API-001#GET/git/{code}.git/info/refs
pub async fn info_refs(
    state: &AppState,
    code: &str,
    raw_query: Option<&str>,
    headers: &HeaderMap,
) -> Result<Response, Problem> {
    let q = fastapi::query_params(raw_query);
    let service = fastapi::query_get(&q, "service").unwrap_or("");
    if !SERVICES.contains(&service) {
        return Err(Problem::NotFound {
            resource: "git-service".into(),
            id: serde_json::Value::from(if service.is_empty() { "-" } else { service }),
        });
    }
    serve(state, code, service, false, headers, Bytes::new()).await
}

/// SYNC-API-001#POST/git/{code}.git/git-upload-pack
pub async fn upload_pack(
    state: &AppState,
    code: &str,
    headers: &HeaderMap,
    body: Bytes,
) -> Result<Response, Problem> {
    serve(state, code, "git-upload-pack", true, headers, body).await
}

/// SYNC-API-001#POST/git/{code}.git/git-receive-pack
pub async fn receive_pack(
    state: &AppState,
    code: &str,
    headers: &HeaderMap,
    body: Bytes,
) -> Result<Response, Problem> {
    serve(state, code, "git-receive-pack", true, headers, body).await
}

/// `/git/{*rest}` — 경로를 starlette처럼 갈라 셋 가운데 하나로. 맞는 경로에 다른 메서드면 405, 아니면 404 path
pub async fn git_entrance(
    State(state): State<AppState>,
    method: Method,
    Path(rest): Path<String>,
    RawQuery(raw): RawQuery,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, ApiProblem> {
    let Some(c) = GIT_PATH.captures(&rest) else {
        return Err(ApiProblem(Problem::NotFound {
            resource: "path".into(),
            id: serde_json::Value::from(format!("/git/{rest}")),
        }));
    };
    let code = c[1].to_string();
    let (allowed, r) = match &c[2] {
        "info/refs" => (
            Method::GET,
            if method == Method::GET {
                Some(info_refs(&state, &code, raw.as_deref(), &headers).await)
            } else {
                None
            },
        ),
        "git-upload-pack" => (
            Method::POST,
            if method == Method::POST {
                Some(upload_pack(&state, &code, &headers, body).await)
            } else {
                None
            },
        ),
        _ => (
            Method::POST,
            if method == Method::POST {
                Some(receive_pack(&state, &code, &headers, body).await)
            } else {
                None
            },
        ),
    };
    match r {
        Some(Ok(resp)) => Ok(resp),
        Some(Err(p)) => Err(ApiProblem(p)),
        None => Ok(render(&Problem::MethodNotAllowed {
            method: method.to_string(),
            allow: vec![allowed.to_string()],
        })
        .into_response()),
    }
}
