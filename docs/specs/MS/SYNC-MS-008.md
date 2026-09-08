---
doc_id: SYNC-MS-008
type: MS
title: MINISPEC — queries — 읽기 조합
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — queries — 읽기 조합

## 0. 이 문서가 다루는 것

`core/queries.py`의 함수 12개. 클래스 명세 [[SYNC-DOM-002]] 4.8의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`queries`는 `pipeline`과 대칭이다. 서비스는 자기 테이블만 알고, `queries`가 pk·ID로 이어 붙여 응답 형태([[SYNC-API-001]] 4장)를 만든다. **절대 쓰지 않는다.**

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#queries.project_summary]] | 프로젝트 목록 + 단계 11칸 + 건수 |
| [[#queries.project_detail]] | + 문서 목록 + 최근 변경 |
| [[#queries.document_list]] | 문서 목록 + 문서별 건수 |
| [[#queries.document_view]] | 문서 + 항목 플래그 + 이웃 |
| [[#queries.item_view]] | 항목 + 플래그 |
| [[#queries.item_references_view]] | 상위·하위 참조 + 표시 이름 + 플래그 |
| [[#queries.graph_view]] | 노드·간선 |
| [[#queries.diff_with_impact]] | diff + 하위 건수 |
| [[#queries.todo]] | 내 할 일 여섯 묶음 |
| [[#queries.project_items]] | 프로젝트 플래그·댓글·오류 목록 |
| [[#queries.upstream_checklist]] | 승인 전 상위 대조 목록 |
| [[#queries.decision_view]] | 전파 미결정 상세 |
| [[#queries.flag_view]] | 플래그 상세 |

---

## 2. 함수

#### queries.project_summary 프로젝트 목록 + 단계 11칸 + 건수

**시그니처** `async def project_summary() -> list[ProjectSummary]`

근거: [[SYNC-SEQ-001#SEQ-9]] · [[SYNC-UC-001#UC-H14]] 1~2 · [[SYNC-API-001#GET/api/projects]]

**처리**
1. `projects = ProjectService.list_projects()`
2. 프로젝트마다:
   - `docs = SpecService.list_by_project(project_id)`
   - **단계 11칸**: 단계 `1..11`마다 `stage_docs = [d for d in docs if d.stage == n]`
     - if 비어 있음 → `status=None, doc_count=0`
     - else → `status = min(stage_docs.status, key=순서 draft<review<approved)` (UC-H14 1a), `doc_count`
     - `gate_warning` = `doc_count > 0 and any(앞 단계 k<n 중 status != approved and doc_count > 0)` (1b)
   - `std_docs = [d for d in docs if d.doc_type == STD]`
   - `counts = TrackingService.count_flags(project_id)` → `{needs_check, broken_ref}`
   - `counts.unresolved_comments = CommentService.count_unresolved(project_id)`
   - `counts.convention_errors = sum(d.has_convention_error for d in docs)` · `counts.incomplete = sum(bool(d.incomplete_warnings))`
   - `updated_at = max(d.updated_at)`
3. `→` 정렬 `updated_at desc`

**출력** `ProjectSummary[]`. `stages`는 항상 11개

**호출하는 것** `ProjectService.list_projects` · `SpecService.list_by_project` · `TrackingService.count_flags` · `CommentService.count_unresolved`

**테스트 관점** 문서 없는 프로젝트 → 11칸 전부 null · 승인 2 + 초안 1인 단계 → `draft` · 3단계 검토중인데 4단계에 문서 → 4단계 `gate_warning=True` · STD 문서는 11칸에 안 세고 `std_docs`에

---

#### queries.project_detail + 문서 목록 + 최근 변경

**시그니처** `async def project_detail(code: str) -> ProjectDetail`

근거: [[SYNC-SEQ-001#SEQ-9]] · [[SYNC-API-001#GET/api/projects/{code}]]

**처리**
1. `project = ProjectService.get(code)` · if 없음 → `! not-found`
2. `summary = project_summary()`에서 이 프로젝트 것 (단계·건수 계산 공유)
3. `docs = document_list(code)` (문서별 건수 포함)
4. `recent = SpecService.recent_changes(project_id, 10)`
5. `→ ProjectDetail(summary, remote_url, docs, recent_changes=recent)`

**호출하는 것** [[#queries.project_summary]] [[#queries.document_list]] · `SpecService.recent_changes`

---

#### queries.document_list 문서 목록 + 문서별 건수

**시그니처** `async def document_list(code: str, stage: int | None = None, status: DocStatus | None = None) -> list[DocumentSummary]`

근거: [[SYNC-SEQ-001#SEQ-10]] · [[SYNC-API-001#GET/api/projects/{code}/docs]] · [[SYNC-API-002#list_documents]]

**처리**
1. `project = ProjectService.get(code)`
2. `docs = SpecService.list_by_project(project_id, stage, status)`
3. `ids = [d.id for d in docs]` · `flags = TrackingService.count_flags_by_document(ids)` · `comments = CommentService.count_unresolved_by_document(ids)` — **각각 쿼리 한 번** (N+1 금지)
4. 문서마다 `counts = {needs_check, broken_ref} ← flags[id]`, `unresolved_comments ← comments[id]`, 없으면 0
5. `→ docs`. MCP `list_documents`는 이걸 `stages`로 다시 묶는다(단계마다 `docs[]`)

**호출하는 것** `ProjectService.get` · `SpecService.list_by_project` · `TrackingService.count_flags_by_document` · `CommentService.count_unresolved_by_document`

**테스트 관점** 문서 30개 → DB 쿼리 3번(문서·플래그·댓글) · 플래그 없는 문서 → counts 전부 0

---

#### queries.document_view 문서 + 항목 플래그 + 이웃

**시그니처** `async def document_view(doc_id: str) -> Document`

근거: [[SYNC-SEQ-001#SEQ-11]] · [[SYNC-UC-001#UC-H2]] · [[SYNC-API-001#GET/api/docs/{docId}]] · [[SYNC-API-002#get_document]]

**처리**
1. `doc = SpecService.get_document(doc_id)` · if 없음 → `! not-found` (전파)
2. `pks = [i.pk for i in doc.items]` · `flags = TrackingService.flags_for_items(pks)` → `{pk: [kind]}`
3. 항목마다 `item.flags = flags.get(pk, [])`
4. `doc.prev_doc_id, doc.next_doc_id = SpecService.neighbors(doc_id)`
5. `names = AccountService.users_by_ids([doc.last_author.user_id, doc.last_author.instructed_by_id])` → API `Author{kind, user: UserRef, instructed_by, via}`로 채움
6. `→ doc`

**호출하는 것** `SpecService.get_document` · `TrackingService.flags_for_items` · `SpecService.neighbors` · `AccountService.users_by_ids`

**테스트 관점** 플래그 있는 항목 → `flags=["needs_check"]` · 규약 오류 문서 → 정상 반환 · 첫 단계 문서 → `prev_doc_id=None`

---

#### queries.item_view 항목 + 플래그

**시그니처** `async def item_view(doc_id: str, item_id: str) -> ItemView`

**처리** `v = SpecService.get_item(doc_id, item_id)` (없음·삭제 예외 전파) · `v.flags = TrackingService.flags_for_items([v.pk]).get(pk, [])` · `→ v`

---

#### queries.item_references_view 상위·하위 참조 + 표시 이름 + 플래그

**시그니처** `async def item_references_view(doc_id: str, item_id: str) -> ItemReferences`

근거: [[SYNC-SEQ-001#SEQ-13]] · [[SYNC-UC-001#UC-H3]] · [[SYNC-UC-001#UC-A4]] · [[SYNC-API-002#get_references]]

**처리**
1. `pk = SpecService.resolve_item(doc_id, item_id)` · 예외 전파 (`not-found` · `item-deleted`)
2. `document_id = pk의 문서`
3. `up = ReferenceService.upstream(pk)` · `down = ReferenceService.downstream(pk) + ReferenceService.downstream_of_document(document_id)` — 문서 전체 참조도 이 항목의 하위로 본다
4. `need = {e.to_item_pk for e in up} ∪ {e.to_document_id…} ∪ {e.from_item_pk for e in down}` · `names = SpecService.describe_items(need)` — **한 번**
5. `RefEdge` → `ItemRef`: `to_item_pk`가 있으면 `names[pk]` · `to_document_id`만 있으면 `ItemRef(doc_id, item_id=None, display_name=문서 제목)` · `is_missing`이면 `ItemRef(raw_target만, is_missing=True)`
6. `flags = TrackingService.flags_for_items([pk])` → `FlagSummary[]` (미해결만)
7. `→ ItemReferences(doc_id, item_id, upstream, downstream, flags)`

**호출하는 것** `SpecService.resolve_item` `SpecService.describe_items` · `ReferenceService.upstream` `downstream` `downstream_of_document` · `TrackingService.flags_for_items`

**테스트 관점** 미존재 참조 → `upstream`에 `is_missing=True, raw_target` · 문서 전체 참조 → `downstream`에 `item_id=None` · 고립 항목 → 둘 다 빈 목록

---

#### queries.graph_view 노드·간선

**시그니처** `async def graph_view(code: str, stage: int | None = None, doc: str | None = None) -> Graph`

근거: [[SYNC-SEQ-001#SEQ-14]] · [[SYNC-UC-001#UC-H4]] · [[SYNC-API-001#GET/api/projects/{code}/graph]]

**처리**
1. `project = ProjectService.get(code)`
2. `nodes = SpecService.list_items_by_project(project_id, stage, doc)` — 항목 + 문서 노드(`item_id=None`)
3. `pks = {n.pk}` · `edges = ReferenceService.references_among(pks, include_document_targets=True)`
4. if `stage or doc` (범위 좁힘, UC-H4 2b) → `edges`의 끝점 중 `pks` 밖의 것을 모아 `SpecService.describe_items`로 노드 추가. 범위 밖이지만 이어진 것만
5. `isolated = {n.pk} - {e.from} - {e.to}` (UC-H4 2a)
6. 노드 `id = f"{doc_id}#{item_id}"` (문서 노드는 `doc_id`만) · 간선 `to`는 미존재면 `None`
7. `→ Graph(nodes, edges)`. **좌표 없음**

**호출하는 것** `ProjectService.get` · `SpecService.list_items_by_project` `describe_items` · `ReferenceService.references_among`

**테스트 관점** 전체 → 항목 수 = 노드 수(문서 노드 포함) · `stage=2` → PRD 항목 + 그것에 직접 이어진 것만 · 참조 없는 항목 → `isolated=True`

---

#### queries.diff_with_impact diff + 하위 건수

**시그니처** `async def diff_with_impact(doc_id: str, from_no: int, to_no: int) -> Diff`

근거: [[SYNC-SEQ-001#SEQ-15]] · [[SYNC-UC-001#UC-H6]] 3a

**처리**
1. `d = SpecService.diff(doc_id, from_no, to_no)`
2. `ids = [h.item_id for h in d.hunks if h.item_id]` · `pks = SpecService.resolve_items(doc_id, ids)` (없는 건 건너뜀)
3. `counts = ReferenceService.count_downstream(pks)`
4. hunk마다 `downstream_count = counts.get(pk, 0)` · 새로 생긴 항목(pk 없음)은 0
5. `→ d`

---

#### queries.todo 내 할 일 여섯 묶음

**시그니처** `async def todo(user: User) -> Todo`

근거: [[SYNC-SEQ-001#SEQ-17]] · [[SYNC-UC-001#UC-H15]] · [[SYNC-API-001#GET/api/todo]]

**처리**
1. `needs_check, broken_ref, upstream_impact = TrackingService.flags_for_assignee(user.id)` — kind별로 나눔
2. `unassigned = TrackingService.flags_unassigned()`
3. `pending_ids = TrackingService.pending_decisions_for(user.id)` → `mine = SpecService.versions_instructed_by(pending_ids, user.id)` → 버전마다 `(version_id, doc_id, version_no, message, affected_count, created_at)`. `affected_count`는 `TrackingService.get_decision(vid).affected_count`
4. `convention_errors = SpecService.convention_error_docs_by(user.id)`
5. `my_docs = SpecService.documents_authored_by(user.id)` → `unresolved_comments = CommentService.unresolved_in(my_docs)` → `CommentSummary`(excerpt 80자)
6. 플래그 전부의 `target`·`cause` pk를 모아 `SpecService.describe_items` — **한 번**
7. 각 묶음 `raised_at`·`created_at` 오름차순 (오래된 게 위)
8. `total = len(needs_check)+len(broken_ref)+len(upstream_impact)+len(pending)+len(convention_errors)+len(unresolved_comments)` — `unassigned` 제외
9. `→ Todo`

**호출하는 것** `TrackingService.flags_for_assignee` `flags_unassigned` `pending_decisions_for` `get_decision` · `SpecService.versions_instructed_by` `convention_error_docs_by` `documents_authored_by` `describe_items` · `CommentService.unresolved_in`

**테스트 관점** 아무것도 없는 사용자 → 여섯 묶음 빈 배열, `total=0` · 담당 미지정 플래그 → 모든 사용자의 `unassigned`에, `total`엔 안 셈 · 에이전트가 저장한 미결정 → 지시자의 `pending_decisions`에

---

#### queries.project_items 프로젝트 플래그·댓글·오류 목록

**시그니처** `async def project_items(code: str, kind: str) -> list`

근거: [[SYNC-SEQ-001#SEQ-18]] · [[SYNC-UC-001#UC-H14]] 4 · [[SYNC-API-001#GET/api/projects/{code}/flags]]

**처리**
1. `project = ProjectService.get(code)`
2. if `kind in (needs_check, broken_ref)` → `flags = TrackingService.flags_in_project(project_id, kind)` → `describe_items`로 채워 `FlagSummary[]`
3. if `kind == comments` → `doc_ids = SpecService.list_by_project(project_id)의 id` → `CommentService.unresolved_in(doc_ids)` → `CommentSummary[]`
4. if `kind == convention_errors` → `SpecService.list_by_project(project_id, has_convention_error=True)` → `DocumentSummary[]`
5. if `kind == incomplete` → `list_by_project` 중 `incomplete_warnings` 있는 것
6. else → `! 422 unknown kind`

---

#### queries.upstream_checklist 승인 전 상위 대조 목록

**시그니처** `async def upstream_checklist(doc_id: str) -> list[UpstreamCheck]`

근거: [[SYNC-SEQ-001#SEQ-5]] · [[SYNC-UC-001#UC-H8]] 3 · [[SYNC-API-001#GET/api/docs/{docId}/upstream]] · UI-5 다이얼로그 11

**처리**
1. `doc = SpecService.get_document(doc_id)`
2. `edges = ReferenceService.upstream_of_document(doc.id)` — 이 문서 **모든 항목**의 upstream 참조 + frontmatter upstream. 미존재 참조 제외
3. 대상별로 묶는다 (같은 상위 항목을 여러 곳에서 참조하면 한 행): `target_pk → referenced_from[]` (참조한 이 문서의 항목 ID. 문서 단위면 `"(문서)"`)
4. `names = SpecService.describe_items(targets)` · 대상 문서마다 `status`·`current_version_no`
5. `→ [UpstreamCheck(target: ItemRef, target_version_no, target_status, referenced_from)]` 상위 문서 단계순

**호출하는 것** `SpecService.get_document` `describe_items` · `ReferenceService.upstream_of_document`(신규 — 문서 전체의 upstream. MS-003 되먹임)

**테스트 관점** 참조 없는 문서(RFQ) → 빈 목록 → UI가 "상위 없음" · 같은 상위를 세 항목이 참조 → 한 행, `referenced_from` 셋

---

#### queries.decision_view 전파 미결정 상세

**시그니처** `async def decision_view(version_id: int) -> DecisionDetail`

근거: [[SYNC-SEQ-001#SEQ-3]] · [[SYNC-UC-001#UC-H10]] 1 · [[SYNC-API-001#GET/api/decisions/{versionId}]]

**처리**
1. `dec = TrackingService.get_decision(version_id)` · if 없음 → `! not-found`
2. `version = DB: versions where id` (SpecService 경유) → `doc_id`, `version_no`, `prev_no = version_no-1`
3. `diff = SpecService.diff(doc_id, prev_no, version_no)` · if `prev_no == 0` → `hunks` 전부 add
4. `affected = dec.affected_pks` (create_pending 때 저장한 것) → `describe_items` + 담당자 `SpecService.last_author(대상 문서)` + `caused_by_items = 어느 변경 항목의 하위인지` (참조 테이블에서)
5. `→ DecisionDetail(version, doc_id, change_diff, affected, choice)`

**호출하는 것** `TrackingService.get_decision` · `SpecService.diff` `describe_items` `last_author`

---

#### queries.flag_view 플래그 상세

**시그니처** `async def flag_view(flag_id: int) -> FlagDetail`

근거: [[SYNC-SEQ-001#SEQ-6]] · [[SYNC-UC-001#UC-H11]] 2 · [[SYNC-API-001#GET/api/flags/{id}]]

**처리**
1. `f = TrackingService.get_flag(flag_id)` · if 없음 → `! not-found`
2. `names = SpecService.describe_items([f.target_item_pk, f.cause_item_pk])`
3. if `f.kind == needs_check and f.cause_item_pk` → `cause_doc = 원인 문서`, `cur_no = cause_doc.current_version_no` · `cause_diff = SpecService.diff(cause_doc_id, f.cause_version_no, cur_no)` · `cause_change_count = cur_no - f.cause_version_no` (UC-H11 3a 누적)
4. if `f.kind == broken_ref` → `cause_diff=None`, `cause_deleted_at = 원인 항목의 deleted_at`
4a. if `f.kind == upstream_impact` → `cause_diff=None` · if `f.cause_item_pk` → `cause_body = SpecService.get_item(하위 항목).body` · else → `cause_body = 하위 문서 제목 + "(문서 단위 지목)"`
5. `target = SpecService.get_item(target_doc_id, target_item_id)` → `target_body`
6. `target_changed_since_raise = DB: versions where document=target_doc and created_at > f.raised_at` 존재 여부 (SpecService 경유)
7. `→ FlagDetail(…)`

**호출하는 것** `TrackingService.get_flag` · `SpecService.describe_items` `diff` `get_item`

**테스트 관점** 원인이 v4→v6 바뀜 → `cause_change_count=2`, diff는 v4→v6 · 부여 후 대상 문서 저장됨 → `target_changed_since_raise=True`

---

## 3. 미결사항

- [ ] `graph_view` 범위 좁힘 시 "직접 이어진 것"을 몇 단계까지 (지금은 1)
