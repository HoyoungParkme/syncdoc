---
doc_id: SYNC-MS-027
type: MS
title: MINISPEC — trace — 실행 기록 받기·기록 도구·요청 보내기 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-025, SYNC-INFRA-001, SYNC-API-001]
---

# MINISPEC — trace (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/trace`(`TraceService`)의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.14. 파이썬 판 [[SYNC-MS-025]]과 **같은 이름·같은 처리·같은 응답**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 같은지는 계약 시험(카드 L28)이 응답 바이트로 본다.

서비스는 다른 서비스처럼 연결을 빌려 받는다(`TraceService { db: &mut PgConnection }`) — 트랜잭션은 입구가 쥔다([[SYNC-STD-004#DEV-10]]). 시각은 `time::OffsetDateTime`, 기록은 `serde_json::Value`(받은 JSON 그대로 — JSONB에 넣고 읽은 차례 그대로 돌려준다).

**상수** — [[SYNC-MS-025]]와 같다(`KEEP = 300` · `MAX_EVENTS = 20000` · `MAX_BYTES = 4 * 1024 * 1024`).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#TraceService.save]] | 기록 하나를 받는다 — 꼴·상한, 같은 기록은 하나, 300개 |
| [[#TraceService.list_recent]] | 최근 기록 머리 |
| [[#TraceService.get]] | 기록 하나 |
| [[#TraceService.delete]] | 하나 또는 전부 지우기 |
| [[#TraceService.coverage]] | 기록에 나온 함수와 닿은 장비 |
| [[#TraceService.delete_by_project]] | 프로젝트 해제와 함께 |

---

## 2. 함수

#### TraceService.save 기록 하나를 받는다

**시그니처**
```rust
pub async fn save(&mut self, project_id: i32, user_id: i32, record: &Value) -> Result<(TraceBrief, bool), Problem>
```

근거: [[SYNC-MS-025#TraceService.save]]

**처리** [[SYNC-MS-025#TraceService.save]] 1~5 그대로 — 꼴(차례·부모·`startedAt`) → 같은 `trace_key`면 그 머리와 거짓 → 넣고 같은 트랜잭션에서 최근 300개만. `startedAt`은 파이썬 `datetime.fromisoformat`과 같은 꼴만 받는다(정규식이 같으니 같은 글이 통과한다), 시간대가 없으면 UTC. `error`는 300자(글자 수)에서 자른다

**테스트 관점** [[SYNC-MS-025#TraceService.save]]의 것

---

#### TraceService.list_recent 최근 기록 머리

**시그니처**
```rust
pub async fn list_recent(&mut self, project_id: i32, limit: i64) -> Result<Vec<TraceBrief>, Problem>
```

**처리** [[SYNC-MS-025#TraceService.list_recent]] 그대로 — `record`를 읽지 않는다

**테스트 관점** [[SYNC-MS-025#TraceService.list_recent]]의 것

---

#### TraceService.get 기록 하나

**시그니처**
```rust
pub async fn get(&mut self, project_id: i32, trace_id: i64) -> Result<TraceView, Problem>
```

**처리** [[SYNC-MS-025#TraceService.get]] 그대로 — 없거나 다른 프로젝트면 `not-found {resource: "trace", id}`

**테스트 관점** [[SYNC-MS-025#TraceService.get]]의 것

---

#### TraceService.delete 하나 또는 전부 지우기

**시그니처**
```rust
pub async fn delete(&mut self, project_id: i32, trace_id: Option<i64>) -> Result<i64, Problem>
```

**처리** [[SYNC-MS-025#TraceService.delete]] 그대로

**테스트 관점** [[SYNC-MS-025#TraceService.delete]]의 것

---

#### TraceService.coverage 기록에 나온 함수와 닿은 장비

**시그니처**
```rust
pub async fn coverage(&mut self, project_id: i32) -> Result<TraceCoverage, Problem>
```

**처리** [[SYNC-MS-025#TraceService.coverage]] 그대로 — 열쇠와 장비는 파이썬 `sorted`처럼 코드 포인트 차례(UTF-8 바이트 차례와 같다)

**테스트 관점** [[SYNC-MS-025#TraceService.coverage]]의 것

---

#### TraceService.delete_by_project 프로젝트 해제와 함께

**시그니처**
```rust
pub async fn delete_by_project(&mut self, project_id: i32) -> Result<(), Problem>
```

**처리** `DB: DELETE FROM traces WHERE project_id=?`

**테스트 관점** 그 프로젝트 것만 지운다

---

## 3. 미결사항

없음.
