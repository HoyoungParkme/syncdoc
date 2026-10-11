---
doc_id: SYNC-MS-020
type: MS
title: MINISPEC — llm 어댑터 — 모델 호출 (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-009, SYNC-INFRA-001, SYNC-STD-004]
---

# MINISPEC — llm 어댑터 (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/infra/llm.rs`(`Llm`)의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.9. 파이썬 판 [[SYNC-MS-009]]의 `llm.step`·`llm.step_stream`과 **같은 요청 본문·같은 파싱·같은 오류 접기**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10).

**카드 L14 몫이다(2026-10-11)** — 읽는 중 질의([[SYNC-PRD-001#R11]])가 부른다. OpenAI 호환 Chat Completions 하나([[SYNC-INFRA-001]] 5.3). 와이어 형식(`content`·`function.arguments`)은 여기만 안다. 루프는 부르는 쪽([[SYNC-MS-018#queries.ask_item]])이 돈다.

`Llm { url, key, model }` — 설정 파일의 `LLM_API_URL`·`LLM_API_KEY`·`LLM_MODEL`([[SYNC-MS-012]] `settings.load`). 파이썬은 모듈 전역 설정을 읽는다.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#Llm.step_stream]] | 스트림으로 한 번 호출 — 글자 조각과 끝의 LlmStep |
| [[#Llm.step]] | 한 번 호출 + 도구 호출 파싱 |

---

## 2. 함수

#### Llm.step_stream 스트림으로 한 번 호출

**시그니처**
```rust
pub async fn step_stream(&self, system: &str, messages: &[LlmMessage], tools: &[ToolSpec], tool_choice: &str, delta: &mut (dyn FnMut(&str) + Send)) -> Result<LlmStep, Problem>
```

근거: [[SYNC-MS-009#llm.step_stream]]

**처리** [[SYNC-MS-009#llm.step_stream]] 1~5와 같다 — 키·주소가 비면 네트워크 전에 `! LlmNotConfigured` · 본문 `{model, messages: [system, …와이어], tools?, tool_choice?, stream: true, stream_options: {include_usage: true}}`(도구가 비면 `tools`·`tool_choice`가 없다, 와이어 변환은 [[SYNC-MS-009#llm.step]]의 표) · `Authorization: Bearer {key}` · 비2xx → `! LlmUnavailable("HTTP {code}")` · `Content-Type`이 `text/event-stream`이 아니면 본문 JSON 하나를 단발로 읽는다 · 줄마다 `data:` 뒤 — `[DONE]`이면 끝, `delta.content`는 모으며 바로 조각으로, `delta.tool_calls`는 `index` 자리에 `id`·`name`을 채우고 `arguments`를 이어 붙인다, `usage` 청크 · 끝에 `LlmStep { text: 모은 글 또는 없음, tool_calls(자리 순), usage }`

**다른 점**
- 파이썬은 async 제너레이터로 조각(`str`)을 낸다 — 여기는 조각마다 `delta`를 부르고 끝의 `LlmStep`을 돌려준다
- `httpx` 대신 `reqwest`(rustls, 운영체제 인증서) — 연결·읽기 타임아웃 60초(파이썬 `httpx` `timeout=60`은 동작마다). 실패 이유 문장은 오류 종류 이름(`TimeoutException`·`ConnectError`처럼 파이썬과 같은 이름으로 접는다 — 연결 실패 `ConnectError`·시간 초과 `ReadTimeout`·그 밖 `HTTPError`)
- 줄 나누기는 `httpx` `aiter_lines`처럼 `\n`·`\r\n`·`\r`
- 요청 본문 JSON은 `httpx` 0.28과 같은 꼴 — 구분 `,`·`:`, 유니코드 그대로, 키 차례 그대로. 이미지는 base64 `data:` 주소

**예외** 키·주소 없음 → `llm-not-configured` · 비2xx·연결·시간 초과·JSON 아님·`arguments`가 JSON이 아니거나 객체가 아님·응답 꼴이 다름 → `llm-unavailable`(`reason`)

**호출하는 것** 없음 — 바깥만 만진다

**테스트 관점** 키가 비면 네트워크를 타지 않는다 · 본문에 `stream`·`stream_options`·도구·`tool_choice`가 실리고 도구가 비면 둘이 없다 · SSE(글자 조각 셋 → tool_calls 조각 둘 → usage → `[DONE]`) → 조각이 차례로, 끝의 `text`가 전체, `arguments`가 객체, `usage`가 마지막 청크 값 · `application/json`이면 단발 · 비2xx → `llm-unavailable` `HTTP {code}` · `arguments`가 JSON이 아니면 `llm-unavailable`

---

#### Llm.step 한 번 호출 + 도구 호출 파싱

**시그니처**
```rust
pub async fn step(&self, system: &str, messages: &[LlmMessage], tools: &[ToolSpec], tool_choice: &str) -> Result<LlmStep, Problem>
```

근거: [[SYNC-MS-009#llm.step]]

**처리** [[#Llm.step_stream]]을 조각을 버리며 끝까지 돌려 `LlmStep`을 돌려준다

**호출하는 것** [[#Llm.step_stream]]

**테스트 관점** [[#Llm.step_stream]]과 같은 답

---

## 3. 미결사항

없음.
