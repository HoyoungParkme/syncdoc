//! SSE 포장 — SYNC-API-001 3.4·3.6 질문 스트림 (파이썬 판 `web/sse.py`, 카드 L14).
//! 경로 둘(문서에 묻기·코드에 묻기)이 같이 쓴다. 프레임은 `event: {이름}\ndata: {JSON}\n\n` — JSON은 파이썬
//! `json.dumps(…, ensure_ascii=False)` 꼴. 시작 전 실패는 처리기가 상태 코드로, 뒤의 실패는 `error` 프레임

use axum::body::{Body, Bytes};
use axum::http::{StatusCode, header};
use axum::response::{IntoResponse, Response};
use futures_util::stream;
use serde_json::{Value, json};
use syncdoc_core::pycompat::json::dumps;
use syncdoc_core::types::{AskEvent, AskStream};

use crate::web::problem::problem_map;

fn frame(name: &str, data: &Value) -> String {
    format!("event: {name}\ndata: {}\n\n", dumps(data, false))
}

/// 이벤트 → 프레임 (파이썬 `event`) — 키 차례는 응답 모델의 것
fn event(ev: &AskEvent) -> String {
    match ev {
        AskEvent::Start {
            doc_id,
            item_id,
            key,
        } => frame(
            "start",
            &json!({"doc_id": doc_id, "item_id": item_id, "key": key}),
        ),
        AskEvent::Delta(text) => frame("delta", &json!({"text": text})),
        AskEvent::Note(text) => frame("note", &json!({"text": text})),
        AskEvent::Read { tool, target } => frame("read", &json!({"tool": tool, "target": target})),
        AskEvent::Answer {
            answer,
            context_item_ids,
            missing_refs,
        } => frame(
            "answer",
            &json!({"answer": answer, "context_item_ids": context_item_ids,
                "missing_refs": missing_refs}),
        ),
    }
}

/// 통로 → 스트림 응답 (파이썬 `stream`) — 실패는 `error` 프레임
pub fn stream(rx: AskStream) -> Response {
    let frames = stream::unfold(rx, |mut rx| async move {
        let item = rx.recv().await?;
        let text = match item {
            Ok(ev) => event(&ev),
            Err(p) => frame("error", &Value::Object(problem_map(&p))),
        };
        Some((Ok::<_, std::convert::Infallible>(Bytes::from(text)), rx))
    });
    (
        StatusCode::OK,
        [
            (header::CONTENT_TYPE, "text/event-stream; charset=utf-8"),
            (header::CACHE_CONTROL, "no-cache"),
            (header::HeaderName::from_static("x-accel-buffering"), "no"),
        ],
        Body::from_stream(frames),
    )
        .into_response()
}

/// 질문 본문의 값 — `question`·`conversation_id`·선택 글자 하나(`item_id`·`key`)·`attachment_ids`.
/// 파이썬 정수는 `i64`로 접는다(그 밖은 어느 행과도 같지 않다 — 대화 id는 int4 밖에서 500)
pub struct AskBody {
    pub question: String,
    pub conversation_id: i64,
    pub hint: Option<String>,
    pub attachment_ids: Vec<i64>,
}

fn clamp(i: &num_bigint::BigInt) -> i64 {
    i64::try_from(i).unwrap_or(if i.sign() == num_bigint::Sign::Minus {
        i64::MIN
    } else {
        i64::MAX
    })
}

/// 검증을 지난 요청 모델 → 값
pub fn ask_body(req: &crate::compat::pyvalue::PyValue, hint: &str) -> AskBody {
    use crate::compat::pyvalue::{PyStr, PyValue};
    let get = |k: &str| req.as_dict().and_then(|d| d.get(&PyStr::from(k)));
    let text = |v: Option<&PyValue>| match v {
        Some(PyValue::Str(PyStr::Utf8(s))) => Some(s.clone()),
        Some(PyValue::Str(s)) => Some(s.repr()),
        _ => None,
    };
    AskBody {
        question: text(get("question")).unwrap_or_default(),
        conversation_id: match get("conversation_id") {
            Some(PyValue::Int(i)) => clamp(i),
            _ => 0,
        },
        hint: text(get(hint)),
        attachment_ids: match get("attachment_ids") {
            Some(PyValue::List(a)) => a
                .iter()
                .filter_map(|v| match v {
                    PyValue::Int(i) => Some(clamp(i)),
                    _ => None,
                })
                .collect(),
            _ => Vec::new(),
        },
    }
}
