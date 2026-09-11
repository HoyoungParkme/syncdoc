---
doc_id: SYNC-MS-007
type: MS
title: MINISPEC — pipeline — 쓰기 조율
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — pipeline — 쓰기 조율

## 0. 이 문서가 다루는 것

`core/pipeline.py`의 함수 5개와 `scheduler.py`의 폴링 함수 2개. 클래스 명세 [[SYNC-DOM-002]] 4.7의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`pipeline`은 조율자다. 자기 테이블이 없고 서비스를 순서대로 부른다. 세 입구(MCP·웹·GitHub)가 전부 `save_pipeline`로 들어온다. 상태 변경·되돌리기도 조율이라 여기(원래 SpecService에 있었으나 세션·async가 꼬여 옮겼다 — B2 되먹임).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#pipeline.save_pipeline]] | 본문 저장 파이프라인 |
| [[#pipeline.process_commit]] | GitHub 커밋 처리 |
| [[#pipeline.rebuild]] | 인덱스 재구축 |
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
                        upstream_impact: list[str] | None = None,
                        confirm_item_deletion: bool = False,
                        commit_hash: str | None = None,
                        reason: str | None = None,
                        session: Session | None = None) -> SaveResult
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
| `upstream_impact` | 어긋난 상위 항목 | `mcp`만. `"SYNC-UC-001#UC-A6"` 형식. 하위→상위 되먹임의 에이전트 경로 |
| `confirm_item_deletion` | 삭제 확인됨 | |
| `commit_hash` | 이미 있는 커밋 | `github`만. push 단계 건너뜀 |
| `reason` | 상태 변경 사유 | `web_status`만. `apply_status`로 |
| `session` | 호출자 세션 | `change_status`·`revert`가 넘긴다. None이면 스스로 연다(DEV-10) |

**처리**

1. `code = project_code if doc_id is None else doc_id.split("-")[0]` · `project = ProjectService.get(code)`, `repo = project.repository`. **저장소 락 획득** (`asyncio.Lock`, 저장소별). 이후 전부 락 안. **세션도 여기서 연다** — 서비스는 세션을 열지 않는다(DEV-10)
2. if `doc_id is not None` → `document = spec.get_document(doc_id)`, `doc_type = document.doc_type` · if 없음 → `! not-found`
   (`entry == github`도 같다 · if github 경로에서 없음 → process_commit이 `doc_id=None`으로 다시 부른다)
3. if `doc_id is None` (생성) → `doc_id = spec.issue_doc_id(project_id, project.code, doc_type)`, `body = spec.apply_frontmatter(body, doc_id, doc_type, "draft")`
4. `(violations, warnings) = spec.validate(body, doc_type, entry, current_status=document.status if document else None)`
   - if `violations and entry != github` → `! convention-violation {violations, warnings}`, 락 해제
   - if `violations and entry == github` → 계속. 8단계에 `has_convention_error=True`로 전달
5. if `entry != github and expected_version != document.current_version_no` → `! version-conflict {current_version, current_body}`
6. if `entry != web_status and document` → `deleted = spec.detect_deleted_items(document, body)`; `deleted`의 pk마다 `refs = reference.downstream(pk)`
   - if `any(refs) and not confirm_item_deletion` → `! item-deletion-needs-confirm {deleted_items: [{item_id, downstream}]}`
7. if `entry != github` → `commit_hash = git.commit_push(repo.workdir, message, author, path=STD-001 1.1 경로, content=body)` · if 실패 → `! push-failed {reason}`, 락 해제. **여기까지 DB 쓰기 없음**
8. **트랜잭션 시작**
   - if 생성 → `version = spec.create(project_id, doc_id, doc_type, body, commit_hash, author, message, validate_result=4단계 결과)`
   - if `entry == web_status` → `spec.apply_status(document, body, commit_hash, author.user, reason)` (Document.status·current_body 갱신 + StatusChange). **Version 없음.** 9~13 건너뛰고 14로
   - else → `version = spec.save(document, body, commit_hash, author, message, deleted, validate_result=4단계 결과)` — **모든 경로.** 경고(`incomplete_warnings`)는 mcp 저장에도 남아야 승인을 막는다. 위반은 github 경로에서만 저장까지 온다
9. `deleted`마다 `tracking.raise_broken(pk)`
10. `reference.extract(document_id, version.id, body, item_pks=spec.item_pks(document_id), upstream_doc_ids=frontmatter upstream)`
10a. `reference.resolve_missing(project_id, target_doc_id=doc_id)` — 이 문서(또는 항목)를 기다리던 미존재 참조를 푼다. 하위가 먼저 저장된 경우가 재구축까지 안 기다려도 되게(UC-S2 2a2)
11. `affected = tracking.detect_impact(document_id, prev_version_id=document.current_version_id (2단계에서 읽은 것. 신규면 None), version.id, changed_items)` · if `affected` → `changed_pks = spec.resolve_items(doc_id, changed_items)` (선언) 또는 `detect_impact`가 diff로 판정한 것 · `pending_id = tracking.create_pending(version.id, affected, changed_pks)` · else `pending_id = None`
12. if `upstream_impact` → 각각 `spec.resolve_item(doc, item)` · if 못 찾음 → `warnings`에 `upstream_impact.unknown` 추가하고 건너뜀 · `tracking.raise_upstream(pks, document_id, version.id, cause_item_pk=None)`
13. `collab.relocate(document_id, old_body, body, old_version_no=document.current_version_no)`
14. **커밋.** 락 해제
15. `→ SaveResult(doc_id, version_no, commit_hash, status, pending_decision_version_id=pending_id, warnings)`

**출력** `SaveResult`. [[SYNC-API-001]] 4장 스키마와 같다.

**예외**

| 조건 | 에러 | 단계 |
|---|---|---|
| 문서 없음 | `not-found` | 2 |
| 규약 위반 (mcp·web) | `convention-violation` | 4 |
| 버전 불일치 | `version-conflict` | 5 |
| 삭제 항목에 하위 참조, 미확인 | `item-deletion-needs-confirm` | 6 |
| push 실패 | `push-failed` | 7 |
| 8~12 중 DB 오류 | 트랜잭션 롤백. 커밋은 이미 원격에 있으므로 `repository.last_processed_commit`을 갱신하지 않아 폴링이 다시 처리한다 | 8 |

**호출하는 것** [[SYNC-MS-004#TrackingService.raise_upstream]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-002#SpecService.issue_doc_id]] [[SYNC-MS-002#SpecService.apply_frontmatter]] [[SYNC-MS-002#SpecService.validate]] [[SYNC-MS-002#SpecService.detect_deleted_items]] [[SYNC-MS-002#SpecService.create]] [[SYNC-MS-002#SpecService.save]] · `ReferenceService.downstream` · `ReferenceService.extract` · `TrackingService.raise_broken` · `TrackingService.detect_impact` · `TrackingService.create_pending` · `CommentService.relocate` · `git.commit_push`

**테스트 관점**
- 정상 수정: 새 버전 번호 +1, 커밋 존재, 참조 갱신
- 규약 위반 mcp: DB 변경 없음, 커밋 없음
- 규약 위반 github: 저장됨, `has_convention_error=True`
- 버전 불일치: `current_body`가 응답에 있음
- 항목 삭제 미확인: 저장 안 됨. `confirm=True`로 재요청 시 `broken_ref` 플래그 생김
- push 실패: DB 변경 없음
- 승인 문서 수정: 상태가 `review`, StatusChange 행 하나
- `web_status`: Version 없음, StatusChange에 commit_hash
- 동시 저장 둘: 락 때문에 직렬화. 둘째가 version-conflict
- `upstream_impact=["SYNC-UC-001#UC-A6"]` → UC-A6에 `upstream_impact` 플래그, 담당은 UC 문서 최근 작성자 · 없는 항목 → 경고, 저장은 됨
- 8단계 이후 DB 오류: 트랜잭션 롤백, `last_processed_commit` 그대로

---

#### pipeline.change_status 상태 변경

**시그니처** `async def change_status(doc_id: str, to: DocStatus, user: User, reason: str | None, upstream_reviewed: bool = False, upstream_mismatch: list[str] = []) -> DocumentSummary`

근거: [[SYNC-SEQ-001#SEQ-5]] · [[SYNC-UC-001#UC-H8]] · [[SYNC-API-001#POST/api/docs/{docId}/status]] · **조율이라 pipeline에 있다** — 검사·frontmatter·push·상태 기록·플래그를 잇는다. SpecService는 DB만

**입력** `doc_id`, 목표 상태 `to`, 누른 사람, 사유

**처리**
1. `document = get_document(doc_id)`
2. `missing = 중복 접은 [e.raw_target for e in ReferenceService.upstream_of_document(document.id, include_missing=True) if e.is_missing]`
2a. if `to == approved and (document.has_convention_error or document.incomplete_warnings or missing)` → `! status-blocked {convention_error_detail, warnings: incomplete_warnings + [f"ref.missing: {t}" for t in missing]}` (UC-H8 1a). `review`·`draft`는 막지 않는다
2b. **끊어진 참조는 읽을 때 센다 — 컬럼에 없다.** `documents.incomplete_warnings`에 넣지 않는 이유는 [[SYNC-STD-001]] 4장에 있다. 값은 UI-5 배너가 보는 `document_view.missing_refs`와 **같아야 한다** — 한쪽만 막거나 한쪽만 보여주면 사람이 이유 없이 막힌다
2c. `warnings`에 `ref.missing: {대상}` 꼴로 섞어 보낸다. `incomplete_warnings`가 이미 `section.missing: 시나리오` 꼴이라 같은 규격이고, 화면이 `:` 앞을 rule로 잘라 한국어로 옮긴다([[SYNC-STD-001]] 4장 화면 문구 열)
3. if `to == approved and not upstream_reviewed` → `! upstream-review-required` (UC-H8 3. 상위 대조를 건너뛸 수 없다)
3a. if `document.status == to` → 아무것도 안 하고 현재 반환 (멱등)
4. `new_body` = `current_body`의 frontmatter `status:` 줄만 교체
5. `save_pipeline(entry=web_status, doc_id, None, new_body, expected_version=current_version_no, project_code=None, author=Author(human, user, None, web), message=f"status({doc_id}): {from} → {to}\n\n{reason or ''}", reason=reason)` — **같은 세션**. `save_pipeline`이 세션을 인자로 받거나(있으면 재사용) 없으면 연다. push 후 `spec.apply_status(…, reason)`
5a. if `upstream_mismatch` → `pks = [resolve_item(d, i) for "d#i" in upstream_mismatch]` · `TrackingService.raise_upstream(pks, document.id, current_version_id, cause_item_pk=None)` (UC-H8 5. 승인 대조의 사람 경로)
6. `→ DocumentSummary`

**출력** 바뀐 문서 요약

**예외** `status-blocked` · `upstream-review-required` · 파이프라인의 `version-conflict`·`push-failed` 전파

**호출하는 것** [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-007#pipeline.save_pipeline]] [[SYNC-MS-003#ReferenceService.upstream_of_document]]

**테스트 관점** 규약 오류 문서를 `approved`로 → blocked · **미존재 참조가 있는 문서를 `approved`로 → blocked이고 `warnings`에 `ref.missing:`이 있다** · 같은 문서를 `review`로 → 됨 · **상대 문서가 들어와 `resolve_missing`이 풀면 그 문서를 다시 저장하지 않아도 승인된다**(읽을 때 계산한다는 증거) · `approved`인데 `upstream_reviewed=false` → 거부 · `upstream_mismatch=["SYNC-UC-001#UC-A6"]` → UC-A6에 플래그 · 같은 문서를 `review`로 → 됨 · 정상 승인 → frontmatter `status: approved` 커밋 존재, Version 없음, StatusChange에 commit_hash · 같은 상태로 다시 → 커밋 없음


---

#### pipeline.revert 되돌리기

**시그니처** `async def revert(doc_id: str, to_version: int, user: User, confirm_item_deletion: bool = False) -> SaveResult` — `pipeline`을 불러 async(DEV-16)

근거: [[SYNC-SEQ-001#SEQ-7]] · [[SYNC-UC-001#UC-H7]] · [[SYNC-API-001#POST/api/docs/{docId}/revert]] · 조율이라 pipeline

**처리**
1. `document = spec.get_document(doc_id)`; `old_body = spec.version_body(doc_id, to_version)` · 없으면 그쪽에서 `! not-found`
2. if `to_version == document.current_version_no` → `! already-current`(422)
3. `save_pipeline(entry=web_revert, doc_id, None, old_body, expected_version=current_version_no, project_code=None, author=Author(human, user, None, web), message=f"revert({doc_id}): v{current} → v{to_version} 내용으로", changed_items=None, confirm_item_deletion)`
4. `→ SaveResult`

**출력** 새 버전의 `SaveResult`. 되돌린 결과가 v{N+1}

**예외** `not-found`, `already-current`, 파이프라인의 `convention-violation`(4a)·`item-deletion-needs-confirm`·`push-failed`

**호출하는 것** [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-007#pipeline.save_pipeline]]

**테스트 관점** v7에서 v6으로 → v8 생성, v7 남음 · 옛 본문이 현 규약 위반 → 거부 · 옛 본문에 없는 항목이 지금 있음 → 삭제 확인 요구 → confirm 후 broken_ref 플래그


---

#### pipeline.process_commit GitHub 커밋 처리

**시그니처**
```python
async def process_commit(repo: Repository, head_hash: str) -> list[SaveResult]
```

근거: [[SYNC-SEQ-001#SEQ-2]] · [[SYNC-UC-001#UC-G1]]

**입력** `repo` 등록된 저장소. `head_hash` 처리할 끝 커밋 (webhook의 `after` 또는 `origin/HEAD`)

**처리**

1. `repo.last_processed_commit == head_hash`면 `→ []`
2. `git.fetch(repo.workdir)` (public)
3. `files = git.changed_files(repo, f"{last}..{head}", path="docs/specs/")`. 각각 `(path, last_commit_hash_of_file, author_login, author_email, message)`. `_templates/`·`assets/`는 제외
3a. **앱 자신이 만든 커밋은 거른다** — `commit_hash`가 이미 `versions.commit_hash`나 `status_changes.commit_hash`에 있으면 건너뛴다. 없으면 앱이 push한 커밋을 폴링이 github 경로로 다시 저장해 같은 커밋의 버전이 하나 더 생긴다
3b. 남은 파일을 **문서 타입의 단계 순**으로 정렬(RFQ→…→CODE→STD). 경로순이면 하위가 먼저 저장돼 상위 참조가 미존재로 남는다
4. 파일마다 (락은 `save_pipeline` 안에서):
   - `body = git.read(repo, path, head_hash)`
   - `doc_id` = **파일명**(github 경로는 `issue_doc_id`를 쓰지 않는다 — 커밋이 진실). `path_type` = 디렉터리명에서 번호를 뗀 것(`06-DOM` → `DOM`, STD-001 1.1). if `path_type != frontmatter.type` → `frontmatter.doc_id` 위반으로 처리(저장은 됨)
   - github 진입은 **항목 삭제 확인을 건너뛴다** — 물어볼 상대가 없고 커밋이 진실이다. 사라진 항목은 `is_deleted` + `raise_broken`으로 통보
   - 파일명·디렉터리·미등록 작성자 위반은 저장 뒤 `spec.mark_convention_error`로 덧붙인다
   - `user = account.user_for_commit(author_email, author_login)` — **이메일 → login → 자리표시** 순([[SYNC-MS-006#AccountService.user_for_commit]])
   - if `user.github_user_id is None` → 위반에 `author.unknown: {author_login}` 추가. **판정은 「자리표시인가」이지 「방금 만들었나」가 아니다** — 후자로 하면 같은 사람의 둘째 문서부터 이미 행이 있어 오류가 안 붙는다(#34)
   - `author = Author(kind=human, user, instructed_by=None, via=github)`
   - if `status == D` (파일 삭제) → `deleted = spec.mark_deleted(document, commit_hash, author)` (`status=draft`, `file.deleted` 오류, 전 항목 `is_deleted`) · 각 pk에 `tracking.raise_broken` · 문서 행은 남는다 · 다음 파일로
   - else → `save_pipeline(entry=github, doc_id, None, body, None, author, message=원 커밋 메시지, changed_items=None, commit_hash=file_commit_hash)` → 결과 모음
5. `repo.last_processed_commit = head_hash`, `synced_at = now`
6. `→ results`

**출력** 파일마다 `SaveResult`

**예외** 파일 하나 실패해도 다음 파일 계속. 실패 목록을 로그. `last_processed_commit`은 **전부 성공했을 때만** 갱신 — 아니면 다음 폴링이 다시 시도

**호출하는 것** [[#pipeline.save_pipeline]] · `git.fetch` `git.changed_files` `git.read` · `AccountService.user_for_commit`

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

1. `project, repo = project.get(code)`. 락 획득
2. `git.fetch(repo.workdir)`, `git.checkout(repo.workdir, "origin/HEAD")` · if fetch 실패 → `! rebuild-failed {reason}` (500으로 새지 않게)
3. **트랜잭션 시작**
3a. `old = spec.version_keys(project_id)` — **지우기 전에** `{옛 version_id: (document_id, commit_hash)}`를 뜬다. 버전 행이 사라지면 그 둘을 알 방법이 없다 — `propagation_decisions`·`flags`는 `version_id` 하나만 들고 있다(#38)
4. `reference.clear(project_id)` · `spec.clear_index(project_id)` — `versions`와 커밋 있는 `status_changes` 삭제. `documents`·`items`는 유지(플래그·댓글 FK)
4a. **`versions`를 가리키는 FK 셋을 여기서 센다**([[SYNC-MS-002#SpecService.clear_index]]). `references`는 4단계가 먼저 지우고, `propagation_decisions.version_id`·`flags.cause_version_id`는 **7a가 다시 잇는다.** 이 셋을 안 세서 실물 재구축이 죽었다 — 지금까지 "지우지 **않는** 테이블에 걸린 FK"만 셌다(#38)
5. `paths = git.list(repo, "docs/specs/*/*.md")` (`_templates`·`assets` 제외. 번호 붙은 디렉터리도 `*`에 걸린다)
6. 파일마다:
   - `log = git.log(repo, path)` 오래된 것부터 `[(hash, login, email, date, message)]`
   - 커밋마다: `body = git.read(path @ hash)` · `user = account.user_for_commit(email, login)` — `process_commit` 4단계와 **같은 순서**(이메일 → login → 자리표시)
     - if `message.startswith("status(")` → `spec.apply_status(…, commit_hash=hash)`만 (StatusChange 복원)
     - else if 이 문서의 첫 커밋 → `spec.create(...)` · else → `spec.save(document, body, hash, author, message, deleted=spec.detect_deleted_items(document, body), validate_result, rebuild=True)` — `version_no`는 남은 버전 수 + 1, `items` upsert. 커밋마다 삭제 항목도 반영한다
   - 커밋마다 `save`가 돌려준 버전을 `new[(document_id, commit_hash)] = version.id`로 모은다 — 7a가 쓴다
   - 마지막 커밋 본문으로 `reference.extract`, `spec.mark_convention_error(document_id, violations + extra, warnings)`
   - **`extra`에 작성자 위반을 얹는다** — 마지막 **본문** 커밋(`status(`가 아닌 것)의 작성자가 `github_user_id is None`이면 `author.unknown: {login}`. `mark_convention_error`는 항상 전량 교체라 여기서 안 얹으면 그 오류가 사라진다. 그래서 실물 인덱스에 규약 오류가 0건이었다(#34)
   - **마지막 본문 커밋을 기준으로 삼는 이유** — 문서의 `author.unknown`은 UI-5 배너가 `last_author`와 함께 보여주는 값이고 `process_commit`도 방금 저장한 버전의 작성자로 판정한다. 옛 커밋이 미등록이었어도 최신 커밋이 등록자면 문서는 깨끗하다
7. `reference.resolve_missing(project_id)` — 파일 순서 때문에 미존재였던 참조 해제
7a. `tracking.relink_versions(project_id, new)` — `new`는 6단계에서 모은 `{(document_id, commit_hash): 새 version_id}`. 전파결정과 플래그가 옛 버전 id를 가리키므로 새 id로 갈아 끼운다. 못 잇는 행은 지우고 몇 건을 왜 버렸는지 `RebuildResult.dropped`에 싣는다([[SYNC-MS-004#TrackingService.relink_versions]])
7b. `tracking.reassign_open_flags(project_id)` — 버전을 다시 만들었으므로 열린 플래그의 담당자(= 대상 문서 최근 버전 작성자)를 다시 계산한다. `clear_index`는 flags를 안 지우고 담당자는 플래그를 만들 때 한 번만 정해지므로, 이게 없으면 **재구축이 절반만 끝난다** — 커밋 이메일을 등록해 작성자가 바뀌어도 플래그는 옛 자리표시를 계속 가리킨다([[SYNC-MS-004#TrackingService.reassign_open_flags]])
8. `repo.last_processed_commit = HEAD`
9. **커밋.** 락 해제
10. `→ RebuildResult(docs, items, references, versions, convention_errors, dropped)`

**출력** [[SYNC-API-001]] `RebuildResult`

**예외** 어느 단계든 실패하면 트랜잭션 롤백. DB는 재구축 전 상태로. `! rebuild-failed {reason}`

**호출하는 것** [[SYNC-MS-002#SpecService.clear_index]] [[SYNC-MS-002#SpecService.version_keys]] [[SYNC-MS-002#SpecService.validate]] [[SYNC-MS-002#SpecService.save]] [[SYNC-MS-002#SpecService.mark_convention_error]] · `ReferenceService.clear` `ReferenceService.extract` `ReferenceService.resolve_missing` · [[SYNC-MS-004#TrackingService.relink_versions]] [[SYNC-MS-004#TrackingService.reassign_open_flags]] · `AccountService.user_for_commit` · `git.*`

**테스트 관점**
- DB 비운 뒤 재구축: 문서·항목·참조·버전 수가 저장소와 일치
- 플래그·댓글이 있는 상태에서 재구축: 그대로 남음. **담당자는 다시 계산된다**(7b)
- **전파결정이 있는 상태에서 재구축**: 행이 남고 `version_id`가 새 버전을 가리킨다. `affected_pks`는 그대로(항목 pk는 `save`의 upsert가 보존한다)
- **`cause_version_id`가 있는 플래그**(`needs_check`·`upstream_impact`)로 재구축: 그 값이 새 버전으로 바뀐다
- 문서가 삭제된 커밋에 매달린 결정: 버려지고 `RebuildResult.dropped`에 뜬다
- **두 번 재구축해도 `status_changes`가 안 늘어난다**(4단계가 커밋 있는 행을 지운다)
- 파일 순서 때문에 미존재였던 참조가 7단계 후 해제됨
- **미등록 작성자만 있는 저장소를 재구축: 문서에 `author.unknown`이 붙는다**(#34)
- 커밋 이메일을 등록하고 재구축: 버전 작성자가 그 사람으로 바뀌고 `author.unknown`이 사라진다. 열린 플래그 담당자도 따라 바뀐다
- `status(` 커밋: Version 안 늘고 StatusChange 생김
- 중간 실패: DB가 재구축 전과 같음

---

#### scheduler.catch_up 밀린 커밋 따라잡기

**시그니처** `async def catch_up() -> list[SaveResult]`

근거: [[SYNC-INFRA-001]] 7장 · [[SYNC-UC-001#UC-G1]] 1a·1b · [[SYNC-MS-001#ProjectService.repo_status]]

**처리** — 저장소마다
1. `head = git.fetch(workdir)`
2. `DB: repositories update behind_by = git.rev_list_count(f"{last_processed_commit}..{head}"), fetched_at = now` — **화면이 읽는 값을 여기서 적는다.** `last_processed_commit`이 없으면 `behind_by=None`
3. if `head != repository.last_processed_commit` → [[#pipeline.process_commit]]
4. `→ 처리 결과 목록`

**예외** **저장소 하나가 실패해도 다음 저장소를 계속한다.** 로그만 남기고 그 저장소의
`behind_by`는 건드리지 않는다 — 낡은 값이 남지만 `fetched_at`이 언제 기준인지 말해 준다.
폴링이 예외로 죽으면 그 뒤로 아무 저장소도 안 따라잡는다.

**호출하는 것** `ProjectService.list_projects` · `git.fetch` `rev_list_count` · [[#pipeline.process_commit]]

**테스트 관점** 원격이 앞서 있으면 `process_commit`이 불림 · 같으면 안 불리고 `fetched_at`만 갱신 · 저장소 둘 중 앞엣것이 실패해도 뒤엣것이 처리됨 · `behind_by`가 DB에 남아 `repo_status`가 그걸 읽음

---

#### scheduler.poll_loop 주기 폴링

**시그니처** `async def poll_loop(interval: int) -> None`

근거: [[SYNC-INFRA-001]] 5장(webhook 없음, 폴링만) · [[SYNC-UC-001#UC-G1]] 1b

**처리** `interval`초 자고 [[#scheduler.catch_up]]을 부르는 것을 끝없이 반복. `interval`은
`POLL_INTERVAL_SECONDS`(기본 300). 0 이하면 아예 켜지 않는다.

**기동 시 한 번은 따로다.** 앱이 뜰 때 `catch_up`을 한 번 부르고(1a) 그다음부터 이 반복에
들어간다. 노트북이 꺼져 있던 동안 쌓인 커밋을 첫 주기까지 기다리지 않고 바로 가져온다.

**호출하는 것** [[#scheduler.catch_up]]

**테스트 관점** `interval` 만큼 자고 부른다 · `catch_up`이 예외를 던져도 반복이 안 멈춘다

---

---

## 3. 미결사항

