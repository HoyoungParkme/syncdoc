---
doc_id: SYNC-MS-025
type: MS
title: MINISPEC — trace — 실행 기록 받기·목록·커버리지
status: approved
upstream: [SYNC-DOM-002, SYNC-DOM-003, SYNC-SEQ-001, SYNC-API-001]
---

# MINISPEC — trace — 실행 기록 받기·목록·커버리지

## 0. 이 문서가 다루는 것

`core/trace/service.py`(`TraceService`)와 `core/trace/repository.py` — 목록은 1장. 클래스 명세 [[SYNC-DOM-002]] 4.12를 함수 내부까지 내린 것. 실행 기록([[SYNC-PRD-001#R17]])을 받아 두고(최근 300개) 목록·하나·커버리지로 내준다. **기록을 고치지 않는다** — 비밀 가리기는 기록 도구의 일이다([[SYNC-INFRA-001#C13]]). 소유 검사는 부르는 쪽(라우터·MCP 도구)이 `ProjectService.get_owned`로 먼저 한다.

형식은 [[SYNC-STD-001]] 2.10. 서비스는 다른 서비스처럼 세션을 받아 만든다 — 함수는 동기다(DB 왕복뿐). 내부 타입 `TraceBrief`·`TraceView`·`TraceCoverage`는 [[SYNC-DOM-002]] 2.8.

**상수** — `KEEP = 300`(프로젝트마다 남기는 수) · `MAX_EVENTS = 20000` · `MAX_BYTES = 4 * 1024 * 1024`(본문).

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

**시그니처** `def save(project_id: int, user_id: int, record: dict) -> tuple[TraceBrief, bool]`

근거: [[SYNC-UC-001#UC-S9]] · [[SYNC-API-001#POST/api/projects/{code}/traces]] · [[SYNC-SEQ-001#SEQ-36]] · 사용자 결정 2026-10-12(300개)

**입력** `record` — 라우터가 [[SYNC-API-001]] 4장 `TraceRecord`로 이미 검증한 것(타입·필수 키·`maxLength`·`maxItems`). 본문 크기 4MB는 라우터가 먼저 본다

**처리**
1. 꼴 — `events`마다 `parent`가 `-1`이거나 앞선 사건의 `i`인지, `i`가 0부터 차례인지. 아니면 `! trace-invalid {reason: "events[n] — 부모가 없다" | "events[n] — i가 차례가 아니다"}`
   · `startedAt`이 ISO 8601(`YYYY-MM-DDTHH:MM:SS`, 소수 1~6자리, `Z`나 `±hh:mm` — 없으면 UTC)이 아니거나 없는 날짜면 `! trace-invalid {reason: "startedAt — 시각이 아니다"}`
2. `DB: SELECT … FROM traces WHERE project_id=? AND trace_key=?` · 있으면 `→ (그 행의 TraceBrief, False)` — 다시 보낸 같은 기록이다
3. 행 — `trace_key = record.id` · `kind` · `method = None if kind == "job" else record.method` · `path` · `status` · `error`(300자에서 자른다 — `record`는 그대로) · `started_at = record.startedAt`(시간대가 없으면 UTC) · `ms` · `commit_hash = record.commit` · `event_count = len(events)` · `truncated` · `record` 그대로 · `received_at = clock.now()`
4. `DB: INSERT` · 같은 트랜잭션에서 `DB: DELETE FROM traces WHERE project_id=? AND id NOT IN (SELECT id … ORDER BY received_at DESC, id DESC LIMIT 300)`
5. `→ (TraceBrief, True)`

**출력** 머리와 새로 넣었나

**예외** `trace-invalid`(1)

**호출하는 것** —

**테스트 관점** 넣으면 머리가 돌아오고 `event_count`가 맞다 · 같은 `id`를 다시 → 새 행 없이 `False` · 301번째를 넣으면 가장 오래된 것이 지워진다(다른 프로젝트는 그대로) · `job`은 `method` None · 부모 없는 사건 → `trace-invalid`, 행 없음 · `startedAt`이 시각이 아니면(`2026-13-01T…`·날짜만) `trace-invalid` · `error` 301자 → 컬럼은 300, `record`는 그대로

---

#### TraceService.list_recent 최근 기록 머리

**시그니처** `def list_recent(project_id: int, limit: int = 300) -> list[TraceBrief]`

근거: [[SYNC-UC-001#UC-H25]] 6 · [[SYNC-UC-001#UC-A11]] 3

**처리** `DB: SELECT 머리 컬럼 FROM traces WHERE project_id=? ORDER BY received_at DESC, id DESC LIMIT ?` — `record`는 읽지 않는다 · `→ [TraceBrief…]`

**테스트 관점** 최근 것부터 · `limit` · `record`를 안 읽는다

---

#### TraceService.get 기록 하나

**시그니처** `def get(project_id: int, trace_id: int) -> TraceView`

**처리** `DB: SELECT * FROM traces WHERE id=? AND project_id=?`(id가 DB 정수 범위 밖이면 묻지 않고 없음) · 없으면 `! not-found {resource: "trace", id}` · `→ TraceView(머리, record)`

**테스트 관점** 다른 프로젝트의 id → not-found · 아주 큰 id → not-found

---

#### TraceService.delete 하나 또는 전부 지우기

**시그니처** `def delete(project_id: int, trace_id: int | None = None) -> int`

근거: UI-19 5.11 · [[SYNC-API-001#DELETE/api/projects/{code}/traces]]

**처리** `trace_id`가 있으면 그 행만(없으면 `! not-found {resource: "trace"}` — [[#TraceService.get]]으로 본다), 없으면 그 프로젝트 전부 · `→ 지운 수`

**호출하는 것** [[#TraceService.get]]

**테스트 관점** 하나 · 전부 · 다른 프로젝트는 그대로 · 없는 id → not-found

---

#### TraceService.coverage 기록에 나온 함수와 닿은 장비

**시그니처** `def coverage(project_id: int) -> TraceCoverage`

근거: [[SYNC-UC-001#UC-H25]] 6 「커버리지」 · UI-19 2.3·5.8

**처리**
1. `DB: SELECT record->'events' FROM traces WHERE project_id=?`
2. 사건마다 — `fn`이 `@`로 시작하지 않으면 `keys`에 · `infra`가 있으면 `(infra.kind, infra.target)`을 `infra`에
3. `→ TraceCoverage(traces=행 수, keys=정렬, infra=[{kind, target}] 정렬)`

**테스트 관점** `@infra`·`@fetch`는 함수가 아니다 · 같은 함수는 하나 · 기록 없음 → 빈 것

---

#### TraceService.delete_by_project 프로젝트 해제와 함께

**시그니처** `def delete_by_project(project_id: int) -> None`

**처리** `DB: DELETE FROM traces WHERE project_id=?`

**테스트 관점** 그 프로젝트 것만 지운다

---

## 3. 미결사항

- [ ] 기록 하나의 크기 — 4MB·사건 2만 개는 view_arc의 값을 그대로 가져왔다. 실제로 써 보고 줄일지
