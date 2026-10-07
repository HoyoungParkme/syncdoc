//! problem+json 응답 — SYNC-API-001 2장 · SYNC-STD-004#DEV-5.
//! 파이썬 판 `core/errors.py`·`main.py` 처리기와 같은 바이트: 키 순서 type·title·status·detail(비면 뺌)·확장,
//! 압축한 UTF-8, `Content-Type: application/problem+json`.

use std::any::Any;

use axum::extract::Request;
use axum::http::{HeaderValue, StatusCode, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use serde_json::{Map, Value};
use syncdoc_core::errors::Problem;

/// 처리기가 돌려주는 문제 — core의 `Problem`을 응답으로 (고아 규칙 때문에 감싼다)
pub struct ApiProblem(pub Problem);

impl From<Problem> for ApiProblem {
    fn from(p: Problem) -> Self {
        ApiProblem(p)
    }
}

impl IntoResponse for ApiProblem {
    fn into_response(self) -> Response {
        render(&self.0)
    }
}

/// 문제 → 응답. `internal`은 로그 문장을 로그로 보낸다 — 본문은 고정 문구
pub fn render(p: &Problem) -> Response {
    if let Problem::Internal { log } = p {
        tracing::error!("{log}");
    }
    let mut body = Map::new();
    let kind = p
        .kind()
        .map_or_else(|| "about:blank".to_string(), |k| format!("urn:syncdoc:{k}"));
    body.insert("type".into(), Value::from(kind));
    body.insert("title".into(), Value::from(p.title()));
    body.insert("status".into(), Value::from(p.status()));
    if let Some(d) = p.detail().filter(|d| !d.is_empty()) {
        body.insert("detail".into(), Value::from(d));
    }
    for (k, v) in p.extras() {
        body.insert(k.into(), v);
    }
    let bytes = serde_json::to_vec(&Value::Object(body)).unwrap_or_default();
    let status = StatusCode::from_u16(p.status()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    let mut resp = (
        status,
        [(header::CONTENT_TYPE, "application/problem+json")],
        bytes,
    )
        .into_response();
    if let Problem::MethodNotAllowed { allow, .. } = p
        && let Ok(v) = HeaderValue::from_str(&allow.join(", "))
    {
        resp.headers_mut().insert(header::ALLOW, v);
    }
    resp
}

/// `allow`에 싣는 메서드 — 이 순서로 (파이썬 판 main.py `_METHODS`)
const METHODS: [&str; 5] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

/// 405 — 라우터가 낸 빈 405를 problem으로. `allow`는 그 경로가 받는 것 가운데 METHODS만(HEAD는 뺀다)
pub async fn method_not_allowed(req: Request, next: Next) -> Response {
    let method = req.method().to_string();
    let resp = next.run(req).await;
    if resp.status() != StatusCode::METHOD_NOT_ALLOWED
        || resp.headers().contains_key(header::CONTENT_TYPE)
    {
        return resp;
    }
    let given: Vec<String> = resp
        .headers()
        .get(header::ALLOW)
        .and_then(|v| v.to_str().ok())
        .map(|v| v.split(',').map(|m| m.trim().to_string()).collect())
        .unwrap_or_default();
    let allow = METHODS
        .iter()
        .filter(|m| given.iter().any(|g| g == *m))
        .map(|m| (*m).to_string())
        .collect();
    render(&Problem::MethodNotAllowed { method, allow })
}

/// 처리기 패닉 → 500 `internal` (파이썬 판은 처리하지 못한 예외를 internal로)
pub fn panic_response(err: Box<dyn Any + Send + 'static>) -> Response {
    let msg = err
        .downcast_ref::<String>()
        .cloned()
        .or_else(|| err.downcast_ref::<&str>().map(|s| (*s).to_string()))
        .unwrap_or_default();
    render(&Problem::Internal {
        log: format!("처리기 패닉 — {msg}"),
    })
}
