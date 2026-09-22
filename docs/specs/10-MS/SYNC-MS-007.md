---
doc_id: SYNC-MS-007
type: MS
title: MINISPEC — pipeline — 쓰기 조율
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — pipeline — 쓰기 조율

## 0. 이 문서가 다루는 것

`core/pipeline.py`의 함수 8개와 `scheduler.py`의 주기 함수 2개. 클래스 명세 [[SYNC-DOM-002]] 4.7의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`pipeline`은 조율자다. 자기 테이블이 없고 서비스를 순서대로 부른다. 세 입구(MCP·웹·GitHub)가 전부 `save_pipeline`로 들어온다. **프로젝트를 여는 첫 줄이 소유를 가른다** — 사람이 있는 입구(MCP·웹)는 [[SYNC-MS-001#ProjectService.get_owned]], 사람이 없는 입구(GitHub·폴링)는 `get`([[SYNC-PRD-001#R12]]). 남의 프로젝트는 `not-found`로 끝나고 DB·저장소에 아무것도 남지 않는다. 상태 변경·되돌리기도 조율이라 여기(원래 SpecService에 있었으나 세션·async가 꼬여 옮겼다 — B2 되먹임).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#pipeline.save_pipeline]] | 본문 저장 파이프라인 |
| [[#pipeline.change_status]] | 초안 ⇄ 완료 토글 |
| [[#pipeline.revert]] | 되돌리기 |
| [[#pipeline.process_commit]] | GitHub 커밋 처리 |
| [[#pipeline.rebuild]] | 인덱스 재구축 |
| [[#pipeline.trash_document]] | 휴지통에 넣기 |
| [[#pipeline.restore_document]] | 휴지통에서 되살리기 |
| [[#pipeline.purge_document]] | 완전 삭제 |
| [[#scheduler.catch_up]] | 밀린 커밋 따라잡기 |
| [[#scheduler.poll_loop]] | 주기 폴링 |

---

## 2. 함수

#### pipeline.save_pipeline 본문 저장 파이프라인

**시그니처**
```python
async def save_pipeline(entry: Entry, doc_id: str | None, doc_type: DocType | None,
                        body: str, expected_version: int | None,
                        project_code: str | None,
                        author: Author, message: str,
                        changed_items: list[str] | None = None,
                        confirm_item_deletion: bool = False,
                        commit_hash: str | None = None,
                        reason: str | None = None,
                        session: Session | None = None,
                        restore: bool = False) -> SaveResult
```

근거: [[SYNC-SEQ-001#SEQ-1]] · [[SYNC-UC-001#UC-A6]] · [[SYNC-DOM-002#SpecService]] 4.7

**입력**

| 인자 | 뜻 | 제약 |
|---|---|---|
| `entry` | 어느 입구 | `mcp` `web_revert` `web_status` `github` |
| `doc_id` | 대상 문서. 생성이면 None | 생성은 `entry=mcp`만 |
| `doc_type` | 생성 시 타입 | 생성이면 필수 |
| `project_code` | 생성 시 프로젝트 | 생성이면 필수. 수정이면 None — `doc_id` 앞부분에서 얻는다 |
| `body` | 원본 MD 전체 | frontmatter 포함 |
| `expected_version` | 낙관적 잠금 | `mcp`·`web_*`면 필수. `github`면 None |
| `author` | 작성 주체 | `kind`·`user`·`instructed_by`·`via` |
| `message` | 커밋 메시지 | `mcp`: 에이전트가 준 것. `web_status`: `status(…)`. `web_revert`: `revert(…)`. `github`: 원 커밋 메시지 |
| `changed_items` | 바뀐 항목 ID | `mcp`만. 나머지는 None → diff 판정 |
| `confirm_item_deletion` | 삭제 확인됨 | |
| `commit_hash` | 이미 있는 커밋 | `github`만. push 단계 건너뜀 |
| `reason` | 상태 변경 사유 | `web_status`만. `apply_status`로 |
| `session` | 호출자 세션 | `change_status`·`revert`가 넘긴다. None이면 스스로 연다(DEV-10) |
| `restore` | 되살리기 중 | `restore_document`만 True — 2단계의 `document-trashed` 검사를 지난다 |

**처리**
0. if `session is None and entry != github` → `read_pending(code, author.user)` — **락 밖에서, 쓰기 전에**([[#pipeline.read_pending]]). 세션이 넘어왔으면 부른 쪽(`change_status`·`revert`·`restore_document`)이 이미 읽었고, `github`는 자기가 처리 중이라 부르면 무한 재귀다

1. `code = project_code if doc_id is None else doc_id.split("-")[0]` · `project = ProjectService.get(code) if entry == github else ProjectService.get_owned(code, author.user)` — 사람이 있는 입구(mcp·web_revert·web_status)는 소유자만 연다. 남의 것이면 `! not-found {resource: project}`, **문서를 읽기 전에** · `repo = project.repository`. **저장소 락 획득** (`asyncio.Lock`, 저장소별). 이후 전부 락 안. **세션도 여기서 연다** — 서비스는 세션을 열지 않는다(DEV-10)
2. if `doc_id is not None` → `document = spec.get_document(doc_id)`, `doc_type = document.doc_type` · if 없음 → `! not-found` · **if `document.trashed_at`이고 `entry != github`이고 되살리기가 아니면 → `! document-trashed`** — 휴지통 문서는 되살린 뒤 고친다. github는 파일이 다시 push된 것이니 그 자체가 되살리기(`save` 7이 `trashed_at`을 비운다)
   (`entry == github`도 같다 · if github 경로에서 없음 → process_commit이 `doc_id=None`으로 다시 부른다)
3. if `doc_id is None` (생성) → `doc_id = spec.issue_doc_id(project_id, project.code, doc_type)`, `body = spec.apply_frontmatter(body, doc_id, doc_type, "draft")`
3a. if 생성이고 `entry == mcp` → `unmet = spec.precondition(project.id, doc_type, fm.title)` · if `unmet` → `! precondition-unmet {requires, have}`, 락 해제. **push·DB 쓰기 전.** github 경로는 안 본다 — 원본이 진실이다. DOM이 아니면 `precondition`이 `None`을 준다([[SYNC-STD-001]] 2.6)
4. `(violations, warnings) = spec.validate(body, doc_type, entry, current_status=document.status if document else None)`
   - if `violations and entry != github` → `! convention-violation {violations, warnings}`, 락 해제
   - if `violations and entry == github` → 계속. 8단계에 `has_convention_error=True`로 전달
5. if `entry != github and expected_version != document.current_version_no` → `! version-conflict {current_version, current_body}`
6. if `entry != web_status and document` → `deleted = spec.detect_deleted_items(document, body)`; `deleted`의 pk마다 `refs = reference.downstream(pk)`
   - if `any(refs) and not confirm_item_deletion` → `! item-deletion-needs-confirm {deleted_items: [{item_id, downstream: [{doc_id, item_id, display_name}]}]}`
   - **`downstream`은 pk가 아니라 이름이다.** [[SYNC-API-002]] 4장이 에이전트에게 "사람에게 보여주고 확인받은 뒤" 다시 부르라고 시키는데, `items.id` 숫자는 사람에게 보여줄 수 없고 그것을 이름으로 바꾸는 MCP 도구도 없다. 그러면 사람은 **무엇이 끊어지는지 모르는 채로 승낙**하게 되어 확인 절차의 뜻이 사라진다(#50). `SpecService.describe_items`가 이미 그 변환을 한다 — 여기서 한 번 부른다
6a. **완료 상태 문서를 고치면 여기서 본문의 `status:`를 `draft`로 낮춘다** — `entry != web_status`이고 `document.status == approved`이고 `body != document.current_body`일 때. github 경로는 **frontmatter가 아직 `approved`일 때만** — 작성자가 같은 커밋에서 스스로 내렸으면 그게 원본의 진실이다. 자동 강등(9단계 뒤 SEQ-1 6a)을 **push 전에** 본문에 반영하는 것이다

   **왜 여기인가.** 강등을 DB에만 적으면 저장소 frontmatter는 `approved`로 남아 [[SYNC-STD-001]] 1.2의 "`status`가 진실이다"가 깨진다. 그리고 다음 저장이 막힌다 — 에이전트가 `get_document`로 받은 본문(`approved`)을 그대로 돌려주면 `frontmatter.status_change` 위반이 된다. **서버가 준 것을 서버가 거부하므로 그 문서는 영영 못 고친다**(#47)

   **github 경로는 본문만 고쳐서는 저장소가 안 바뀐다** — 커밋이 이미 저장소에 있기 때문이다. 그래서 여기서 커밋을 하나 더 민다: `status_commit_hash = git.commit_push(repo.workdir, f"status({doc_id}): approved → draft\n\n본문 수정으로 자동 강등", author, path, content=body)`. 8단계가 이 해시를 `spec.save`에 넘겨 `status_changes.commit_hash`에 적는다. **적지 않으면 다음 폴링이 [[#pipeline.process_commit]] 3a에서 걸러내지 못해, 앱이 민 커밋을 남의 편집으로 다시 저장한다.** 작성자는 그 커밋을 유발한 사람 그대로 둔다 — 판단은 앱이 했지만 원인은 그 사람의 편집이고, 그래야 `user_for_commit`이 사람을 찾는다 (#58)

   **서버가 에이전트의 본문을 고치는 유일한 자리다.** mcp·web_revert는 커밋을 하나로 둔다 — 저장마다 `status(…)` 커밋이 하나씩 더 쌓이면 이력이 본문 변경보다 상태 줄로 더 두꺼워진다. github만 둘이 되는 것은 첫 커밋을 우리가 만들지 않았기 때문이다

7. if `entry != github` → `commit_hash = git.commit_push(repo.workdir, message, author, path=STD-001 1.1 경로, content=body)` — **본문은 부른 쪽이 정한다.** 상태 토글은 저장소에서 읽은 것(change_status 4), 되돌리기는 옛 버전, MCP는 에이전트가 준 것이다. 0단계가 밀린 것을 먼저 읽었으므로 여기서 덮을 남의 커밋이 없다 · if 실패 → `! push-failed {reason}`, 락 해제. **여기까지 DB 쓰기 없음**
8. **트랜잭션 시작**
   - if 생성 → `version = spec.create(project_id, doc_id, doc_type, body, commit_hash, author, message, validate_result=4단계 결과)`
   - if `entry == web_status` → `spec.apply_status(document, body, commit_hash, author.user, reason)` (Document.status·current_body 갱신 + StatusChange). **Version 없음.** 9~10a 건너뛰고 14로
   - else → `version = spec.save(document, body, commit_hash, author, message, deleted, validate_result=4단계 결과, status_commit_hash=6a가 민 해시)` — **모든 경로.** 경고(`incomplete_warnings`)는 mcp 저장에도 남아야 완료 전환을 막는다. 위반은 github 경로에서만 저장까지 온다
9. `broken = reference.mark_missing(deleted)` — 사라진 항목을 가리키던 참조가 **그 자리에서** 미존재가 된다([[SYNC-MS-003#ReferenceService.mark_missing]]). 플래그를 세우지 않는다 — 참조 행이 스스로 끊어졌다고 말하고, UI-5 4a 배너·UI-4 3.2가 그것을 보여준다
10. `reference.extract(document_id, version.id, body, item_pks=spec.item_pks(document_id), upstream_doc_ids=frontmatter upstream)`
10a. `reference.resolve_missing(project_id, target_doc_id=doc_id)` — 이 문서(또는 항목)를 기다리던 미존재 참조를 푼다. 하위가 먼저 저장된 경우가 재구축까지 안 기다려도 되게(UC-S2 2a2)
10b~13. 없음 — 끊어진 참조 해제·전파 감지·상위 불일치·댓글 재배치가 있던 자리. 카드 V에서 걷어냈다. 되살아난 참조는 10a가 이미 잇는다
14. **커밋.** 락 해제
15. `→ SaveResult(doc_id, version_no, commit_hash, status, warnings, next_step)` — `deleted`가 있었으면 `warnings`에 `ref.broken: {n}`(9단계의 `broken`)을 섞는다. 에이전트가 「무엇이 끊어졌나」를 응답에서 본다 — `next_step`은 `entry == mcp`면 `f"{doc_id} v{version_no} 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)"`, 아니면 `None`. 규약을 에이전트가 잊어도 응답이 매번 다시 말한다([[SYNC-STD-001]] 1.8)

**출력** `SaveResult`. [[SYNC-API-001]] 4장 스키마와 같다.

**예외**

| 조건 | 에러 | 단계 |
|---|---|---|
| 남의 프로젝트 (github 아님) · 없는 프로젝트 | `not-found {resource: project}` | 1 |
| 문서 없음 | `not-found` | 2 |
| DOM 선행조건 미충족 (생성·mcp) | `precondition-unmet` | 3a |
| 규약 위반 (mcp·web) | `convention-violation` | 4 |
| 버전 불일치 | `version-conflict` | 5 |
| 삭제 항목에 하위 참조, 미확인 | `item-deletion-needs-confirm` | 6 |
| push 실패 | `push-failed` | 7 |
| 8~10a 중 DB 오류 | 트랜잭션 롤백. 커밋은 이미 원격에 있으므로 `repository.last_processed_commit`을 갱신하지 않아 폴링이 다시 처리한다 | 8 |

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `ProjectService.get`(github) · [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-002#SpecService.issue_doc_id]] [[SYNC-MS-002#SpecService.apply_frontmatter]] [[SYNC-MS-002#SpecService.validate]] [[SYNC-MS-002#SpecService.detect_deleted_items]] [[SYNC-MS-002#SpecService.create]] [[SYNC-MS-002#SpecService.save]] · `ReferenceService.downstream` · [[SYNC-MS-003#ReferenceService.mark_missing]] · `ReferenceService.extract` · `ReferenceService.resolve_missing` · `git.commit_push`

**테스트 관점**
- 정상 수정: 새 버전 번호 +1, 커밋 존재, 참조 갱신
- **남의 프로젝트에 mcp로 생성·수정: `not-found`(project). DB·커밋 없음, 문서 존재 여부가 응답에 안 새어 나감** · github 경로는 소유와 무관하게 저장된다
- 규약 위반 mcp: DB 변경 없음, 커밋 없음
- 규약 위반 github: 저장됨, `has_convention_error=True`
- 버전 불일치: `current_body`가 응답에 있음
- 항목 삭제 미확인: 저장 안 됨. `confirm=True`로 재요청 시 그 항목을 가리키던 참조가 `is_missing`이고 응답 `warnings`에 `ref.broken`
- push 실패: DB 변경 없음
- 완료 문서 수정: 상태가 `draft`, StatusChange 행 하나
- **완료 문서를 github 커밋으로 고침: DB가 `draft`이고 저장소 frontmatter도 `draft`다. `status(…)` 커밋이 하나 더 있고 `StatusChange.commit_hash`가 그 해시다** (#58)
- **그 status 커밋은 다음 `process_commit`에서 3a로 걸러진다** — 버전이 하나 더 생기지 않는다
- **github 커밋이 frontmatter를 `draft`로 내리면서 본문도 고침: `draft`. 강등이 덮지 않는다**
- `web_status`: Version 없음, StatusChange에 commit_hash
- 동시 저장 둘: 락 때문에 직렬화. 둘째가 version-conflict
- 8단계 이후 DB 오류: 트랜잭션 롤백, `last_processed_commit` 그대로

---

#### pipeline.read_pending 쓰기 전에 밀린 커밋을 읽는다

**시그니처**
```python
async def read_pending(code: str, user: User) -> int
```

근거: [[SYNC-UC-001#UC-H8]] 1d · [[SYNC-UC-001#UC-G1]] · #137

**입력** 프로젝트 코드, 누른 사람

**처리**
1. `ProjectService.get_owned(code, user)` — 남의 것이면 `! not-found {resource: project}`. **쓰기 경로의 소유 검사를 겸한다**
1a. **읽기 락**(`_read_lock(code)`, 쓰기 락과 다른 것)을 잡는다 — 두 요청이 같은 작업 사본에 동시에 `git fetch`를 걸면 git이 인덱스 잠금으로 죽는다. 락 안에서 `last_processed_commit`을 **다시 읽는다**: 앞서 기다린 요청이 이미 따라잡아 놨을 수 있다
1b. **쓰기 락과 따로인 이유** — 4단계의 `process_commit`이 파일마다 쓰기 락을 잡는다. 같은 락이면 교착한다
2. `head = git.fetch(repo.workdir)`
3. if `head == repo.last_processed_commit` → **`fetched_at`을 지금으로 적고** `→ 0`. 방금 확인했다는 사실 자체가 화면이 보여줄 값이다(카드 AF) — 안 적으면 1초 전에 확인한 저장소가 5분 전으로 보인다. `behind_by`도 0으로 둔다(방금 재서 같았다)
3a. `last_processed_commit`이 **비어 있어도 `→ 0`.** 그 값이 비는 것은 등록 중뿐이고([[SYNC-MS-001#ProjectService.init_project]]가 첫 커밋 해시를, `import_existing`은 재구축이 head를 적는다) 그 둘은 자기가 저장소를 읽는다
4. `results = process_commit(repo, head)` → `→ len(results)`

**왜 이것이 먼저인가 (#137).** 저장소에 쓰는 일은 전부 「덮어쓰기」다. 아직 읽지 않은 커밋이 있는 채로 쓰면 그 내용이 사라지는데, `git.commit_push`가 `reset --hard origin/main` 뒤에 본문을 덮으므로 push가 거부되지도 않아 **조용히** 사라진다. 읽기를 먼저 하면 덮을 것이 없다.

**쓰기 락 밖에서 부른다.** `process_commit`은 파일마다 `save_pipeline`이 같은 `_lock(code)`를 잡았다 논다 — 쓰기 락 안에서 부르면 교착한다(재진입 불가). 그래서 부르는 자리는 전부 세션·쓰기 락을 열기 **전**이다. 대신 자기 읽기 락으로 동시 `fetch`를 막는다(1a).

**부르는 곳** [[#pipeline.change_status]] 0 · [[#pipeline.revert]] 0 · [[#pipeline.restore_document]] 0 · [[#pipeline.trash_document]] 0 · [[#pipeline.save_pipeline]] 0(세션을 안 받았고 `entry != github`일 때만 — 세션이 넘어온 것은 부른 쪽이 이미 읽었다는 뜻이고, `github`는 자기가 처리 중이라 부르면 무한 재귀다)

**출력** 읽어 반영한 문서 수. 밀린 것이 없으면 0

**예외** `not-found`(1) · `git.fetch` 실패는 그대로 올린다 — 저장소에 닿지 못하면 쓰지도 못한다

**테스트 관점** 같은 프로젝트에 동시에 둘이 써도 `fetch`가 겹치지 않는다(읽기 락) · 밀린 것이 없으면 0이고 커밋이 안 생긴다 · **밀린 것이 없어도 `fetched_at`이 갱신된다** · 밖에서 push한 뒤 부르면 그 문서가 DB에 들어오고 `last_processed_commit`이 head가 된다 · 두 번 불러도 두 번째는 0(멱등) · 남의 프로젝트 → `not-found` · **`github` 경로에서는 불리지 않는다**(재귀 방지)

---

#### pipeline.change_status 초안 ⇄ 완료 토글

**시그니처** `async def change_status(doc_id: str, to: DocStatus, user: User, reason: str | None = None) -> DocumentSummary`

근거: [[SYNC-SEQ-001#SEQ-5]] · [[SYNC-UC-001#UC-H8]] · [[SYNC-API-001#POST/api/docs/{docId}/status]] · **조율이라 pipeline에 있다** — 검사·frontmatter·push·상태 기록을 잇는다. SpecService는 DB만

**입력** `doc_id`, 목표 상태 `to`(`draft` | `approved`), 누른 사람, 사유(선택 — 웹 토글은 안 보낸다)

**처리**
0. `read_pending(code, user)` — **밀린 커밋을 먼저 읽는다**([[#pipeline.read_pending]], UC-H8 1d). 소유 검사도 여기서 끝난다. 문서를 읽기 전에, 락 밖에서
1. `document = get_document(doc_id)` · `trashed_at`이면 `! document-trashed`
2. `missing = 중복 접은 [e.raw_target for e in ReferenceService.upstream_of_document(document.id, include_missing=True) if e.is_missing]`
2a. if `to == approved and (document.has_convention_error or document.incomplete_warnings or missing)` → `! status-blocked {convention_error_detail, warnings: incomplete_warnings + [f"ref.missing: {t}" for t in missing]}` (UC-H8 1a). `draft`로 내리는 것은 막지 않는다. **혼자 써도 이 검사는 남는다** — 완료는 「규약에 맞고 참조가 다 이어진 문서」라는 뜻이고, 그 뜻이 없으면 UI-5 4a 배너가 「알아두세요」로 약해진다
2b. **끊어진 참조는 읽을 때 센다 — 컬럼에 없다.** `documents.incomplete_warnings`에 넣지 않는 이유는 [[SYNC-STD-001]] 4장에 있다. 값은 UI-5 배너가 보는 `document_view.missing_refs`와 **같아야 한다** — 한쪽만 막거나 한쪽만 보여주면 사람이 이유 없이 막힌다
2c. `warnings`에 `ref.missing: {대상}` 꼴로 섞어 보낸다. `incomplete_warnings`가 이미 `section.missing: 시나리오` 꼴이라 같은 규격이고, 화면이 `:` 앞을 rule로 잘라 한국어로 옮긴다([[SYNC-STD-001]] 4장 화면 문구 열)
3. 없음 — 상위 대조가 있던 자리. 카드 V에서 걷어냈다. 완료는 사람 하나가 누르는 토글이다
3a. if `document.status == to` → 아무것도 안 하고 현재 반환 (멱등)
4. `body = git.read(repo.workdir, STD-001 1.1 경로, "origin/main")` → `new_body` = 그 본문의 frontmatter `status:` 줄만 교체. **원본이 진실이다**([[SYNC-DOM-001#StatusChange]]) — `current_body`는 조회 캐시라 쓰기 출처로 쓰지 않는다. 0단계가 방금 `fetch`했으므로 `origin/main`이 최신이다
4a. 저장소에서 못 읽으면(`GitError` — 파일이 아직 없다) `current_body`로 떨어지고 경고 로그 한 줄. 이때 커밋은 파일을 만드는 복구가 된다
4b. **왜 저장소에서 읽나 (#137).** `current_body`로 만든 본문을 커밋하면, 아직 읽지 않은 커밋이 있을 때 그 내용이 통째로 되돌아간다. `git.commit_push`가 `reset --hard origin/main` 뒤에 본문을 덮어쓰므로 push가 거부되지도 않아 조용히 사라진다. 실제로 카드 AA 완료란이 그렇게 날아갔다
5. `save_pipeline(entry=web_status, doc_id, None, new_body, expected_version=current_version_no, project_code=None, author=Author(human, user, None, web), message=f"status({doc_id}): {from} → {to}\n\n{reason or ''}", reason=reason)` — **같은 세션**. `save_pipeline`이 세션을 인자로 받거나(있으면 재사용) 없으면 연다. push 후 `spec.apply_status(…, reason)`
6. `→ DocumentSummary`

**출력** 바뀐 문서 요약

**예외** `not-found`(0) · `status-blocked` · `document-trashed` · 파이프라인의 `version-conflict`·`push-failed` 전파

**호출하는 것** [[SYNC-MS-007#pipeline.read_pending]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-007#pipeline.save_pipeline]] [[SYNC-MS-003#ReferenceService.upstream_of_document]] · `git.read`

**테스트 관점** **저장소를 앞세워 놓고 토글 → 그 커밋의 내용이 살아 있고 상태 커밋의 diff가 한 줄 추가·한 줄 삭제(#137)** · 규약 오류 문서를 `approved`로 → blocked · **미존재 참조가 있는 문서를 `approved`로 → blocked이고 `warnings`에 `ref.missing:`이 있다** · 같은 문서를 `draft`로 → 됨 · **상대 문서가 들어와 `resolve_missing`이 풀면 그 문서를 다시 저장하지 않아도 완료된다**(읽을 때 계산한다는 증거) · 정상 완료 → frontmatter `status: approved` 커밋 존재, Version 없음, StatusChange에 commit_hash · 같은 상태로 다시 → 커밋 없음 · `reason` 없이 불러도 된다 · 휴지통 문서 → `document-trashed` · **남의 프로젝트 문서 → `not-found`(project), 상태 그대로**

---

#### pipeline.trash_document 휴지통에 넣기

**시그니처** `async def trash_document(doc_id: str, author: Author, confirm: bool) -> TrashResult` — `TrashResult(doc_id, commit_hash, broken_refs, next_step)`

근거: [[SYNC-SEQ-001#SEQ-22]] · [[SYNC-UC-001#UC-A7]] · [[SYNC-UC-001#UC-H18]] 1~3 · [[SYNC-API-002#delete_document]] · [[SYNC-API-001#DELETE/api/docs/{docId}]] · [[SYNC-PRD-001#N3]]

**입력** `doc_id` · `author` — MCP면 `_agent_author`, 웹이면 `Author(human, user, None, web_status)` · `confirm` — MCP는 에이전트가 준 것, 웹은 `True`(다이얼로그 13이 받았다)

**처리**
0. `read_pending(code, author.user)` — **락 밖에서, 쓰기 전에**([[#pipeline.read_pending]]). 소유 검사도 여기서 끝난다
— 아래는 저장소 락 안 —
1. `document = spec.get_document(doc_id)` · 없으면 `! not-found` · `trashed_at`이면 `! document-trashed`
2. 끊어질 것 — `inbound = reference.inbound_of_document(id)`(이름으로). **막지 않는다** — 보여준다
3. if `not confirm` → `! document-deletion-needs-confirm {doc_id, title, version_count, inbound_refs}`. 웹은 여기 안 온다
4. `commit_hash = git.commit_push(repo.workdir, f"spec({doc_id}): 휴지통", author, delete=[STD-001 1.1 경로])` · 실패 → `! push-failed`. **여기까지 DB 쓰기 없음**
5. **트랜잭션** — `pks = spec.trash(document, commit_hash, author)` · `broken = reference.mark_missing(pks)` · 커밋 · 락 해제
6. `→ TrashResult(doc_id, commit_hash, broken, next_step=f"{doc_id} 휴지통에 넣음 — 끊어진 참조 {broken}. 사람에게 알리고 멈춘다")`

**예외** `not-found`(0·1) · `document-trashed`(1) · `document-deletion-needs-confirm`(3) · `push-failed`(4)

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-003#ReferenceService.inbound_of_document]] [[SYNC-MS-009#git.commit_push]] [[SYNC-MS-002#SpecService.trash]] [[SYNC-MS-003#ReferenceService.mark_missing]]

**테스트 관점** 남이 가리키는 문서도 confirm이면 들어간다 — `broken_refs`가 그 수이고 그 참조들이 `is_missing` · 원격에서 파일 사라짐, 커밋 메시지 `spec(…): 휴지통` · 행·버전 남음, `trashed_at` 있음, 목록에서 빠짐 · 두 번 넣으면 `document-trashed` · 그 뒤 폴링이 `D`를 건너뛰고 `last_processed_commit`이 나아감 · 휴지통 문서에 `update_document`·상태 변경 → `document-trashed`

---

#### pipeline.restore_document 휴지통에서 되살리기

**시그니처** `async def restore_document(doc_id: str, author: Author) -> SaveResult`

근거: [[SYNC-SEQ-001#SEQ-23]] · [[SYNC-UC-001#UC-A8]] · [[SYNC-UC-001#UC-H18]] 4~5 · [[SYNC-API-002#restore_document]] · [[SYNC-API-001#POST/api/docs/{docId}/restore]]

**처리**
0. `read_pending(code, author.user)` — **밀린 커밋을 먼저 읽는다**([[#pipeline.read_pending]]). 소유 검사도 여기서. 락 밖
1. `document = spec.get_document(doc_id)` · `trashed_at` 없으면 `! document-not-trashed`
2. `hash = spec.trash_commit(document.id)` · `body = git.read(repo.workdir, path, f"{hash}^")` — 지우기 직전 내용
3. `body`의 frontmatter `status:`를 `draft`로 — DB가 `draft`라 mcp 경로의 `frontmatter.status_change`에 안 걸리게
4. `r = save_pipeline(entry=author.via가 mcp면 mcp 아니면 web_revert, doc_id, None, body, expected_version=current_version_no, project_code=None, author, message=f"spec({doc_id}): 되살림 — 휴지통에서", changed_items=[] (mcp) | None, session=같은 세션)` — `validate`는 휴지통 문서의 삭제 항목을 `item.reused`에서 빼고(MS-002 validate 3), `save`가 항목을 복구하고 `trashed_at`을 비운다(MS-002 save 3·7)
5. 없음 — 되살아난 항목을 가리키던 미존재 참조는 `save_pipeline` 10a의 `resolve_missing(target_doc_id=doc_id)`가 이미 다시 이었다. 따로 할 일이 없다
6. `→ r`

**예외** `not-found`(0·1) · `document-not-trashed`(1) · 파이프라인의 `convention-violation`(3a)·`push-failed`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-002#SpecService.trash_commit]] [[SYNC-MS-009#git.read]] [[#pipeline.save_pipeline]]

**테스트 관점** 넣기 → 되살리기 → 본문이 지우기 직전과 같고 버전 +1 · `trashed_at` null · 항목 `is_deleted` 풀림 · 하위에서 이 문서 항목을 가리키던 미존재 참조가 다시 이어진다 · 목록에 다시 나옴 · 휴지통에 없는 문서 → `document-not-trashed`

---

#### pipeline.purge_document 완전 삭제

**시그니처** `async def purge_document(doc_id: str, author: Author) -> None`

근거: [[SYNC-SEQ-001#SEQ-22]] 끝 · [[SYNC-UC-001#UC-H18]] 6~8 · [[SYNC-API-001#POST/api/docs/{docId}/purge]] · [[SYNC-PRD-001#N3]]

**처리** — 저장소 락 안. 웹에서만 부른다
0. `ProjectService.get_owned(doc_id.split("-")[0], author.user)` — v1에서 유일하게 프로젝트를 안 열던 함수다. 남의 것이면 `! not-found {resource: project}`
1. `document = spec.get_document(doc_id)` · `trashed_at` 없으면 `! document-not-trashed`
2. 문지기 하나 — `inbound = reference.inbound_of_document(id)` · 있으면 `! document-has-history {inbound_refs(이름)}`. **미존재 참조는 안 센다** — `to_*`가 비어 `inbound`에 안 잡히고, 그것은 이 문서가 아니라 가리키는 쪽의 사정이다
3. **트랜잭션** — `spec.delete_document(document)` · 커밋. 파일은 이미 저장소에 없다(휴지통 커밋) — push 없음
4. `→ None`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-003#ReferenceService.inbound_of_document]] [[SYNC-MS-002#SpecService.delete_document]]

**테스트 관점** **남의 프로젝트 → `not-found`, 행 그대로** · 휴지통 아닌 문서 → `document-not-trashed` · 남이 아직 가리킴 → `document-has-history`에 `inbound_refs` · 다 걷어낸 뒤 → 행 다섯 종류(documents·items·versions·status_changes·references) 0 · 남이 이 문서를 미존재로 가리키는 것은 막지 않는다 · 번호 재발급

---

#### pipeline.revert 되돌리기

**시그니처** `async def revert(doc_id: str, to_version: int, user: User, confirm_item_deletion: bool = False) -> SaveResult` — `pipeline`을 불러 async(DEV-16)

근거: [[SYNC-SEQ-001#SEQ-7]] · [[SYNC-UC-001#UC-H7]] · [[SYNC-API-001#POST/api/docs/{docId}/revert]] · 조율이라 pipeline

**처리**
0. `read_pending(code, user)` — **밀린 커밋을 먼저 읽는다**([[#pipeline.read_pending]]). 소유 검사도 여기서. 락 밖
1. `document = spec.get_document(doc_id)`; `old_body = spec.version_body(doc_id, to_version)` · 없으면 그쪽에서 `! not-found`
1a. 본문은 **`versions.body`에서 온다** — 되돌리기는 옛 버전을 쓰는 것이 목적이라 지금 저장소를 읽을 수 없다. 이름이 바뀐 문서는 옛 커밋에서 옛 경로에 살아(#39) 해시로 읽는 길도 안전하지 않다. 0단계가 밀린 것을 먼저 흡수하므로 남의 커밋을 덮지는 않는다
2. if `to_version == document.current_version_no` → `! already-current`(422)
3. `save_pipeline(entry=web_revert, doc_id, None, old_body, expected_version=current_version_no, project_code=None, author=Author(human, user, None, web), message=f"revert({doc_id}): v{current} → v{to_version} 내용으로", changed_items=None, confirm_item_deletion)`
4. `→ SaveResult`

**출력** 새 버전의 `SaveResult`. 되돌린 결과가 v{N+1}

**예외** `not-found`, `already-current`, 파이프라인의 `convention-violation`(4a)·`item-deletion-needs-confirm`·`push-failed`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-007#pipeline.save_pipeline]]

**테스트 관점** 남의 프로젝트 → `not-found`, 버전 그대로 · v7에서 v6으로 → v8 생성, v7 남음 · 옛 본문이 현 규약 위반 → 거부 · 옛 본문에 없는 항목이 지금 있음 → 삭제 확인 요구 → confirm 후 그 항목을 가리키던 참조가 미존재


---

#### pipeline.process_commit GitHub 커밋 처리

**시그니처**
```python
async def process_commit(repo: Repository, head_hash: str) -> list[SaveResult]
```

근거: [[SYNC-SEQ-001#SEQ-2]] · [[SYNC-UC-001#UC-G1]]

**입력** `repo` 등록된 저장소. `head_hash` 처리할 끝 커밋 (webhook의 `after` 또는 `origin/main`)

**처리**

1. `repo.last_processed_commit == head_hash`면 `→ []`
2. `git.fetch(repo.workdir)` (public)
3. `files = git.changed_files(repo, f"{last}..{head}", path="docs/specs/")`. 각각 `(path, last_commit_hash_of_file, author_login, author_email, message)`. `_templates/`·`assets/`는 제외
3a. **앱 자신이 만든 커밋은 거른다** — `commit_hash`가 이미 `versions.commit_hash`나 `status_changes.commit_hash`에 있으면 건너뛴다. 없으면 앱이 push한 커밋을 폴링이 github 경로로 다시 저장해 같은 커밋의 버전이 하나 더 생긴다
3b. 남은 파일을 **문서 타입의 단계 순**으로 정렬(RFQ→…→CODE→STD). 경로순이면 하위가 먼저 저장돼 상위 참조가 미존재로 남는다
4. 파일마다 (락은 `save_pipeline` 안에서):
   - `body = git.read(repo, path, head_hash)`
   - `doc_id` = **파일명**(github 경로는 `issue_doc_id`를 쓰지 않는다 — 커밋이 진실). `path_type` = 디렉터리명에서 번호를 뗀 것(`06-DOM` → `DOM`, STD-001 1.1). if `path_type != frontmatter.type` → `frontmatter.doc_id` 위반으로 처리(저장은 됨)
   - github 진입은 **항목 삭제 확인을 건너뛴다** — 물어볼 상대가 없고 커밋이 진실이다. 사라진 항목은 `is_deleted` + `mark_missing`으로 통보
   - 파일명·디렉터리·미등록 작성자 위반은 저장 뒤 `spec.mark_convention_error`로 덧붙인다
   - `user = account.user_for_commit(author_email, author_login)` — **이메일 → login → 자리표시** 순([[SYNC-MS-006#AccountService.user_for_commit]])
   - if `user.github_user_id is None` → 위반에 `author.unknown: {author_login}` 추가. **판정은 「자리표시인가」이지 「방금 만들었나」가 아니다** — 후자로 하면 같은 사람의 둘째 문서부터 이미 행이 있어 오류가 안 붙는다(#34)
   - `author = Author(kind=human, user, instructed_by=None, via=github)`
   - if `status == D` (파일 삭제) → **문서 행이 없거나 `trashed_at`이 있으면 건너뛴다** — 앱이 [[#pipeline.trash_document]]·[[#pipeline.purge_document]]로 만든 삭제 커밋이거나 등록 전에 사라진 파일이다. `mark_deleted`로 가면 `not-found`가 나서 그 커밋이 영영 「처리 실패」로 남고 `last_processed_commit`이 안 나아간다 · else → `deleted = spec.mark_deleted(document, commit_hash, author)` (`status=draft`, `file.deleted` 오류, 전 항목 `is_deleted`) · `reference.mark_missing(deleted)` · 문서 행은 남는다 · 다음 파일로
   - else → `save_pipeline(entry=github, doc_id, None, body, None, author, message=원 커밋 메시지, changed_items=None, commit_hash=file_commit_hash)` → 결과 모음
5. `repo.last_processed_commit = head_hash`, `synced_at = now`
6. `→ results`

**출력** 파일마다 `SaveResult`

**예외** 파일 하나 실패해도 다음 파일 계속. 실패 목록을 로그. `last_processed_commit`은 **전부 성공했을 때만** 갱신 — 아니면 다음 폴링이 다시 시도

**호출하는 것** [[#pipeline.save_pipeline]] · [[SYNC-MS-002#SpecService.mark_deleted]] [[SYNC-MS-003#ReferenceService.mark_missing]] · `git.fetch` `git.changed_files` `git.read` · `AccountService.user_for_commit`

**테스트 관점**
- 커밋 하나에 파일 둘: 결과 둘, 각각 새 버전
- 밀린 커밋 셋에 같은 파일: 버전 하나(최종 상태)
- 미등록 작성자: 자리표시 User 생성, 문서에 `author.unknown`
- **같은 미등록 작성자가 문서 둘을 커밋: 둘 다 `author.unknown`** (자리표시는 하나만 생긴다)
- 커밋 이메일이 등록된 사람: 자리표시를 안 만들고 그 사람으로 붙는다. `author.unknown` 없음
- 파일명 ≠ frontmatter: 규약 오류로 저장됨
- 한 파일 실패: 나머지 처리됨, `last_processed_commit` 안 바뀜

---

#### pipeline.rebuild 인덱스 재구축

**시그니처**
```python
async def rebuild(code: str, session: Session | None = None) -> RebuildResult
```

근거: [[SYNC-SEQ-001#SEQ-21]] · [[SYNC-UC-001#UC-S6]]

**입력** 프로젝트 코드. `session` — `init_project(import_existing)`가 아직 커밋 안 된 프로젝트 행이 있는 자기 세션을 넘긴다. None이면 스스로 연다(`save_pipeline`과 같은 방식, DEV-10)

**처리**

1. `project, repo = project.get(code)`. 락 획득 — `get`이다. 사람 경로는 [[SYNC-MS-001#ProjectService.rebuild_index]]가 `get_owned`로 이미 걸렀고, `init_project(import_existing)`는 등록하는 사람 자신이며 폴링에는 사람이 없다
2. `git.fetch(repo.workdir)`, `git.checkout(repo.workdir, "origin/main")` · if fetch 실패 → `! rebuild-failed {reason}` (500으로 새지 않게)
3. **트랜잭션 시작**
4. `reference.clear(project_id)` · `spec.clear_index(project_id)` — `versions`와 커밋 있는 `status_changes` 삭제. `documents`·`items`는 유지(`status_changes` FK, 항목 pk 보존)
4a. **`versions`를 가리키는 FK는 `references.extracted_version_id` 하나다**([[SYNC-MS-002#SpecService.clear_index]]) — 4단계가 먼저 지운다. 지우는 테이블에 걸린 FK를 안 세서 실물 재구축이 죽은 적이 있다(#38). 전파결정·플래그가 사라지면서 재연결 단계(옛 3a·7a·7b)도 사라졌다
5. `paths = git.list(repo, "docs/specs/*/*.md")` (`_templates`·`assets` 제외. 번호 붙은 디렉터리도 `*`에 걸린다)
6. 파일마다:
   - `log = git.log(repo, path)` 오래된 것부터 `[(hash, login, email, date, message, path)]`
   - 커밋마다: `body = git.read(c.path @ hash)` — **그 커밋 시점의 경로로 읽는다.** 이름이 바뀐 문서는 옛 커밋에서 옛 경로에 있어 지금 경로로는 못 읽는다(#39) · `user = account.user_for_commit(email, login)` — `process_commit` 4단계와 **같은 순서**(이메일 → login → 자리표시)
     - if `message.startswith("status(")` → `spec.apply_status(…, commit_hash=hash)`만 (StatusChange 복원)
     - else if 이 문서의 첫 커밋 → `spec.create(...)` · else → `spec.save(document, body, hash, author, message, deleted=spec.detect_deleted_items(document, body), validate_result, rebuild=True)` — `version_no`는 남은 버전 수 + 1, `items` upsert. 커밋마다 삭제 항목도 반영한다
   - 마지막 커밋 본문으로 `reference.extract`, `spec.mark_convention_error(document_id, violations + extra, warnings)`. 삭제된 항목을 가리키는 참조는 `extract` 4단계가 `is_deleted=false`만 찾으므로 **저절로 미존재**가 된다 — `mark_missing`을 따로 부르지 않는다
   - **`extra`에 작성자 위반을 얹는다** — 마지막 **본문** 커밋(`status(`가 아닌 것)의 작성자가 `github_user_id is None`이면 `author.unknown: {login}`. `mark_convention_error`는 항상 전량 교체라 여기서 안 얹으면 그 오류가 사라진다. 그래서 실물 인덱스에 규약 오류가 0건이었다(#34)
   - **마지막 본문 커밋을 기준으로 삼는 이유** — 문서의 `author.unknown`은 UI-5 배너가 `last_author`와 함께 보여주는 값이고 `process_commit`도 방금 저장한 버전의 작성자로 판정한다. 옛 커밋이 미등록이었어도 최신 커밋이 등록자면 문서는 깨끗하다
7. `reference.resolve_missing(project_id)` — 파일 순서 때문에 미존재였던 참조 해제
7a~7b. 없음 — 전파결정·플래그를 새 버전에 다시 잇던 자리. 카드 V에서 걷어냈다
8. `repo.last_processed_commit = HEAD`
9. **커밋.** 락 해제
10. `→ RebuildResult(docs, items, references, versions, convention_errors)`

**출력** [[SYNC-API-001]] `RebuildResult`

**예외** 어느 단계든 실패하면 트랜잭션 롤백. DB는 재구축 전 상태로. `! rebuild-failed {reason}`

**호출하는 것** [[SYNC-MS-002#SpecService.clear_index]] [[SYNC-MS-002#SpecService.validate]] [[SYNC-MS-002#SpecService.save]] [[SYNC-MS-002#SpecService.mark_convention_error]] · `ReferenceService.clear` `ReferenceService.extract` `ReferenceService.resolve_missing` · `AccountService.user_for_commit` · `git.*`

**테스트 관점**
- DB 비운 뒤 재구축: 문서·항목·참조·버전 수가 저장소와 일치
- 항목 pk가 재구축 전후로 같다(`items`는 안 지운다)
- 삭제된 항목을 가리키던 참조: 재구축 뒤에도 `is_missing`이고 `raw_target`이 남는다
- **두 번 재구축해도 `status_changes`가 안 늘어난다**(4단계가 커밋 있는 행을 지운다)
- 파일 순서 때문에 미존재였던 참조가 7단계 후 해제됨
- **미등록 작성자만 있는 저장소를 재구축: 문서에 `author.unknown`이 붙는다**(#34)
- 커밋 이메일을 등록하고 재구축: 버전 작성자가 그 사람으로 바뀌고 `author.unknown`이 사라진다
- `status(` 커밋: Version 안 늘고 StatusChange 생김
- 중간 실패: DB가 재구축 전과 같음

---

#### scheduler.catch_up 밀린 커밋 따라잡기

**시그니처** `async def catch_up() -> list[SaveResult]`

근거: [[SYNC-INFRA-001]] 7장 · [[SYNC-UC-001#UC-G1]] 1a·1b · [[SYNC-MS-001#ProjectService.repo_status]]

**처리** — 저장소마다
1. `head = git.fetch(workdir)`
2. `DB: repositories update behind_by = git.rev_list_count(f"{last_processed_commit}..{head}"), fetched_at = now, fetch_error = null` — **화면이 읽는 값을 여기서 적는다.** `last_processed_commit`이 없으면 `behind_by=None`
3. if `head != repository.last_processed_commit` → [[#pipeline.process_commit]]
4. `→ 처리 결과 목록`

**예외** **저장소 하나가 실패해도 다음 저장소를 계속한다.** 그 저장소의 `behind_by`는 건드리지
않는다 — 낡은 값이 남지만 `fetched_at`이 언제 기준인지 말해 준다.
폴링이 예외로 죽으면 그 뒤로 아무 저장소도 안 따라잡는다.

**실패를 로그로만 남기지 않는다.** `DB: repositories update fetch_error = {사유}`를 함께 적는다
([[SYNC-DOM-003#repositories]]). 로그만 남기면 **폴링이 죽은 프로젝트가 조용히 멈추고, 사람은
「아무도 push를 안 했나 보다」로 읽는다.** 실제로 빈 저장소로 만든 프로젝트가 30분 동안 매 주기
같은 오류로 실패했는데 관리 화면에는 아무 표시가 없었다(#46). 이 값은 [[SYNC-MS-001#ProjectService.repo_status]]가
`RepoStatus.error`로 올려 UI-14 2.3에 뜬다. **성공한 주기가 지우므로 낡은 오류가 남지 않는다.**

**호출하는 것** `ProjectService.list_projects` · `git.fetch` `rev_list_count` · [[#pipeline.process_commit]]

**테스트 관점** 원격이 앞서 있으면 `process_commit`이 불림 · 같으면 안 불리고 `fetched_at`만 갱신 · 저장소 둘 중 앞엣것이 실패해도 뒤엣것이 처리됨 · `behind_by`가 DB에 남아 `repo_status`가 그걸 읽음 · **실패한 저장소의 `fetch_error`에 사유가 남고, 다음 성공이 그것을 비운다**

---

#### scheduler.poll_loop 주기 폴링

**시그니처** `async def poll_loop(interval: int) -> None`

근거: [[SYNC-INFRA-001]] 5장(webhook 없음, 폴링만) · [[SYNC-UC-001#UC-G1]] 1b

**처리** `interval`초 자고 [[#scheduler.catch_up]]을 부르는 것을 끝없이 반복. `interval`은
`POLL_INTERVAL_SECONDS`(기본 300). 0 이하면 아예 켜지 않는다.

**기동 시 한 번은 따로다.** 앱이 뜰 때 `catch_up`을 한 번 부르고(1a) 그다음부터 이 반복에
들어간다. 노트북이 꺼져 있던 동안 쌓인 커밋을 첫 주기까지 기다리지 않고 바로 가져온다.

**반복 전체를 감싸 잡는다.** `catch_up`은 저장소 하나가 실패해도 다음 저장소를 계속하지만, 저장소 목록을 읽는 단계에서 DB가 잠깐 죽으면 그 예외가 이 반복까지 올라와 **그 뒤로 영영 폴링이 없다.** 한 주기를 통째로 `try/except`로 감싸고 로그만 남긴다.

**호출하는 것** [[#scheduler.catch_up]]

**테스트 관점** `interval` 만큼 자고 부른다 · `catch_up`이 예외를 던져도 반복이 안 멈춘다

---

## 3. 미결사항

