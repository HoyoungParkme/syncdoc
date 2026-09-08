---
doc_id: SYNC-MS-007
type: MS
title: MINISPEC — pipeline — 쓰기 조율
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — pipeline — 쓰기 조율

## 0. 이 문서가 다루는 것

`core/pipeline.py`의 함수 3개. 클래스 명세 [[SYNC-DOM-002]] 4.7의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`pipeline`은 조율자다. 자기 테이블이 없고 서비스를 순서대로 부른다. 세 입구(MCP·웹·GitHub)가 전부 `save_pipeline`로 들어온다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#pipeline.save_pipeline]] | 본문 저장 파이프라인 |
| [[#pipeline.process_commit]] | GitHub 커밋 처리 |
| [[#pipeline.rebuild]] | 인덱스 재구축 |

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
                        commit_hash: str | None = None) -> SaveResult
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
   - if 생성 → `version = spec.create(project_id, doc_id, doc_type, body, commit_hash, author)`
   - if `entry == web_status` → `spec.apply_status(document, new_body, commit_hash, user, reason)` (Document.status·current_body 갱신 + StatusChange). **Version 없음.** 9~12 건너뛰고 13으로
   - else → `version = spec.save(document, body, commit_hash, author, deleted, validate_result=(4단계 결과 if entry == github else None))`
9. `deleted`마다 `tracking.raise_broken(pk)`
10. `reference.extract(document_id, version.id, body, item_pks=spec.item_pks(document_id), upstream_doc_ids=frontmatter upstream)`
11. `affected = tracking.detect_impact(document_id, prev_version_id=document.current_version_id (2단계에서 읽은 것. 신규면 None), version.id, changed_items)` · if `affected` → `pending_id = tracking.create_pending(version.id)` · else `pending_id = None`
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

#### pipeline.process_commit GitHub 커밋 처리

**시그니처**
```python
async def process_commit(repo: Repository, head_hash: str) -> list[SaveResult]
```

근거: [[SYNC-SEQ-001#SEQ-2]] · [[SYNC-UC-001#UC-G1]]

**입력** `repo` 등록된 저장소. `head_hash` 처리할 끝 커밋 (webhook의 `after` 또는 `origin/HEAD`)

**처리**

1. `repo.last_processed_commit == head_hash`면 `→ []`
2. `git.fetch(repo)`
3. `files = git.changed_files(repo, f"{last}..{head}", path="docs/specs/")`. 각각 `(path, last_commit_hash_of_file, author_login, message)`. `_templates/`·`assets/`는 제외
4. 파일마다 (락은 `save_pipeline` 안에서):
   - `body = git.read(repo, path, head_hash)`
   - `doc_id` = 파일명, `path_type` = 디렉터리명. if `path_type != frontmatter.type` → `frontmatter.doc_id` 위반으로 처리(저장은 됨)
   - `user = account.user_by_login(author_login)` · if None → `user = account.create_placeholder(author_login)`, 위반에 `author.unknown` 추가
   - `author = Author(kind=human, user, instructed_by=None, via=github)`
   - if `status == D` (파일 삭제) → `deleted = spec.mark_deleted(document, commit_hash, author)` (`status=draft`, `file.deleted` 오류, 전 항목 `is_deleted`) · 각 pk에 `tracking.raise_broken` · 문서 행은 남는다 · 다음 파일로
   - else → `save_pipeline(entry=github, doc_id, None, body, None, author, message=원 커밋 메시지, changed_items=None, commit_hash=file_commit_hash)` → 결과 모음
5. `repo.last_processed_commit = head_hash`, `synced_at = now`
6. `→ results`

**출력** 파일마다 `SaveResult`

**예외** 파일 하나 실패해도 다음 파일 계속. 실패 목록을 로그. `last_processed_commit`은 **전부 성공했을 때만** 갱신 — 아니면 다음 폴링이 다시 시도

**호출하는 것** [[#pipeline.save_pipeline]] · `git.fetch` `git.changed_files` `git.read` · `AccountService.user_by_login` `AccountService.create_placeholder`

**테스트 관점**
- 커밋 하나에 파일 둘: 결과 둘, 각각 새 버전
- 밀린 커밋 셋에 같은 파일: 버전 하나(최종 상태)
- 미등록 작성자: 자리표시 User 생성, 문서에 `author.unknown`
- 파일명 ≠ frontmatter: 규약 오류로 저장됨
- 한 파일 실패: 나머지 처리됨, `last_processed_commit` 안 바뀜

---

#### pipeline.rebuild 인덱스 재구축

**시그니처**
```python
async def rebuild(code: str) -> RebuildResult
```

근거: [[SYNC-SEQ-001#SEQ-21]] · [[SYNC-UC-001#UC-S6]]

**입력** 프로젝트 코드

**처리**

1. `project, repo = project.get(code)`. 락 획득
2. `git.fetch(repo)`, `git.checkout(repo, "origin/HEAD")`
3. **트랜잭션 시작**
4. `reference.clear(project_id)` · `spec.clear_index(project_id)` — `versions`만 삭제. `documents`·`items`는 유지(플래그·댓글 FK)
5. `paths = git.list(repo, "docs/specs/*/*.md")` (`_templates`·`assets` 제외)
6. 파일마다:
   - `log = git.log(repo, path)` 오래된 것부터 `[(hash, login, date, message)]`
   - 커밋마다: `body = git.read(path @ hash)`
     - if `message.startswith("status(")` → `spec.apply_status(…, commit_hash=hash)`만 (StatusChange 복원)
     - else → `spec.validate(body, doc_type, entry=github)` → `spec.save(document, body, hash, author, [], has_convention_error, warnings, rebuild=True)` — `version_no` 순서대로, `items` upsert
   - 마지막 커밋 본문으로 `reference.extract`, `spec.mark_convention_error(document_id, violations, warnings)`
7. `reference.resolve_missing(project_id)` — 파일 순서 때문에 미존재였던 참조 해제
8. `repo.last_processed_commit = HEAD`
9. **커밋.** 락 해제
10. `→ RebuildResult(docs, items, references, versions, convention_errors)`

**출력** [[SYNC-API-001]] `RebuildResult`

**예외** 어느 단계든 실패하면 트랜잭션 롤백. DB는 재구축 전 상태로. `! rebuild-failed {reason}`

**호출하는 것** [[SYNC-MS-002#SpecService.clear_index]] [[SYNC-MS-002#SpecService.validate]] [[SYNC-MS-002#SpecService.save]] [[SYNC-MS-002#SpecService.mark_convention_error]] · `ReferenceService.clear` `ReferenceService.extract` `ReferenceService.resolve_missing` · `git.*`

**테스트 관점**
- DB 비운 뒤 재구축: 문서·항목·참조·버전 수가 저장소와 일치
- 플래그·댓글이 있는 상태에서 재구축: 그대로 남음
- 파일 순서 때문에 미존재였던 참조가 7단계 후 해제됨
- `status(` 커밋: Version 안 늘고 StatusChange 생김
- 중간 실패: DB가 재구축 전과 같음

---

---

## 3. 미결사항

