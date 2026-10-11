//! 2026-07-28 — 핸드셰이크 없는 요청 하나짜리 봉투. mcp 2.2.0 `server/_streamable_http_modern.py`(입구)·
//! `shared/inbound.py`(분류 사다리)·`server/runner.py`(`serve_one`·`modern_error_data`)를 옮겼다 (카드 L18).
//! 요청 하나 → 응답 하나, `Mcp-Session-Id`는 없다. 상태·머리·본문 바이트가 파이썬 판과 같다 —
//! 본문은 `json.dumps(…, separators=(",", ":"))`(ASCII). 처리기가 15초 안에 알림 없이 끝나면 JSON, 아니면 SSE로
//! 바꾸고 15초마다 `: ping`. `subscriptions/listen`은 응답이 곧 알림 흐름이다(첫 프레임 확인, 그 뒤 ping).
//! `Mcp-Param-*` 머리 검증은 옮기지 않는다 — 도구 스키마에 `x-mcp-header`가 없어 파이썬 판도 늘 통과한다.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use axum::body::{Body, Bytes};
use axum::http::{HeaderMap, HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::pycompat::json::{dumps_compact, dumps_str};
use tokio::task::JoinHandle;

use crate::compat::pydantic::{Failure, Opts};
use crate::compat::pyjson::{self, Depth};
use crate::compat::pyvalue::{PyStr, PyValue};
use crate::state::AppState;

use super::decl::decl;
use super::dispatch::{self, ErrData, Outcome};

/// 본문을 `json.loads`로 읽을 때 파이썬 C 재귀가 남긴 깊이 — 파이썬 판 새 프로토콜 입구에서 잰 값.
/// 파이썬은 9987겹부터 Parse error인 때가 많고 가끔 9988겹부터다(같은 프로세스에서도 흔들린다) — 많은 쪽을 따른다
pub const MODERN_JSON_DEPTH: Depth = Depth(9_986);
/// `_SSE_PING_INTERVAL`
const PING: Duration = Duration::from_secs(15);
/// `ListenHandler.max_subscriptions`
const MAX_LISTENS: usize = 1024;

const PROTOCOL_VERSION_KEY: &str = "io.modelcontextprotocol/protocolVersion";
const CLIENT_CAPABILITIES_KEY: &str = "io.modelcontextprotocol/clientCapabilities";
const SUBSCRIPTION_ID_KEY: &str = "io.modelcontextprotocol/subscriptionId";

const PARSE_ERROR: i64 = -32700;
const INVALID_REQUEST: i64 = -32600;
const METHOD_NOT_FOUND: i64 = -32601;
const INVALID_PARAMS: i64 = -32602;
const INTERNAL_ERROR: i64 = -32603;
const HEADER_MISMATCH: i64 = -32020;
const MISSING_REQUIRED_CLIENT_CAPABILITY: i64 = -32021;
const UNSUPPORTED_PROTOCOL_VERSION: i64 = -32022;

/// 열린 듣기 흐름 수
static LISTENS: AtomicUsize = AtomicUsize::new(0);

/// `ERROR_CODE_HTTP_STATUS` — 표에 없으면 200
fn status_of(code: i64) -> StatusCode {
    match code {
        PARSE_ERROR
        | INVALID_REQUEST
        | INVALID_PARAMS
        | HEADER_MISMATCH
        | MISSING_REQUIRED_CLIENT_CAPABILITY
        | UNSUPPORTED_PROTOCOL_VERSION => StatusCode::BAD_REQUEST,
        METHOD_NOT_FOUND => StatusCode::NOT_FOUND,
        _ => StatusCode::OK,
    }
}

/// JSON-RPC 오류 하나 — 파이썬 `ErrorData`
struct Rpc {
    code: i64,
    message: String,
    /// 이미 ASCII JSON인 값
    data: Option<String>,
}

fn rpc(code: i64, message: impl Into<String>) -> Rpc {
    Rpc {
        code,
        message: message.into(),
        data: None,
    }
}

/// id 하나 — 수는 글자 그대로, 글자는 ASCII JSON
fn id_json(id: &PyValue) -> String {
    match id {
        PyValue::Int(i) => i.to_string(),
        PyValue::Str(PyStr::Utf8(s)) => dumps_str(s, true),
        PyValue::Str(s) => s.repr(),
        _ => "null".into(),
    }
}

/// `_write` — 오류는 표의 상태, id가 없으면 끝에 `"id":null`
fn write_error(id: Option<&PyValue>, e: &Rpc) -> Response {
    let data = e
        .data
        .as_ref()
        .map_or(String::new(), |d| format!(",\"data\":{d}"));
    let error = format!(
        "{{\"code\":{},\"message\":{}{data}}}",
        e.code,
        dumps_str(&e.message, true)
    );
    let body = match id {
        Some(id) => format!(
            "{{\"jsonrpc\":\"2.0\",\"id\":{},\"error\":{error}}}",
            id_json(id)
        ),
        None => format!("{{\"jsonrpc\":\"2.0\",\"error\":{error},\"id\":null}}"),
    };
    json_response(status_of(e.code), body)
}

fn json_response(status: StatusCode, body: String) -> Response {
    (status, [(header::CONTENT_TYPE, "application/json")], body).into_response()
}

/// 본문 없는 응답 — starlette `Response(status_code=…)`(종류 머리가 없다)
fn empty(status: StatusCode) -> Response {
    (status, Body::empty()).into_response()
}

/// `_INVALID_BODY`
fn invalid_body() -> Response {
    write_error(
        None,
        &rpc(
            INVALID_REQUEST,
            "Body must be a single JSON-RPC request or notification object",
        ),
    )
}

fn field<'a>(v: &'a PyValue, name: &str) -> Option<&'a PyValue> {
    v.as_dict().and_then(|d| d.get(&PyStr::from(name)))
}

/// starlette `Headers.get` — 같은 이름이면 처음 것, latin-1
fn first(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get(name)
        .map(|v| v.as_bytes().iter().map(|&b| char::from(b)).collect())
}

/// `dict(request.headers)` — 같은 이름이면 뒤의 것
fn last(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get_all(name)
        .iter()
        .next_back()
        .map(|v| v.as_bytes().iter().map(|&b| char::from(b)).collect())
}

/// `unsupported_protocol_version_rejection`
fn unsupported(requested: &str) -> Option<Rpc> {
    let d = decl();
    if d.modern.iter().any(|v| v == requested) {
        return None;
    }
    let supported: Vec<String> = d.modern.iter().map(|v| dumps_str(v, true)).collect();
    Some(Rpc {
        code: UNSUPPORTED_PROTOCOL_VERSION,
        message: "Unsupported protocol version".into(),
        data: Some(format!(
            "{{\"supported\":[{}],\"requested\":{}}}",
            supported.join(","),
            dumps_str(requested, true)
        )),
    })
}

/// `decode_header_value` — `=?base64?…?=`면 정규 base64·UTF-8일 때만 푼다, 아니면 없음
fn decode_header_value(value: Option<String>) -> Option<String> {
    let value = value?;
    let Some(payload) = value
        .strip_prefix("=?base64?")
        .and_then(|r| r.strip_suffix("?="))
    else {
        return Some(value);
    };
    // 파이썬 b64decode(validate=True) — 알파벳 밖·짝 안 맞는 꼴은 없음, 다시 써서 같아야 한다(정규형)
    let decoded = STANDARD.decode(payload.as_bytes()).ok()?;
    if STANDARD.encode(&decoded) != payload {
        return None;
    }
    String::from_utf8(decoded).ok()
}

/// 파이썬 `==` — 머리 글자와 본문 값(글자일 때만 같을 수 있다)
fn same_str(header: Option<&str>, body: Option<&PyValue>) -> bool {
    match (header, body) {
        (None, None) | (None, Some(PyValue::None)) => true,
        (Some(h), Some(PyValue::Str(PyStr::Utf8(b)))) => h == b,
        _ => false,
    }
}

/// `classify_inbound_request` — 사다리. 통과하면 판
fn classify(decoded: &PyValue, headers: &HeaderMap) -> Result<String, Rpc> {
    let meta = field(decoded, "params").and_then(|p| field(p, "_meta"));
    let Some(meta) = meta.filter(|m| matches!(m, PyValue::Dict(_))) else {
        return Err(rpc(
            INVALID_PARAMS,
            format!(
                "params._meta must be an object carrying the required '{PROTOCOL_VERSION_KEY}' and '{CLIENT_CAPABILITIES_KEY}' envelope keys"
            ),
        ));
    };
    let missing: Vec<&str> = [PROTOCOL_VERSION_KEY, CLIENT_CAPABILITIES_KEY]
        .into_iter()
        .filter(|k| field(meta, k).is_none())
        .collect();
    if !missing.is_empty() {
        return Err(rpc(
            INVALID_PARAMS,
            format!(
                "params._meta is missing the required envelope key(s): {}",
                missing.join(", ")
            ),
        ));
    }
    let version = field(meta, PROTOCOL_VERSION_KEY);
    // 머리 줄 — 판·메서드·이름이 본문과 같아야 한다(지원 판 확인보다 먼저)
    let version_header = last(headers, "mcp-protocol-version");
    if version_header.is_none() || !same_str(version_header.as_deref(), version) {
        return Err(rpc(
            HEADER_MISMATCH,
            "mcp-protocol-version header does not match the request envelope's protocol version",
        ));
    }
    let method = field(decoded, "method");
    if !same_str(last(headers, "mcp-method").as_deref(), method) {
        return Err(rpc(
            HEADER_MISMATCH,
            "mcp-method header does not match the request body's method",
        ));
    }
    let name_key = match method {
        Some(PyValue::Str(PyStr::Utf8(m))) => match m.as_str() {
            "tools/call" | "prompts/get" => Some("name"),
            "resources/read" => Some("uri"),
            _ => None,
        },
        _ => None,
    };
    if let Some(key) = name_key {
        let body_value = field(decoded, "params").and_then(|p| field(p, key));
        if body_value.is_some_and(|v| !v.is_none())
            && !same_str(
                decode_header_value(last(headers, "mcp-name")).as_deref(),
                body_value,
            )
        {
            return Err(rpc(
                HEADER_MISMATCH,
                format!("mcp-name header does not match the request body's '{key}' parameter"),
            ));
        }
    }
    let Some(PyValue::Str(PyStr::Utf8(version))) = version else {
        return Err(rpc(
            INVALID_PARAMS,
            "the protocol-version envelope value must be a string",
        ));
    };
    match unsupported(version) {
        Some(e) => Err(e),
        None => Ok(version.clone()),
    }
}

/// `find_duplicated_routing_header` — 머리 줄 차례로 처음 겹친 이름
fn duplicated_routing_header(headers: &HeaderMap) -> Option<&'static str> {
    let mut seen: Vec<&str> = Vec::new();
    for name in headers.iter().map(|(k, _)| k.as_str()) {
        let key = match name {
            "mcp-protocol-version" => "mcp-protocol-version",
            "mcp-method" => "mcp-method",
            "mcp-name" => "mcp-name",
            _ => continue,
        };
        if seen.contains(&key) {
            return Some(key);
        }
        seen.push(key);
    }
    None
}

/// `check_accept_headers` — (json, sse)
fn accepts(headers: &HeaderMap) -> (bool, bool) {
    super::transport::accepts(headers)
}

/// 새 프로토콜 요청 하나 — 인증은 바깥이 이미 했다
pub async fn handle(
    state: &AppState,
    user: Option<&UserRow>,
    method: &Method,
    headers: &HeaderMap,
    bytes: &Bytes,
) -> Response {
    // TransportSecurityMiddleware — POST는 Content-Type부터(DNS 재바인딩 보호는 꺼 둔다)
    if method == Method::POST
        && !first(headers, "content-type")
            .is_some_and(|c| c.to_lowercase().starts_with("application/json"))
    {
        return (
            StatusCode::BAD_REQUEST,
            Body::from("Invalid Content-Type header"),
        )
            .into_response();
    }
    if method != Method::POST {
        // starlette `Response(status_code=405, headers={"Allow": "POST"})` — 본문·종류 머리 없음, problem으로 바꾸지 않는다
        let mut resp = (
            StatusCode::METHOD_NOT_ALLOWED,
            [(header::ALLOW, "POST")],
            Body::empty(),
        )
            .into_response();
        resp.extensions_mut().insert(crate::web::problem::Bare405);
        return resp;
    }
    let (json, sse) = accepts(headers);
    if !json || !sse {
        return empty(StatusCode::NOT_ACCEPTABLE);
    }
    let Ok(decoded) = pyjson::loads_bytes(bytes, MODERN_JSON_DEPTH) else {
        return write_error(None, &rpc(PARSE_ERROR, "Parse error"));
    };
    let d = decl();
    let opts = Opts::default();
    // 알림 꼴 — `id`가 없는 객체: 받고 버린다(판만 본다)
    if let PyValue::Dict(o) = &decoded
        && o.get(&PyStr::from("id")).is_none()
    {
        if d.notification_modern.validate(&decoded, opts).is_err() {
            return invalid_body();
        }
        let requested = first(headers, "mcp-protocol-version").unwrap_or_default();
        if let Some(e) = unsupported(&requested) {
            return write_error(None, &e);
        }
        return empty(StatusCode::ACCEPTED);
    }
    let req = match d.request_modern.validate(&decoded, opts) {
        Ok(r) => r,
        Err(Failure::Invalid(_) | Failure::Exception(_)) => return invalid_body(),
    };
    let id = field(&req, "id").cloned().unwrap_or(PyValue::None);
    let rpc_method = match field(&req, "method") {
        Some(PyValue::Str(PyStr::Utf8(m))) => m.clone(),
        _ => String::new(),
    };
    if let Some(dup) = duplicated_routing_header(headers) {
        return write_error(
            Some(&id),
            &rpc(
                HEADER_MISMATCH,
                format!("{dup} header appears more than once"),
            ),
        );
    }
    let version = match classify(&decoded, headers) {
        Ok(v) => v,
        Err(e) => return write_error(Some(&id), &e),
    };
    let params = field(&req, "params").filter(|p| !p.is_none()).cloned();
    run(state, user, id, rpc_method, params, version).await
}

/// 놓이면 작업을 끝낸다 — 받는 쪽이 끊기면 처리기도 멈춘다(`watch_disconnect`)
struct AbortOnDrop<T>(JoinHandle<T>);

impl<T> Drop for AbortOnDrop<T> {
    fn drop(&mut self) {
        self.0.abort();
    }
}

/// 처리기를 따로 띄우고 15초 기다린다 — 알림 없이 끝나면 JSON, 아니면 SSE
async fn run(
    state: &AppState,
    user: Option<&UserRow>,
    id: PyValue,
    method: String,
    params: Option<PyValue>,
    version: String,
) -> Response {
    let (state2, user2) = (state.clone(), user.cloned());
    let task = tokio::spawn(async move {
        dispatch::dispatch(&state2, user2.as_ref(), &method, params.as_ref(), &version).await
    });
    let mut guard = AbortOnDrop(task);
    let outcome = tokio::select! {
        done = &mut guard.0 => Some(done),
        () = tokio::time::sleep(PING) => None,
    };
    match outcome {
        Some(Ok(Outcome::Listen(honored))) => listen(&id, &honored),
        Some(Ok(o)) => {
            let (status, body) = reply(&id, o);
            json_response(status, body)
        }
        Some(Err(_)) => write_error(Some(&id), &rpc(INTERNAL_ERROR, "Internal server error")),
        // 조용히 15초를 넘겼다 — SSE로 바꾸고 ping, 끝나면 마지막 사건
        None => late(id, guard),
    }
}

/// `modern_error_data` — 처리기의 그 밖의 예외(파이썬 `code=0` 자리)는 INTERNAL_ERROR
fn reply(id: &PyValue, outcome: Outcome) -> (StatusCode, String) {
    let id = id_json(id);
    match outcome {
        Outcome::Ok(result) => (
            StatusCode::OK,
            format!("{{\"jsonrpc\":\"2.0\",\"id\":{id},\"result\":{result}}}"),
        ),
        Outcome::Listen(_) => (StatusCode::OK, String::new()),
        Outcome::Err {
            code,
            message,
            data,
        } => {
            let (code, message, data) = if code == 0 {
                (
                    INTERNAL_ERROR,
                    "Internal server error".to_string(),
                    ErrData::Unset,
                )
            } else {
                (code, message, data)
            };
            let data = match data {
                ErrData::Unset => String::new(),
                ErrData::Str(s) => format!(",\"data\":{}", dumps_str(&s, true)),
                ErrData::Json(j) => {
                    let v: serde_json::Value =
                        serde_json::from_str(&j).unwrap_or(serde_json::Value::Null);
                    format!(",\"data\":{}", dumps_compact(&v, true))
                }
            };
            (
                status_of(code),
                format!(
                    "{{\"jsonrpc\":\"2.0\",\"id\":{id},\"error\":{{\"code\":{code},\"message\":{}{data}}}}}",
                    dumps_str(&message, true)
                ),
            )
        }
    }
}

/// `_sse_event` — `event: message\r\ndata: …\r\n\r\n`
fn sse_event(json: &str) -> Bytes {
    Bytes::from(format!("event: message\r\ndata: {json}\r\n\r\n"))
}

fn ping() -> Bytes {
    Bytes::from_static(b": ping\r\n\r\n")
}

fn sse_response(body: Body) -> Response {
    let mut resp = (StatusCode::OK, body).into_response();
    let h = resp.headers_mut();
    h.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    h.insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-cache, no-transform"),
    );
    h.insert(header::CONNECTION, HeaderValue::from_static("keep-alive"));
    h.insert("x-accel-buffering", HeaderValue::from_static("no"));
    resp
}

/// 15초를 넘긴 처리기 — 곧바로 ping, 그 뒤 15초마다, 끝나면 결과 사건으로 닫는다
fn late(id: PyValue, guard: AbortOnDrop<Outcome>) -> Response {
    enum Step {
        First,
        Wait,
        Done,
    }
    let stream = futures_util::stream::unfold(
        (Step::First, guard, id),
        |(step, mut guard, id)| async move {
            match step {
                Step::First => Some((Ok::<_, std::io::Error>(ping()), (Step::Wait, guard, id))),
                Step::Wait => {
                    tokio::select! {
                        done = &mut guard.0 => {
                            let last = match done {
                                Ok(o) => reply(&id, o).1,
                                Err(_) => reply(&id, Outcome::Err { code: 0, message: String::new(), data: ErrData::Unset }).1,
                            };
                            Some((Ok(sse_event(&last)), (Step::Done, guard, id)))
                        }
                        () = tokio::time::sleep(PING) => Some((Ok(ping()), (Step::Wait, guard, id))),
                    }
                }
                Step::Done => None,
            }
        },
    );
    sse_response(Body::from_stream(stream))
}

/// 열린 듣기 흐름 하나 — 놓이면 수를 줄인다
struct ListenSlot;

impl Drop for ListenSlot {
    fn drop(&mut self) {
        LISTENS.fetch_sub(1, Ordering::SeqCst);
    }
}

/// `ListenHandler` — 상한을 넘으면 오류(확인 전이라 JSON), 아니면 확인 프레임 뒤 15초마다 ping. 사건은 오지 않는다
fn listen(id: &PyValue, honored: &str) -> Response {
    if LISTENS.fetch_add(1, Ordering::SeqCst) >= MAX_LISTENS {
        LISTENS.fetch_sub(1, Ordering::SeqCst);
        return write_error(Some(id), &rpc(INTERNAL_ERROR, "Subscription limit reached"));
    }
    let slot = ListenSlot;
    let ack = format!(
        "{{\"jsonrpc\":\"2.0\",\"method\":\"notifications/subscriptions/acknowledged\",\"params\":{{\"_meta\":{{\"{SUBSCRIPTION_ID_KEY}\":{}}},\"notifications\":{honored}}}}}",
        id_json(id)
    );
    let stream = futures_util::stream::unfold((true, slot, ack), |(first, slot, ack)| async move {
        if first {
            let frame = sse_event(&ack);
            return Some((Ok::<_, std::io::Error>(frame), (false, slot, ack)));
        }
        tokio::time::sleep(PING).await;
        Some((Ok(ping()), (false, slot, ack)))
    });
    sse_response(Body::from_stream(stream))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_value_sentinel() {
        assert_eq!(
            decode_header_value(Some("abc".into())).as_deref(),
            Some("abc")
        );
        assert_eq!(
            decode_header_value(Some("=?base64?6rCA?=".into())).as_deref(),
            Some("가")
        );
        assert_eq!(decode_header_value(Some("=?base64?6rC?=".into())), None);
        assert_eq!(decode_header_value(None), None);
    }

    /// 몸을 사건 조각으로 — 시계를 멈춘 채 다음 조각을 받는다
    async fn frames(resp: Response, n: usize) -> Vec<(u64, String)> {
        use futures_util::StreamExt;
        let t0 = tokio::time::Instant::now();
        let mut body = resp.into_body().into_data_stream();
        let mut out = Vec::new();
        while out.len() < n {
            let Some(Ok(chunk)) = body.next().await else {
                break;
            };
            out.push((
                t0.elapsed().as_secs(),
                String::from_utf8_lossy(&chunk).into_owned(),
            ));
        }
        out
    }

    /// 15초를 넘긴 처리기 — 곧바로 ping, 15초마다 ping, 끝나면 결과 사건으로 닫는다
    #[tokio::test(start_paused = true)]
    async fn late_handler_turns_into_sse_with_pings() {
        let task = tokio::spawn(async {
            tokio::time::sleep(Duration::from_secs(40)).await;
            Outcome::Ok("{}".into())
        });
        let resp = late(PyValue::Int(7.into()), AbortOnDrop(task));
        assert_eq!(resp.headers()["content-type"], "text/event-stream");
        assert_eq!(resp.headers()["cache-control"], "no-cache, no-transform");
        let got = frames(resp, 5).await;
        assert_eq!(
            got,
            [
                (0, ": ping\r\n\r\n".to_string()),
                (15, ": ping\r\n\r\n".to_string()),
                (30, ": ping\r\n\r\n".to_string()),
                (
                    40,
                    "event: message\r\ndata: {\"jsonrpc\":\"2.0\",\"id\":7,\"result\":{}}\r\n\r\n"
                        .to_string()
                ),
            ]
        );
    }

    /// 듣기 — 확인 프레임 뒤 15초마다 ping, 놓으면 자리를 돌려준다
    #[tokio::test(start_paused = true)]
    async fn listen_acks_then_pings() {
        let before = LISTENS.load(Ordering::SeqCst);
        let resp = listen(&PyValue::str("L1"), "{\"toolsListChanged\":true}");
        assert_eq!(LISTENS.load(Ordering::SeqCst), before + 1);
        let got = frames(resp, 3).await;
        assert_eq!(got[0].0, 0);
        assert_eq!(
            got[0].1,
            "event: message\r\ndata: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/subscriptions/acknowledged\",\"params\":{\"_meta\":{\"io.modelcontextprotocol/subscriptionId\":\"L1\"},\"notifications\":{\"toolsListChanged\":true}}}\r\n\r\n"
        );
        assert_eq!(
            (got[1].0, got[2].0, got[1].1.as_str()),
            (15, 30, ": ping\r\n\r\n")
        );
        assert_eq!(
            LISTENS.load(Ordering::SeqCst),
            before,
            "흐름을 놓으면 자리가 돌아온다"
        );
    }

    #[test]
    fn status_table() {
        assert_eq!(status_of(METHOD_NOT_FOUND), StatusCode::NOT_FOUND);
        assert_eq!(status_of(HEADER_MISMATCH), StatusCode::BAD_REQUEST);
        assert_eq!(status_of(INTERNAL_ERROR), StatusCode::OK);
    }
}
