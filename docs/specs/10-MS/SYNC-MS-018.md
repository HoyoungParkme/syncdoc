---
doc_id: SYNC-MS-018
type: MS
title: MINISPEC — queries — 읽기 조합 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-008, SYNC-MS-014, SYNC-MS-015, SYNC-MS-016, SYNC-API-001, SYNC-API-002]
---

# MINISPEC — queries (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/queries.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.7. 파이썬 판 [[SYNC-MS-008]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 여러 묶음의 서비스를 불러 응답 하나로 엮는다 — 쓰지 않는다.

**카드 L6 몫은 프로젝트 요약 하나다(2026-10-08)** — `init_project`·`POST /api/projects`가 돌려주고 `GET /api/projects`가 목록으로 낸다(사용자 결정 — 요약 전부, 문서가 있어도 맞게). **카드 L7이 MCP 읽기 도구의 넷을 더했다(2026-10-08)** — `list_documents`·`get_document`·`get_item`·`get_references`가 부른다. **카드 L8이 웹 읽기의 일곱을 더했다(2026-10-11)** — 프로젝트 상세·끊어진 참조 목록·관계도·체인·diff 영향·추적표·휴지통 목록(UI-4가 처음부터 부른다 — 휴지통 쓰기는 L9). 코드(L12)·묻기(L14)는 그 카드가 더한다.

**파이썬 `set`의 차례** — [[#queries.item_chain]]은 폐포를 파이썬 `set`에 모아 그 순회 차례로 단계 행을 채운다. 행 안 항목의 차례가 응답 바이트이므로 Rust는 CPython 3.12의 정수 `set`(열린 주소·선형 탐사 9·`perturb`·크기 키움·`discard`의 빈 표시)을 그대로 흉내 낸 `pycompat::pyset`으로 같은 차례를 낸다(에이전트 판단 2026-10-11 — 「바이트까지」 결정을 따름).

**작성자 이름** — 문서의 작성자 `AuthorRef`를 `ApiAuthor { kind, user, instructed_by, via }`로(파이썬 `_api_author`): `AccountService.users_by_ids([user_id, instructed_by_id])` 한 번 · `user`는 그 지도의 것(없으면 없음) · `instructed_by`는 id가 있을 때만.

**다른 점(전체)** 파이썬은 함수마다 세션을 연다 — Rust는 부르는 쪽의 연결을 받는다(첫 인자 `db`). 프로젝트를 읽는 함수는 서버 저장소 자리(`repos` — [[SYNC-MS-013]] 0장)도 받는다 — `ProjectService`가 그 둘로 선다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#queries.project_summary]] | 내 프로젝트들의 요약 — 11단계·STD 문서·수 |
| [[#queries.document_list]] | 문서 목록 + 문서별 건수 |
| [[#queries.document_view]] | 문서 + 미존재 참조 + 이웃 |
| [[#queries.item_view]] | 항목 블록 |
| [[#queries.item_references_view]] | 상위·하위 참조 + 표시 이름 |
| [[#queries.project_detail]] | 프로젝트 상세 — 요약 + 문서 목록 + 최근 변경 |
| [[#queries.project_items]] | 끊어진 참조·규약 오류·미완성 목록 |
| [[#queries.graph_view]] | 관계도 노드·간선 |
| [[#queries.item_chain]] | 항목의 11단계 체인 |
| [[#queries.diff_with_impact]] | diff + 하위 건수 |
| [[#queries.downstream_view]] | 이 문서를 참조하는 것 |
| [[#queries.trash_list]] | 휴지통 목록 |

---

## 2. 함수

#### queries.project_summary 내 프로젝트들의 요약

**시그니처**
```rust
pub async fn project_summary(db: &mut PgConnection, repos: &ServerRepos, user: &UserRow) -> Result<Vec<ProjectSummary>, Problem>
```

근거: [[SYNC-MS-008#queries.project_summary]] · [[SYNC-UC-001#UC-H14]] · [[SYNC-API-001#GET/api/projects]]

**처리** [[SYNC-MS-008#queries.project_summary]]와 같다
1. 프로젝트마다(`ProjectService.list_owned` — 코드 차례) `docs = SpecService.list_by_project(id)` · `per_doc = ReferenceService.count_missing_by_document(docs의 id)`
2. 단계 1~11(`RFQ`…`CODE`)마다 그 단계 문서 — `status`는 하나라도 `draft`면 `draft`, 다 `approved`면 `approved`, 없으면 없음 · `gate_warning`은 문서가 있고 앞 단계 가운데 문서가 있는데 `approved`가 아닌 것이 있나 · `broken_count`는 그 단계 문서들의 미존재 참조 합
3. `counts` — `broken_ref`(미존재 참조 합)·`convention_errors`(규약 오류 문서 수)·`incomplete`(경고 있는 문서 수) · `std_docs` — 타입 `STD` 문서 · `updated_at` — 문서들의 가장 늦은 것, 없으면 없음 · `remote_url` — 서버 저장이면 없음
4. `updated_at`이 있는 것을 먼저 그 내림차순, 없는 것은 뒤에 원래 차례로(파이썬 안정 정렬)

**출력** `ProjectSummary { code, name, storage, remote_url, stages[11], std_docs, counts, updated_at }`. 입구가 직렬화한다 — REST는 pydantic 꼴(`Z`), MCP는 파이썬 `_project_json` 꼴(`+00:00`, `std_docs`의 `last_author`는 늘 없음 — 파이썬 판에서 이 경로는 작성자 이름을 붙이지 않는다)

**호출하는 것** [[SYNC-MS-013#ProjectService.list_owned]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.count_missing_by_document]]

**테스트 관점** (시험 DB) 새 프로젝트 → 11칸 모두 없음·수 0·`updated_at` 없음 · 단계에 초안 하나 + 완료 하나 → 그 단계 `draft` · 앞 단계 초안 뒤 단계 문서 → `gate_warning` · 휴지통 문서는 안 센다 · 미존재 참조 → 단계 `broken_count`와 `counts.broken_ref` · `STD` 문서는 `std_docs`에만(단계 밖) · 두 프로젝트 → 최근 것 먼저, 문서 없는 것은 뒤 · 남의 프로젝트는 안 나온다

---

#### queries.document_list 문서 목록 + 문서별 건수

**시그니처**
```rust
pub async fn document_list(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow, stage: Option<i32>, status: Option<&str>) -> Result<Vec<DocumentSummary>, Problem>
```

근거: [[SYNC-MS-008#queries.document_list]] · [[SYNC-API-002#list_documents]]

**처리** [[SYNC-MS-008#queries.document_list]]와 같다 — `ProjectService.get_owned(code, user)` · `SpecService.list_by_project(id, stage, status, 없음)` · `ReferenceService.count_missing_by_document(ids)` 한 번 · 문서마다 `counts = {broken_ref: 수 또는 0}` · `author` = 위 「작성자 이름」(문서마다 — 파이썬과 같다)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.count_missing_by_document]] · [[SYNC-MS-016#AccountService.users_by_ids]]

**테스트 관점** (시험 DB) 남의 프로젝트 → `not-found` · 미존재 참조 없는 문서 → `broken_ref: 0` · 작성자 이름이 로그인·표시 이름으로 · 단계·상태 조건

---

#### queries.document_view 문서 + 미존재 참조 + 이웃

**시그니처**
```rust
pub async fn document_view(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, user: &UserRow) -> Result<Document, Problem>
```

근거: [[SYNC-MS-008#queries.document_view]] · [[SYNC-API-002#get_document]]

**처리** [[SYNC-MS-008#queries.document_view]]와 같은 차례
0. `project = ProjectService.get_owned(doc_id의 첫 "-" 앞(없으면 전부), user)` — 본문을 읽기 전에
1. `doc = SpecService.get_document(doc_id)`
4. `(prev, next) = SpecService.neighbors(doc_id)`
4a. `missing = ReferenceService.upstream_of_document(doc.id, true)` 가운데 미존재 · `doc.missing_refs` = 그 `raw_target`을 중복 없이 정렬(파이썬 `sorted` — 코드포인트 차례) · 항목마다 `missing_refs` = 그 항목에서 나간 것을 처음 본 차례로 중복 없이(출발 항목 없는 것은 빠진다)
5. `doc.author` = 위 「작성자 이름」
5a. `doc.project_name = project.name`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.neighbors]] · [[SYNC-MS-015#ReferenceService.upstream_of_document]] · [[SYNC-MS-016#AccountService.users_by_ids]]

**테스트 관점** (시험 DB) 남의 프로젝트 문서 → `not-found`(project) · 같은 미존재 대상 둘 → 하나 · 항목의 `missing_refs`는 그 항목 것만 · 첫 단계 문서 → 앞 이웃 없음

---

#### queries.item_view 항목 블록

**시그니처**
```rust
pub async fn item_view(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, item_id: &str, user: &UserRow) -> Result<ItemView, Problem>
```

근거: [[SYNC-MS-008#queries.item_view]] · [[SYNC-API-002#get_item]]

**처리** `ProjectService.get_owned(doc_id의 첫 "-" 앞, user)` · `→ SpecService.get_item(doc_id, item_id)` — 없음·삭제는 그대로

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_item]]

**테스트 관점** 남의 것 → `not-found`(project) · 없는 항목 → `not-found`와 `available_items`

---

#### queries.item_references_view 상위·하위 참조 + 표시 이름

**시그니처**
```rust
pub async fn item_references_view(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, item_id: &str, user: &UserRow) -> Result<ItemReferences, Problem>
```

근거: [[SYNC-MS-008#queries.item_references_view]] · [[SYNC-API-002#get_references]]

**처리** [[SYNC-MS-008#queries.item_references_view]]와 같은 차례
0. `ProjectService.get_owned(doc_id의 첫 "-" 앞, user)`
1. `pk = SpecService.resolve_item(doc_id, item_id)`
2. `up = ReferenceService.upstream(pk)` · `down = ReferenceService.downstream(pk)`
3. `names = SpecService.describe_items(상위의 to_item_pk + 하위의 from_item_pk)` 한 번 · 문서 쪽 — 상위에서 `to_document_id`만 있는 것, 하위에서 출발 항목이 없는 것의 `from_document_id` — 은 `SpecService.describe_documents`로 따로(`ItemRef { doc_id, item_id: 없음, display_name: 제목 }`)
4. 상위 — 미존재면 `raw_target`만인 미존재 `ItemRef` · 항목이면 `names`에서, 없으면 문서 쪽 지도에서 같은 수로(파이썬 `{**doc_names, **names}`) · 문서면 문서 쪽 지도에서 · 못 찾으면 미존재 `ItemRef` · 하위 — 출발 항목이 있으면 `names`, 없으면 출발 문서 · 못 찾으면 뺀다 · **참조마다 새 `ItemRef`**에 제 `raw_target`(#353)
5. `→ ItemReferences { doc_id, item_id, upstream, downstream }` — 받은 `doc_id`·`item_id` 그대로

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.resolve_item]] · [[SYNC-MS-015#ReferenceService.upstream]] · [[SYNC-MS-015#ReferenceService.downstream]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.describe_documents]]

**테스트 관점** (시험 DB) 미존재 → `upstream`에 `is_missing`·`raw_target` · 문서 전체 참조 → `item_id` 없음 · 항목 밖에서 건 참조 → `downstream`에 출발 문서 · 고립 항목 → 둘 다 빈 목록 · 같은 대상을 두 꼴로 → 각자의 `raw_target`, id 차례 · 삭제된 항목 → `item-deleted`

---

#### queries.project_detail 프로젝트 상세 — 요약 + 문서 목록 + 최근 변경

**시그니처**
```rust
pub async fn project_detail(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<ProjectDetail, Problem>
```

근거: [[SYNC-MS-008#queries.project_detail]] · [[SYNC-API-001#GET/api/projects/{code}]]

**처리** [[SYNC-MS-008#queries.project_detail]]와 같은 차례
1. `(project, repo) = ProjectService.get_owned(code, user)`
2. `recent = SpecService.recent_changes(project.id, 10)` · 작성자 이름을 `AccountService.users_by_ids`로 한 번(판마다 `ApiAuthor`)
3. `repo`의 `last_processed_commit`·`behind_by`·`fetched_at` — DB에 적힌 그대로(받아 오지 않는다)
4. `summary = project_summary(user)`에서 이 코드의 것 · `docs = document_list(code, user)`
5. `→ ProjectDetail { summary, docs, recent_changes, last_processed_commit, behind_by, fetched_at }`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.recent_changes]] · [[SYNC-MS-016#AccountService.users_by_ids]] · [[#queries.project_summary]] · [[#queries.document_list]]

**테스트 관점** (시험 DB) 남의 프로젝트 → `not-found` · 최근 변경은 새 것부터 열 개, 작성자 이름 · 동기화 칸은 DB 값 그대로

---

#### queries.project_items 끊어진 참조·규약 오류·미완성 목록

**시그니처**
```rust
pub async fn project_items(db: &mut PgConnection, repos: &ServerRepos, code: &str, kind: &str, user: &UserRow) -> Result<Vec<ProjectItem>, Problem>
```

근거: [[SYNC-MS-008#queries.project_items]] · [[SYNC-API-001#GET/api/projects/{code}/flags]]

**처리** [[SYNC-MS-008#queries.project_items]]와 같다
1. `get_owned(code, user)`
2. `broken_ref` → `ReferenceService.missing_in_project` · 출발 항목은 `SpecService.describe_items`, 항목 밖이면 출발 문서(`describe_documents` — 항목 없음·제목) · 둘 다 못 찾으면 뺀다 · `BrokenRefSummary { source, raw_target }` — `source`의 `raw_target`은 비었다(파이썬과 같다)
3. `convention_errors` → `SpecService.list_by_project(…, has_convention_error=true)` · `incomplete` → `list_by_project` 가운데 경고 있는 것
4. 그 밖 → `! Internal`(라우터가 패턴으로 막아 오지 않는다 — 파이썬 `ValueError`)

**출력** `ProjectItem` — `Broken(BrokenRefSummary)` 또는 `Document(DocumentSummary)`(작성자 이름 없음)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-015#ReferenceService.missing_in_project]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-014#SpecService.list_by_project]]

**테스트 관점** (시험 DB) 미존재마다 한 행·id 차례 · 항목 밖 참조 → 출발 문서 · 경고 있는 문서만 `incomplete`

---

#### queries.graph_view 관계도 노드·간선

**시그니처**
```rust
pub async fn graph_view(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow, scope: GraphScope) -> Result<Graph, Problem>
```

근거: [[SYNC-MS-008#queries.graph_view]] · [[SYNC-API-001#GET/api/projects/{code}/graph]]

**처리** [[SYNC-MS-008#queries.graph_view]]와 같은 차례
1. `(project, _) = get_owned(code, user)` · `briefs = SpecService.list_items_by_project(project.id)`
2. `approved`면 `SpecService.list_by_project(…, status "approved")`의 문서 것만
3. 항목 노드 `{pk: "DOC#ITEM"}` · 문서 노드 `{문서 pk: "DOC"}` · `edges = ReferenceService.references_among(항목 pk들, true)`
4. 간선마다 출발 = 출발 항목이 있으면 그 항목 노드, 없으면 출발 문서 노드 · 없으면 버린다 · 도착 = 항목이면 그 항목 노드(없으면 버린다 — 범위 밖), 문서면 그 문서 노드(없으면 버린다), 미존재면 없음 · `GraphEdge { from, to, raw_target, is_missing }`
5. 노드마다 `isolated` = 어느 간선에도 안 닿았나 · `→ Graph { nodes, edges, project_name }`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.list_items_by_project]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.references_among]]

**테스트 관점** (시험 DB) 노드 = 문서 + 항목 · 미존재는 `to` 없음 · `approved`면 완료 문서만, 밖으로 가는 간선은 없다 · 참조 없는 항목은 `isolated`

---

#### queries.item_chain 항목의 11단계 체인

**시그니처**
```rust
pub async fn item_chain(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, item_id: &str, user: &UserRow) -> Result<ItemChain, Problem>
```

근거: [[SYNC-MS-008#queries.item_chain]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/chain]]

**처리** [[SYNC-MS-008#queries.item_chain]]와 같은 차례
1. `get_owned(doc_id의 첫 "-" 앞)` · `pk = SpecService.resolve_item(doc_id, item_id)`
2. 폐포 둘 — 너비 우선, 위는 `ReferenceService.upstream`의 `to_item_pk`, 아래는 `downstream`의 `from_item_pk` · 본 것은 `pycompat::pyset::IntSet`(파이썬 `set`)에 넣고 끝에 시작점을 `discard`
3. `described = SpecService.describe_items(위 ∪ 아래 ∪ 자기)` · 문서마다 상태 `SpecService.get_document(문서).status`
4. `(자기, self)` → 위의 것들(`upstream`, 집합 차례) → 아래의 것들(`downstream`, 집합 차례)을 차례로 그 문서의 단계 행에 넣는다 — 단계는 문서 ID의 둘째 조각으로, 단계 밖(STD)은 뺀다
5. `→ ItemChain { item: 자기, upstream_count, downstream_count, rows: 11 }` — 빈 단계도 행이 있다

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.resolve_item]] · [[SYNC-MS-015#ReferenceService.upstream]] · [[SYNC-MS-015#ReferenceService.downstream]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.get_document]]

**테스트 관점** (시험 DB) 직접 참조 하나 → 위 1 · 건너 이어진 것도 · 사이클에서 멈춘다 · 행은 늘 11 · 한 단계에 여럿이면 파이썬 `set` 차례

---

#### queries.diff_with_impact diff + 하위 건수

**시그니처**
```rust
pub async fn diff_with_impact(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, from_no: i32, to_no: i32, user: &UserRow) -> Result<Diff, Problem>
```

근거: [[SYNC-MS-008#queries.diff_with_impact]] · [[SYNC-API-001#GET/api/docs/{docId}/diff]]

**처리** [[SYNC-MS-008#queries.diff_with_impact]]와 같다 — `get_owned(doc_id의 첫 "-" 앞)` · `d = SpecService.diff(doc_id, from_no, to_no, 3)` · hunk의 항목 ID들 → `SpecService.resolve_items` → `describe_items`로 `{item_id: pk}` · `ReferenceService.count_downstream` · hunk마다 그 수(새 항목·항목 밖은 0)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.diff]] · [[SYNC-MS-014#SpecService.resolve_items]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-015#ReferenceService.count_downstream]]

**테스트 관점** (시험 DB) 하위 둘인 항목을 고친 hunk → 2 · 새 항목 → 0 · 없는 판 → `not-found`

---

#### queries.downstream_view 이 문서를 참조하는 것

**시그니처**
```rust
pub async fn downstream_view(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, user: &UserRow) -> Result<DownstreamView, Problem>
```

근거: [[SYNC-MS-008#queries.downstream_view]] · [[SYNC-API-001#GET/api/docs/{docId}/downstream]]

**처리** [[SYNC-MS-008#queries.downstream_view]]와 같은 차례
1. `get_owned(doc_id의 첫 "-" 앞)` · `document = SpecService.get_document(doc_id)` · `pks = SpecService.item_pks(문서)`
2. `ReferenceService.references_among(항목 pk들, true)` 가운데 도착이 이 문서 항목이거나 이 문서인 것 — **항목이 없는 문서는 문서 참조도 안 나온다**(파이썬과 같다)
3. 출발 항목 이름 `describe_items` · 출발 문서 `describe_documents`
4. 간선마다 키 = 도착 항목 ID, 문서면 `"(문서)"` · 출발이 항목이면 그 `ItemRef`(**`raw_target`은 비었다** — 파이썬은 이름 지도의 것을 그대로 쓴다), 아니면 출발 문서 `ItemRef { doc_id, item_id: 없음, display_name: 제목, raw_target }` · 출발 문서가 이 문서면 뺀다
5. `by_item` = 키마다 처음 본 차례 · `by_document` = 출발 문서마다 `{doc_id, title, items: 키들 정렬}`을 `(단계, 없으면 99) → doc_id` 차례로 · 제목은 그 문서의 `describe_documents` 제목
6. `→ DownstreamView { by_item, by_document }`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.item_pks]] · [[SYNC-MS-015#ReferenceService.references_among]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.describe_documents]]

**테스트 관점** (시험 DB) 다른 문서의 항목이 건 참조 → 그 키에 · 문서 전체를 가리킨 것 → `"(문서)"` · 같은 문서 안 참조는 없다 · 문서 차례는 단계

---

#### queries.trash_list 휴지통 목록

**시그니처**
```rust
pub async fn trash_list(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<Vec<DocumentSummary>, Problem>
```

근거: [[SYNC-MS-008#queries.trash_list]] · [[SYNC-API-001#GET/api/projects/{code}/trash]]

**처리** [[SYNC-MS-008#queries.trash_list]]와 같다 — `get_owned(code, user)` · `SpecService.list_trashed` · 문서마다 작성자 이름 · 건수는 안 센다(`counts` 빈 것)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.list_trashed]] · [[SYNC-MS-016#AccountService.users_by_ids]]

**테스트 관점** (시험 DB) 휴지통 문서만 · 남의 프로젝트 → `not-found`

---

## 3. 미결사항

없음. 나머지 조회(코드·묻기)는 그 카드가 더한다 — [[SYNC-CODE-002]].
