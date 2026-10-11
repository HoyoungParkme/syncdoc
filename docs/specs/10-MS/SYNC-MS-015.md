---
doc_id: SYNC-MS-015
type: MS
title: MINISPEC — ReferenceService (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-003, SYNC-MS-017, SYNC-STD-004]
---

# MINISPEC — ReferenceService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/reference/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.4. 파이썬 판 [[SYNC-MS-003]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10).

서비스는 연결을 빌려 받는다 — `ReferenceService<'c> { pub db: &'c mut PgConnection }`. 트랜잭션은 부르는 쪽이 쥔다([[SYNC-STD-004#DEV-10]]).

**카드 L6 몫은 미존재 참조 세기 하나다(2026-10-08)** — 프로젝트 요약([[SYNC-MS-018#queries.project_summary]])이 쓴다. **카드 L7이 뽑기·끊기·잇기와 조회 셋을 더했다(2026-10-08)** — 저장 파이프라인([[SYNC-MS-017#pipeline.save_pipeline]])과 MCP 읽기 도구가 쓴다. **카드 L8이 웹 읽기의 셋을 더했다(2026-10-11)** — 관계도·추적표·diff 영향·끊어진 참조 목록. **카드 L9가 휴지통 문지기 하나를, 카드 L11이 재구축의 비우기 하나를 더했다(2026-10-11).**

돌려주는 간선은 `RefEdge { from_item_pk, to_item_pk, to_document_id, raw_target, is_missing, from_document_id }`([[SYNC-DOM-004]] 4.4) — 파이썬 `_edge`와 같은 꼴이다.

**표기** — `→` 반환·결과, `DB:` 테이블 접근, `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ReferenceService.extract]] | 본문에서 참조 추출·갱신 |
| [[#ReferenceService.upstream]] | 이 항목이 근거로 삼은 것 |
| [[#ReferenceService.downstream]] | 이 항목을 근거로 삼은 것 |
| [[#ReferenceService.upstream_of_document]] | 문서의 상위 참조 전부 |
| [[#ReferenceService.resolve_missing]] | 미존재 참조 해제 |
| [[#ReferenceService.mark_missing]] | 삭제된 항목을 가리키던 참조를 미존재로 |
| [[#ReferenceService.count_missing_by_document]] | 문서별 미존재 참조 수 |
| [[#ReferenceService.references_among]] | 노드 집합 사이 간선 |
| [[#ReferenceService.count_downstream]] | 하위 건수 |
| [[#ReferenceService.missing_in_project]] | 프로젝트의 미존재 참조 전부 |
| [[#ReferenceService.inbound_of_document]] | 남이 이 문서에 건 참조 |
| [[#ReferenceService.clear]] | 재구축 전에 프로젝트 참조를 비운다 |

---

## 2. 함수

#### ReferenceService.extract 본문에서 참조 추출·갱신

**시그니처**
```rust
pub async fn extract(&mut self, document_id: i32, version_id: i32, body: &str, item_pks: &HashMap<String, i32>, upstream_doc_ids: &[String]) -> Result<ExtractResult, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.extract]] · [[SYNC-SEQ-001#SEQ-1]] 10단계

**처리** [[SYNC-MS-003#ReferenceService.extract]]와 같은 차례 — 부르는 쪽의 트랜잭션 안
1. 항목 블록 경계는 `markdown::cut_blocks(body, item_pks에 든 것)` — 줄마다 그 블록 항목의 pk(블록 밖은 없음)
2. `markdown::masked_lines(body)`의 줄마다 `REF`에 걸린 것 → 원하는 것 `(출발 항목 pk, raw)`에 `resolve(raw)` — 처음 넣은 차례를 지킨다(파이썬 사전)
3. frontmatter `upstream`의 문서마다 `(없음, doc_id)` — 이미 있으면 자리는 그대로
4. `resolve(raw)` — `#` 앞이 비면 이 문서, 아니면 `DB: documents where doc_id`(휴지통도) · 못 찾음 → 미존재 · `#` 뒤가 비면 문서 참조 · 아니면 `DB: items where document_id and item_id and not is_deleted` · 못 찾음 → 미존재
5. `DB: references where from_document_id`(미존재 포함, id 차례)를 `(from_item_id, raw_target)`으로 — 원하는 것에 없으면 지운다(`removed`) · 원하는 것 차례대로 있으면 `extracted_version_id`만 바꾸고(**대상은 다시 풀지 않는다** — 잇기·끊기는 [[#ReferenceService.resolve_missing]]·[[#ReferenceService.mark_missing]]의 몫) 없으면 넣는다(`added`) · `missing`은 원하는 것 가운데 이번에 미존재로 푼 수
6. `→ ExtractResult { added, removed, missing }`

**다른 점** 행을 넣는 차례가 원하는 것의 차례다 — 파이썬 세션이 `add`한 차례로 넣는 것과 같아 id 차례가 같다

**호출하는 것** [[SYNC-MS-014#markdown.cut_blocks]] · [[SYNC-MS-014#markdown.masked_lines]]

**테스트 관점** (시험 DB) `[[X#Y]]` 하나 → `added=1` · 코드블록 안 → 무시 · 대상 없는 참조 → `missing=1`, `raw_target` 그대로 · 같은 본문 다시 → `added=0, removed=0`, `extracted_version_id`가 새 판 · 항목 밖 참조 → 출발 항목 없음 · `[[#A]]` → 이 문서 항목 · `[[X#]]` → 문서 참조 · upstream과 같은 본문 참조 → 행 하나 · 삭제된 항목 → 미존재

---

#### ReferenceService.upstream 이 항목이 근거로 삼은 것

**시그니처**
```rust
pub async fn upstream(&mut self, item_pk: i32) -> Result<Vec<RefEdge>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.upstream]]

**처리** `DB: references where from_item_id = item_pk order by id` — 미존재 포함

---

#### ReferenceService.downstream 이 항목을 근거로 삼은 것

**시그니처**
```rust
pub async fn downstream(&mut self, item_pk: i32) -> Result<Vec<RefEdge>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.downstream]]

**처리** `DB: references where to_item_id = item_pk order by id` — 항목 삭제 확인의 하위 목록도 이 차례(#353)

---

#### ReferenceService.upstream_of_document 문서의 상위 참조 전부

**시그니처**
```rust
pub async fn upstream_of_document(&mut self, document_id: i32, include_missing: bool) -> Result<Vec<RefEdge>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.upstream_of_document]]

**처리** `DB: references where from_document_id` · if `include_missing`가 아니다 → `and not is_missing` · `order by id`

**다른 점** 기본값이 없다 — 파이썬의 `False`를 부르는 쪽이 적는다

**테스트 관점** 미존재 하나 + 이어진 것 하나 → `include_missing`이면 둘, 아니면 하나

---

#### ReferenceService.resolve_missing 미존재 참조 해제

**시그니처**
```rust
pub async fn resolve_missing(&mut self, project_id: i32, target_doc_id: Option<&str>) -> Result<i64, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.resolve_missing]] · [[SYNC-UC-001#UC-S2]] 2a2

**처리** `DB: references where is_missing and from_document_id in (그 프로젝트 문서 — 휴지통도)` · if `target_doc_id` → `raw_target = target_doc_id or raw_target like '{target_doc_id}#' || '%'`(파이썬 SQLAlchemy `startswith`가 내는 SQL 그대로 — 글자를 거르지 않는다. 발급된 문서 ID에는 `%`·`_`가 없다) · `order by id` · 행마다 `raw_target`을 [[#ReferenceService.extract]] 4의 `resolve`로(출발 문서 기준) · 찾으면 `to_*`를 채우고 `is_missing=false` · `→` 해제된 수

**테스트 관점** 상위 문서를 나중에 만들면 그 문서를 가리키던 미존재가 풀린다 · 다른 문서를 가리키는 미존재는 그대로 · 삭제 뒤 되살린 항목 → 다시 이어진다

---

#### ReferenceService.mark_missing 삭제된 항목을 가리키던 참조를 미존재로

**시그니처**
```rust
pub async fn mark_missing(&mut self, item_pks: &[i32]) -> Result<i64, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.mark_missing]] · [[SYNC-UC-001#UC-A6]] 확장

**처리** if 빈 목록 → `0`(쿼리 없음) · `DB: update references set to_item_id=null, to_document_id=null, is_missing=true where to_item_id in pks` → 바뀐 행 수. `raw_target`은 그대로

**테스트 관점** 하위 둘이 가리키던 항목 → `2`, 두 행 다 미존재·`to_*` 없음·`raw_target` 그대로 · 아무도 안 가리키면 `0` · 빈 목록 → `0`

---

#### ReferenceService.count_missing_by_document 문서별 미존재 참조 수

**시그니처**
```rust
pub async fn count_missing_by_document(&mut self, document_ids: &[i32]) -> Result<HashMap<i32, i64>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.count_missing_by_document]]

**처리** if 빈 목록 → 빈 지도 · `DB: references where from_document_id in ids and is_missing group by from_document_id` → `{문서 id: 수}` — 쿼리 한 번. 미존재가 없는 문서는 지도에 없다

**테스트 관점** (시험 DB) 미존재 둘 + 이어진 것 하나 → 2 · 미존재가 없는 문서는 키가 없다 · 빈 목록 → 쿼리 없이 빈 지도

---

#### ReferenceService.references_among 노드 집합 사이 간선

**시그니처**
```rust
pub async fn references_among(&mut self, item_pks: &[i32], include_document_targets: bool) -> Result<Vec<RefEdge>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.references_among]] · [[SYNC-SEQ-001#SEQ-14]]

**처리** [[SYNC-MS-003#ReferenceService.references_among]]와 같다 — `docs = include_document_targets`면 `DB: items where id in pks`의 문서들, 아니면 없음 · 항목도 문서도 없으면 빈 목록(쿼리 없음) · `DB: references where from_item_id in pks or to_item_id in pks [or to_document_id in docs] order by id`. 미존재 포함

**다른 점** 항목 pk를 집합이 아니라 조각으로 받는다 — 겹쳐도 같은 답

**테스트 관점** 항목에서 나간 것·들어온 것·그 항목들의 문서를 가리킨 것 · 항목이 없으면 문서를 가리킨 것도 없다(파이썬과 같다)

---

#### ReferenceService.count_downstream 하위 건수

**시그니처**
```rust
pub async fn count_downstream(&mut self, item_pks: &[i32]) -> Result<HashMap<i32, i64>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.count_downstream]]

**처리** 빈 목록 → 빈 지도(쿼리 없음) · `DB: select to_item_id, count(*) from references where to_item_id in pks group by to_item_id` — 없는 키는 0으로 읽는다

**테스트 관점** 하위 둘 → 2 · 없으면 키 없음

---

#### ReferenceService.missing_in_project 프로젝트의 미존재 참조 전부

**시그니처**
```rust
pub async fn missing_in_project(&mut self, project_id: i32) -> Result<Vec<RefEdge>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.missing_in_project]] · [[SYNC-MS-018#queries.project_items]]

**처리** `DB: references where is_missing and from_document_id in (그 프로젝트 문서 — 휴지통도) order by id` → 간선

**테스트 관점** 미존재만, id 차례 · 다른 프로젝트 것은 없다


---

#### ReferenceService.inbound_of_document 남이 이 문서에 건 참조

**시그니처**
```rust
pub async fn inbound_of_document(&mut self, document_id: i32) -> Result<Vec<RefEdge>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.inbound_of_document]] · [[SYNC-UC-001#UC-A7]] 2

**처리** `DB: references where (to_document_id = id or to_item_id in (그 문서 항목 — 지운 것까지)) and from_document_id != id order by id` — 자기 참조는 뺀다. 미존재는 `to_*`가 비어 안 잡힌다

**테스트 관점** (시험 DB) 아무도 안 가리키면 빈 것 · 다른 문서가 항목을 걸면 하나 · 같은 문서 안 참조는 안 센다 · 미존재는 안 센다


---

#### ReferenceService.clear 재구축 전에 프로젝트 참조를 비운다

**시그니처**
```rust
pub async fn clear(&mut self, project_id: i32) -> Result<(), Problem>
```

근거: [[SYNC-MS-003#ReferenceService.clear]] · [[SYNC-MS-017#pipeline.rebuild]] 4

**처리** 그 프로젝트 문서에서 나간 참조를 모두 지운다 — 버전을 가리키는 유일한 외래 키(`extracted_version_id`)라 [[SYNC-MS-014#SpecService.clear_index]]보다 먼저(MS-007 rebuild 4a, #38)

**테스트 관점** 그 프로젝트 참조 0 · 다른 프로젝트 것은 그대로

---

## 3. 미결사항

없음.
