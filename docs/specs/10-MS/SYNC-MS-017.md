---
doc_id: SYNC-MS-017
type: MS
title: MINISPEC — pipeline — 쓰기 조율 (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-007, SYNC-MS-013, SYNC-MS-014, SYNC-MS-015, SYNC-SEQ-001, SYNC-STD-004]
---

# MINISPEC — pipeline (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/pipeline.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.6. 파이썬 판 [[SYNC-MS-007]]과 **같은 이름·같은 처리·같은 차례**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 여러 서비스를 한 트랜잭션으로 묶고 git과 DB의 차례를 쥔다.

**다른 점(전체)** 파이썬은 함수마다 세션을 연다 — Rust도 같게 연결 풀(`pool`)을 받아 트랜잭션을 연다(파이프라인은 입구처럼 트랜잭션을 쥔다, [[SYNC-STD-004#DEV-10]]의 「부르는 쪽」). 서버 저장소 자리 `repos`([[SYNC-MS-013]] 0장)도 받는다.

**락** — 프로젝트 코드마다 둘, 프로세스 전역(파이썬 모듈 사전과 같다). **쓰기 락**은 저장을 한 줄로 세우고, **읽기 락**은 밀린 커밋 읽기(fetch)를 한 줄로 세운다. 차례는 읽기 → 쓰기 — `read_pending`은 쓰기 락 **밖**에서 부른다(같은 락이면 교착, [[SYNC-STD-004#DEV-19]]). 시간 제한은 없다. 프로젝트 만들기·지우기의 잠금([[SYNC-MS-013]])과는 따로다. 끌 때 [[SYNC-MS-012#runtime.shutdown]]이 쓰기 락이 다 풀리기를 기다린다.

**카드 L7 몫은 `mcp` 입구다(2026-10-08)** — 에이전트의 `create_document`·`update_document`. 웹의 상태 바꾸기·되돌리기·휴지통(`web_status`·`web_revert`·`restore`, L9)과 GitHub·서버 저장소 push 처리(`github`, L11)는 그 카드가 이 문서에 갈래를 더한다. **밀린 커밋 처리는 L11이다**(사용자 결정 2026-10-08) — 처리 지점과 서버 저장소 끝이 다르면 저장하지 않고 `not-implemented(L11)`. L10 전에는 앱만 쓰므로 생기지 않는다.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `DB:` 테이블 접근, `git:` [[SYNC-MS-019]], `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#pipeline.write_lock]] | 프로젝트의 쓰기 락 |
| [[#pipeline.read_lock]] | 프로젝트의 읽기 락 |
| [[#pipeline.wait_idle]] | 쓰기 락이 다 풀리기를 기다린다 |
| [[#pipeline.read_pending]] | 쓰기 전에 밀린 커밋을 읽는다 |
| [[#pipeline.save_pipeline]] | 저장 — 검사 → push → DB → 참조 |

---

## 2. 함수

#### pipeline.write_lock 프로젝트의 쓰기 락

**시그니처**
```rust
pub fn write_lock(code: &str) -> Arc<tokio::sync::Mutex<()>>
```

근거: [[SYNC-MS-007#pipeline.save_pipeline]] · [[SYNC-INFRA-001]] 4.3 — 저장은 저장소 단위 락

**처리** 코드마다 하나 — 없으면 만들어 두고 지우지 않는다(파이썬 `_lock`) · 들어온 차례로 받는다

**테스트 관점** 같은 코드 → 같은 락 · 다른 코드 → 다른 락

---

#### pipeline.read_lock 프로젝트의 읽기 락

**시그니처**
```rust
pub fn read_lock(code: &str) -> Arc<tokio::sync::Mutex<()>>
```

근거: [[SYNC-MS-007#pipeline.read_pending]] · #194 — fetch와 커밋 처리를 저장소마다 한 줄로

**처리** 쓰기 락과 따로인 지도 — 코드마다 하나, 지우지 않는다(파이썬 `read_lock`)

**테스트 관점** 쓰기 락과 다른 락이다

---

#### pipeline.wait_idle 쓰기 락이 다 풀리기를 기다린다

**시그니처**
```rust
pub async fn wait_idle(limit: Duration) -> bool
```

근거: [[SYNC-INFRA-001]] 9.1 끄기 — 쓰기 락이 풀리기를 기다린다(최대 10초)

**처리** 지금까지 만든 쓰기 락마다 차례로 잡아 본다 — 다 잡으면 `true`, `limit`이 지나면 `false`

**호출되는 것** [[SYNC-MS-012#runtime.shutdown]]

**테스트 관점** 아무도 안 쥐면 바로 `true` · 저장이 쥐고 있으면 끝날 때까지 기다린다 · 끝나지 않으면 `limit` 뒤 `false`

---

#### pipeline.read_pending 쓰기 전에 밀린 커밋을 읽는다

**시그니처**
```rust
pub async fn read_pending(pool: &PgPool, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<i64, Problem>
```

근거: [[SYNC-MS-007#pipeline.read_pending]] · [[SYNC-STD-004#DEV-19]]

**처리** [[SYNC-MS-007#pipeline.read_pending]]과 같은 차례
1. `ProjectService.get_owned(code, user)`의 저장소 — 쓰기 경로의 소유 검사를 겸한다
2. 읽기 락을 쥐고 처리 지점(`last_processed_commit`)을 **다시** 읽는다
3. `head = git.fetch(작업 사본)`
4. if 처리 지점이 없거나 `head`와 같다 → 처리 지점이 있으면 `DB: repositories update behind_by=0, fetched_at=now` 커밋 · `→ 0`
5. 다르면 `! NotImplemented { card: "L11" }` — 파이썬은 `process_commit`(카드 L11)

**다른 점** 5 — 사용자 결정 2026-10-08

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[#pipeline.read_lock]] · [[SYNC-MS-019#Git.fetch]]

**테스트 관점** (시험 DB · 임시 데이터 자리) 앱이 만든 프로젝트 → 0, `fetched_at`이 적힌다 · 밖에서 서버 저장소에 커밋을 넣으면 `not-implemented(L11)` · 남의 프로젝트 → `not-found`

---

#### pipeline.save_pipeline 저장 — 검사 → push → DB → 참조

**시그니처**
```rust
pub async fn save_pipeline(pool: &PgPool, repos: &ServerRepos, input: SaveInput) -> Result<SaveResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.save_pipeline]] · [[SYNC-SEQ-001#SEQ-1]] · [[SYNC-UC-001#UC-A6]] · [[SYNC-API-002#create_document]] · [[SYNC-API-002#update_document]]

**입력** `SaveInput { entry, doc_id, doc_type, body, expected_version, project_code, author, message, confirm_item_deletion }` — 만들기는 `doc_id` 없이 `project_code`·`doc_type`(아무 문자열 — 파이썬처럼 거르지 않는다), 고치기는 `doc_id`·`expected_version`. `author`는 `Author { kind, user, instructed_by, via }`(에이전트는 `agent`·발급자·발급자·`mcp`)

**처리** [[SYNC-MS-007#pipeline.save_pipeline]]의 `mcp` 갈래와 같은 차례·같은 문장
- 앞. `code = project_code`가 비지 않았으면 그것, 아니면 `doc_id`가 비지 않았으면 그 첫 `-` 앞 · 없으면 `! NotFound { resource: "project", id: "None" }`(파이썬 `str(None)`)
- 0. 쓰기 락 **밖**에서 `read_pending(code, author.user)`
- 쓰기 락을 쥐고 트랜잭션 하나
- 1. `ProjectService.get_owned(code, author.user)`
- 2. 고치기 — `SpecService.get_document(doc_id)`(없으면 `not-found`) · 타입은 문서의 것 · 휴지통이면 `! DocumentTrashed { trashed_at }`(파이썬 `isoformat`)
- 3. 만들기 — `doc_id = SpecService.issue_doc_id(project, code, doc_type)` · `body = SpecService.apply_frontmatter(body, doc_id, doc_type, draft)` · 3a. `SpecService.precondition(project, doc_type, frontmatter 제목)` · 못 채우면 `! PreconditionUnmet { requires, have }`
- 4. `vr = SpecService.validate(body, doc_type, mcp, 문서 상태)` · 위반이 있으면 `! ConventionViolation { violations, warnings }`
- 5. 고치기 — `expected_version`이 현재 판이 아니면 `! VersionConflict { current_version, current_body }`(검증 **뒤**)
- 6. 고치기 — `deleted = SpecService.detect_deleted_items(문서, body)` · 그 항목마다 `ReferenceService.downstream` · 하위가 하나라도 있고 `confirm_item_deletion`이 아니면 출발 항목 이름(`SpecService.describe_items`)으로 `! ItemDeletionNeedsConfirm { deleted_items: [{item_id, downstream: [{doc_id, item_id, display_name}]}] }` — 항목이 없는 하위는 목록에서 빠진다
- 6a. 고치기 — 완료 문서이고 본문이 다르면 본문의 첫 `^status: .*$` 줄을 `status: draft`로(push **전에**)
- 7. `commit_hash = git.commit_push(작업 사본, message, author.user, {docs/specs/{NN-TYPE}/{doc_id}.md: body}, [])` — 여기까지 DB 쓰기 없음. 같은 본문이면 커밋 없이 HEAD
- 8. 만들기 → `SpecService.create(…, vr)` · 고치기 → `SpecService.save(문서, body, commit_hash, author, message, deleted, vr)`
- 9. `broken = ReferenceService.mark_missing(deleted)`
- 10. `ReferenceService.extract(문서, 판, body, SpecService.item_pks(문서), frontmatter upstream의 [\w-]+ 낱말들)` · 10a. `ReferenceService.resolve_missing(project, doc_id)`
- 경고 = `vr`의 경고마다 `rule: message`(빈 message면 `rule`) · `deleted`가 있으면 `ref.broken: {broken}`
- 13a. 처리 지점이 있고 `git.rev_list_count(작업 사본, "{처리 지점}..{commit_hash}")`가 1이면 처리 지점을 `commit_hash`로·`synced_at=now`
- 14. 커밋 · 15. `status = SpecService.get_document(doc_id).status` · `next_step = "{doc_id} v{판} 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)"`
- `→ SaveResult { doc_id, version_no, commit_hash, status, warnings, next_step }`

**다른 점** 입구 갈래는 `mcp`만(카드 L7) — 다른 입구는 `! NotImplemented`(그 카드) · `changed_items`는 파이썬도 쓰지 않는다 — 받지 않는다 · **0부터 끝까지 따로 띄운 작업(`tokio::spawn`)에서 돈다** — 부른 요청이 끊겨도(연결이 닫혀 입구의 future가 버려져도) push한 뒤 DB를 쓰지 않은 채 멈추지 않는다. 파이썬 판은 연결이 끊겨도 처리기가 끝까지 돈다

**예외** 위의 것 · git 실패는 `Problem::Git`(파이썬 `GitError` — MCP는 「Error executing tool」 문장) · `push-failed`

**호출하는 것** [[#pipeline.read_pending]] · [[#pipeline.write_lock]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.issue_doc_id]] · [[SYNC-MS-014#SpecService.apply_frontmatter]] · [[SYNC-MS-014#SpecService.precondition]] · [[SYNC-MS-014#SpecService.validate]] · [[SYNC-MS-014#SpecService.detect_deleted_items]] · [[SYNC-MS-015#ReferenceService.downstream]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-019#Git.commit_push]] · [[SYNC-MS-014#SpecService.create]] · [[SYNC-MS-014#SpecService.save]] · [[SYNC-MS-015#ReferenceService.mark_missing]] · [[SYNC-MS-014#SpecService.item_pks]] · [[SYNC-MS-015#ReferenceService.extract]] · [[SYNC-MS-015#ReferenceService.resolve_missing]] · [[SYNC-MS-019#Git.rev_list_count]] · [[SYNC-MS-014#markdown.parse_frontmatter]](제목·upstream)

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 만들기 → ID 발급·frontmatter·커밋 하나(원격 main = 반환 해시)·참조 행·`via=mcp` · 위반 → 아무것도 안 남고 HEAD 그대로 · 고치기 → v2·커밋·참조 갈아끼움 · 낡은 판 → `version-conflict`(현재 판·본문) · 하위 있는 항목 삭제 → 확인 요청, 확인 뒤 `ref.broken: 1`·미존재 참조 · 지운 ID를 에이전트가 다시 쓰면 `item.reused`(되살리기는 웹, L9) · 나중에 만든 상위 문서가 기다리던 미존재 참조를 잇는다 · 같은 본문 → 커밋 없이 HEAD로 새 판, 참조 행 그대로 · 완료 문서 고치기 → 초안·상태 변경 행 하나 · 동시 저장 둘 → 둘째가 `version-conflict` · 모르는 타입 → `frontmatter.type` 위반 · 처리 지점이 앱 커밋만큼 앞선다 · 부른 쪽을 중간에 버려도 저장이 끝까지 간다(커밋과 행이 둘 다 있다)

---

## 3. 미결사항

없음. 다른 입구의 갈래는 그 카드가 더한다 — [[SYNC-CODE-002]].
