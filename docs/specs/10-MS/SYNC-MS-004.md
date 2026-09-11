---
doc_id: SYNC-MS-004
type: MS
title: MINISPEC — TrackingService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — TrackingService

## 0. 이 문서가 다루는 것

`core/tracking/service.py`의 함수 17개. 클래스 명세 [[SYNC-DOM-002]] 4.4의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`flags`·`propagation_decisions`만. 변경 영향 감지는 `SpecService.diff`·`ReferenceService.downstream`을 **직접** 부른다 — 서비스→서비스 예외 둘 중 하나(클래스 3.2).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#TrackingService.detect_impact]] | 변경 영향 감지 |
| [[#TrackingService.create_pending]] | 전파 미결정 생성 |
| [[#TrackingService.get_decision]] | 결정 행 조회 |
| [[#TrackingService.record_decision]] | 전파 결정 |
| [[#TrackingService.raise_flags]] | 확인 필요 플래그 |
| [[#TrackingService.raise_broken]] | 끊어진 참조 플래그 |
| [[#TrackingService.raise_upstream]] | 하위 불일치 플래그 (상위에) |
| [[#TrackingService.get_flag]] | 플래그 행 |
| [[#TrackingService.resolve]] | 확인함 |
| [[#TrackingService.flags_for_items]] | 항목별 플래그 종류 |
| [[#TrackingService.flags_for_assignee]] | 내 담당 플래그 |
| [[#TrackingService.flags_unassigned]] | 담당 미지정 |
| [[#TrackingService.flags_in_project]] | 프로젝트 플래그 |
| [[#TrackingService.count_flags]] | 프로젝트 건수 |
| [[#TrackingService.count_flags_by_document]] | 문서별 건수 |
| [[#TrackingService.pending_decisions_for]] | 미결정 버전 ID |
| [[#TrackingService.reassign_open_flags]] | 담당자 다시 계산 |
| [[#TrackingService.relink_versions]] | 재구축 뒤 버전 다시 잇기 |

---

## 2. 함수

#### TrackingService.detect_impact 변경 영향 감지

**시그니처** `detect_impact(document_id: int, prev_version_id: int | None, new_version_id: int, changed_items: list[str] | None) -> list[int]`

근거: [[SYNC-SEQ-001#SEQ-1]] 11단계 · [[SYNC-UC-001#UC-S3]] · 결정: MCP는 에이전트 지정, 나머지는 diff

**입력** `changed_items` — `mcp`면 에이전트가 준 항목 ID 목록(빈 배열 = 영향 없음 선언). `None`이면 diff로 판정

**처리**
1. if `prev_version_id is None` (신규 문서) → `→ []` (UC-S3 1a)
2. if `changed_items is not None` → `changed = changed_items` · else → `d = SpecService.diff(doc_id, prev_no, new_no)`, `changed = [h.item_id for h in d.hunks if h.item_id and 공백 제외 변경 있음]`
3. if `not changed` → `→ []`
4. `pks = SpecService.resolve_items(doc_id, changed)`
5. `affected = ⋃ ReferenceService.downstream(pk) for pk in pks` ∪ `ReferenceService.downstream_of_document(document_id)` → `from_item_pk` 집합. **같은 문서 안 항목도 포함** — 결정: R1을 고치며 같은 PRD의 R9를 봤으리라는 가정은 안 한다. `changed_items`에 R9도 있으면 R9는 원인이지 대상이 아니므로 자연히 빠진다
6. `→ sorted(affected)`

**출력** 영향받는 하위 항목 pk 목록

**호출하는 것** `SpecService.diff` `resolve_items` · `ReferenceService.downstream` `downstream_of_document`

**테스트 관점** `changed_items=[]` → 빈 목록(오탈자 선언) · `changed_items=None`, 공백만 바뀜 → 빈 목록 · R12 바뀌고 UC-A6이 R12 참조 → `[UC-A6 pk]` · R1 바뀌고 같은 문서 R9가 R1 참조 → `[R9 pk]` · R1·R9 둘 다 `changed_items` → R9는 대상 아님 · 문서 전체 참조 → 어느 항목이 바뀌어도 포함

---

#### TrackingService.create_pending 전파 미결정 생성

**시그니처** `create_pending(version_id: int, affected_pks: list[int], changed_pks: list[int]) -> int`

근거: [[SYNC-SEQ-001#SEQ-1]] 11 · [[SYNC-UC-001#UC-S3]] 3

**처리** `DB: propagation_decisions insert (version_id, choice=undecided, affected_pks JSON, changed_pks JSON)` → id. `affected`를 저장해 두는 이유 — 결정 시점에 참조가 바뀌어 있어도 **저장 시점의 영향 목록**으로 플래그를 붙인다

---

#### TrackingService.get_decision 결정 행 조회

**시그니처** `get_decision(version_id: int) -> PropagationDecision`

**처리** `DB: propagation_decisions where version_id` · if 없음 → `! not-found`. `affected_count = len(affected_pks)`

---

#### TrackingService.record_decision 전파 결정

**시그니처** `record_decision(version_id: int, choice: Propagation, reason: str | None, user: User) -> DecisionResult`

근거: [[SYNC-SEQ-001#SEQ-3]] · [[SYNC-UC-001#UC-H10]] 2·2a · [[SYNC-API-001#POST/api/decisions/{versionId}]]

**처리**
1. `dec = get_decision(version_id)`
2. if `dec.choice != undecided` → `! already-decided {choice, decided_at}`
3. if `choice == skip and not reason` → `! reason-required`
4. `DB: update choice, reason, decided_by=user, decided_at=now`
5. if `choice == propagate` → `n = raise_flags(version_id, dec.affected_pks)` · else `n = 0`
6. `→ DecisionResult(choice, flags_raised=n)`

**테스트 관점** 두 번 결정 → `already-decided` · `skip` 사유 없음 → `reason-required` · `propagate` → `flags_raised = len(affected)`

---

#### TrackingService.raise_flags 확인 필요 플래그

**시그니처** `raise_flags(version_id: int, target_item_pks: list[int]) -> int`

근거: [[SYNC-SEQ-001#SEQ-3]] · [[SYNC-UC-001#UC-S4]] · 결정: 담당자 = 대상 문서 최근 버전 작성자

**처리** — 호출자의 트랜잭션 안
1. `dec = get_decision(version_id)` → `changed_pks`
2. `target_pk`마다:
   - `causes` = `changed_pks` 중 이 target을 참조하는 것 전부 (`ReferenceService.upstream(target_pk)` ∩ `changed_pks`)
   - `assignee = (SpecService.last_author(target의 document_id) or None).user_id` (None 가능, UC-S4 3b)
   - if `causes` 비어 있음 (문서 단위 참조 `to_document_id`로 영향받은 것) → 플래그 하나, `cause_item_pk=None`. 원인은 "이 문서의 변경"
   - `cause_pk`마다 — **원인 하나에 플래그 하나** (결정: 첫 것만이면 손실, jsonb 묶음은 화면·스키마 변경이 큼):
     - if 같은 `(target, cause, cause_version)` 미해결 플래그 있음 → 건너뜀
     - `DB: flags insert (kind=needs_check, target_item_pk, cause_item_pk=cause_pk, cause_version_id=version_id, assignee_user_id, raised_at=now)`
3. `→` 생성 수

**호출하는 것** `ReferenceService.upstream` · `SpecService.last_author`

**테스트 관점** 담당자 null → `assignee` null, 내 할 일 `unassigned`에 · 같은 결정 두 번 → 중복 없음 · UC-A6이 R1·R9 둘 다 참조하고 둘 다 바뀜 → 플래그 2개, 각각 확인

---

#### TrackingService.raise_broken 끊어진 참조 플래그

**시그니처** `raise_broken(cause_item_pk: int) -> int`

근거: [[SYNC-SEQ-001#SEQ-1]] 9 · [[SYNC-UC-001#UC-H13]] 5

**처리** `refs = ReferenceService.downstream(cause_item_pk)` · 각 `from_item_pk`에 `DB: flags insert (kind=broken_ref, target=from_item_pk, cause=cause_item_pk, cause_version=None, assignee=SpecService.last_author(target 문서).user_id)` · `→` 수. 원인 항목은 `is_deleted=true`지만 행이 남아 있어 FK가 유지된다

---

#### TrackingService.raise_upstream 하위 불일치 플래그

**시그니처** `raise_upstream(target_item_pks: list[int], cause_document_id: int, cause_version_id: int, cause_item_pk: int | None) -> int`

근거: [[SYNC-UC-001#UC-S4]] · [[SYNC-UC-001#UC-H8]] 5 · [[SYNC-SEQ-001#SEQ-5]] · [[SYNC-SEQ-001#SEQ-1]] — 하위→상위 되먹임. `pipeline`(에이전트 지정)과 `SpecService.change_status`(승인 대조) 둘이 부른다

**입력** `target_item_pks` 상위 항목 pk들 · `cause_document_id` 어긋났다고 지목한 하위 문서 · `cause_version_id` 그 시점 버전 · `cause_item_pk` 지목한 하위 항목(승인 대조는 문서 단위라 None). 담당자 결정에 필요한 "대상 항목의 문서"는 `items.document_id`에서 읽는다(items는 spec 묶음이지만 pk→document_id 조회는 허용 — 참조 테이블과 같은 성격)

**처리** — 호출자의 트랜잭션 안
1. `target_pk`마다:
   - `assignee = SpecService.last_author(target의 document_id)` (None 가능)
   - if 같은 `(target, cause_document_id, kind=upstream_impact)` 미해결 플래그 있음 → 건너뜀. `cause_document_id`는 컬럼이 없으므로 `cause_version_id`로 `versions`를 조인해 얻는다
   - `DB: flags insert (kind=upstream_impact, target_item_pk, cause_item_pk, cause_version_id, assignee_user_id, raised_at=now)`
2. `→` 생성 수

**테스트 관점** 같은 하위 문서가 같은 상위를 두 번 지목 → 플래그 하나 · 담당자 = 상위 문서 최근 작성자 · 내 할 일 `upstream_impact` 묶음에 뜸

---

#### TrackingService.get_flag 플래그 행

**시그니처** `get_flag(flag_id: int) -> Flag`

**처리** `DB: flags where id` · if 없음 → `! not-found`

---

#### TrackingService.resolve 확인함

**시그니처** `resolve(flag_id: int, user: User, target_changed: bool) -> FlagSummary`

근거: [[SYNC-SEQ-001#SEQ-6]] · [[SYNC-UC-001#UC-H11]] 5~6, 3b

**입력** `target_changed` — `queries.flag_view`와 같은 판정(부여 후 대상 문서에 새 버전). 라우터가 `SpecService`로 계산해 넘긴다

**처리**
1. `f = get_flag(flag_id)` · if `f.resolved_at` → `! already-resolved`(409)
2. `DB: update resolved_by=user, resolved_at=now, resolved_with_edit=target_changed`
3. `→ FlagSummary`

**테스트 관점** 수정 없이 확인 → `resolved_with_edit=False` · 담당 미지정 플래그 확인 → `resolved_by=user`, `assignee` 그대로 null

---

#### TrackingService.flags_for_items 항목별 플래그 종류

**시그니처** `flags_for_items(item_pks: list[int]) -> dict[int, list[Flag]]`

**처리** `DB: flags where target_item_pk in pks and resolved_at is null` → pk별 `Flag` 행 묶음. 미해결만. **행을 그대로 준다** — `kind` 문자열 목록으로 접거나 `FlagSummary`(ItemRef·UserRef 채움)로 만드는 건 `queries`가 `describe_items`·`users_by_ids`로

---

#### TrackingService.flags_for_assignee 내 담당 플래그

**시그니처** `flags_for_assignee(user_id: int) -> tuple[list[Flag], list[Flag], list[Flag]]`

**처리** `DB: flags where assignee=user_id and resolved_at is null order by raised_at` → kind별 `(needs_check[], broken_ref[], upstream_impact[])`

---

#### TrackingService.flags_unassigned 담당 미지정

**시그니처** `flags_unassigned() -> list[Flag]`

**처리** `DB: flags where assignee is null and resolved_at is null order by raised_at`

---

#### TrackingService.flags_in_project 프로젝트 플래그

**시그니처** `flags_in_project(project_id: int, kind: FlagKind) -> list[Flag]`

**처리** `DB: flags join items join documents where project_id and kind and resolved_at is null`

---

#### TrackingService.count_flags 프로젝트 건수

**시그니처** `count_flags(project_id: int) -> dict[str, int]`

**처리** `DB: select kind, count(*) … where project_id and resolved_at is null group by kind` → `{needs_check: n, broken_ref: m}`

---

#### TrackingService.count_flags_by_document 문서별 건수

**시그니처** `count_flags_by_document(document_ids: list[int]) -> dict[int, dict[str, int]]`

**처리** `DB: select document_id, kind, count(*) … where document_id in ids and resolved_at is null group by 1,2` → 중첩 dict. **쿼리 한 번**

---

#### TrackingService.pending_decisions_for 미결정 버전 ID

**시그니처** `pending_decisions_for(user_id: int) -> list[int]`

**처리** `DB: propagation_decisions where choice=undecided` → `version_id[]`. 누가 저장했는지는 모른다(versions는 spec 묶음) — `queries.todo`가 `SpecService.versions_instructed_by`로 거른다

---

#### TrackingService.relink_versions 재구축 뒤 버전 다시 잇기

**시그니처** `relink_versions(project_id: int, by_key: dict[tuple[int, str], int]) -> RelinkResult`

근거: [[SYNC-MS-007#pipeline.rebuild]] 7a단계 · #38

**입력** `by_key` — 재구축이 새로 만든 버전의 `{(document_id, commit_hash): version_id}`. 호출자가 [[SYNC-MS-002#SpecService.version_keys]]로 뜬 **옛** 지도와 함께 넘긴다

**처리**
1. 프로젝트의 `propagation_decisions`마다: 옛 `version_id` → 옛 지도로 `(document_id, commit_hash)` → `by_key`로 새 id
   - 찾으면 `DB: update version_id`
   - 못 찾으면 `DB: delete` — `version_id`가 **NOT NULL**이라 빈 값으로 둘 수 없다. `dropped`에 센다
2. 프로젝트의 `flags` 중 `cause_version_id is not null`인 것마다: 같은 방식
   - 못 찾으면 `DB: delete`. **`cause_version_id`를 NULL로 비우지 않는다** — 비우면 UI-11의 원인 diff·"그 뒤로 N번 더 바뀜"·중복 플래그 방지 JOIN이 전부 죽어 **판단 재료 없는 빈 카드**가 남는다. 사람이 처리할 수 없는 플래그를 남기느니 버리고 보고하는 게 낫다
3. `→ RelinkResult(relinked, dropped=[{kind, count, reason}])`

**못 잇는 경우는 셋이고, 전부 「재구축이 그 버전을 다시 안 만든다」다.**
- 커밋이 `origin/HEAD`에서 도달 불가 — force-push·브랜치 삭제
- 문서 파일이 HEAD에 없다 — 삭제된 문서. `git.list`가 HEAD 기준이라 재구축 루프에 안 들어온다
- 커밋 메시지가 `status(`로 시작 — 재구축이 상태 변경으로 처리하고 버전을 안 만든다

**버린 것은 조용히 사라지지 않는다.** `RebuildResult.dropped`로 올라가 UI-14 결과(요소 5)에 뜬다. 재구축 확인 다이얼로그가 "플래그·전파 결정·댓글은 건드리지 않습니다"라고 약속하므로([[SYNC-UI-002#UI-14]]), 예외가 생겼으면 **몇 건을 왜 버렸는지 말해야** 그 약속이 거짓이 안 된다.

**`version_id`는 UNIQUE다.** 두 옛 버전이 한 새 버전으로 접히면 제약 위반이다. `(document_id, commit_hash)`는 구조적으로 유일하지만(재구축이 커밋마다 버전 하나를 만든다), 충돌하면 나중 것을 버리고 `dropped`에 센다

**호출하는 것** `pipeline.rebuild` 7a단계

**테스트 관점** 전파결정이 새 버전을 가리킨다 · `affected_pks`가 그대로 · `needs_check` 플래그의 `cause_version_id`가 새 버전으로 · 문서가 삭제된 커밋의 결정은 버려지고 `dropped`에 센다 · 해제된 플래그도 `cause_version_id`가 있으면 다시 잇는다(FK는 해제 여부를 안 가린다)

---

#### TrackingService.reassign_open_flags 담당자 다시 계산

**시그니처** `reassign_open_flags(project_id: int) -> int`

근거: [[SYNC-MS-007#pipeline.rebuild]] 7b단계 · 결정: 담당자 = 대상 문서 최근 버전 작성자

**처리**
1. `flags = DB: flags join items join documents where project_id and resolved_at is null` — **종류를 안 가린다**(`flags_in_project`는 `kind`가 필수라 쓸 수 없다)
2. 각 플래그에 `a = SpecService.last_author(대상 항목의 document_id).user_id`(None 가능)
3. if `a != flag.assignee_user_id` → `DB: update assignee_user_id=a` · 센다
4. `→` 바뀐 수

**왜 필요한가.** 재구축은 git을 진실로 삼아 `versions`를 다시 만든다. `assignee_user_id`는 거기서 파생된 값인데 플래그를 **만들 때 한 번** 계산되고 다시 계산되지 않는다. `clear_index`는 versions·references만 지우고 flags는 남긴다 — 원본을 다시 만들고 파생값을 그대로 두면 재구축이 절반만 끝난다. 커밋 이메일을 등록해 작성자가 바뀌어도 플래그는 옛 자리표시를 계속 가리킨다(#34).

**해제된 플래그는 안 건드린다.** 해제 시점의 담당자는 그때의 사실이라 이력이다.

**호출하는 것** `pipeline.rebuild` 7b단계 — **`relink_versions`(7a) 뒤에 온다.** 담당자는 대상 문서의 최근 버전에서 오므로 버전이 다 제자리를 찾은 뒤라야 한다

**테스트 관점** 대상 문서 작성자가 바뀌면 담당자도 바뀐다 · 해제된 플래그는 그대로 · 작성자가 없어지면 `null`(내 할 일 `담당 미지정`으로) · 안 바뀐 플래그는 세지 않는다

---

## 3. 미결사항

