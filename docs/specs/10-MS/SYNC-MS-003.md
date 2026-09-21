---
doc_id: SYNC-MS-003
type: MS
title: MINISPEC — ReferenceService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — ReferenceService

## 0. 이 문서가 다루는 것

`core/reference/service.py`의 함수 13개. 클래스 명세 [[SYNC-DOM-002]] 4.3의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`references` 테이블만. **pk만 안다** — 표시 이름은 `queries`가 `SpecService.describe_items`로 채운다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ReferenceService.extract]] | 본문에서 참조 추출·갱신 |
| [[#ReferenceService.upstream]] | 이 항목이 근거로 삼은 것 |
| [[#ReferenceService.downstream]] | 이 항목을 근거로 삼은 것 |
| [[#ReferenceService.upstream_of_document]] | 문서의 상위 참조 전부 (미존재 세기) |
| [[#ReferenceService.downstream_of_document]] | 문서 전체를 참조한 것 |
| [[#ReferenceService.inbound_of_document]] | 남이 이 문서(항목 포함)에 건 참조 |
| [[#ReferenceService.references_among]] | 노드 집합 사이 간선 |
| [[#ReferenceService.count_downstream]] | 하위 건수 |
| [[#ReferenceService.resolve_missing]] | 미존재 참조 해제 |
| [[#ReferenceService.mark_missing]] | 삭제된 항목을 가리키던 참조를 미존재로 |
| [[#ReferenceService.count_missing_by_document]] | 문서별 미존재 참조 수 |
| [[#ReferenceService.missing_in_project]] | 프로젝트의 미존재 참조 전부 |
| [[#ReferenceService.clear]] | 재구축용 삭제 |

---

## 2. 함수

#### ReferenceService.extract 본문에서 참조 추출·갱신

**시그니처** `extract(document_id: int, version_id: int, body: str, item_pks: dict[str, int], upstream_doc_ids: list[str]) -> ExtractResult`

근거: [[SYNC-SEQ-001#SEQ-1]] 10단계 · [[SYNC-UC-001#UC-S2]] · [[SYNC-STD-001]] 1.4

**입력** `document_id`, 새 `version_id`, `body`, `item_pks` — 이 문서의 `{item_id: pk}` (SpecService.save가 만든 것), `upstream_doc_ids` — frontmatter `upstream`

**처리** — 호출자의 트랜잭션 안
1. `core/markdown.py`의 마스킹·헤딩·참조 함수로 본문을 자른다 — spec 모듈을 import하지 않는다(묶음 경계). 항목 블록 경계는 같은 순수 함수가 준다
2. `[[ ]]`마다 **어느 항목 블록 안**에 있는지 → `item_pks[item_id]`로 `from_item_pk`. 항목 밖(절 본문)의 참조는 문서 노드에서 나가는 것으로 `from_item_pk=None`, `from_document_id`
3. 참조 문자열 파싱: `[[DOC]]` → 문서 참조 · `[[DOC#ITEM]]` → 항목 참조 · `[[#ITEM]]` → 같은 문서 항목
4. 대상 찾기: `DB: documents where doc_id` → `to_document_id` · 항목이면 `DB: items where document_id and item_id and is_deleted=false` → `to_item_pk` · if 못 찾음 → `is_missing=True`, `to_*=None`, `raw_target` 보존
5. frontmatter `upstream`마다 문서 참조 행 (`from_item_pk=None`, `to_document_id`)
6. `DB: references where from in 이 문서` 전부 읽어 새 집합과 대조 — 없어진 건 delete, 새 건 insert, 있는 건 `extracted_version_id` 갱신. 행 자체를 지우고 다시 넣지 않는다 — 같은 참조는 같은 행으로 남긴다. 지우고 다시 넣으면 매 저장이 전부 삭제·추가로 보인다
7. `→ ExtractResult(added, removed, missing)`

**출력** `ExtractResult`

**예외** 없음. 미존재 참조는 예외가 아니다(UC-S2 2a)

**테스트 관점** `[[X#Y]]` 하나 추가 → `added=1` · 코드블록 안 `[[X#Y]]` → 무시 · 대상 없는 참조 → `missing=1`, `raw_target` 저장 · 같은 본문 재저장 → `added=0, removed=0` · 항목 밖 참조 → `from_item_pk=None`

---

#### ReferenceService.upstream 이 항목이 근거로 삼은 것

**시그니처** `upstream(item_pk: int) -> list[RefEdge]`

**처리** `DB: references where from_item_pk = item_pk` → `RefEdge[]`. 미존재 포함

---

#### ReferenceService.downstream 이 항목을 근거로 삼은 것

**시그니처** `downstream(item_pk: int) -> list[RefEdge]`

**처리** `DB: references where to_item_pk = item_pk` → `RefEdge[]`

---

#### ReferenceService.upstream_of_document 문서의 상위 참조 전부

**시그니처** `upstream_of_document(document_id: int, include_missing: bool = False) -> list[RefEdge]`

근거: [[SYNC-MS-008#queries.document_view]] 4a단계 · [[SYNC-MS-007#pipeline.change_status]] 2단계 — 한 문서의 미존재 참조를 세는 자리 둘이 같은 함수를 본다

**처리** `DB: references where from_document_id = document_id` · if `not include_missing` → `and not is_missing` → `RefEdge[]`. 항목 참조와 frontmatter upstream 모두. `document_view.missing_refs`와 완료 전환 검사는 `include_missing=True`로 부른다

---

#### ReferenceService.downstream_of_document 문서 전체를 참조한 것

**시그니처** `downstream_of_document(document_id: int) -> list[RefEdge]`

**처리** `DB: references where to_document_id = document_id and to_item_pk is null` → `RefEdge[]`. **이 문서의 어느 항목이 바뀌어도 이것들이 영향받는다** — `item_references_view`가 항목 하위와 합쳐 보여준다

---

#### ReferenceService.inbound_of_document 남이 이 문서에 건 참조

**시그니처** `inbound_of_document(document_id: int) -> list[RefEdge]`

근거: [[SYNC-UC-001#UC-A7]] 2 · [[SYNC-PRD-001#N3]]

**처리** `DB: references where (to_document_id = id or to_item_id in (items of id)) and from_document_id != id` → `RefEdge[]`. **자기 참조는 뺀다** — 문서 안에서 자기 항목을 가리킨 것은 이력이 아니다. `downstream_of_document`(문서 전체 참조만)와 `downstream`(항목 하나)을 합친 것에 자기 참조를 뺀 것 — 삭제 문지기용이라 따로 둔다

**테스트 관점** 아무도 안 가리키면 `[]` · 다른 문서가 `[[X#A]]`를 걸면 하나 · 같은 문서 안 `[[#A]]`는 안 센다 · 미존재 참조(`is_missing`)는 `to_*`가 비어 안 센다

---

#### ReferenceService.references_among 노드 집합 사이 간선

**시그니처** `references_among(item_pks: set[int], include_document_targets: bool = True) -> list[RefEdge]`

근거: [[SYNC-SEQ-001#SEQ-14]]

**처리** `DB: references where from_item_pk in pks or to_item_pk in pks` · if `include_document_targets` → `or to_document_id in (pks의 문서들)`. 미존재 참조 포함(`to=None`으로 그린다)

---

#### ReferenceService.count_downstream 하위 건수

**시그니처** `count_downstream(item_pks: list[int]) -> dict[int, int]`

**처리** `DB: select to_item_pk, count(*) from references where to_item_pk in pks group by to_item_pk` → dict. 없으면 키 없음(0으로 읽는다)

---

#### ReferenceService.resolve_missing 미존재 참조 해제

**시그니처** `resolve_missing(project_id: int, target_doc_id: str | None = None) -> int`

근거: [[SYNC-UC-001#UC-S2]] 2a2 · [[SYNC-SEQ-001#SEQ-21]] 7단계

**처리**
1. `rows = DB: references where is_missing and from이 project_id 안` · if `target_doc_id` → `raw_target`이 그 문서를 가리키는 것만 (저장 직후 좁혀 부를 때)
2. 행마다 `raw_target` 다시 파싱 → 대상 찾기(extract 4단계와 같음) · if 찾음 → `to_*` 채우고 `is_missing=False`
3. `→` 해제된 수

**테스트 관점** 상위 문서가 나중에 생성된 뒤 → 그 문서를 가리키던 미존재 참조가 즉시 해제 · 재구축에서도 해제 · **휴지통에서 되살린 항목**을 가리키던 참조(`mark_missing`이 비운 것)가 되살리기 직후 해제

---

#### ReferenceService.mark_missing 삭제된 항목을 가리키던 참조를 미존재로

**시그니처** `mark_missing(item_pks: list[int]) -> int`

근거: [[SYNC-UC-001#UC-A6]] 확장 · [[SYNC-UC-001#UC-A7]] 5 · [[SYNC-UC-001#UC-G1]] 3d · [[SYNC-PRD-001#R4]] — 상위 항목이 사라지면 그것을 가리키던 하위 참조가 「끊어진 참조」가 된다. 플래그를 세우는 대신 **참조 행 자신이** 끊어졌다고 말한다

**입력** 방금 `is_deleted`가 된 항목 pk 목록. 호출자가 확인을 끝낸 것(항목 삭제 확인 · 휴지통 · 파일 삭제 · 재구축 재생)

**처리** — 호출자의 트랜잭션 안
1. if `not item_pks` → `→ 0`
2. `DB: update references set to_item_id=null, to_document_id=null, is_missing=true where to_item_id in pks` — **둘 다 비운다.** `ck_references_target`이 `is_missing`이면 `to_*`가 전부 NULL이기를 요구한다([[SYNC-DOM-003#references]]). `raw_target`은 그대로라 상대가 돌아오면 [[#ReferenceService.resolve_missing]]이 다시 잇는다
3. `→` 바뀐 행 수

**출력** 끊어진 참조 수. `TrashResult.broken_refs`·`SaveResult.warnings`가 사람에게 알리는 값

**예외** 없음

**호출하는 것** 없음

**호출되는 것** [[SYNC-MS-007#pipeline.save_pipeline]] 9단계 · [[SYNC-MS-007#pipeline.trash_document]] 5단계 · [[SYNC-MS-007#pipeline.process_commit]] 4단계(파일 삭제). 재구축은 부르지 않는다 — 참조를 다 지우고 마지막 본문으로 다시 뽑으면 삭제된 항목은 [[#ReferenceService.extract]] 4단계에서 저절로 미존재가 된다

**테스트 관점** 하위 둘이 가리키던 항목을 지움 → `2`, 두 행 다 `is_missing=True`이고 `to_item_id`·`to_document_id`가 NULL · `raw_target`은 그대로 · 아무도 안 가리키던 항목 → `0` · 빈 목록 → `0`, 쿼리 없음 · 그 뒤 `resolve_missing` → 항목이 돌아오면 두 행이 다시 이어진다 · **`document_view.missing_refs`에 그 대상이 뜬다**(별도 표가 없다는 증거)

---

#### ReferenceService.count_missing_by_document 문서별 미존재 참조 수

**시그니처** `count_missing_by_document(document_ids: list[int]) -> dict[int, int]`

근거: [[SYNC-MS-008#queries.project_summary]] · [[SYNC-MS-008#queries.document_list]] — 「끊어진 참조」 수치. 플래그가 있던 자리를 참조 행 자신이 채운다

**처리** `DB: select from_document_id, count(*) from references where from_document_id in ids and is_missing group by from_document_id` → dict. 없으면 키 없음(0으로 읽는다). **쿼리 한 번**

**테스트 관점** 미존재 둘인 문서 → `2` · 없는 문서 → 키 없음 · 빈 목록 → 빈 dict

---

#### ReferenceService.missing_in_project 프로젝트의 미존재 참조 전부

**시그니처** `missing_in_project(project_id: int) -> list[RefEdge]`

근거: [[SYNC-MS-008#queries.project_items]] `broken_ref` — UI-4 목록 다이얼로그(6)

**처리** `DB: references where is_missing and from_document_id in (project의 documents)` → `RefEdge[]`(`from_item_pk`·`from_document_id`·`raw_target`). [[#ReferenceService.resolve_missing]] 1단계와 같은 조건 — 그쪽은 고치고 이쪽은 보여준다

**테스트 관점** 문서 둘에 미존재 하나씩 → 둘 · 상대가 들어와 `resolve_missing`이 풀면 빈 목록

---

#### ReferenceService.clear 재구축용 삭제

**시그니처** `clear(project_id: int) -> None`

**처리** `DB: delete references where from_item_pk in (project의 items) or from_document_id in (project의 documents)`. 트랜잭션 안에서만

---

## 3. 미결사항

없음.
