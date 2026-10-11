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

**카드 L7 몫은 `mcp` 입구다(2026-10-08)** — 에이전트의 `create_document`·`update_document`. **카드 L9가 상태 바꾸기·되돌리기·휴지통 넣기·되살리기·완전 삭제와 저장의 `web_status`·`web_revert`·되살림 갈래를 더했다(2026-10-11).** **카드 L11이 밀린 커밋 처리·재구축·코드 올리기·저장 방식 옮기기·따라잡기와 저장의 `github` 갈래를 더했다(2026-10-11)** — 서버 저장소에 git으로 민 것(L10 git 입구)이 문서가 된다. **카드 L12가 코드 그래프 걸기·만들기를 더했다(2026-10-11)** — 커밋 처리(5a)·재구축(10)·코드 올리기(커밋 처리를 거쳐)가 건다. 카드 L13이 만들기에 커뮤니티를 더했다(2026-10-11).

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
| [[#pipeline.change_status]] | 초안 ⇄ 완료 토글 |
| [[#pipeline.revert]] | 되돌리기 |
| [[#pipeline.trash_document]] | 휴지통에 넣기 |
| [[#pipeline.restore_document]] | 휴지통에서 되살리기 |
| [[#pipeline.purge_document]] | 완전 삭제 |
| [[#pipeline.process_commit]] | 밀린 커밋 처리 |
| [[#pipeline.type_of_dir]] | 디렉터리 이름 → 타입 |
| [[#pipeline.rebuild]] | 인덱스 재구축 |
| [[#pipeline.upload_code]] | 서버 저장소에 코드 올리기 |
| [[#pipeline.move_to_server]] | 서버 저장으로 옮기기 — 이미 서버다 |
| [[#pipeline.move_to_github]] | GitHub 저장으로 되돌리기 — 켜지 않은 방식 |
| [[#pipeline.catch_up]] | 밀린 커밋 따라잡기 |
| [[#pipeline.poll_loop]] | 주기 확인 |
| [[#pipeline.schedule_code_graph]] | 코드 그래프 만들기를 걸어 둔다 |
| [[#pipeline.build_code_graph]] | 코드 그래프를 만든다 |

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
5. 다르면 `→ process_commit(code, head, locked=true)`의 결과 수 — 이미 읽기 락 안이다

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[#pipeline.read_lock]] · [[SYNC-MS-019#Git.fetch]] · [[#pipeline.process_commit]]

**테스트 관점** (시험 DB · 임시 데이터 자리) 앱이 만든 프로젝트 → 0, `fetched_at`이 적힌다 · 밖에서 서버 저장소에 명세 커밋을 넣으면 → 1, 문서가 생긴다 · 남의 프로젝트 → `not-found`

---

#### pipeline.save_pipeline 저장 — 검사 → push → DB → 참조

**시그니처**
```rust
pub async fn save_pipeline(pool: &PgPool, repos: &ServerRepos, input: SaveInput) -> Result<SaveResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.save_pipeline]] · [[SYNC-SEQ-001#SEQ-1]] · [[SYNC-UC-001#UC-A6]] · [[SYNC-API-002#create_document]] · [[SYNC-API-002#update_document]]

**입력** `SaveInput { entry, doc_id, doc_type, body, expected_version, project_code, author, message, confirm_item_deletion, reason, restore, read_first, commit_hash }` — 만들기는 `doc_id` 없이 `project_code`·`doc_type`(아무 문자열 — 파이썬처럼 거르지 않는다), 고치기는 `doc_id`·`expected_version`. `author`는 `Author { kind, user, instructed_by, via }`(에이전트는 `agent`·발급자·발급자·`mcp`). `reason`은 상태 바꾸기의 사유, `restore`는 되살림(휴지통 검사를 지난다), `read_first`는 0단계를 할지 — 부르는 쪽(상태·되돌리기·되살리기)이 이미 읽었으면 거짓(파이썬 `session`을 넘긴 경우), `github`은 늘 거짓(처리 중이라 부르면 끝없이 돈다) · `commit_hash`는 `github` 입구의 파일 커밋(다른 입구는 없음)

**처리** [[SYNC-MS-007#pipeline.save_pipeline]]과 같은 차례·같은 문장. `github` 갈래는 줄 끝 「github —」
- 앞. `code = project_code`가 비지 않았으면 그것, 아니면 `doc_id`가 비지 않았으면 그 첫 `-` 앞 · 없으면 `! NotFound { resource: "project", id: "None" }`(파이썬 `str(None)`)
- 0. `read_first`면 쓰기 락 **밖**에서 `read_pending(code, author.user)`
- 쓰기 락을 쥐고 트랜잭션 하나
- 1. `ProjectService.get_owned(code, author.user)` · github — `ProjectService.get(code)`(사람이 없는 배치다)
- 2. 고치기 — `SpecService.get_document(doc_id)`(없으면 `not-found`) · 타입은 문서의 것 · 휴지통이고 `restore`가 아니면 `! DocumentTrashed { trashed_at }`(파이썬 `isoformat`) · github — 없으면 만들기(파일명이 `doc_id`, frontmatter는 그대로 — 3을 건너뛴다), 휴지통 검사를 건너뛴다(파일이 다시 push된 것 자체가 되살리기)
- 3. 만들기 — `doc_id = SpecService.issue_doc_id(project, code, doc_type)` · `body = SpecService.apply_frontmatter(body, doc_id, doc_type, draft)` · 3a. `SpecService.precondition(project, doc_type, frontmatter 제목)` · 못 채우면 `! PreconditionUnmet { requires, have }`
- 4. `vr = SpecService.validate(body, doc_type, entry, 문서 상태)` · 위반이 있으면 `! ConventionViolation { violations, warnings }` · github — 막지 않는다(원본이 진실)
- 5. 고치기 — `expected_version`이 현재 판이 아니면 `! VersionConflict { current_version, current_body }`(검증 **뒤**) · github — 보지 않는다
- 6. 고치기이고 `web_status`가 아니면 — `deleted = SpecService.detect_deleted_items(문서, body)` · 그 항목마다 `ReferenceService.downstream` · 하위가 하나라도 있고 `confirm_item_deletion`이 아니면 출발 항목 이름(`SpecService.describe_items`)으로 `! ItemDeletionNeedsConfirm { deleted_items: [{item_id, downstream: [{doc_id, item_id, display_name}]}] }` — 항목이 없는 하위는 목록에서 빠진다 · github — 묻지 않는다(커밋이 진실, 끊어진 참조로 통보)
- 6a. 고치기이고 `web_status`가 아니면 — 완료 문서이고 본문이 다르면(github은 frontmatter가 아직 `approved`일 때만 — 작성자가 스스로 내렸으면 그것이 진실) 본문의 첫 `^status: .*$` 줄을 `status: draft`로(push **전에**) · github — 커밋이 이미 저장소에 있으니 강등을 커밋 하나로 더 민다: `status_commit_hash = git.commit_push(작업 사본, "status({doc_id}): approved → draft\n\n본문 수정으로 자동 강등", 등록한 사람, {경로: body}, [])` — 미는 사람은 저장소를 등록한 사람, 그 해시를 상태 변경에 적어 다음 처리가 앱 커밋으로 거른다(#58)
- 7. `commit_hash = git.commit_push(작업 사본, message, author.user, {docs/specs/{NN-TYPE}/{doc_id}.md: body}, [])` — 여기까지 DB 쓰기 없음. 같은 본문이면 커밋 없이 HEAD · github — 밀지 않는다(`input.commit_hash`)
- 8w. `web_status` — `SpecService.apply_status(문서, body, commit_hash, author, reason)` · 13a(1) · 커밋 · `→ SaveResult { doc_id, version_no: 지금 판, commit_hash, status: 다시 읽은 상태, warnings: [], next_step: 없음 }`
- 8. 만들기 → `SpecService.create(…, vr)` · 고치기 → `SpecService.save(문서, body, commit_hash, author, message, deleted, vr, false, status_commit_hash)`
- 9. `broken = ReferenceService.mark_missing(deleted)`
- 10. `ReferenceService.extract(문서, 판, body, SpecService.item_pks(문서), frontmatter upstream의 [\w-]+ 낱말들)` · 10a. `ReferenceService.resolve_missing(project, doc_id)`
- 경고 = `vr`의 경고마다 `rule: message`(빈 message면 `rule`) · `deleted`가 있으면 `ref.broken: {broken}`
- 13a. github이 아니고 처리 지점이 있고 `git.rev_list_count(작업 사본, "{처리 지점}..{commit_hash}")`가 1이면 처리 지점을 `commit_hash`로·`synced_at=now`
- 14. 커밋 · 15. `status = SpecService.get_document(doc_id).status` · `mcp`면 `next_step = "{doc_id} v{판} 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)"`, 웹·github이면 없음
- `→ SaveResult { doc_id, version_no, commit_hash, status, warnings, next_step }`

**다른 점** `changed_items`는 파이썬도 쓰지 않는다 — 받지 않는다 · **0부터 끝까지 따로 띄운 작업(`tokio::spawn`)에서 돈다** — 부른 요청이 끊겨도(연결이 닫혀 입구의 future가 버려져도) push한 뒤 DB를 쓰지 않은 채 멈추지 않는다. 파이썬 판은 연결이 끊겨도 처리기가 끝까지 돈다

**예외** 위의 것 · git 실패는 `Problem::Git`(파이썬 `GitError` — MCP는 「Error executing tool」 문장) · `push-failed`

**호출하는 것** [[#pipeline.read_pending]] · [[#pipeline.write_lock]] · [[SYNC-MS-014#SpecService.apply_status]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-013#ProjectService.get]](github) · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.issue_doc_id]] · [[SYNC-MS-014#SpecService.apply_frontmatter]] · [[SYNC-MS-014#SpecService.precondition]] · [[SYNC-MS-014#SpecService.validate]] · [[SYNC-MS-014#SpecService.detect_deleted_items]] · [[SYNC-MS-015#ReferenceService.downstream]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-019#Git.commit_push]] · [[SYNC-MS-014#SpecService.create]] · [[SYNC-MS-014#SpecService.save]] · [[SYNC-MS-015#ReferenceService.mark_missing]] · [[SYNC-MS-014#SpecService.item_pks]] · [[SYNC-MS-015#ReferenceService.extract]] · [[SYNC-MS-015#ReferenceService.resolve_missing]] · [[SYNC-MS-019#Git.rev_list_count]] · [[SYNC-MS-014#markdown.parse_frontmatter]](제목·upstream)

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 만들기 → ID 발급·frontmatter·커밋 하나(원격 main = 반환 해시)·참조 행·`via=mcp` · 위반 → 아무것도 안 남고 HEAD 그대로 · 고치기 → v2·커밋·참조 갈아끼움 · 낡은 판 → `version-conflict`(현재 판·본문) · 하위 있는 항목 삭제 → 확인 요청, 확인 뒤 `ref.broken: 1`·미존재 참조 · 지운 ID를 에이전트가 다시 쓰면 `item.reused`(되살리기는 웹, L9) · 나중에 만든 상위 문서가 기다리던 미존재 참조를 잇는다 · 같은 본문 → 커밋 없이 HEAD로 새 판, 참조 행 그대로 · 완료 문서 고치기 → 초안·상태 변경 행 하나 · 동시 저장 둘 → 둘째가 `version-conflict` · 모르는 타입 → `frontmatter.type` 위반 · 처리 지점이 앱 커밋만큼 앞선다 · 부른 쪽을 중간에 버려도 저장이 끝까지 간다(커밋과 행이 둘 다 있다) · github — 위반이 있어도 저장 · 완료 문서를 밖에서 고쳐 민 것 → 초안과 강등 커밋 하나(상태 변경 행에 그 해시) · 작성자가 frontmatter를 `draft`로 내려 민 것 → 강등 커밋 없음

---

#### pipeline.change_status 초안 ⇄ 완료 토글

**시그니처**
```rust
pub async fn change_status(pool: &PgPool, repos: &ServerRepos, doc_id: &str, to: DocStatus, author: &Author, reason: Option<&str>) -> Result<Document, Problem>
```

근거: [[SYNC-MS-007#pipeline.change_status]] · [[SYNC-UC-001#UC-H8]] · [[SYNC-API-001#POST/api/docs/{docId}/status]] · [[SYNC-API-002#change_status]]

**처리** [[SYNC-MS-007#pipeline.change_status]]와 같은 차례
0. `read_pending(doc_id의 첫 "-" 앞, author.user)` — 소유 검사도 여기서
1. `get_owned` · `document = SpecService.get_document(doc_id)` · 휴지통이면 `! DocumentTrashed`
2. `missing` = `ReferenceService.upstream_of_document(문서, true)`의 미존재 `raw_target`을 중복 없이 정렬 · `approved`로 올리는데 규약 오류·경고·`missing`이 있으면 `! StatusBlocked { convention_error_detail, warnings: 경고 + ["ref.missing: {t}"…] }`
3. 이미 그 상태면 `→ document`(아무것도 안 한다)
4. 본문은 **저장소에서** — `Git.read(작업 사본, docs/specs/{NN-TYPE}/{doc_id}.md, "origin/main")`, 못 읽으면 DB 본문 · 첫 `status:` 줄을 `to`로
5. `save_pipeline(web_status, doc_id, 본문, 지금 판, author, "status({doc_id}): {지금} → {to}\n\n{reason 또는 빈 것}", reason, read_first: 거짓)`
6. `→ SpecService.get_document(doc_id)`

**호출하는 것** [[#pipeline.read_pending]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-015#ReferenceService.upstream_of_document]] · [[SYNC-MS-019#Git.read]] · [[#pipeline.save_pipeline]]

**테스트 관점** (시험 DB · 진짜 git) 완료로 → frontmatter `status: approved` 커밋, 판 그대로, 상태 변경 행에 해시 · 미존재 참조·경고 → `status-blocked`(`ref.missing:`) · 내리기는 막지 않는다 · 같은 상태 → 커밋 없음 · 휴지통 → `document-trashed` · 에이전트 → `via=mcp`

---

#### pipeline.revert 되돌리기

**시그니처**
```rust
pub async fn revert(pool: &PgPool, repos: &ServerRepos, doc_id: &str, to_version: i32, user: &UserRow, confirm_item_deletion: bool) -> Result<SaveResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.revert]] · [[SYNC-UC-001#UC-H7]] · [[SYNC-API-001#POST/api/docs/{docId}/revert]]

**처리** [[SYNC-MS-007#pipeline.revert]]와 같은 차례 — `read_pending` · `document = get_document` · `old = SpecService.version_body(doc_id, to_version)` · 지금 판이면 `! AlreadyCurrent` · `save_pipeline(web_revert, doc_id, old, 지금 판, Author { human, user, 없음, web_revert }, "revert({doc_id}): v{지금} → v{to_version} 내용으로", confirm_item_deletion, read_first: 거짓)`

**호출하는 것** [[#pipeline.read_pending]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.version_body]] · [[#pipeline.save_pipeline]]

**테스트 관점** (시험 DB · 진짜 git) v2에서 v1로 → v3 · 지금 판 → `already-current` · 없는 판 → `not-found` · 지운 항목을 되돌리면 `item.reused`가 아니다(복원)

---

#### pipeline.trash_document 휴지통에 넣기

**시그니처**
```rust
pub async fn trash_document(pool: &PgPool, repos: &ServerRepos, doc_id: &str, author: &Author, confirm: bool) -> Result<TrashResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.trash_document]] · [[SYNC-UC-001#UC-A7]] · [[SYNC-API-002#delete_document]] · [[SYNC-API-001#DELETE/api/docs/{docId}]]

**처리** [[SYNC-MS-007#pipeline.trash_document]]와 같은 차례 — 따로 띄운 작업에서(push 뒤 DB까지 끝까지)
0. `read_pending`(락 밖)
1. 쓰기 락 · 트랜잭션 · `get_owned` · `document = get_document` · 휴지통이면 `! DocumentTrashed`
2. `inbound` = `ReferenceService.inbound_of_document`를 이름으로(`DOC#ITEM` 또는 `DOC`, 못 찾으면 `?`) 정렬
3. `confirm`이 아니면 `! DocumentDeletionNeedsConfirm { doc_id, title: frontmatter 제목(없으면 빈 것), version_count: 지금 판, inbound_refs }`
4. `commit_hash = Git.commit_push(작업 사본, "spec({doc_id}): 휴지통", author.user, {}, [경로])`
5. `pks = SpecService.trash` · `broken = ReferenceService.mark_missing(pks)` · 처리 지점(13a, 1) · 커밋
6. `→ TrashResult { doc_id, commit_hash, broken_refs, next_step: "{doc_id} 휴지통에 넣음 — 끊어진 참조 {broken}. 사람에게 알리고 멈춘다" }`

**호출하는 것** [[#pipeline.read_pending]] · [[#pipeline.write_lock]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-015#ReferenceService.inbound_of_document]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-019#Git.commit_push]] · [[SYNC-MS-014#SpecService.trash]] · [[SYNC-MS-015#ReferenceService.mark_missing]] · [[SYNC-MS-019#Git.rev_list_count]] · [[SYNC-MS-014#markdown.parse_frontmatter]]

**테스트 관점** (시험 DB · 진짜 git) 확인 없이 → 끊어질 것 목록 · 확인 → 원격에서 파일 사라짐, `broken_refs`가 그 수, 그 참조들이 미존재 · 두 번 → `document-trashed` · 처리 지점이 그 커밋

---

#### pipeline.restore_document 휴지통에서 되살리기

**시그니처**
```rust
pub async fn restore_document(pool: &PgPool, repos: &ServerRepos, doc_id: &str, author: &Author) -> Result<SaveResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.restore_document]] · [[SYNC-UC-001#UC-A8]] · [[SYNC-API-002#restore_document]] · [[SYNC-API-001#POST/api/docs/{docId}/restore]]

**처리** [[SYNC-MS-007#pipeline.restore_document]]와 같은 차례 — `read_pending` · `get_owned` · `document = get_document` · 휴지통이 아니면 `! DocumentNotTrashed` · `h = SpecService.trash_commit` · 본문 = `Git.read(작업 사본, 경로, "{h}^")`의 `status:`를 `draft`로 · `save_pipeline(author.via가 mcp면 mcp 아니면 web_revert, doc_id, 본문, 지금 판, author, "spec({doc_id}): 되살림 — 휴지통에서", restore: 참, read_first: 거짓)` — 항목이 돌아오고 그것을 기다리던 미존재 참조는 저장의 10a가 잇는다

**호출하는 것** [[#pipeline.read_pending]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.trash_commit]] · [[SYNC-MS-019#Git.read]] · [[#pipeline.save_pipeline]]

**테스트 관점** (시험 DB · 진짜 git) 넣기 → 되살리기 → 본문이 직전과 같고 판 +1 · 항목 돌아옴 · 끊긴 참조 다시 이어짐 · 휴지통이 아니면 `document-not-trashed`

---

#### pipeline.purge_document 완전 삭제

**시그니처**
```rust
pub async fn purge_document(pool: &PgPool, repos: &ServerRepos, doc_id: &str, author: &Author) -> Result<(), Problem>
```

근거: [[SYNC-MS-007#pipeline.purge_document]] · [[SYNC-UC-001#UC-H18]] 6~8 · [[SYNC-API-001#POST/api/docs/{docId}/purge]]

**처리** [[SYNC-MS-007#pipeline.purge_document]]와 같다 — 쓰기 락 · 트랜잭션 · `get_owned` · `get_document` · 휴지통이 아니면 `! DocumentNotTrashed` · `inbound`(이름)이 있으면 `! DocumentHasHistory { inbound_refs }` · `SpecService.delete_document` · 커밋. push 없음(파일은 휴지통 커밋에서 이미 없다). 밀린 커밋은 읽지 않는다(파이썬과 같다)

**호출하는 것** [[#pipeline.write_lock]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-015#ReferenceService.inbound_of_document]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-014#SpecService.delete_document]]

**테스트 관점** (시험 DB) 휴지통 아님 → `document-not-trashed` · 남이 아직 가리킴 → `document-has-history` · 다 걷어낸 뒤 → 행 없음, 같은 번호 다시 발급

---

#### pipeline.process_commit 밀린 커밋 처리

**시그니처**
```rust
pub async fn process_commit(pool: &PgPool, repos: &ServerRepos, code: &str, head: &str, locked: bool) -> Result<Vec<SaveResult>, Problem>
```

근거: [[SYNC-MS-007#pipeline.process_commit]] · [[SYNC-SEQ-001#SEQ-2]] · [[SYNC-SEQ-001#SEQ-29]] · [[SYNC-UC-001#UC-G1]] · [[SYNC-SCN-001#S7]]

**처리** [[SYNC-MS-007#pipeline.process_commit]]과 같은 차례
0. `locked`가 아니면 읽기 락을 쥔다([[#pipeline.read_pending]]·[[#pipeline.catch_up]]은 이미 쥐었다)
1. 락 안에서 `ProjectService.get(code)`의 처리 지점을 **다시** 읽는다 · `head`와 같으면 `→ []`
2. `git.fetch(작업 사본)` · 처리 지점이 있고 `git.rev_list_count("{처리 지점}..{head}")`가 0이면 `→ []`(늦게 온 것 — 처리 지점을 뒤로 돌리지 않는다)
3. `files = git.changed_files(작업 사본, "{처리 지점}..{head}" 또는 처리 지점이 없으면 head, "docs/specs/")` · `(stage_of(경로의 셋째 조각) 또는 99, 경로)` 순 — 파이썬 판 그대로 디렉터리 이름(`02-PRD`)으로 찾으므로 번호 붙은 디렉터리는 모두 99이고 경로 순이 곧 단계 순이다
4. 파일마다(하나가 실패해도 다음 파일 — 실패한 경로를 모아 경고로 남긴다)
   - `doc_id` = 파일 이름에서 `.md`를 뗀 것 · `dir_type` = 셋째 조각을 [[#pipeline.type_of_dir]]처럼(조각이 넷 미만이면 빈 것)
   - `user = AccountService.user_for_commit(메일, 아이디)` · `author = Author { human, user, 없음, github }`
   - `D`(파일 삭제) — 문서가 없거나 휴지통이면 `[]`(앱이 넣은 휴지통·완전 삭제의 커밋, 등록 전에 사라진 파일) · 아니면 `ReferenceService.mark_missing(SpecService.mark_deleted(문서, 그 파일의 커밋, author))` · 커밋 · `[]`
   - 그 파일의 커밋이 이미 그 문서의 이력(`SpecService.list_versions`의 커밋 해시 — 버전과 상태 변경)에 있으면 `[]` — 앱이 민 커밋이다
   - `body = git.read(작업 사본, 경로, head)` · `dir_type`이 타입이 아니면 그 파일은 실패(파이썬 `DocType(dir_type)`의 `ValueError` — 처리 지점이 나아가지 않는다, 사람 실수라 알린다)
   - `r = save_pipeline(SaveInput { entry: github, doc_id, doc_type: dir_type, body, author, message: 커밋 메시지, commit_hash: 파일의 커밋, read_first: false, … })`
   - frontmatter의 `doc_id`가 파일 이름이 아니면 `Violation(2, "frontmatter.doc_id", "파일명 {doc_id} ≠ {repr(fm doc_id)}")` · `type`이 디렉터리가 아니면 `Violation(2, "frontmatter.doc_id", "디렉터리 {dir_type} ≠ type {repr(fm type)}")` · 하나라도 있으면 `vr = SpecService.validate(body, dir_type, github, 없음)` 뒤에 붙여 `SpecService.mark_convention_error` · 커밋 · `[r]`
5. 실패가 없으면 `DB: repositories update last_processed_commit=head, synced_at=now, behind_by=0, fetched_at=now` 커밋 · 5a. 처리 지점이 있었으면 `paths = git.changed_paths(작업 사본, "{처리 지점}..{head}")`(없었으면 빈 것) · `codegraph.touches_code(paths)`이거나 그래프 행이 없으면([[SYNC-MS-022#CodeGraphService.get]]) `schedule_code_graph(code, head)` — 명세만 바뀐 커밋은 그래프가 있으면 건너뛴다
6. `→` 결과 모음

**다른 점** 저장소 행 대신 코드를 받는다(파이썬은 행에서 코드를 찾는다) · 작성자는 늘 로컬 사용자라 `author.unknown`이 없다([[SYNC-MS-016#AccountService.user_for_commit]])

**예외** 1·2의 git 실패 · 파일 하나의 실패는 예외가 아니다(처리 지점만 멈춘다)

**호출하는 것** [[#pipeline.read_lock]] · [[SYNC-MS-013#ProjectService.get]] · [[SYNC-MS-019#Git.fetch]] · [[SYNC-MS-019#Git.rev_list_count]] · [[SYNC-MS-019#Git.changed_files]] · [[#pipeline.type_of_dir]] · [[SYNC-MS-019#Git.read]] · [[SYNC-MS-016#AccountService.user_for_commit]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.mark_deleted]] · [[SYNC-MS-015#ReferenceService.mark_missing]] · [[SYNC-MS-014#SpecService.list_versions]] · [[#pipeline.save_pipeline]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-014#SpecService.validate]] · [[SYNC-MS-014#SpecService.mark_convention_error]] · [[SYNC-MS-019#Git.changed_paths]] · [[SYNC-MS-022#codegraph.touches_code]] · [[SYNC-MS-022#CodeGraphService.get]] · [[#pipeline.schedule_code_graph]]

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 코드 파일을 민 커밋 → 그래프가 생긴다 · 명세만 민 커밋 → 그래프가 있으면 다시 만들지 않는다 · 밖에서 민 커밋 하나에 파일 둘(상위·하위) → 결과 둘, 하위의 참조가 미존재가 아니다 · 앱이 민 커밋은 거른다(버전이 늘지 않는다) · 파일 삭제 push → 초안·`file.deleted`·하위 참조 끊김 · 되살려 push → 오류가 풀리고 항목이 산다 · 휴지통 문서의 삭제 커밋 → 건너뛴다 · 파일 이름 ≠ frontmatter `doc_id` → 저장되고 규약 오류 · 모르는 디렉터리 → 처리 지점이 그대로 · 같은 head를 두 번 → 둘째는 `[]`

---

#### pipeline.type_of_dir 디렉터리 이름 → 타입

**시그니처**
```rust
pub fn type_of_dir(name: &str) -> String
```

근거: 파이썬 `types.type_of_dir` · [[SYNC-STD-001]] 1.1

**처리** 앞 두 글자가 파이썬 `str.isdigit()`이고 `-`가 있으면 첫 `-` 뒤, 아니면 그대로(`06-DOM` → `DOM`, `STD` → `STD`)

**테스트 관점** `06-DOM` → `DOM` · `STD` → `STD` · `0-X` → 그대로 · `²³-PRD` → `PRD`(파이썬 `isdigit`)

---

#### pipeline.rebuild 인덱스 재구축

**시그니처**
```rust
pub async fn rebuild(conn: &mut PgConnection, pool: &PgPool, repos: &ServerRepos, code: &str) -> Result<RebuildResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.rebuild]] · [[SYNC-SEQ-001#SEQ-21]] · [[SYNC-UC-001#UC-S6]]

**처리** [[SYNC-MS-007#pipeline.rebuild]]과 같은 차례 — 쓰기 락을 쥐고 `conn` 위에 트랜잭션(이미 트랜잭션이면 저장점) 하나
1. `ProjectService.get(code)`
2. `head = git.fetch(작업 사본)` · `git.checkout(작업 사본, "origin/main")`
4. `ReferenceService.clear(project)` · `SpecService.clear_index(project)`
5. `paths = git.list(작업 사본, "docs/specs/*/*.md", head)`
6. 경로마다 — `doc_id`·`dir_type`([[#pipeline.type_of_dir]]) · `dir_type`이 타입이 아니면 `convention_errors`에 `{doc_id, "frontmatter.doc_id: 알 수 없는 디렉터리 {dir_type}"}`를 넣고 다음 · `document = SpecService.get_document(doc_id)`(없으면 없음) · `git.log(작업 사본, 경로)`의 커밋마다(지운 커밋은 없다, #325): `body = git.read(작업 사본, 그 커밋의 경로, 해시)` · `user = AccountService.user_for_commit` · `author = Author { human, user, 없음, github }` · 메시지가 `status(`로 시작하고 문서가 있으면 `SpecService.apply_status(문서, body, 해시, author, 없음)` · 아니면 `vr = SpecService.validate(body, dir_type, github, 없음)` 뒤 문서가 없으면 `SpecService.create`, 있으면 `SpecService.save(문서, body, 해시, author, 메시지, SpecService.detect_deleted_items(문서, body), vr, true, 없음)` · `versions += 1` · 커밋마다 문서를 다시 읽는다
   - 문서가 끝내 없으면 다음 · `ReferenceService.extract(문서, 지금 판, 본문, item_pks, upstream 낱말들)` · `vr = validate(본문, dir_type, github, 없음)` · `SpecService.mark_convention_error(문서, vr)` · 위반이 있으면 `convention_errors`에 `{doc_id, "rule: message" 줄들}` · `docs += 1` · `items += 문서 항목 수` · `references += 뽑은 수`
7. `ReferenceService.resolve_missing(project, 없음)`
8. `DB: repositories update last_processed_commit=head, synced_at=now, behind_by=0, fetched_at=now`
9. 커밋 · 10. `schedule_code_graph(pool, repos, code, head)` — 재구축은 늘 다시 만든다(UC-S8) · `→ RebuildResult { docs, items, references, versions, convention_errors, readme_updated: false }`

**다른 점** 연결을 받는다 — 보관본 가져오기([[SYNC-MS-013#ProjectService.init_project]] 8)가 막 넣은 행이 있는 자기 저장점을 넘긴다(파이썬 `session`). 그때 10의 그래프 만들기는 아직 커밋되지 않은 프로젝트를 못 보고 그냥 끝날 수 있다 — 가져오기가 커밋 뒤에 한 번 더 건다 · 연결 풀도 받는다 — 연결은 트랜잭션이라 따로 띄운 그래프 만들기에 줄 수 없다 · 작성자는 늘 로컬 사용자라 `author.unknown`이 없다

**예외** 어느 단계든 실패하면 되돌리고 `! RebuildFailed { reason }`(로그에 남긴다)

**호출하는 것** [[#pipeline.write_lock]] · [[SYNC-MS-013#ProjectService.get]] · [[SYNC-MS-019#Git.fetch]] · [[SYNC-MS-019#Git.checkout]] · [[#pipeline.type_of_dir]] · [[SYNC-MS-015#ReferenceService.clear]] · [[SYNC-MS-014#SpecService.clear_index]] · [[SYNC-MS-019#Git.list]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-019#Git.log]] · [[SYNC-MS-019#Git.read]] · [[SYNC-MS-016#AccountService.user_for_commit]] · [[SYNC-MS-014#SpecService.apply_status]] · [[SYNC-MS-014#SpecService.validate]] · [[SYNC-MS-014#SpecService.create]] · [[SYNC-MS-014#SpecService.detect_deleted_items]] · [[SYNC-MS-014#SpecService.save]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-015#ReferenceService.extract]] · [[SYNC-MS-014#SpecService.item_pks]] · [[SYNC-MS-014#SpecService.mark_convention_error]] · [[SYNC-MS-015#ReferenceService.resolve_missing]] · [[#pipeline.schedule_code_graph]]

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 재구축 뒤 그래프가 생긴다 · DB를 비운 뒤 재구축 → 문서·항목·참조·버전 수가 저장소와 같다 · 항목 pk가 전후로 같다 · `status(` 커밋 → 판이 늘지 않고 상태 변경 행 · 두 번 해도 상태 변경 행이 늘지 않는다 · 지웠다 되살린 문서가 있어도 끝난다 · 중간 실패 → DB가 재구축 전과 같다

---

#### pipeline.upload_code 서버 저장소에 코드 올리기

**시그니처**
```rust
pub async fn upload_code(pool: &PgPool, repos: &ServerRepos, code: &str, files: &IndexMap<String, String>, delete: &[String], message: &str, author: &Author) -> Result<UploadResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.upload_code]] · [[SYNC-SEQ-001#SEQ-30]] · [[SYNC-UC-001#UC-A10]] · [[SYNC-API-002#upload_code]]

**처리** [[SYNC-MS-007#pipeline.upload_code]]과 같은 차례·같은 문장
0. `ProjectService.get_owned(code, author.user)` — 남의 것이면 `not-found`
1. 서버 저장이 아니면 `! StorageMismatch { storage }` — 싱크독_로컬에서는 생기지 않는다
2. 한도 — UTF-8 바이트 합 > 5MiB 또는 파일 수 + 지운 경로 수 > 500이면 `! UploadTooLarge { limit: {bytes: 5242880, count: 500}, size, count }`(락 밖)
3. 경로마다(올릴 것 → 지울 것 차례) 거절 사유 — 빈 경로(파이썬 `strip` 뒤) `빈 경로` · `\` `역슬래시 — / 로 쓴다` · 절대 경로 `절대 경로` · `..` 조각 `상위 경로(..)` · `.git` 조각 `.git` · `docs/specs`로 시작 `명세 경로 — create_document·update_document로 쓴다` · 이름(소문자)이 비밀 꼴(파이썬 `CODE_DENY` + `fnmatch`) `비밀 꼴` · 그다음 거절되지 않은 올릴 것 가운데 NUL이 든 것 `글자가 아니다(이진)` · 하나라도 있으면 `! UploadPathRefused { paths: [{path, reason}] }`
4. `read_pending(code, author.user)`
5. 쓰기 락 안에서 `before = git.fetch(작업 사본)` · `commit = git.commit_push(작업 사본, message, author.user, files, delete)`
6. `read_pending(code, author.user)` — 처리 지점을 이 커밋으로 옮기고, 코드가 바뀌었으면 커밋 처리(5a)가 코드 그래프를 건다(명세 경로가 없으니 버전은 생기지 않는다)
7. `→ UploadResult { commit, changed: commit != before, files: 파일 수, deleted: 지운 경로 수 }`

**다른 점** 경로 규칙의 `PurePosixPath`는 파이썬 판처럼 `/`로 조각낸다(빈 조각·`.` 조각은 버린다 — 파이썬 `parts`), 절대 경로는 `/`로 시작

**예외** `not-found` · `upload-too-large` · `upload-path-refused` · `push-failed` · git 실패

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[#pipeline.read_pending]] · [[#pipeline.write_lock]] · [[SYNC-MS-019#Git.fetch]] · [[SYNC-MS-019#Git.commit_push]]

**테스트 관점** 파일 둘 + 지운 경로 하나 → 커밋 하나, 작성자가 토큰 주인, 처리 지점 = 그 커밋 · 같은 내용 → `changed=false` · 5MiB+1바이트·501개 → `upload-too-large` · 거절 경로 여덟 → `upload-path-refused`에 전부, 원본 그대로 · 먼저 push된 명세 커밋이 올린 뒤에도 문서로 살아 있다(4)

---

#### pipeline.move_to_server 서버 저장으로 옮기기 — 이미 서버다

**시그니처**
```rust
pub async fn move_to_server(pool: &PgPool, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<MoveResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.move_to_server]] 0·1 · [[SYNC-API-001#POST/api/admin/repos/{code}/move-to-server]]

**처리** `ProjectService.get_owned(code, user)` · `! StorageMismatch { storage: "server", detail: "이미 서버 저장이다" }`

**다른 점** 서버 저장뿐이라 1에서 늘 멈춘다 — 옮기는 갈래(복제·통지 거두기·원격 바꾸기)가 없다

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]]

**테스트 관점** 내 것 → `storage-mismatch` · 남의 것 → `not-found`

---

#### pipeline.move_to_github GitHub 저장으로 되돌리기 — 켜지 않은 방식

**시그니처**
```rust
pub async fn move_to_github(pool: &PgPool, repos: &ServerRepos, code: &str, user: &UserRow, remote_url: &str) -> Result<MoveResult, Problem>
```

근거: [[SYNC-MS-007#pipeline.move_to_github]] 0·1·1a · [[SYNC-API-001#POST/api/admin/repos/{code}/move-to-github]]

**처리** `ProjectService.get_owned(code, user)` · `! StorageUnavailable { storage: "github", enabled: ["server"] }`(1a — 싱크독_로컬)

**다른 점** 1a에서 늘 멈춘다 — `remote_url`은 받기만 한다(본문 검사는 입구가 한다)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]]

**테스트 관점** 내 것 → `storage-unavailable` · 남의 것 → `not-found`

---

#### pipeline.catch_up 밀린 커밋 따라잡기

**시그니처**
```rust
pub async fn catch_up(pool: &PgPool, repos: &ServerRepos) -> Result<Vec<SaveResult>, Problem>
```

근거: [[SYNC-MS-007#scheduler.catch_up]] · [[SYNC-INFRA-001]] 9.1 켜기 · [[SYNC-UC-001#UC-G1]] 1a·1b

**처리** [[SYNC-MS-007#scheduler.catch_up]]과 같다 — `ProjectService.list_projects()`의 저장소마다, 읽기 락 안에서
1. 처리 지점을 다시 읽고 `head = git.fetch(작업 사본)`
2. `DB: repositories update behind_by = (처리 지점이 있으면 git.rev_list_count("{처리 지점}..{head}"), 없으면 없음), fetched_at=now, fetch_error=없음` 커밋
3. `head`가 처리 지점과 다르면 `process_commit(code, head, locked=true)`
- 저장소 하나가 실패해도 다음 — 그 저장소의 `fetch_error`에 사유 앞 300자를 적는다(못 적으면 로그만) · `behind_by`는 건드리지 않는다
4. `→` 처리 결과 모음

**다른 점** 파이썬은 `scheduler` 모듈이다 — Rust는 조율을 한 곳에 두려고 pipeline에 둔다

**호출하는 것** [[SYNC-MS-013#ProjectService.list_projects]] · [[#pipeline.read_lock]] · [[SYNC-MS-013#ProjectService.get]] · [[SYNC-MS-019#Git.fetch]] · [[SYNC-MS-019#Git.rev_list_count]] · [[#pipeline.process_commit]]

**테스트 관점** 원격이 앞서 있으면 문서가 생긴다 · 같으면 `fetched_at`만 · 앞 저장소가 실패해도 뒤 저장소는 처리되고, 실패한 쪽 `fetch_error`가 남았다가 다음 성공이 지운다

---

#### pipeline.poll_loop 주기 확인

**시그니처**
```rust
pub async fn poll_loop(pool: PgPool, repos: Arc<ServerRepos>, interval: Duration)
```

근거: [[SYNC-MS-007#scheduler.poll_loop]] · [[SYNC-INFRA-001]] 9.1 켜기

**처리** `interval` 자고 [[#pipeline.catch_up]] — 끝없이. 한 주기의 실패는 로그만 남기고 다음 주기로(목록 읽기에서 DB가 잠깐 죽어도 폴링이 멈추지 않는다). 켤 때 한 번은 따로다([[SYNC-MS-012#runtime.run]])

**다른 점** 주기는 300초로 고정이다 — 설정 파일의 키는 다섯뿐이다(INFRA 9.3, 사용자 결정 2026-10-07). 파이썬 판 `POLL_INTERVAL_SECONDS` 기본값과 같다

**호출하는 것** [[#pipeline.catch_up]]

**테스트 관점** 짧은 주기로 띄우고 원격에 민 커밋이 다음 주기에 문서가 된다

---

#### pipeline.schedule_code_graph 코드 그래프 만들기를 걸어 둔다

**시그니처**
```rust
pub fn schedule_code_graph(pool: &PgPool, repos: &ServerRepos, code: &str, commit: &str)
```

근거: [[SYNC-MS-007#pipeline.schedule_code_graph]] · [[SYNC-UC-001#UC-S8]] 2b

**처리** [[SYNC-MS-007#pipeline.schedule_code_graph]]와 같다 — 저장소 락 밖, 프로젝트마다 하나. 그 프로젝트의 만들기가 돌고 있으면 「다음」만 적고(나중 것이 이긴다) 돌아온다 · 아니면 따로 띄운 작업이 `build_code_graph(code, commit)`를 하고, 끝난 뒤 「다음」이 있으면 그것으로 한 번 더 — 없을 때까지

**다른 점** 연결 풀과 저장소 자리를 받는다(파이썬은 모듈 전역)

**호출하는 것** [[#pipeline.build_code_graph]]

**테스트 관점** 돌고 있는 동안 둘을 걸면 마지막 것으로 한 번 더 만들고 끝난다 · 다른 프로젝트는 따로 돈다

---

#### pipeline.build_code_graph 코드 그래프를 만든다

**시그니처**
```rust
pub async fn build_code_graph(pool: &PgPool, repos: &ServerRepos, code: &str, commit: &str)
```

근거: [[SYNC-MS-007#pipeline.build_code_graph]] · [[SYNC-UC-001#UC-S8]] · [[SYNC-INFRA-001]] 4.3

**처리** [[SYNC-MS-007#pipeline.build_code_graph]]와 같은 차례
1. `ProjectService.get(code)` — 없으면 그냥 끝(그새 해제됐다)
2. 임시 폴더에 `git.archive(작업 사본, commit, 임시)` — 작업 사본을 건드리지 않는다
3. `(source, raw) = codegraph.load(임시)` · `graph = codegraph.communities(raw, codegraph.enrich(임시, codegraph.reduce(raw)))` — 커뮤니티는 보강 뒤에(보강이 더한 함수도 받는다) · 파일 읽기·파싱·군집은 막히는 일이라 따로(블로킹 작업)에서
4. `CodeGraphService.save(project, commit, source, graph)` 커밋 · 로그 「code graph code=… commit=… source=… functions=n calls=n communities=n elapsed=…」
- 어느 단계든 실패하면 `CodeGraphService.fail(project, commit, 이유)` 커밋(그새 해제됐으면 남길 곳이 없다 — 삼킨다) · 경고 로그 — 배치라 옛 그래프를 두고 이유만 남긴다(UC-S8 2a). 이유는 `CodeGraphFailed`면 그 문장, 아니면 오류 문장

**호출하는 것** [[SYNC-MS-013#ProjectService.get]] · [[SYNC-MS-019#Git.archive]] · [[SYNC-MS-022#codegraph.load]] · [[SYNC-MS-022#codegraph.reduce]] · [[SYNC-MS-022#codegraph.enrich]] · [[SYNC-MS-022#codegraph.communities]] · [[SYNC-MS-022#CodeGraphService.save]] · [[SYNC-MS-022#CodeGraphService.fail]]

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 파이썬 코드를 민 커밋 → 함수·선·항목·커뮤니티가 든 그래프 행, 출처 `server` · 커밋된 graph.json이 있으면 `repo` · 깨진 graph.json → 옛 그래프를 두고 `error` · 해제된 프로젝트 → 아무것도 안 한다

---

## 3. 미결사항

없음.
