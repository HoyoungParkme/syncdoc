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
use syncdoc_core::pycompat::chars::strip;

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

/// starlette `Headers.get` — 같은 이름이면 처음 것, latin-1로 푼다. 파이썬 판은 이 글자를 CGI 변수로 넘긴다(UTF-8)
fn latin1(headers: &HeaderMap, name: &str) -> String {
    headers
        .get(name)
        .map(|v| v.as_bytes().iter().map(|&b| char::from(b)).collect())
        .unwrap_or_default()
}

/// Basic의 비밀번호 칸이 개인 토큰 — 통과하면 곧바로 커밋한다(사용 흔적·토큰 행 잠금, #318) (파이썬 `_token_user`).
/// 앞 여섯 글자가 `basic `(대소문자 무시) · 나머지를 파이썬 `str.strip()` · 파이썬 3.12 `b64decode(validate=True)`는
/// 정규 `=`만 받고 남는 비트는 받는다 · UTF-8이 아니거나 `:`가 없거나 토큰이 비면 없는 것
async fn token_user(state: &AppState, headers: &HeaderMap) -> Result<Option<UserRow>, Problem> {
    let value = latin1(headers, "authorization");
    let mut chars = value.chars();
    let prefix: String = chars.by_ref().take(6).collect();
    if !prefix.eq_ignore_ascii_case("basic ") {
        return Ok(None);
    }
    let rest: String = chars.collect();
    let engine = base64::engine::GeneralPurpose::new(
        &base64::alphabet::STANDARD,
        base64::engine::GeneralPurposeConfig::new().with_decode_allow_trailing_bits(true),
    );
    let Ok(raw) = engine.decode(strip(&rest)) else {
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
    let protocol = Some(latin1(headers, "git-protocol")).filter(|v| !v.is_empty());
    if !rpc {
        let out = state
            .repos
            .git
            .advertise_refs(&origin, service, protocol.as_deref())
            .await?;
        return Ok(reply(
            StatusCode::OK,
            Some(&format!("application/x-{service}-advertisement")),
            out,
        ));
    }
    let resp = rpc_reply(state, &origin, service, headers, body, protocol.as_deref()).await?;
    if service == "git-receive-pack" {
        // 응답이 무엇이든(415·깨진 gzip까지) 밀린 커밋을 곧바로 읽는다 — 파이썬 판 `BackgroundTask` 자리(SEQ-29).
        // 배치다, 실패는 폴링이 메운다
        let (state, code) = (state.clone(), code.to_string());
        tokio::spawn(async move {
            if let Err(e) = pipeline::read_pending(&state.pool, &state.repos, &code, &user).await {
                tracing::warn!("git push 처리 실패 code={code} — 폴링이 메운다: {e}");
            }
        });
    }
    Ok(resp)
}

/// http-backend `service_rpc` — Content-Type이 다르면 415와 문장, gzip이면 풀어 서비스에 넘긴다
async fn rpc_reply(
    state: &AppState,
    origin: &std::path::Path,
    service: &str,
    headers: &HeaderMap,
    body: Bytes,
    protocol: Option<&str>,
) -> Result<Response, Problem> {
    // http-backend `check_content_type` — 머리 글자 그대로(파이썬 판이 latin-1로 읽어 UTF-8로 넘긴다)
    let want = format!("application/x-{service}-request");
    let got = latin1(headers, "content-type");
    if got != want {
        let text =
            format!("Expected POST with Content-Type '{want}', but received '{got}' instead.\n");
        return Ok(reply(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            None,
            text.into_bytes(),
        ));
    }
    let result = format!("application/x-{service}-result");
    let input = if matches!(
        latin1(headers, "content-encoding").as_str(),
        "gzip" | "x-gzip"
    ) {
        let mut out = Vec::new();
        if let Err(e) = flate2::read::GzDecoder::new(&body[..]).read_to_end(&mut out) {
            // http-backend는 `die`하고 자식도 함께 끝난다 — 머리는 이미 나갔고 본문은 빈다
            tracing::warn!("git 입구 gzip 본문을 못 풀었다 — {e}");
            return Ok(reply(StatusCode::OK, Some(&result), Vec::new()));
        }
        out
    } else {
        body.to_vec()
    };
    let out = state
        .repos
        .git
        .service_rpc(origin, service, input, protocol)
        .await?;
    Ok(reply(StatusCode::OK, Some(&result), out))
}

/// http-backend의 응답 — 캐시 막는 머리 셋과 (있으면) Content-Type
fn reply(status: StatusCode, content_type: Option<&str>, body: Vec<u8>) -> Response {
    let mut resp = Response::new(Body::from(body));
    *resp.status_mut() = status;
    nocache(resp.headers_mut());
    if let Some(v) = content_type.and_then(|t| HeaderValue::from_str(t).ok()) {
        resp.headers_mut().insert(header::CONTENT_TYPE, v);
    }
    resp
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
