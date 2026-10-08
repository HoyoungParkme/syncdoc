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

**카드 L6 몫은 프로젝트 요약 하나다(2026-10-08)** — `init_project`·`POST /api/projects`가 돌려주고 `GET /api/projects`가 목록으로 낸다(사용자 결정 — 요약 전부, 문서가 있어도 맞게). **카드 L7이 MCP 읽기 도구의 넷을 더했다(2026-10-08)** — `list_documents`·`get_document`·`get_item`·`get_references`가 부른다. 나머지 조회(L8)는 그 카드가 더한다.

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

## 3. 미결사항

없음. 나머지 조회는 L8이 더한다 — [[SYNC-CODE-002]].
