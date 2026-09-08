---
doc_id: SYNC-MS-003
type: MS
title: MINISPEC — ReferenceService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — ReferenceService

## 0. 이 문서가 다루는 것

`core/reference/service.py`의 함수 8개. 클래스 명세 [[SYNC-DOM-002]] 4.3의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

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
| [[#ReferenceService.upstream_of_document]] | 문서의 상위 참조 전부 (승인 대조) |
| [[#ReferenceService.downstream_of_document]] | 문서 전체를 참조한 것 |
| [[#ReferenceService.references_among]] | 노드 집합 사이 간선 |
| [[#ReferenceService.count_downstream]] | 하위 건수 |
| [[#ReferenceService.resolve_missing]] | 미존재 참조 해제 |
| [[#ReferenceService.clear]] | 재구축용 삭제 |

---

## 2. 함수

#### ReferenceService.extract 본문에서 참조 추출·갱신

**시그니처** `extract(document_id: int, version_id: int, body: str, item_pks: dict[str, int], upstream_doc_ids: list[str]) -> ExtractResult`

근거: [[SYNC-SEQ-001#SEQ-1]] 10단계 · [[SYNC-UC-001#UC-S2]] · [[SYNC-STD-001]] 1.4

**입력** `document_id`, 새 `version_id`, `body`, `item_pks` — 이 문서의 `{item_id: pk}` (SpecService.save가 만든 것), `upstream_doc_ids` — frontmatter `upstream`

**처리** — 호출자의 트랜잭션 안
1. 코드블록·인라인 코드를 공백으로 치환 (MS-001 `item_blocks`와 같은 방식)
2. `SpecService.item_blocks`가 준 블록 경계로, `[[ ]]`마다 **어느 항목 블록 안**에 있는지 → `from_item_pk`. 항목 밖(절 본문)의 참조는 문서 노드에서 나가는 것으로 `from_item_pk=None`, `from_document_id`
3. 참조 문자열 파싱: `[[DOC]]` → 문서 참조 · `[[DOC#ITEM]]` → 항목 참조 · `[[#ITEM]]` → 같은 문서 항목
4. 대상 찾기: `DB: documents where doc_id` → `to_document_id` · 항목이면 `DB: items where document_id and item_id and is_deleted=false` → `to_item_pk` · if 못 찾음 → `is_missing=True`, `to_*=None`, `raw_target` 보존
5. frontmatter `upstream`마다 문서 참조 행 (`from_item_pk=None`, `to_document_id`)
6. `DB: references where from in 이 문서` 전부 읽어 새 집합과 대조 — 없어진 건 delete, 새 건 insert, 있는 건 `extracted_version_id` 갱신. 행 자체를 지우고 다시 넣지 않는다(플래그 원인 추적에 pk가 쓰임)
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

**시그니처** `upstream_of_document(document_id: int) -> list[RefEdge]`

근거: [[SYNC-MS-008#queries.upstream_checklist]] — 승인 대조용

**처리** `DB: references where from_document_id = document_id and not is_missing` → `RefEdge[]`. 항목 참조(`from_item_pk` 있음)와 frontmatter upstream(`from_item_pk` null) 모두. 미존재는 대조 대상이 아니므로 제외

---

#### ReferenceService.downstream_of_document 문서 전체를 참조한 것

**시그니처** `downstream_of_document(document_id: int) -> list[RefEdge]`

**처리** `DB: references where to_document_id = document_id and to_item_pk is null` → `RefEdge[]`. **이 문서의 어느 항목이 바뀌어도 이것들이 영향받는다** — `detect_impact`가 합쳐 본다

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

**시그니처** `resolve_missing(project_id: int) -> int`

근거: [[SYNC-UC-001#UC-S2]] 2a2 · [[SYNC-SEQ-001#SEQ-21]] 7단계

**처리**
1. `rows = DB: references where is_missing and from이 project_id 안`
2. 행마다 `raw_target` 다시 파싱 → 대상 찾기(extract 4단계와 같음) · if 찾음 → `to_*` 채우고 `is_missing=False`
3. `→` 해제된 수

**테스트 관점** 상위 문서가 나중에 생성된 뒤 → 다음 저장(또는 재구축)에서 해제

---

#### ReferenceService.clear 재구축용 삭제

**시그니처** `clear(project_id: int) -> None`

**처리** `DB: delete references where from_item_pk in (project의 items) or from_document_id in (project의 documents)`. 트랜잭션 안에서만. 플래그는 `cause_item`·`target_item`으로 items를 물고 있어 references 삭제와 무관

---

## 3. 미결사항

- [ ] (없음)
