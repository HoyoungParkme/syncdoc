//! `/mcp` 전송 — mcp 2.2.0 `streamable_http_manager.py`(세션 없음)·`streamable_http.py`·
//! `transport_security.py`(본문 4MiB·Content-Type)와 sse-starlette 3.4.11의 응답 꼴을 옮겼다.
//! 상태 코드·머리·본문 바이트가 파이썬 판과 같다 — SSE는 `event: message\r\ndata: …\r\n\r\n`.

use std::time::Duration;

use axum::body::{Body, Bytes};
use axum::extract::Request;
use axum::http::{HeaderMap, HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use futures_util::stream;
use jiter::JsonValue;

use crate::compat::pydantic::{Failure, Opts};
use crate::compat::pyvalue::{PyStr, PyValue};

use super::decl::decl;
use super::dispatch::{self, ErrData, Outcome};

/// `DEFAULT_MAX_REQUEST_BODY_SIZE` — 4MiB
const MAX_BODY: usize = 4 * 1024 * 1024;
/// sse-starlette `DEFAULT_PING_INTERVAL`
const PING: Duration = Duration::from_secs(15);

/// starlette `Headers.get` — 같은 이름이면 처음 것, latin-1로 푼다
fn first(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get(name)
        .map(|v| v.as_bytes().iter().map(|&b| char::from(b)).collect())
}

/// 파이썬 `str.strip()`
fn py_strip(s: &str) -> &str {
    s.trim_matches(|c: char| {
        matches!(
            c,
            '\t' | '\n' | '\u{0b}' | '\u{0c}' | '\r' | '\u{1c}'
                ..='\u{1f}' | ' ' | '\u{85}' | '\u{a0}'
        )
    })
}

fn plain(status: StatusCode, text: &'static str) -> Response {
    (status, Body::from(text)).into_response()
}

/// `_create_error_response` — JSON-RPC 오류(id 없음)
fn rpc_error(status: StatusCode, code: i64, message: &str) -> Response {
    let body = format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":null,\"error\":{{\"code\":{code},\"message\":{}}}}}",
        serde_json::to_string(message).unwrap_or_default()
    );
    (status, [(header::CONTENT_TYPE, "application/json")], body).into_response()
}

/// `check_accept_headers` — (json, sse)
fn accepts(headers: &HeaderMap) -> (bool, bool) {
    let accept = first(headers, "accept").unwrap_or_default();
    let types: Vec<String> = accept
        .split(',')
        .map(|m| py_strip(py_strip(m).split(';').next().unwrap_or("")).to_lowercase())
        .collect();
    let wild = types.iter().any(|t| t == "*/*");
    let json = wild
        || types
            .iter()
            .any(|t| t == "application/json" || t == "application/*");
    let sse = wild
        || types
            .iter()
            .any(|t| t == "text/event-stream" || t == "text/*");
    (json, sse)
}

/// `/mcp` 처리 — 인증은 바깥(`auth::bearer`)이 이미 했다
pub async fn handle(req: Request) -> Response {
    let (parts, body) = req.into_parts();
    let headers = parts.headers;
    // RequestBodyLimitMiddleware — 선언한 길이부터, 그다음 읽으며
    if let Some(n) = first(&headers, "content-length").and_then(|v| v.trim().parse::<u64>().ok())
        && n > MAX_BODY as u64
    {
        return plain(StatusCode::PAYLOAD_TOO_LARGE, "Request body too large");
    }
    let Ok(bytes) = axum::body::to_bytes(body, MAX_BODY).await else {
        return plain(StatusCode::PAYLOAD_TOO_LARGE, "Request body too large");
    };
    let hint = first(&headers, "mcp-protocol-version");
    if let Some(v) = &hint
        && !decl().handshake.contains(v)
    {
        return modern(&parts.method, &bytes);
    }
    match parts.method {
        Method::POST => post(&headers, &bytes, hint.as_deref()),
        Method::GET => get(&headers),
        Method::DELETE => rpc_error(
            StatusCode::METHOD_NOT_ALLOWED,
            -32600,
            "Method Not Allowed: Session termination not supported",
        ),
        _ => rpc_error(StatusCode::METHOD_NOT_ALLOWED, -32600, "Method Not Allowed"),
    }
}

fn post(headers: &HeaderMap, bytes: &Bytes, hint: Option<&str>) -> Response {
    // TransportSecurityMiddleware — POST는 Content-Type을 먼저 본다(소문자로 application/json 시작)
    let ct = first(headers, "content-type");
    if !ct
        .as_ref()
        .is_some_and(|c| c.to_lowercase().starts_with("application/json"))
    {
        return plain(StatusCode::BAD_REQUEST, "Invalid Content-Type header");
    }
    let (json, sse) = accepts(headers);
    if !(json && sse) {
        return rpc_error(
            StatusCode::NOT_ACCEPTABLE,
            -32600,
            "Not Acceptable: Client must accept both application/json and text/event-stream",
        );
    }
    let ct = ct.unwrap_or_default();
    let ok_type = ct
        .split(';')
        .next()
        .unwrap_or("")
        .split(',')
        .any(|p| py_strip(p) == "application/json");
    if !ok_type {
        return rpc_error(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            -32600,
            "Unsupported Media Type: Content-Type must be application/json",
        );
    }
    let raw = match JsonValue::parse(bytes, true) {
        Ok(v) => PyValue::from_jiter(&v),
        Err(e) => {
            return rpc_error(
                StatusCode::BAD_REQUEST,
                -32700,
                &format!("Parse error: {}", e.description(bytes)),
            );
        }
    };
    let d = decl();
    let (kind, msg) = match d.envelope.validate_union(
        &raw,
        Opts {
            by_name: Some(false),
            ..Opts::default()
        },
    ) {
        Ok(r) => r,
        Err(Failure::Invalid(e)) => {
            return rpc_error(
                StatusCode::BAD_REQUEST,
                -32602,
                &format!("Validation error: {}", e.display(&d.url_prefix)),
            );
        }
        Err(Failure::Exception(_)) => {
            return rpc_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                -32603,
                "Error handling POST request",
            );
        }
    };
    // 요청이 아닌 것(알림·응답·오류)은 202로 받고 끝
    if kind != 0 {
        return (
            StatusCode::ACCEPTED,
            [(header::CONTENT_TYPE, "application/json")],
            Body::empty(),
        )
            .into_response();
    }
    let field = |name: &str| {
        msg.as_dict()
            .and_then(|m| m.get(&PyStr::from(name)))
            .cloned()
    };
    let id = field("id").unwrap_or(PyValue::None);
    let method = match field("method") {
        Some(PyValue::Str(PyStr::Utf8(m))) => m,
        _ => String::new(),
    };
    let params = field("params").filter(|p| !p.is_none());
    let version = hint.map_or_else(|| d.default_negotiated.clone(), str::to_string);
    let outcome = dispatch::dispatch(&method, params.as_ref(), &version);
    sse_message(&envelope(&id, outcome))
}

/// JSON-RPC 응답 — `model_dump_json(by_alias=True, exclude_unset=True)`
fn envelope(id: &PyValue, outcome: Outcome) -> String {
    let id = match id {
        PyValue::Int(i) => i.to_string(),
        PyValue::Str(PyStr::Utf8(s)) => serde_json::to_string(s).unwrap_or_default(),
        _ => "null".into(),
    };
    match outcome {
        Outcome::Ok(result) => format!("{{\"jsonrpc\":\"2.0\",\"id\":{id},\"result\":{result}}}"),
        Outcome::Err {
            code,
            message,
            data,
        } => {
            let data = match data {
                ErrData::Unset => String::new(),
                ErrData::Str(s) => format!(
                    ",\"data\":{}",
                    serde_json::to_string(&s).unwrap_or_default()
                ),
                ErrData::Json(j) => format!(",\"data\":{j}"),
            };
            format!(
                "{{\"jsonrpc\":\"2.0\",\"id\":{id},\"error\":{{\"code\":{code},\"message\":{}{data}}}}}",
                serde_json::to_string(&message).unwrap_or_default()
            )
        }
    }
}

fn sse_headers(resp: &mut Response) {
    let h = resp.headers_mut();
    h.insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-cache, no-transform"),
    );
    h.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    h.insert("x-accel-buffering", HeaderValue::from_static("no"));
}

/// 사건 하나 — sse-starlette `ServerSentEvent(event="message", data=…)`. 데이터의 줄바꿈은 `data:` 줄로 나눈다
fn sse_message(data: &str) -> Response {
    let mut body = String::from("event: message\r\n");
    for line in split_lines(data) {
        body.push_str("data: ");
        body.push_str(line);
        body.push_str("\r\n");
    }
    body.push_str("\r\n");
    let mut resp = (StatusCode::OK, Body::from(body)).into_response();
    sse_headers(&mut resp);
    resp
}

/// `re.split(r"\r\n|\r|\n")`
fn split_lines(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    let b = s.as_bytes();
    let mut i = 0;
    while i < b.len() {
        match b[i] {
            b'\r' => {
                out.push(&s[start..i]);
                i += if b.get(i + 1) == Some(&b'\n') { 2 } else { 1 };
                start = i;
            }
            b'\n' => {
                out.push(&s[start..i]);
                i += 1;
                start = i;
            }
            _ => i += 1,
        }
    }
    out.push(&s[start..]);
    out
}

/// GET — 서버가 먼저 보낼 것을 흘리는 SSE. 세션이 없어 보낼 것이 없다 — 15초마다 ping만
fn get(headers: &HeaderMap) -> Response {
    let (_, sse) = accepts(headers);
    if !sse {
        return rpc_error(
            StatusCode::NOT_ACCEPTABLE,
            -32600,
            "Not Acceptable: Client must accept text/event-stream",
        );
    }
    // Last-Event-ID — 이벤트 저장소가 없어 아무 응답도 쓰지 않는다 → uvicorn의 500
    if first(headers, "last-event-id").is_some_and(|v| !v.is_empty()) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            [(header::CONTENT_TYPE, "text/plain; charset=utf-8")],
            "Internal Server Error",
        )
            .into_response();
    }
    let pings = stream::unfold((), |()| async {
        tokio::time::sleep(PING).await;
        let now = time::OffsetDateTime::now_utc();
        let line = format!(": ping - {}\r\n\r\n", py_utc(now));
        Some((Ok::<_, std::io::Error>(Bytes::from(line)), ()))
    });
    let mut resp = (StatusCode::OK, Body::from_stream(pings)).into_response();
    sse_headers(&mut resp);
    resp
}

/// 파이썬 `str(datetime.now(timezone.utc))` — `2026-10-08 00:13:02.123456+00:00`(μs가 0이면 뺀다)
fn py_utc(t: time::OffsetDateTime) -> String {
    let micro = t.microsecond();
    let frac = if micro == 0 {
        String::new()
    } else {
        format!(".{micro:06}")
    };
    format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02}{frac}+00:00",
        t.year(),
        u8::from(t.month()),
        t.day(),
        t.hour(),
        t.minute(),
        t.second()
    )
}

/// 2026-07-28 새 프로토콜 — 카드 L18까지 계약 밖. 파이썬 판이 핸드셰이크 꼴 요청에 내는 거절만 흉내 낸다
fn modern(method: &Method, bytes: &Bytes) -> Response {
    if method != Method::POST {
        return rpc_error(
            StatusCode::BAD_REQUEST,
            -32600,
            "Bad Request: Unsupported protocol version",
        );
    }
    let id = JsonValue::parse(bytes, true)
        .ok()
        .and_then(|v| match v {
            JsonValue::Object(o) => o
                .iter()
                .rev()
                .find(|(k, _)| k == "id")
                .map(|(_, v)| match v {
                    JsonValue::Int(i) => i.to_string(),
                    JsonValue::Str(s) => serde_json::to_string(s.as_ref()).unwrap_or_default(),
                    _ => "null".into(),
                }),
            _ => None,
        })
        .unwrap_or_else(|| "null".into());
    let body = format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":{id},\"error\":{{\"code\":-32602,\"message\":\"params._meta must be an object carrying the required 'io.modelcontextprotocol/protocolVersion' and 'io.modelcontextprotocol/clientCapabilities' envelope keys\"}}}}"
    );
    (
        StatusCode::BAD_REQUEST,
        [(header::CONTENT_TYPE, "application/json")],
        body,
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_like_sse_starlette() {
        assert_eq!(split_lines("a\r\nb\rc\nd"), vec!["a", "b", "c", "d"]);
        assert_eq!(split_lines("{}"), vec!["{}"]);
    }

    #[test]
    fn ping_time_like_python() {
        let t = time::macros::datetime!(2026-10-08 00:13:02.123456 UTC);
        assert_eq!(py_utc(t), "2026-10-08 00:13:02.123456+00:00");
        let t = time::macros::datetime!(2026-10-08 00:13:02 UTC);
        assert_eq!(py_utc(t), "2026-10-08 00:13:02+00:00");
    }
}
