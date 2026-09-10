---
doc_id: SYNC-MS-002
type: MS
title: MINISPEC — SpecService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — SpecService

## 0. 이 문서가 다루는 것

`core/spec/service.py`의 함수 27개. 클래스 명세 [[SYNC-DOM-002]] 4.2의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`documents`·`items`·`versions`·`status_changes`만. 다른 묶음 것이 필요하면 인자로 받는다. 항목 판정은 `item_blocks` 한 곳.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#SpecService.get_document]] | 문서 조회 |
| [[#SpecService.get_item]] | 항목 블록 조회 |
| [[#SpecService.validate]] | 규약 검증 |
| [[#SpecService.apply_frontmatter]] | 생성 시 frontmatter 채움 |
| [[#SpecService.detect_deleted_items]] | 사라진 항목 찾기 |
| [[#SpecService.create]] | 문서 행 생성 |
| [[#SpecService.save]] | 버전·항목 저장 |
| [[#SpecService.apply_status]] | 상태 변경 적용 |
| [[#SpecService.mark_deleted]] | 파일 삭제 반영 |
| [[#SpecService.version_body]] | 특정 버전 본문 |
| [[#SpecService.list_versions]] | 버전 + 상태변경 이력 |
| [[#SpecService.diff]] | 두 버전 diff |
| [[#SpecService.list_by_project]] | 프로젝트 문서 목록 |
| [[#SpecService.describe_items]] | 항목 pk → 표시 정보 |
| [[#SpecService.describe_documents]] | 문서 pk → 표시 정보 |
| [[#SpecService.versions_by_ids]] | 버전 id → 요약 |
| [[#SpecService.resolve_item]] | doc_id·item_id → pk |
| [[#SpecService.resolve_items]] | 여러 개 |
| [[#SpecService.item_pks]] | 문서의 항목 pk 지도 |
| [[#SpecService.list_items_by_project]] | 그래프용 항목 목록 |
| [[#SpecService.neighbors]] | 앞뒤 단계 문서 |
| [[#SpecService.last_author]] | 최근 버전 작성자 |
| [[#SpecService.recent_changes]] | 최근 변경 N건 |
| [[#SpecService.versions_instructed_by]] | 내가 저장시킨 버전 |
| [[#SpecService.convention_error_docs_by]] | 내 커밋의 오류 문서 |
| [[#SpecService.documents_authored_by]] | 내 문서 |
| [[#SpecService.clear_index]] | 재구축용 삭제 |
| [[#SpecService.mark_convention_error]] | 오류·경고 표시 |
| [[#SpecService.issue_doc_id]] | 문서 ID 발급 |
| [[#SpecService.item_blocks]] | 본문 → 항목 블록 |

---

## 2. 함수

#### SpecService.get_document 문서 조회

**시그니처** `get_document(doc_id: str) -> Document`

근거: [[SYNC-SEQ-001#SEQ-11]] · [[SYNC-UC-001#UC-A2]] · [[SYNC-API-002#get_document]]

**입력** `doc_id` 문서 ID

**처리**
1. `DB: documents where doc_id` · if 없음 → `! not-found {resource: document, id}`
2. `DB: items where document_id and is_deleted=false` — `item_id`, `display_name`
3. `DB: versions where document_id order by version_no desc limit 1` — 최근 작성 주체를 `AuthorRef(kind, user_id, instructed_by_id, via)`로. **users를 읽지 않는다** — 이름은 `queries`가 `AccountService.users_by_ids`로
4. `missing_refs` = 이 문서 참조 중 `is_missing`인 `raw_target` 목록 — **references는 reference 묶음이라 SpecService가 읽지 않는다.** 비워 두고 `queries.document_view`가 `ReferenceService.upstream_of_document`로 채운다
5. `→ Document(id, doc_id, doc_type, stage, status, current_body, current_version_no, current_version_id=최근 versions.id, commit_hash=최근 버전의 것, missing_refs=[], has_convention_error, convention_error_detail, incomplete_warnings, items[], last_author: AuthorRef)`. 플래그·이웃은 **넣지 않는다** — `queries.document_view`가 붙인다

**출력** `Document`. `items[].flags`·`prev_doc_id`·`next_doc_id`는 비어 있다

**예외** 없는 문서 → `not-found`. 규약 오류 문서는 예외가 아니다(UC-A2 2a)

**호출하는 것** 없음

**테스트 관점** 없는 ID → not-found · 규약 오류 문서 → 정상 반환 + `has_convention_error=True` · 삭제된 항목은 `items`에 없음

---

#### SpecService.get_item 항목 블록 조회

**시그니처** `get_item(doc_id: str, item_id: str) -> ItemView`

근거: [[SYNC-SEQ-001#SEQ-12]] · [[SYNC-UC-001#UC-A3]] · [[SYNC-API-002#get_item]]

**입력** `doc_id`, `item_id` (`#` 없이. `/`는 `~`로 왔으면 되돌림)

**처리**
1. `document = get_document(doc_id)` · if 없음 → `! not-found` (get_document가 던진다)
2. `item = DB: items where document_id and item_id` · if 없음 → `! not-found {resource: item, id, available_items: [모든 item_id]}` (UC-A3 1b)
3. if `item.is_deleted` → `! item-deleted {deleted_at}` (1a)
4. `blocks = item_blocks(document.current_body, doc_type)`. `item_id`에 해당하는 블록 본문
5. `→ ItemView(doc_id, item_id, display_name, body=블록, doc_status, doc_version_no)`. `flags`는 비움 — `queries`가

**출력** `ItemView`

**예외** `not-found`(문서·항목), `item-deleted`

**호출하는 것** [[#SpecService.get_document]] [[#SpecService.item_blocks]]

**테스트 관점** 마지막 항목 블록이 문서 끝까지 · 항목 안 `#####` 소제목이 블록에 포함 · 없는 항목 → `available_items` 채워짐

---

#### SpecService.validate 규약 검증

**시그니처** `validate(body: str, doc_type: DocType, entry: Entry, current_status: DocStatus | None = None) -> ValidateResult`

근거: [[SYNC-STD-001]] 3장·4장 · [[SYNC-UC-001#UC-S1]] · `_tools/validate.py`(원형)

**입력** `body` 전체 MD. `doc_type` 타입. `entry` 입구(`mcp`면 status 변경 검사). `current_status` DB의 현재 상태(수정 시)

**처리** — 규약 3장 순서대로. 위반은 **전부** 모은다(첫 것에서 멈추지 않음)
1. frontmatter 블록 파싱 · if 없음 → `frontmatter.missing` 추가하고 3으로 · else → 필수 필드 · `type` 목록 · `status` 값 · `doc_id` 형식과 `type` 일치 · `upstream` 형식을 각각 검사, 어긋나면 해당 rule 추가
2. if `entry == mcp and current_status and fm.status != current_status` → `frontmatter.status_change` 추가
3. 코드블록·인라인 코드를 빈 칸으로 치환한 본문에서 헤딩 순회. 타입의 항목 패턴(STD-001 2장 표 — DOM·UI·API는 `title`로 세분)으로 항목 판정
   - if 이미 본 ID → `item.duplicate` · if 토큰 끝이 `.`·`:`이고 떼면 패턴에 맞음 → `item.punct` · if 번호 앞자리 0 → `item.padding` · if `^[A-Z]+-?\d+$`인데 패턴 밖 → `item.pattern`
   - `deleted = DB: items where document_id and is_deleted=true` · if `item_id in deleted` → `item.reused`. 단 문서의 `convention_error_detail`이 `file.deleted:`로 시작하면 그 문서의 삭제 항목은 `deleted`에서 뺀다 — 파일 삭제로 지워진 것을 되살리는 것은 재사용이 아니라 복구다
4. `[[ ]]` 전부 형식 검사 → `ref.format`
5. **경고**: 필수 절마다 if 해당 절 없음 → `section.missing` · if `not items and doc_type not in (CODE, STD)` → `item.none`
6. DOM 클래스 명세면 2장·4장 mermaid의 같은 클래스 속성 대조 → `entity.mismatch` 경고
7. `→ ValidateResult(violations: [{line, rule, message}], warnings: [{rule, message}])`

**출력** `ValidateResult`. `violations`가 비면 통과

**예외** 던지지 않는다. 결과로 돌려주고 `pipeline`이 판단

**호출하는 것** [[#SpecService.item_blocks]](헤딩 순회 공유)

**테스트 관점** `_tools/validate.py`가 15개 문서에 대해 위반 0·경고 0을 내는 것이 첫 테스트 · frontmatter 없는 본문 → 위반 하나만 · `R01` → `item.padding` · `R1.` → `item.punct` · 삭제된 `R15` 재사용 → `item.reused` · MCP에서 status 바꿈 → `frontmatter.status_change`, GitHub에서는 통과 · 필수 절 하나 빼면 경고 하나, 저장은 됨

---

#### SpecService.apply_frontmatter 생성 시 frontmatter 채움

**시그니처** `apply_frontmatter(body: str, doc_id: str, doc_type: DocType, status: DocStatus) -> str`

근거: [[SYNC-SEQ-001#SEQ-19]] · [[SYNC-API-002#create_document]]

**입력** 에이전트가 보낸 `body` (frontmatter가 있을 수도 없을 수도), 발급된 `doc_id`, `doc_type`, `status`(생성이면 `draft`)

**처리**
1. if frontmatter 없음 → `---\ndoc_id:\ntype:\ntitle:\nstatus:\n---\n`을 앞에 붙임. `title` = 첫 `# ` 헤딩 · if 그것도 없음 → `doc_id`
2. if `fm.doc_id` 비어 있음 → 채움 · if `fm.doc_id != doc_id` → `! convention-violation [frontmatter.doc_id: 발급 {doc_id}와 다름]`
3. `type`·`status`: 인자로 덮어쓴다
4. 다른 필드(`title` `upstream` 등)는 그대로
5. `→ body'`

**출력** frontmatter가 채워진 본문

**예외** `doc_id` 불일치만

**호출하는 것** 없음

**테스트 관점** frontmatter 없는 본문 → 네 필드 생김 · `doc_id` 비움 → 채워짐 · `doc_id` 다른 값 → 위반 · `upstream`은 보존

---

#### SpecService.detect_deleted_items 사라진 항목 찾기

**시그니처** `detect_deleted_items(document: Document, body: str) -> list[int]`

근거: [[SYNC-SEQ-001#SEQ-1]] 6단계 · [[SYNC-UC-001#UC-A6]] 4b · [[SYNC-UC-001#UC-H13]]

**입력** 현재 `document`, 새 `body`

**처리**
1. `new_ids = {b.item_id for b in item_blocks(body, document.doc_type)}`
2. `DB: items where document_id and is_deleted=false` → `cur`
3. `→ [i.id for i in cur if i.item_id not in new_ids]`

**출력** 사라진 항목의 pk 목록. 하위 참조가 있는지는 **모른다** — `pipeline`이 `ReferenceService.downstream`으로 판정

**예외** 없음

**호출하는 것** [[#SpecService.item_blocks]]

**테스트 관점** 항목 하나 지운 본문 → pk 하나 · 항목 제목만 바꾼 본문 → 빈 목록 · 순서만 바꾼 본문 → 빈 목록

---

#### SpecService.create 문서 행 생성

**시그니처** `create(project_id: int, doc_id: str, doc_type: DocType, body: str, commit_hash: str, author: Author, message: str, validate_result: ValidateResult | None = None) -> VersionRow`

근거: [[SYNC-SEQ-001#SEQ-19]] 8단계

**입력** 전부 `pipeline`이 확정한 값. `commit_hash`는 push 성공 후

**처리** — 호출자의 트랜잭션 안
1. `DB: documents insert (project_id, doc_id, doc_type, status=frontmatter의 status (없으면 draft), current_body=body, current_version_no=1, has_convention_error=bool(violations), convention_error_detail, incomplete_warnings=warnings JSON)` — `save` 7단계와 같은 규칙. **첫 저장부터 경고가 남아야** 생성 직후 승인이 막힌다
2. `blocks = item_blocks(body, doc_type)`. `DB: items insert` 블록마다 `(document_id, item_id, display_name, is_deleted=False)`
3. `DB: versions insert (document_id, version_no=1, commit_hash, body, author_kind, author_user_id, instructed_by_user_id, via, message, created_at)`
4. `→ Version`

**출력** `VersionRow(version_no=1)` (ORM)

**예외** `doc_id` unique 위반 → `! project-code-conflict`는 아니고 `! not-found`도 아님 — `issue_doc_id`가 락 안에서 발급하므로 일어나지 않는다. 일어나면 버그

**호출하는 것** [[#SpecService.item_blocks]]

**테스트 관점** 생성 후 `get_document` → `current_version_no=1`, 항목 수 = 헤딩 수

---

#### SpecService.save 버전·항목 저장

**시그니처** `save(document: Document, body: str, commit_hash: str, author: Author, message: str, deleted_item_pks: list[int], validate_result: ValidateResult | None = None, rebuild: bool = False) -> VersionRow`

근거: [[SYNC-SEQ-001#SEQ-1]] 8단계 · [[SYNC-UC-001#UC-A6]] 6a

**입력** `document` 현재 행(DTO의 `id`로 다시 읽는다). `body` 새 본문. `commit_hash`. `author`. `deleted_item_pks` — `pipeline`이 확인 끝낸 것. `validate_result` — github 경로에서 위반이어도 저장할 때. 위반·경고 둘 다 여기서. `rebuild` — 재구축이면 `version_no`를 커밋 순서대로

**처리** — 호출자의 트랜잭션 안. **버전 충돌 검사는 하지 않는다**(`pipeline` 5단계가 이미)
1. `new_no = document.current_version_no + 1`
2. `DB: versions insert (document_id, version_no=new_no, commit_hash, body, author_kind, author_user_id, instructed_by_user_id, via=author.via를 mcp|web|github로 접음, message)`
3. `blocks = item_blocks(body, doc_type)`. 블록마다 `DB: items where document_id and item_id` · if 있음 → `display_name` 갱신, **`is_deleted=false, deleted_at=null`로 되돌림**(본문에 다시 나타났으므로 복구) · else → insert
4. `deleted_item_pks`마다 `DB: items set is_deleted=true, deleted_at=now`
5. if `author.via == github` → `new_status = fm.status` (원본이 진실) · else → `new_status = document.status`
6. if `document.status == approved and body != document.current_body` → `new_status = review`, `DB: status_changes insert (from=approved, to=review, changed_by=author.user, reason="본문 수정으로 자동 강등", commit_hash=None)` (UC-A6 6a)
7. `DB: documents update (current_body, current_version_no=new_no, status=new_status)` · if `validate_result` → `has_convention_error = bool(violations)`, `convention_error_detail = violations를 "rule: message" 줄로 (없으면 null)`, `incomplete_warnings = warnings JSON (없으면 null)` · else → 오류·경고 컬럼 그대로
8. `→ Version`

**출력** 새 `VersionRow` (ORM)

**예외** 없음 (DB 오류는 트랜잭션이 잡음)

**호출하는 것** [[#SpecService.item_blocks]]

**테스트 관점** 저장 후 `version_no` +1 · 승인 문서 저장 → `review` + StatusChange · github 경로에서 frontmatter status가 `approved`로 바뀐 본문 → 그대로 `approved` · 삭제 pk → `is_deleted=true`이고 행은 남음 · 경고 있는 저장 → `incomplete_warnings` 채워짐

---

#### SpecService.apply_status 상태 변경 적용

**시그니처** `apply_status(document: Document, new_body: str, commit_hash: str | None, user: User, reason: str | None, to: DocStatus | None = None) -> None`

근거: [[SYNC-SEQ-001#SEQ-5]] · `pipeline.save_pipeline` 8단계 `web_status` 분기(`reason`은 `pipeline.change_status`가 인자로 넘긴다 — 커밋 메시지를 다시 파싱하지 않는다) · `pipeline.rebuild`의 status 커밋 복원

**처리** — 호출자의 트랜잭션 안. Version을 만들지 않는다
1. `to = to or new_body의 frontmatter status`
2. `DB: status_changes insert (document_id, from=document.status, to, changed_by=user, reason, commit_hash, changed_at=now)`
3. `DB: documents update (status=to, current_body=new_body)`

**테스트 관점** Version 수 그대로 · StatusChange에 commit_hash 있음 · `current_body`의 frontmatter만 바뀜

---

#### SpecService.mark_deleted 파일 삭제 반영

**시그니처** `mark_deleted(document: Document, commit_hash: str, author: Author) -> list[int]`

근거: [[SYNC-UC-001#UC-G1]] 3d · [[SYNC-MS-007#pipeline.process_commit]] · 결정: 원본에서 파일이 사라지면 문서는 남기고 `draft` + `file.deleted`

**처리** — 호출자의 트랜잭션 안
1. `DB: items where document_id and is_deleted=false` → 전부 `is_deleted=true, deleted_at=now` · pk 목록 기억
2. `DB: status_changes insert (from=document.status, to=draft, changed_by=author.user, reason="파일 삭제됨", commit_hash)`
3. `DB: documents update status=draft, has_convention_error=true, convention_error_detail="file.deleted: {commit_hash}"`
4. `→` 삭제된 항목 pk 목록 (호출자가 `raise_broken`)

**테스트 관점** 파일 삭제 push → 문서 행 남음, `draft`, 항목 전부 삭제됨, 하위에 끊어진 참조 · 파일 되살려 push → 다음 저장이 `file.deleted`를 지우고, 되살아난 항목 ID는 위반이 아니며 `is_deleted`가 풀린다(복구)

---

#### SpecService.version_body 특정 버전 본문

**시그니처** `version_body(doc_id: str, version_no: int) -> str`

근거: [[SYNC-MS-007#pipeline.revert]] 1단계 — 되돌릴 본문을 읽는다

**처리** `DB: versions join documents where doc_id and version_no` → `body` · if 없음 → `! not-found {resource: version}`

---

#### SpecService.list_versions 버전 + 상태변경 이력

**시그니처** `list_versions(doc_id: str) -> list[Version]`

근거: [[SYNC-SEQ-001#SEQ-C1]] · [[SYNC-UC-001#UC-H6]]

**처리**
1. `DB: versions where document_id` → `Version(version_no, commit_hash, message=versions.message, author=AuthorRef, created_at)` (DTO)
2. `DB: status_changes where document_id and commit_hash is not null` → `Version(version_no=None, commit_hash, message="status(...): from → to", author=AuthorRef(kind=human, user_id=changed_by_user_id, instructed_by_id=None, via="web"), created_at=changed_at)`
3. 둘을 `created_at` 내림차순으로 합쳐 `→`

**출력** `Version[]` (DTO, API 스키마 + `doc_id`). status 행은 `version_no: null`. `author`는 `AuthorRef` — 이름은 호출한 입구(라우터 또는 `queries`)가 `users_by_ids`로 채워 API `author`로 내보낸다

**테스트 관점** 버전 3 + 상태변경 2 → 5행 시각순 · 자동 강등 StatusChange(commit_hash null)는 안 나옴 — 본문 커밋 행에 딸린 것

---

#### SpecService.diff 두 버전 diff

**시그니처** `diff(doc_id: str, from_no: int, to_no: int, context: int = settings.DIFF_CONTEXT_LINES) -> Diff`

근거: [[SYNC-SEQ-001#SEQ-15]] · [[SYNC-UC-001#UC-H6]] · `TrackingService.detect_impact`·`get_flag`도 쓴다

**입력** 문서 ID, 두 버전 번호. `from_no > to_no`도 허용(역방향 diff)

**처리**
1. `DB: versions where document_id and version_no in (from, to)` → 본문 둘 · if 하나라도 없음 → `! not-found`
2. 각 본문을 `item_blocks`로 자른다. 항목 ID → 블록 텍스트. 항목 밖 텍스트는 `item_id=None` 블록 하나
3. 두 쪽에 있는 항목 ID 합집합마다 `difflib.unified_diff(from_block, to_block, n=context)` → 줄 목록 `(op: add|del|ctx, text)`. 양쪽 같으면 hunk 없음

   `context`는 앞뒤로 몇 줄을 함께 보여줄지다. 기본은 `DIFF_CONTEXT_LINES`(3). 한 줄이면 마크다운 문단에서 무엇이 바뀌었는지는 보여도 **어느 절의 변경인지가 안 보인다.** 이 diff는 이력(UI-7)·플래그(UI-11)·전파(UI-12) 세 화면에 쓰인다
4. 새로 생긴 항목은 전부 `add`, 사라진 항목은 전부 `del`
5. `→ Diff(from_version, to_version, hunks=[{item_id, lines}])`. `downstream_count`는 **비움** — `queries.diff_with_impact`가 붙인다

**출력** `Diff`

**예외** `not-found`

**호출하는 것** [[#SpecService.item_blocks]]

**테스트 관점** `context`를 키우면 `ctx` 줄만 늘고 `add`·`del` 수는 그대로 · `detect_impact`와 `pipeline`은 hunk의 `item_id`만 쓰므로 `context`와 무관하게 같은 결과

**테스트 관점** 항목 하나만 고침 → hunk 하나 · 공백만 바꿈 → hunk 없음(`text.strip()` 비교) · 항목 추가 → 전부 add인 hunk · 역방향 → op가 뒤집힘

---

#### SpecService.list_by_project 프로젝트 문서 목록

**시그니처** `list_by_project(project_id: int, stage: int | None = None, status: DocStatus | None = None, has_convention_error: bool | None = None) -> list[DocumentSummary]`

근거: [[SYNC-SEQ-001#SEQ-10]] · [[SYNC-UC-001#UC-A5]] · [[SYNC-API-001#GET/api/projects/{code}/docs]]

**처리**
1. `DB: documents where project_id` + 조건. `stage`는 `doc_type`의 단계 번호(STD-001 2장 순서. STD는 단계 없음 → `stage=None` 조건에서만)
2. 문서마다 최근 버전 작성자 (`versions` 조인, 문서당 1행)
3. 정렬: `stage, doc_id`
4. `→ DocumentSummary[]`. `counts`는 비움 — `queries`가

**테스트 관점** `stage=6` → DOM 셋 · `status=approved` 필터 · STD 문서는 `stage` 필터 없을 때만

---

#### SpecService.describe_items pk → 표시 정보

**시그니처** `describe_items(item_pks: list[int]) -> dict[int, ItemRef]`

근거: [[SYNC-SEQ-001#SEQ-13]] · `ReferenceService`가 pk만 알기 때문

**처리** `DB: items join documents where items.id in pks` → `{pk: ItemRef(doc_id, item_id, display_name, is_deleted)}`. **항목 pk만.** 문서 pk는 id 공간이 겹치므로 `describe_documents`로 따로

**테스트 관점** 빈 목록 → 빈 dict · 삭제된 항목 → `is_deleted=True`로 포함

---

#### SpecService.describe_documents 문서 pk → 표시 정보

**시그니처** `describe_documents(document_ids: list[int]) -> dict[int, DocRef]`

**처리** `DB: documents where id in ids` → `{id: DocRef(document_id, doc_id, title=frontmatter title, stage, status)}`. 참조의 `to_document_id`(문서 단위 참조)·댓글 응답의 `doc_id`·미결정 목록이 쓴다. `doc_id_of(document_id)`는 이걸로 대신한다

---

#### SpecService.versions_by_ids 버전 id → 요약

**시그니처** `versions_by_ids(version_ids: list[int]) -> dict[int, VersionBrief]`

**처리** `DB: versions where id in ids` → `{id: VersionBrief(id, document_id, version_no, created_at, message)}`. 플래그의 `cause_version_id`를 `cause_version_no`로, 미결정의 `version_id`를 문서·번호·메시지로 바꿀 때. **쿼리 한 번**

---

#### SpecService.resolve_item doc_id·item_id → pk

**시그니처** `resolve_item(doc_id: str, item_id: str) -> int`

**처리** `item = DB: items join documents where doc_id and item_id` · if 없음 → `! not-found` · if `item.is_deleted` → `! item-deleted` · else → `item.id`

**테스트 관점** 삭제된 항목 → `item-deleted`(pk는 있지만)

---

#### SpecService.resolve_items 여러 개

**시그니처** `resolve_items(doc_id: str, item_ids: list[str]) -> list[int]`

**처리** `resolve_item`을 IN 쿼리 하나로. 없는 것은 건너뛴다(예외 없음). `diff`의 hunk에 새로 생긴 항목이 아직 `items`에 없을 수 있어서

---

#### SpecService.item_pks 문서의 항목 pk 지도

**시그니처** `item_pks(document_id: int) -> dict[str, int]`

근거: [[SYNC-MS-007#pipeline.save_pipeline]] 10단계 — `ReferenceService.extract`에 넘길 `{item_id: pk}`. `save`가 `Version`을 돌려주므로 따로 읽는다

**처리** `DB: items where document_id and is_deleted=false` → `{item_id: id}`. 저장 직후(같은 트랜잭션)에 부르므로 방금 upsert한 것이 보인다

---

#### SpecService.list_items_by_project 그래프용 항목 목록

**시그니처** `list_items_by_project(project_id: int, stage: int | None = None, doc_id: str | None = None) -> list[ItemBrief]`

근거: [[SYNC-SEQ-001#SEQ-14]] · [[SYNC-UC-001#UC-H4]]

**처리** `DB: items join documents where project_id and is_deleted=false` + 조건 → `ItemBrief(pk, doc_id, item_id, stage, display_name)`. 문서도 노드가 되므로 문서마다 `item_id=None`인 `ItemBrief` 하나 추가(문서 단위 참조 대상)

---

#### SpecService.neighbors 앞뒤 단계 문서

**시그니처** `neighbors(doc_id: str) -> tuple[str | None, str | None]`

근거: [[SYNC-SEQ-001#SEQ-11]] · UI-5 요소 9

**처리** if `doc_type == STD` → `(None, None)` · else → 같은 프로젝트에서 `stage-1`·`stage+1` 문서의 `doc_id` 순 첫 것. 각각 없으면 None

**테스트 관점** 6단계 DOM-002 → prev=INFRA-001, next=UI-001 (DOM-001·003이 아니라 앞뒤 **단계**)

---

#### SpecService.last_author 최근 버전 작성자

**시그니처** `last_author(document_id: int) -> AuthorRef | None`

근거: [[SYNC-SEQ-001#SEQ-3]] · `TrackingService.raise_flags` 담당자 결정 (클래스 5장 1)

**처리** `v = DB: versions where document_id order by version_no desc limit 1` · if 없음 → None · else → `AuthorRef(v.author_kind, v.author_user_id, v.instructed_by_user_id, v.via)`. 담당자 결정은 `.user_id`. 자리표시 User도 그대로 — 담당은 되지만 로그인 전엔 못 본다

---

#### SpecService.recent_changes 최근 변경 N건

**시그니처** `recent_changes(project_id: int, n: int = 10) -> list[Version]`

근거: [[SYNC-SEQ-001#SEQ-9]] · UI-4 요소 5

**처리** `list_versions`와 같이 `versions` ∪ `status_changes(commit_hash not null)`를 프로젝트 전체로, `created_at desc, id desc limit n` (같은 시각 안정 정렬). 각 행에 `doc_id`

---

#### SpecService.versions_instructed_by 내가 저장시킨 버전

**시그니처** `versions_instructed_by(version_ids: list[int], user_id: int) -> list[int]`

근거: [[SYNC-SEQ-001#SEQ-17]] · 내 할 일 전파 미결정 묶음

**처리** `DB: versions where id in ids and (instructed_by_user_id=user_id or author_user_id=user_id)` → id 목록. 에이전트 저장이면 지시자, 되돌리기면 작성자

---

#### SpecService.convention_error_docs_by 내 커밋의 오류 문서

**시그니처** `convention_error_docs_by(user_id: int) -> list[DocumentSummary]`

**처리** `DB: documents where has_convention_error and 최근 version의 author_user_id=user_id`

---

#### SpecService.documents_authored_by 내 문서

**시그니처** `documents_authored_by(user_id: int) -> list[int]`

**처리** 최근 버전 작성자가 `user_id`인 `document_id` 목록. 내 할 일 미해결 댓글 묶음의 "내 문서" 기준(클래스 5장 1과 같은 결정)

---

#### SpecService.clear_index 재구축용 삭제

**시그니처** `clear_index(project_id: int) -> None`

근거: [[SYNC-SEQ-001#SEQ-21]] · [[SYNC-DOM-003]] 설계 규칙

**처리** `DB: delete versions where document in project`. **`documents`·`items`는 지우지 않는다** — `flags`·`comments`·`status_changes`가 FK. `items`는 재구축 `save`가 upsert. `current_version_no`는 **건드리지 않는다** — `ck_documents_version_no(>=1)` 때문에 0을 넣을 수 없다. 재구축의 `save(rebuild=True)`가 남은 버전 수 + 1로 다시 매긴다

---

#### SpecService.mark_convention_error 오류·경고 표시

**시그니처** `mark_convention_error(document_id: int, violations: list | None, warnings: list | None) -> None`

**처리** `DB: documents update has_convention_error=(violations 있음), convention_error_detail=violations를 "rule: message" 줄로, incomplete_warnings=warnings JSON`. 둘 다 비면 오류 해제

---

#### SpecService.issue_doc_id 문서 ID 발급

**시그니처** `issue_doc_id(project_id: int, code: str, doc_type: DocType) -> str` (private) — `code`는 인자로 받는다. SpecService가 `projects`를 읽지 않게

근거: [[SYNC-SEQ-001#SEQ-19]] · [[SYNC-STD-001]] 1.1

**처리** `DB: max(번호) from documents where project_id and doc_type` — `doc_id`의 마지막 세 자리. +1, 세 자리 패딩. `→ f"{code}-{doc_type}-{n:03d}"`. `code`는 pipeline이 `ProjectService.get`에서 얻어 넘긴다. **저장소 락 안에서만** 부른다(동시 발급 방지)

**테스트 관점** 첫 PRD → `-001` · 002 삭제 후 → `-003`(재사용 안 함. 문서는 삭제 안 하지만 규칙은 같다)

---

#### SpecService.item_blocks 본문 → 항목 블록

**시그니처** `item_blocks(body: str, doc_type: DocType, title: str | None = None) -> list[ItemBlock]` (private)

근거: [[SYNC-STD-001]] 1.3 · 클래스 5장 2 (미결 해소)

**입력** 본문, 타입, `title`(DOM·UI·API처럼 타입 안에서 패턴이 갈릴 때)

**처리**
1. frontmatter 제거
2. 코드블록(```` ``` ````)·인라인 코드(`` ` ``)를 같은 길이의 공백으로 치환 — 줄 번호 유지. 이 마스킹과 헤딩·참조 정규식은 `core/markdown.py` 순수 함수 — `ReferenceService.extract`도 같은 것을 쓴다
3. 줄마다 `^(#{1,6}) (\S+)(?: (.*))?$` · if 첫 토큰이 타입 패턴에 맞음 → 항목 시작, 레벨 기억 · else → 절(무시)
4. 블록 끝 = 다음 헤딩 중 `레벨 <= 시작 레벨`인 것의 직전 줄 · if 그런 헤딩 없음 → 문서 끝
5. `→ [ItemBlock(item_id, display_name=제목, level, start_line, end_line, text)]`. `text`는 **원본**(치환 전) 줄 범위

**출력** 항목 블록 목록. 순서는 본문 순

**호출하는 것** 없음. `validate`·`get_item`·`detect_deleted_items`·`create`·`save`·`diff`가 전부 이걸 쓴다 — **항목 판정은 여기 한 곳**

**테스트 관점** `_tools/validate.py`와 같은 결과 · 코드블록 안 `#### R99`는 항목 아님 · `#### R1` 아래 `##### 소제목`은 R1 블록 안 · 문서 끝 항목은 끝까지

---

## 3. 미결사항

- [x] `mark_deleted` 후 파일을 되살리면 항목 ID가 `item.reused` 위반에 걸린다. 되살림은 재사용이 아니라 복구 — 예외 필요 — 결정: **파일 삭제로 지워진 항목은 복구다.** 문서의 `convention_error_detail`이 `file.deleted:`로 시작하면 그 문서의 삭제 항목은 `item.reused`에서 빼고, 본문에 다시 나타나면 `is_deleted`·`deleted_at`을 되돌린다. 파일은 살아 있는데 항목만 지웠다가 같은 ID를 다시 쓰는 것만 재사용으로 남긴다

- [x] `diff`의 hunk 문맥 줄 수 (`n=1`) — 화면에서 부족할 수 있다 — 결정: 설정값으로 뺀다 (`DIFF_CONTEXT_LINES`, 기본 3). 한 줄은 마크다운 문단에 부족해 어느 절의 변경인지 안 보인다. `detect_impact`와 `pipeline`은 hunk의 `item_id`만 쓰므로 동작이 안 바뀐다
- [x] `list_versions`가 자동 강등 StatusChange(commit_hash null)를 보여줄지 — 결정: 안 보여준다. `commit_hash is not null`인 상태 변경만 (본문 커밋에 딸린 강등은 그 버전 행이 이미 보인다)
