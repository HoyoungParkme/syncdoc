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

**카드 L6 몫은 프로젝트 요약 하나다(2026-10-08)** — `init_project`·`POST /api/projects`가 돌려주고 `GET /api/projects`가 목록으로 낸다(사용자 결정 — 요약 전부, 문서가 있어도 맞게). **카드 L7이 MCP 읽기 도구의 넷을 더했다(2026-10-08)** — `list_documents`·`get_document`·`get_item`·`get_references`가 부른다. **카드 L8이 웹 읽기의 일곱을 더했다(2026-10-11)** — 프로젝트 상세·끊어진 참조 목록·관계도·체인·diff 영향·추적표·휴지통 목록(UI-4가 처음부터 부른다 — 휴지통 쓰기는 L9). **카드 L12가 코드의 넷을 더했다(2026-10-11)** — 코드 탭·관계도 코드 호출·코드 보기·코드 그래프의 코드. **카드 L13이 코드 그래프 노드를 더했다(2026-10-11)** — UI-17. **카드 L14가 묻기의 넷을 더했다(2026-10-11)** — 문서·코드 그래프에서 묻기(SSE)·모델이 부르는 읽기 도구·대화 하나.

**파이썬 `set`의 차례** — [[#queries.item_chain]]은 폐포를 파이썬 `set`에 모아 그 순회 차례로 단계 행을 채운다. 행 안 항목의 차례가 응답 바이트이므로 Rust는 CPython 3.12의 정수 `set`(열린 주소·선형 탐사 9·`perturb`·크기 키움·`discard`의 빈 표시)을 그대로 흉내 낸 `pycompat::pyset`으로 같은 차례를 낸다(에이전트 판단 2026-10-11 — 「바이트까지」 결정을 따름).

**작성자 이름** — 문서의 작성자 `AuthorRef`를 `ApiAuthor { kind, user, instructed_by, via }`로(파이썬 `_api_author`): `AccountService.users_by_ids([user_id, instructed_by_id])` 한 번 · `user`는 그 지도의 것(없으면 없음) · `instructed_by`는 id가 있을 때만. 문서 여럿이면 모든 id를 모아 한 번 묻고 같은 지도에서 꺼낸다 — 답은 같다(카드 L19).

**다른 점(전체)** 파이썬은 함수마다 세션을 연다 — Rust는 부르는 쪽의 연결을 받는다(첫 인자 `db`). 프로젝트를 읽는 함수는 서버 저장소 자리(`repos` — [[SYNC-MS-013]] 0장)도 받는다 — `ProjectService`가 그 둘로 선다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#queries.project_summary]] | 내 프로젝트들의 요약 — 11단계·STD 문서·수 |
| [[#queries.project_summary_of]] | 프로젝트 하나의 요약 |
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
| [[#queries.code_view]] | 코드 탭 — 항목의 코드 대조 |
| [[#queries.code_calls]] | 관계도 코드 호출 |
| [[#queries.code_source]] | 코드 보기 |
| [[#queries.code_text]] | 코드 그래프의 코드 — 파일·줄로 |
| [[#queries.code_nodes]] | 코드 그래프 노드 — 함수 전부·커뮤니티·대조 상태 |
| [[#queries.flow_view]] | 흐름 보기 — 그래프·흐름 키·층 표·대조 상태 |
| [[#queries.flow_of]] | 함수 하나의 흐름 — MCP get_flow |
| [[#queries.trace_spans]] | 기록 도구가 감쌀 함수 |
| [[#queries.ask_item]] | 문서를 읽다가 묻는다 — 모델이 관계도를 따라 읽는다 |
| [[#queries.ask_tool]] | 모델이 부른 읽기 도구 하나를 실행한다 |
| [[#queries.ask_code]] | 코드 그래프에서 묻는다 — 고른 함수가 시작 맥락 |
| [[#queries.conversation_view]] | 대화 하나 — 답 속 참조를 실제 항목과 맞춘 링크로 |

---

## 2. 함수

#### queries.project_summary 내 프로젝트들의 요약

**시그니처**
```rust
pub async fn project_summary(db: &mut PgConnection, repos: &ServerRepos, user: &UserRow) -> Result<Vec<ProjectSummary>, Problem>
```

근거: [[SYNC-MS-008#queries.project_summary]] · [[SYNC-UC-001#UC-H14]] · [[SYNC-API-001#GET/api/projects]]

**처리** [[SYNC-MS-008#queries.project_summary]]와 같다 — 프로젝트마다(`ProjectService.list_owned` — 코드 차례) [[#queries.project_summary_of]] · `updated_at`이 있는 것을 먼저 그 내림차순, 없는 것은 뒤에 원래 차례로(파이썬 안정 정렬)

**출력** `[ProjectSummary]` — 꼴은 [[#queries.project_summary_of]]

**호출하는 것** [[SYNC-MS-013#ProjectService.list_owned]] · [[#queries.project_summary_of]]

**테스트 관점** (시험 DB) 두 프로젝트 → 최근 것 먼저, 문서 없는 것은 뒤 · 남의 프로젝트는 안 나온다

---

#### queries.project_summary_of 프로젝트 하나의 요약

**시그니처**
```rust
pub async fn project_summary_of(db: &mut PgConnection, project: &ProjectRow, repo: &RepositoryRow) -> Result<ProjectSummary, Problem>
```

근거: [[SYNC-MS-008#queries.project_summary]] · 카드 L19 — 상세([[#queries.project_detail]])가 이 프로젝트만 요약한다

**처리**
1. `docs = SpecService.list_by_project(id)` · `per_doc = ReferenceService.count_missing_by_document(docs의 id)`
2. 단계 1~11(`RFQ`…`CODE`)마다 그 단계 문서 — `status`는 하나라도 `draft`면 `draft`, 다 `approved`면 `approved`, 없으면 없음 · `gate_warning`은 문서가 있고 앞 단계 가운데 문서가 있는데 `approved`가 아닌 것이 있나 · `broken_count`는 그 단계 문서들의 미존재 참조 합
3. `counts` — `broken_ref`(미존재 참조 합)·`convention_errors`(규약 오류 문서 수)·`incomplete`(경고 있는 문서 수) · `std_docs` — 타입 `STD` 문서 · `updated_at` — 문서들의 가장 늦은 것, 없으면 없음 · `remote_url` — 서버 저장이면 없음

**다른 점** 파이썬은 `project_summary` 안의 고리다 — 상세가 프로젝트 하나만 요약하려고 떼어 냈다(카드 L19)

**출력** `ProjectSummary { code, name, storage, remote_url, stages[11], std_docs, counts, updated_at }`. 입구가 직렬화한다 — REST는 pydantic 꼴(`Z`), MCP는 파이썬 `_project_json` 꼴(`+00:00`, `std_docs`의 `last_author`는 늘 없음 — 파이썬 판에서 이 경로는 작성자 이름을 붙이지 않는다)

**호출하는 것** [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.count_missing_by_document]]

**테스트 관점** (시험 DB) 새 프로젝트 → 11칸 모두 없음·수 0·`updated_at` 없음 · 단계에 초안 하나 + 완료 하나 → 그 단계 `draft` · 앞 단계 초안 뒤 단계 문서 → `gate_warning` · 휴지통 문서는 안 센다 · 미존재 참조 → 단계 `broken_count`와 `counts.broken_ref` · `STD` 문서는 `std_docs`에만(단계 밖)

---

#### queries.document_list 문서 목록 + 문서별 건수

**시그니처**
```rust
pub async fn document_list(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow, stage: Option<i32>, status: Option<&str>) -> Result<Vec<DocumentSummary>, Problem>
```

근거: [[SYNC-MS-008#queries.document_list]] · [[SYNC-API-002#list_documents]]

**처리** [[SYNC-MS-008#queries.document_list]]와 같다 — `ProjectService.get_owned(code, user)` · `SpecService.list_by_project(id, stage, status, 없음)` · `ReferenceService.count_missing_by_document(ids)` 한 번 · 문서마다 `counts = {broken_ref: 수 또는 0}` · `author` = 위 「작성자 이름」 — 모든 문서의 id를 모아 `users_by_ids` 한 번

**다른 점** 파이썬은 문서마다 묻는다(N+1) — 같은 답을 한 번에(윈도 조회 0.1초, 카드 L19)

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
4. `summary = project_summary_of(project, repo)` — 이 프로젝트만 · `docs = document_list(code, user)`
5. `→ ProjectDetail { summary, docs, recent_changes, last_processed_commit, behind_by, fetched_at }`

**다른 점** 파이썬은 내 프로젝트 전부를 요약하고 이 코드의 것을 고른다 — 이 프로젝트만 요약한다(같은 답, 카드 L19)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.recent_changes]] · [[SYNC-MS-016#AccountService.users_by_ids]] · [[#queries.project_summary_of]] · [[#queries.document_list]]

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
5. 노드마다 `isolated` = 어느 간선에도 안 닿았나 · `display_name` = 항목 제목(`ItemBrief.display_name`, 문서 노드는 없음 — UI-8 찾기, 카드 L21) · `→ Graph { nodes, edges, project_name }`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.list_items_by_project]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.references_among]]

**테스트 관점** (시험 DB) 노드 = 문서 + 항목 · 항목 노드에 제목, 문서 노드는 없음 · 미존재는 `to` 없음 · `approved`면 완료 문서만, 밖으로 가는 간선은 없다 · 참조 없는 항목은 `isolated`

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

#### queries.code_view 코드 탭 — 항목의 코드 대조

**시그니처**
```rust
pub async fn code_view(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, item_id: Option<&str>, user: &UserRow) -> Result<CodeView, Problem>
```

근거: [[SYNC-MS-008#queries.code_view]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code]] · [[SYNC-API-001#GET/api/docs/{docId}/code]] · [[SYNC-API-002#get_code_graph]]

**처리** [[SYNC-MS-008#queries.code_view]] 0~6과 같다 — 프로젝트 소유 → 문서 → 항목 → 그래프 행(없으면 `graph` 없이) → 프로젝트 MINISPEC 항목의 「호출하는 것」(`impl_of` — MS 문서 `upstream` 중 제목에 「클래스」가 든 DOM 문서가 꼭 하나일 때) → 대조 → MINISPEC 항목이면 그 함수의 부르는 것(코드만 → 명세만 → 같음)·불리는 곳, 못 찾으면 `item_function`·`item_neighbors`(대조 없음) · MINISPEC 밖 항목이면 하위 체인의 MINISPEC 함수 · MINISPEC 문서 단위면 그 문서 항목 전부(블록 차례). `graph` 머리는 `{commit_hash, source, built_at, error, function_count}`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.resolve_item]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.item_function]] · [[SYNC-MS-022#codegraph.item_neighbors]] · [[#queries.item_chain]]

**테스트 관점** [[SYNC-MS-008#queries.code_view]]의 것

---

#### queries.code_calls 관계도 코드 호출

**시그니처**
```rust
pub async fn code_calls(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<CodeCalls, Problem>
```

근거: [[SYNC-MS-008#queries.code_calls]] · [[SYNC-API-001#GET/api/projects/{code}/code-calls]]

**처리** [[SYNC-MS-008#queries.code_calls]]와 같다 — 대조의 항목마다 같음 → 코드만 → 명세만 차례로 선 `{from, to, status}`(대조는 항목 ID 순)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#markdown.parse_frontmatter]]

**테스트 관점** 그래프 없음 → `graph` 없이 빈 선 · 같음·코드만·명세만이 다 나온다

---

#### queries.code_source 코드 보기

**시그니처**
```rust
pub async fn code_source(db: &mut PgConnection, repos: &ServerRepos, doc_id: &str, item_id: &str, user: &UserRow) -> Result<CodeText, Problem>
```

근거: [[SYNC-MS-008#queries.code_source]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code/source]]

**처리** [[SYNC-MS-008#queries.code_source]]와 같다 — 소유·항목 → 그래프 없으면 `! NotFound(code_graph, 코드)` → `compare(graph, {항목: ∅})`의 함수, 없으면 `item_function` → 없으면 `! NotFound(function, 항목)` → 끝 줄(없으면 같은 파일 다음 함수 앞 줄, 그것도 없으면 시작 + 59) → `CodeGraphService.read`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.resolve_item]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.item_function]] · [[SYNC-MS-022#CodeGraphService.read]]

**테스트 관점** MINISPEC 항목 → 그 함수의 줄 · API 항목 → `item`의 함수 · 함수 없는 항목 → `not-found`(function) · 그래프 없음 → `not-found`(code_graph)

---

#### queries.code_text 코드 그래프의 코드 — 파일·줄로

**시그니처**
```rust
pub async fn code_text(db: &mut PgConnection, repos: &ServerRepos, code: &str, file: &str, line: i64, user: &UserRow) -> Result<CodeText, Problem>
```

근거: [[SYNC-MS-008#queries.code_text]] · [[SYNC-API-001#GET/api/projects/{code}/code/source]]

**처리** [[SYNC-MS-008#queries.code_text]]와 같다 — 그래프의 함수 중 파일·시작 줄이 같은 것(없으면 `! NotFound(function, "{file}:{line}")`) → `code_source`와 같은 끝 줄 → `CodeGraphService.read`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#CodeGraphService.read]]

**테스트 관점** 함수의 시작 줄 → 그 함수 · 없는 줄 → `not-found`(function) · 그래프 없음 → `not-found`(code_graph)

---

#### queries.code_nodes 코드 그래프 노드 — 함수 전부·커뮤니티·대조 상태

**시그니처**
```rust
pub async fn code_nodes(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<CodeNodes, Problem>
```

근거: [[SYNC-MS-008#queries.code_nodes]] · [[SYNC-API-001#GET/api/projects/{code}/code-graph]]

**처리** [[SYNC-MS-008#queries.code_nodes]] 0~5와 같다 — 소유 → 그래프 행(없으면 `graph` 없이 빈 것 셋) → 대조(`code_view`와 같은 재료)에서 함수 key → 대조 줄 · 층(프로젝트 클래스 명세 전부의 층 표를 문서 차례로 이어 [[SYNC-MS-022#codegraph.layers]]) → 함수마다 `CodeNode { key, name, qual, file, line, community, item: item 또는 ms, ms, status: 코드만 > 명세만 > 같음, layer }` · `communities`는 그래프 그대로(없으면 빈 것) · `calls`는 선마다 `[from, to]`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.layer_table]] · [[SYNC-MS-022#codegraph.layers]]

**테스트 관점** [[SYNC-MS-008#queries.code_nodes]]의 것

---

#### queries.flow_view 흐름 보기 — 그래프·흐름 키·층 표·대조 상태

**시그니처**
```rust
pub async fn flow_view(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<FlowView, Problem>
```

근거: [[SYNC-MS-008#queries.flow_view]] · [[SYNC-API-001#GET/api/projects/{code}/flow]] · [[SYNC-MS-026]] 0장(흐름 키는 `Graph` 밖의 값)

**처리** [[SYNC-MS-008#queries.flow_view]] 0~5와 같다 — 소유 → 그래프 행(없으면 빈 `FlowView`) · 저장된 그래프 값([[SYNC-MS-022#CodeGraphService.value]]) → 대조·층은 [[#queries.code_nodes]]와 같은 재료(층 표 줄은 클래스 명세 ID와 함께) → 함수마다 `FlowFunction`(그래프 값의 함수에서 — `end`·`route`·`steps`는 든 그대로, 없으면 null·null·`[]`) · `files`·`http`·`units`·`infra`·`communities`는 값 그대로(없으면 빈 것) · `calls`는 `[from, to]`

**다른 점** 흐름 키를 `Graph`로 읽지 않는다 — 행의 그래프 값을 따로 읽는다(JSONB 키 차례 그대로라 파이썬 판과 바이트로 같다)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#CodeGraphService.value]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.layer_table]] · [[SYNC-MS-022#codegraph.layers]]

**테스트 관점** [[SYNC-MS-008#queries.flow_view]]의 것 · 계약 시험(카드 L25) — 파이썬 판 응답과 바이트로 같다

---

#### queries.flow_of 함수 하나의 흐름 — MCP get_flow

**시그니처**
```rust
pub async fn flow_of(db: &mut PgConnection, repos: &ServerRepos, code: &str, function: &str, user: &UserRow) -> Result<FlowOf, Problem>
```

근거: [[SYNC-MS-008#queries.flow_of]] · [[SYNC-API-002]] `get_flow`

**처리** [[SYNC-MS-008#queries.flow_of]] 0~5와 같다 — 그래프 없음 → `not-found(code_graph)` · 함수는 열쇠, 아니면 `ms`·`item`이 같은 첫 함수(없으면 `not-found(function)`) · 그 함수와 `callees`(steps의 `to`, 처음 본 차례·하나씩·자기 자신 빼고)의 `FlowFunction` · 닿는 장비는 그 함수와 callees의 `steps.infra`(처음 본 차례)에 해당하는 장비 노드

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#CodeGraphService.value]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.layer_table]] · [[SYNC-MS-022#codegraph.layers]]

**테스트 관점** [[SYNC-MS-008#queries.flow_of]]의 것 · 계약 시험(카드 L26)

---

#### queries.trace_spans 기록 도구가 감쌀 함수

**시그니처**
```rust
pub async fn trace_spans(db: &mut PgConnection, repos: &ServerRepos, code: &str, user: &UserRow) -> Result<TraceSpans, Problem>
```

근거: [[SYNC-MS-008#queries.trace_spans]] · [[SYNC-API-001#GET/api/projects/{code}/trace-spans]]

**처리** [[SYNC-MS-008#queries.trace_spans]] 0~3 그대로 — 그래프 값([[SYNC-MS-022#CodeGraphService.value]])의 함수 중 `end`가 있는 것, 장비 중 `host`가 있는 것

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#CodeGraphService.value]]

**테스트 관점** [[SYNC-MS-008#queries.trace_spans]]의 것 · 계약 시험(카드 L28)

---

#### queries.ask_item 문서를 읽다가 묻는다

**시그니처**
```rust
pub async fn ask_item(pool: &PgPool, repos: &ServerRepos, llm: &Llm, doc_id: &str, item_id: Option<&str>, conversation_id: i64, question: &str, attachment_ids: &[i64], user: &UserRow) -> Result<AskStream, Problem>
```

근거: [[SYNC-MS-008#queries.ask_item]] · [[SYNC-API-001#POST/api/docs/{docId}/ask]]

**처리** [[SYNC-MS-008#queries.ask_item]] 0~7과 같다 — 키·주소 없음 → `! LlmNotConfigured` · 소유 → 대화(내 것·이 프로젝트) → 한 트랜잭션에서 앞 대화(10턴)·턴 만들기·이 턴의 이미지·시작 맥락(제목·상태·판·항목 `ID 이름`·`[지금 보는 항목]`·`[첨부]` 줄, 본문 없음 — 보는 항목이 없으면 턴을 `not-found`로 닫고 `! NotFound(item)`) → 커밋 → 루프(비공개 도우미 `ask_loop` — [[#queries.ask_code]]가 같이 쓴다): `start` → 모델 스트림의 조각마다 `delta` → 도구 호출이 없으면 답 → 있으면 곁들인 말 `note` · 호출마다 `reason`의 `note` → [[#queries.ask_tool]] → `read`(본 것) · 여덟 번이나 120초가 넘으면 마무리 문장을 넣고 `tool_choice="none"`으로 한 번(답이 비면 `! LlmUnavailable("상한 뒤에도 답이 없다")`) → 턴을 답으로 닫고 커밋 → 로그 한 줄 → 답 속 맨 ID를 실제 항목과 맞춘 링크로(`answer_links`) → `answer` · 시작 뒤의 실패는 턴을 오류(`reason` 또는 오류 종류 이름, 300자)로 닫고 내보낸다. 지시문·마무리 문장·도구 설명은 파이썬 판 글 그대로

**다른 점**
- 파이썬은 async 제너레이터 — 여기는 시작 전 검사까지 마치고 `AskStream`(이벤트 통로 `mpsc::UnboundedReceiver<Result<AskEvent, Problem>>` — 글자 조각을 기다림 없이 넣는다)을 돌려준다. 루프는 따로 띄운 작업이 돌며 `start`를 먼저 넣는다 — 시작 전 실패는 `Err`(상태 코드), 뒤의 실패는 통로의 `Err`(`error` 이벤트)
- `Problem::Internal`(파이썬의 `Problem` 밖 예외)은 통로를 닫아 스트림이 끊긴다 — 파이썬도 그 예외는 `error` 이벤트 없이 끊긴다
- 받는 쪽이 끊기면(통로 닫힘) 다음 이벤트를 넣을 때 멈추고 턴을 `CancelledError`로 닫는다 — 파이썬은 응답 작업이 취소될 때 같은 이름으로 닫는다
- `conversation_id`는 파이썬 정수(요청 본문)라 `i64` — int4 밖이면 대화 조회에서 `internal`(파이썬은 DB가 거절해 500)
- 「답 속 참조」 정규식의 앞뒤 보기(`(?<!…)`·`(?!…)`)는 Rust `regex`에 없어 글자를 직접 본다 — 같은 규칙

**호출하는 것** [[SYNC-MS-020#Llm.step_stream]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-021#ConversationService.get]] · [[SYNC-MS-021#ConversationService.history]] · [[SYNC-MS-021#ConversationService.add_turn]] · [[SYNC-MS-021#ConversationService.pending_images]] · [[SYNC-MS-021#ConversationService.finish_turn]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-014#SpecService.list_items_by_project]] · [[#queries.ask_tool]]

**테스트 관점** [[SYNC-MS-008#queries.ask_item]]의 것 — 키 없음은 네트워크 전 · 남의 대화·없는 항목은 스트림 전 · 도구 한 번 → `start`·`delta`·`note`·`read`·`answer` 차례 · 턴이 답으로 닫힌다 · 모델 실패 → `error` 이벤트, 턴은 오류 · 여덟 번째 뒤 마무리 호출 · 답 속 맨 ID가 링크, 없는 참조는 `missing_refs`

---

#### queries.ask_tool 모델이 부른 읽기 도구 하나

**시그니처**
```rust
pub async fn ask_tool(db: &mut PgConnection, repos: &ServerRepos, name: &str, args: &Map<String, Value>, code: &str, user: &UserRow, conversation_id: i32) -> Result<ToolResult, Problem>
```

근거: [[SYNC-MS-008#queries.ask_tool]]

**처리** [[SYNC-MS-008#queries.ask_tool]]과 같다 — 도구 아홉(`get_item`·`get_references`·`item_chain`·`list_documents`·`get_document`·`read_attachment`·`code_graph`·`read_code`·`find_code`)의 JSON(파이썬 `json.dumps(…, ensure_ascii=False)` 꼴)과 `target` · 모르는 도구·빠진 인자·다른 프로젝트 문서는 `{"error": …}` 글 · 남의 프로젝트는 `! NotFound` · 없음·삭제는 글(`hint`) · 인자 값은 파이썬 `str()`로 글자로(`None`·`True`·숫자 그대로)

**다른 점** 연결을 받는다(파이썬은 도구마다 세션) · `attachment_id`는 파이썬 `int(… or 0)`처럼 정수·정수 글자·실수(버림)·참거짓을 받고 그 밖은 `internal`(파이썬은 `ValueError`로 끊긴다)

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]] · [[#queries.item_view]] · [[#queries.item_references_view]] · [[#queries.item_chain]] · [[#queries.document_list]] · [[#queries.document_view]] · [[#queries.code_view]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#markdown.parse_frontmatter]](`find_code`의 층 — 클래스 명세 찾기) · [[SYNC-MS-021#ConversationService.attachment_text]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#CodeGraphService.read]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.item_function]] · [[SYNC-MS-022#codegraph.layer_table]] · [[SYNC-MS-022#codegraph.layers]]

**테스트 관점** [[SYNC-MS-008#queries.ask_tool]]의 것 — 아홉 도구의 키 · `read_code` 여러 꼴과 후보 · `find_code` 상한과 층 · 다른 프로젝트 문서 → 「없음」 · 남의 프로젝트 → `not-found` · DB에 쓰지 않는다

---

#### queries.ask_code 코드 그래프에서 묻는다

**시그니처**
```rust
pub async fn ask_code(pool: &PgPool, repos: &ServerRepos, llm: &Llm, code: &str, key: Option<&str>, conversation_id: i64, question: &str, attachment_ids: &[i64], user: &UserRow) -> Result<AskStream, Problem>
```

근거: [[SYNC-MS-008#queries.ask_code]] · [[SYNC-API-001#POST/api/projects/{code}/code/ask]]

**처리** [[SYNC-MS-008#queries.ask_code]] 0~4와 같다 — 시작 맥락만 다르고(문서 목록·그래프 머리·고른 함수 블록 — 대조 상태·`item`·층, 부르는 것·불리는 곳 20까지) 루프는 [[#queries.ask_item]]과 같은 `ask_loop` · `start`는 `{doc_id: null, item_id: null, key}`

**다른 점** [[#queries.ask_item]]과 같다

**호출하는 것** [[SYNC-MS-020#Llm.step_stream]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-021#ConversationService.get]] · [[SYNC-MS-021#ConversationService.history]] · [[SYNC-MS-021#ConversationService.add_turn]] · [[SYNC-MS-021#ConversationService.pending_images]] · [[SYNC-MS-021#ConversationService.finish_turn]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#SpecService.list_items_by_project]] · [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.layer_table]] · [[SYNC-MS-022#codegraph.layers]] · [[#queries.ask_tool]]

**테스트 관점** [[SYNC-MS-008#queries.ask_code]]의 것 — 시작 맥락의 문서 목록·그래프 머리·보는 함수·층 · 그래프 없음 → 그 줄로 답 · 없는 `key` → 스트림 전 `not-found function`

---

#### queries.conversation_view 대화 하나

**시그니처**
```rust
pub async fn conversation_view(db: &mut PgConnection, repos: &ServerRepos, conv_id: i32, user: &UserRow) -> Result<ConversationView, Problem>
```

근거: [[SYNC-MS-008#queries.conversation_view]] · [[SYNC-API-001#GET/api/conversations/{id}]]

**처리** [[SYNC-MS-008#queries.conversation_view]]와 같다 — 대화(내 것) → 소유 → 항목 색인 한 번 → 답 있는 턴마다 `answer_links`

**호출하는 것** [[SYNC-MS-021#ConversationService.get]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-014#SpecService.list_items_by_project]]

**테스트 관점** 답 속 맨 ID가 링크 · 없는 참조 · 실패 턴은 그대로 · 남의 대화 → `not-found`

---

## 3. 미결사항

없음. 나머지 조회(코드·묻기)는 그 카드가 더한다 — [[SYNC-CODE-002]].
