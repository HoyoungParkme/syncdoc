//! llm 어댑터 — 모델 호출 (SYNC-MS-020 · SYNC-DOM-004 4.9, 카드 L14). 파이썬 판 `infra/llm.py`와 같은 요청 본문·파싱·오류 접기.
//! OpenAI 호환 Chat Completions 하나(INFRA 5.3). 와이어 형식(`content`·`function.arguments`)은 여기만 안다.
//! 루프는 부르는 쪽(`queries.ask_item`)이 돈다

use std::collections::BTreeMap;
use std::time::Duration;

use base64::Engine;
use futures_util::StreamExt;
use serde_json::{Map, Value, json};

use crate::errors::Problem;
use crate::pycompat::chars::strip;
use crate::pycompat::json::dumps;
use crate::types::{LlmMessage, LlmStep, LlmUsage, ToolCall, ToolSpec};

/// 초 — 모델이 느려도 요청 하나가 앱을 붙들지 않게(파이썬 `httpx` `timeout=60`)
const TIMEOUT: Duration = Duration::from_secs(60);

/// 모델 — 설정 파일의 `LLM_API_URL`·`LLM_API_KEY`·`LLM_MODEL`
#[derive(Clone, Debug, Default)]
pub struct Llm {
    pub url: String,
    pub key: String,
    pub model: String,
}

fn unavailable(reason: &str) -> Problem {
    Problem::LlmUnavailable {
        reason: reason.to_string(),
    }
}

/// 우리 대화록 항목 → OpenAI 호환 메시지 (파이썬 `_wire`)
fn wire(m: &LlmMessage) -> Value {
    match m {
        LlmMessage::Tool { tool_call_id, text } => {
            json!({"role": "tool", "tool_call_id": tool_call_id, "content": text})
        }
        LlmMessage::Text { role, text, images } => {
            if *role == "user" && !images.is_empty() {
                // 이 턴에 붙인 이미지 — content 파트 배열(vision). 뒤 턴에는 안 실린다
                let mut parts = vec![json!({"type": "text", "text": text})];
                for (mime, data) in images {
                    let b64 = base64::engine::general_purpose::STANDARD.encode(data);
                    parts.push(json!({"type": "image_url",
                        "image_url": {"url": format!("data:{mime};base64,{b64}")}}));
                }
                return json!({"role": role, "content": parts});
            }
            // 빈 글은 None → 도구 호출이 없으면 ""
            json!({"role": role, "content": text})
        }
        LlmMessage::Calls { text, tool_calls } => {
            let calls: Vec<Value> = tool_calls
                .iter()
                .map(|c| {
                    json!({"id": c.id, "type": "function", "function": {"name": c.name,
                        "arguments": dumps(&Value::Object(c.arguments.clone()), true)}})
                })
                .collect();
            let content = if text.is_empty() {
                Value::Null
            } else {
                Value::from(text.as_str())
            };
            if calls.is_empty() {
                let content = if content.is_null() {
                    Value::from("")
                } else {
                    content
                };
                return json!({"role": "assistant", "content": content});
            }
            json!({"role": "assistant", "content": content, "tool_calls": calls})
        }
    }
}

/// 토큰 수 — 없으면 0 (파이썬 `_usage`)
fn usage_of(u: Option<&Value>) -> Result<LlmUsage, Problem> {
    let int = |k: &str| -> Result<i64, Problem> {
        match u.and_then(|u| u.get(k)) {
            None | Some(Value::Null) => Ok(0),
            Some(Value::Number(n)) => n
                .as_i64()
                .or_else(|| n.as_f64().map(|f| f.trunc() as i64))
                .ok_or_else(|| unavailable("응답 형식이 다르다")),
            Some(Value::Bool(b)) => Ok(i64::from(*b)),
            Some(Value::String(s)) if s.is_empty() => Ok(0),
            Some(Value::String(s)) => strip(s)
                .parse()
                .map_err(|_| unavailable("응답 형식이 다르다")),
            Some(_) => Err(unavailable("응답 형식이 다르다")),
        }
    };
    Ok(LlmUsage {
        prompt_tokens: int("prompt_tokens")?,
        completion_tokens: int("completion_tokens")?,
    })
}

/// 와이어 tool_calls → ToolCall. arguments가 JSON이 아니거나 객체가 아니면 llm-unavailable (파이썬 `_calls`)
fn calls_of(raw: &[(String, String, String)]) -> Result<Vec<ToolCall>, Problem> {
    let mut out = Vec::new();
    for (id, name, arguments) in raw {
        let text = if arguments.is_empty() {
            "{}"
        } else {
            arguments
        };
        let args: Value =
            serde_json::from_str(text).map_err(|_| unavailable("도구 인자 형식이 다르다"))?;
        let Value::Object(arguments) = args else {
            return Err(unavailable("도구 인자 형식이 다르다"));
        };
        out.push(ToolCall {
            id: id.clone(),
            name: name.clone(),
            arguments,
        });
    }
    Ok(out)
}

/// 단발 응답(choices[0].message) → LlmStep (파이썬 `_single`)
fn single(data: &Value) -> Result<LlmStep, Problem> {
    let bad = || unavailable("응답 형식이 다르다");
    let msg = data
        .get("choices")
        .and_then(|c| c.get(0))
        .and_then(|c| c.get("message"))
        .ok_or_else(bad)?;
    let mut raw = Vec::new();
    match msg.get("tool_calls") {
        None | Some(Value::Null) => {}
        Some(Value::Array(a)) => {
            for c in a {
                let id = c.get("id").and_then(Value::as_str).ok_or_else(bad)?;
                let f = c.get("function").ok_or_else(bad)?;
                let name = f.get("name").and_then(Value::as_str).ok_or_else(bad)?;
                let args = match f.get("arguments") {
                    None | Some(Value::Null) => "",
                    Some(Value::String(s)) => s.as_str(),
                    Some(_) => return Err(bad()),
                };
                raw.push((id.to_string(), name.to_string(), args.to_string()));
            }
        }
        Some(_) => return Err(bad()),
    }
    let tool_calls = calls_of(&raw)?;
    let usage = usage_of(data.get("usage"))?;
    let text = match msg.get("content") {
        Some(Value::String(s)) if !s.is_empty() => Some(s.clone()),
        _ => None,
    };
    Ok(LlmStep {
        text,
        tool_calls,
        usage,
    })
}

/// `httpx`가 내는 오류 종류 이름 — 이유 문장이 된다
fn http_error_name(e: &reqwest::Error) -> &'static str {
    if e.is_connect() && e.is_timeout() {
        "ConnectTimeout"
    } else if e.is_connect() {
        "ConnectError"
    } else if e.is_timeout() {
        "ReadTimeout"
    } else if e.is_body() || e.is_decode() {
        "ReadError"
    } else {
        "HTTPError"
    }
}

/// 한 줄(`data:` 줄) 처리의 상태 — 글자 조각·도구 호출 자리·토큰
#[derive(Default)]
struct Acc {
    parts: Vec<String>,
    slots: BTreeMap<i64, (String, String, String)>,
    usage: LlmUsage,
    done: bool,
}

impl Acc {
    /// `data:` 뒤 하나 — `[DONE]`이면 끝. 글자 조각은 `delta`로
    fn line(&mut self, line: &str, delta: &mut (dyn FnMut(&str) + Send)) -> Result<(), Problem> {
        let Some(rest) = line.strip_prefix("data:") else {
            return Ok(());
        };
        let payload = strip(rest);
        if payload == "[DONE]" {
            self.done = true;
            return Ok(());
        }
        let chunk: Value =
            serde_json::from_str(payload).map_err(|_| unavailable("응답 형식이 다르다"))?;
        if !chunk.is_object() {
            return Err(unavailable("응답 형식이 다르다"));
        }
        if chunk.get("usage").is_some_and(truthy) {
            self.usage = usage_of(chunk.get("usage"))?;
        }
        let choices = match chunk.get("choices") {
            Some(Value::Array(a)) => a.clone(),
            None | Some(Value::Null) => Vec::new(),
            Some(_) => return Err(unavailable("응답 형식이 다르다")),
        };
        for ch in &choices {
            let d = ch.get("delta").filter(|d| truthy(d));
            let Some(d) = d else { continue };
            if let Some(Value::String(c)) = d.get("content")
                && !c.is_empty()
            {
                self.parts.push(c.clone());
                delta(c);
            }
            let tcs = match d.get("tool_calls") {
                Some(Value::Array(a)) => a.clone(),
                _ => Vec::new(),
            };
            for tc in &tcs {
                let idx = match tc.get("index") {
                    Some(Value::Number(n)) => n.as_i64().unwrap_or(0),
                    _ => 0,
                };
                let slot = self.slots.entry(idx).or_default();
                if let Some(Value::String(id)) = tc.get("id")
                    && !id.is_empty()
                {
                    slot.0 = id.clone();
                }
                let f = tc.get("function").cloned().unwrap_or(Value::Null);
                if let Some(Value::String(n)) = f.get("name")
                    && !n.is_empty()
                {
                    slot.1 = n.clone();
                }
                if let Some(Value::String(a)) = f.get("arguments")
                    && !a.is_empty()
                {
                    slot.2.push_str(a);
                }
            }
        }
        Ok(())
    }
}

/// 파이썬 참거짓 — 비면 거짓
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

impl Llm {
    /// 키와 주소가 다 있다
    pub fn enabled(&self) -> bool {
        !self.key.is_empty() && !self.url.is_empty()
    }

    /// 요청 본문 — 도구가 비면 `tools`·`tool_choice`를 싣지 않는다 (파이썬 `_body`)
    fn body(
        &self,
        system: &str,
        messages: &[LlmMessage],
        tools: &[ToolSpec],
        tool_choice: &str,
    ) -> Value {
        let mut msgs = vec![json!({"role": "system", "content": system})];
        msgs.extend(messages.iter().map(wire));
        let mut body = Map::new();
        body.insert("model".into(), Value::from(self.model.as_str()));
        body.insert("messages".into(), Value::Array(msgs));
        if !tools.is_empty() {
            body.insert(
                "tools".into(),
                Value::Array(
                    tools
                        .iter()
                        .map(|t| {
                            json!({"type": "function", "function": {"name": t.name,
                                "description": t.description, "parameters": t.parameters}})
                        })
                        .collect(),
                ),
            );
            body.insert("tool_choice".into(), Value::from(tool_choice));
        }
        Value::Object(body)
    }

    /// SYNC-MS-020#Llm.step_stream
    ///
    /// 스트림으로 한 번 호출한다. 글자 조각을 오는 대로 `delta`로 넘기고 끝의 `LlmStep`을 돌려준다 — 조각은
    /// 화면용이고 `LlmStep`이 진실이다. 스트림을 무시하는 호환 서버면 본문을 JSON 하나로 읽는다
    pub async fn step_stream(
        &self,
        system: &str,
        messages: &[LlmMessage],
        tools: &[ToolSpec],
        tool_choice: &str,
        delta: &mut (dyn FnMut(&str) + Send),
    ) -> Result<LlmStep, Problem> {
        if !self.enabled() {
            return Err(Problem::LlmNotConfigured);
        }
        let mut body = self.body(system, messages, tools, tool_choice);
        if let Value::Object(m) = &mut body {
            m.insert("stream".into(), Value::Bool(true));
            m.insert("stream_options".into(), json!({"include_usage": true}));
        }
        // httpx 0.28 — 짧은 꼴, 유니코드 그대로
        let text =
            serde_json::to_string(&body).map_err(|e| Problem::Internal { log: e.to_string() })?;
        let client = reqwest::Client::builder()
            .connect_timeout(TIMEOUT)
            .read_timeout(TIMEOUT)
            .build()
            .map_err(|e| unavailable(http_error_name(&e)))?;
        let r = client
            .post(&self.url)
            .header("Authorization", format!("Bearer {}", self.key))
            .header("Content-Type", "application/json")
            .body(text)
            .send()
            .await
            .map_err(|e| unavailable(http_error_name(&e)))?;
        if !r.status().is_success() {
            return Err(unavailable(&format!("HTTP {}", r.status().as_u16())));
        }
        let sse = r
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .is_some_and(|v| v.starts_with("text/event-stream"));
        if !sse {
            let bytes = r
                .bytes()
                .await
                .map_err(|e| unavailable(http_error_name(&e)))?;
            let data: Value =
                serde_json::from_slice(&bytes).map_err(|_| unavailable("응답 형식이 다르다"))?;
            return single(&data);
        }
        let mut acc = Acc::default();
        let mut buf: Vec<u8> = Vec::new();
        let mut stream = r.bytes_stream();
        // httpx `aiter_lines` — `\n`·`\r\n`·`\r`에서 끊는다. 끝의 `\r`은 다음 조각을 보고 정한다
        'read: while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|e| unavailable(http_error_name(&e)))?;
            buf.extend_from_slice(&chunk);
            while let Some(pos) = buf.iter().position(|b| *b == b'\n' || *b == b'\r') {
                if buf[pos] == b'\r' && pos + 1 == buf.len() {
                    break; // `\r\n`일 수 있다 — 다음 조각까지
                }
                let line = String::from_utf8_lossy(&buf[..pos]).into_owned();
                let skip = if buf[pos] == b'\r' && buf.get(pos + 1) == Some(&b'\n') {
                    2
                } else {
                    1
                };
                buf.drain(..pos + skip);
                acc.line(&line, delta)?;
                if acc.done {
                    break 'read;
                }
            }
        }
        if !acc.done && !buf.is_empty() {
            let rest = String::from_utf8_lossy(&buf).into_owned();
            let rest = rest.strip_suffix('\r').unwrap_or(&rest).to_string();
            acc.line(&rest, delta)?;
        }
        let raw: Vec<(String, String, String)> = acc.slots.into_values().collect();
        let tool_calls = calls_of(&raw)?;
        let text = acc.parts.concat();
        Ok(LlmStep {
            text: if text.is_empty() { None } else { Some(text) },
            tool_calls,
            usage: acc.usage,
        })
    }

    /// SYNC-MS-020#Llm.step
    ///
    /// 한 번 호출하고 답이나 도구 호출을 돌려준다 — `step_stream`을 끝까지 돌려 마지막 `LlmStep`
    pub async fn step(
        &self,
        system: &str,
        messages: &[LlmMessage],
        tools: &[ToolSpec],
        tool_choice: &str,
    ) -> Result<LlmStep, Problem> {
        self.step_stream(system, messages, tools, tool_choice, &mut |_| {})
            .await
    }
}
