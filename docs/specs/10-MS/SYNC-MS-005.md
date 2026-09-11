---
doc_id: SYNC-MS-005
type: MS
title: MINISPEC — CommentService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — CommentService

## 0. 이 문서가 다루는 것

`core/collab/service.py`의 함수 10개. 클래스 명세 [[SYNC-DOM-002]] 4.5의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`comments`만. 본문은 인자로 받는다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#CommentService.list]] | 스레드 목록 |
| [[#CommentService.add]] | 댓글 작성 |
| [[#CommentService.resolve]] | 해결됨 토글 |
| [[#CommentService.relocate]] | 새 버전에서 줄 찾기 |
| [[#CommentService.unresolved_count]] | 문서 미해결 수 |
| [[#CommentService.count_unresolved]] | 프로젝트 미해결 수 |
| [[#CommentService.count_unresolved_by_document]] | 문서별 |
| [[#CommentService.unresolved_in]] | 문서들의 미해결 목록 |
| [[#CommentService.all_in_project]] | 백업용 댓글 전량 |
| [[#CommentService.restore]] | 백업에서 댓글 하나 되붙이기 |

---

## 2. 함수

#### CommentService.list 스레드 목록

**시그니처** `list(document_id: int) -> list[Comment]`

**처리** `DB: comments where document_id order by created_at` → `parent_comment_id`로 트리 조립. 최상위(`parent=None`)만 반환, 답글은 `replies[]` 안에. 해결된 것도 포함(`is_resolved` 표시)

---

#### CommentService.add 댓글 작성

**시그니처** `add(document_id: int, line_no: int, line_text: str, body: str, user: User, parent_id: int | None) -> Comment`

근거: [[SYNC-SEQ-001#SEQ-16]] · [[SYNC-UC-001#UC-H9]] 1~2

**입력** `line_text` — 라우터가 `SpecService.get_document().current_body`에서 `line_no`번째 줄을 뽑아 넘긴다. 범위 밖이면 라우터가 422

**처리**
1. if `parent_id` → `DB: comments where id=parent_id and document_id` · if 없음 → `! not-found`
2. `line_hash = sha256(line_text.strip()).hexdigest()`
3. `DB: comments insert (document_id, parent_comment_id, line_no, line_hash, body, author_user_id=user, is_resolved=False, created_at=now)`
4. `→ Comment`

**테스트 관점** 같은 줄에 둘 → 스레드 둘 · 답글 → 부모의 `replies`에 · 다른 문서의 parent → not-found

---

#### CommentService.resolve 해결됨 토글

**시그니처** `resolve(comment_id: int, resolved: bool) -> Comment`

**처리** `DB: comments where id` · if 없음 → `! not-found` · `update is_resolved=resolved` · 답글에도 되지만 "미해결 수"는 최상위만 센다

---

#### CommentService.relocate 새 버전에서 줄 찾기

**시그니처** `relocate(document_id: int, old_body: str, new_body: str, old_version_no: int) -> int`

근거: [[SYNC-SEQ-001#SEQ-1]] 12단계 · [[SYNC-UC-001#UC-H9]] 2a·2b · [[SYNC-DOM-003#comments]] `line_hash`·`original_location`

**처리** — 호출자의 트랜잭션 안
1. `rows = DB: comments where document_id and is_resolved=false` (해결된 건 옮기지 않는다)
2. `new_hashes = {sha256(line.strip()): [줄번호…] for 줄 in new_body}` — 같은 내용 줄이 여럿이면 목록
3. 댓글마다:
   - `cands = new_hashes.get(line_hash, [])`
   - if `len(cands) == 1` → `line_no = cands[0]`
   - if `len(cands) > 1` → 옛 `line_no`에 가장 가까운 것
   - if `cands` 비어 있음 (줄이 사라짐, 2b) → `line_no` 유지, `original_location = f"v{old_version_no}:{line_no}"` (이미 있으면 그대로)
   - `DB: update line_no, original_location`
4. `→` 옮긴 수

**테스트 관점** 위에 줄 3개 삽입 → 댓글 `line_no` +3 · 댓글 단 줄 삭제 → `original_location` 채워짐 · 같은 줄 내용 둘 → 가까운 쪽

---

#### CommentService.unresolved_count 문서 미해결 수

**시그니처** `unresolved_count(document_id: int) -> int`

**처리** `DB: count(*) comments where document_id and parent_comment_id is null and is_resolved=false`. UI-5 요소 5·`change_status` 확인용

---

#### CommentService.count_unresolved 프로젝트 미해결 수

**시그니처** `count_unresolved(project_id: int) -> int`

**처리** `DB: count(*) comments join documents where project_id and parent is null and not is_resolved`

---

#### CommentService.count_unresolved_by_document 문서별

**시그니처** `count_unresolved_by_document(document_ids: list[int]) -> dict[int, int]`

**처리** `DB: select document_id, count(*) … where document_id in ids and parent is null and not is_resolved group by 1`. **쿼리 한 번**

---

#### CommentService.unresolved_in 문서들의 미해결 목록

**시그니처** `unresolved_in(document_ids: list[int]) -> list[CommentSummary]`

**처리** `DB: comments join documents join users where document_id in ids and not is_resolved order by created_at` → `CommentSummary(id, doc_id, line_no, excerpt=body[:80], author, created_at)`. 답글도 포함

---

#### CommentService.all_in_project 백업용 댓글 전량

**시그니처** `all_in_project(project_id: int) -> list[Comment]`

근거: [[SYNC-INFRA-001]] 6.1 · [[SYNC-MS-007#pipeline.export_tracking]] 3단계

**처리** `DB: comments join documents where project_id order by document_id, created_at, id` → 전부

**해결된 것도 준다.** [[#CommentService.unresolved_in]]은 미해결만이라 백업에 못 쓴다. 정렬을 `(문서, 작성시각)`으로 고정하는 이유는 **부모가 자식보다 먼저 오게** 하기 위해서다 — 답글의 작성 시각은 부모가 이미 있어야 생기므로 항상 부모보다 크다

---

#### CommentService.restore 백업에서 댓글 하나 되붙이기

**시그니처** `restore(document_id: int, parent_comment_id: int | None, line_no: int, line_hash: str, author_user_id: int, is_resolved: bool, created_at: datetime, original_location: str | None) -> tuple[Comment, bool]`

근거: [[SYNC-INFRA-001]] 6.1 · [[SYNC-MS-007#pipeline.import_tracking]] 8단계

**처리** `(document_id, author_user_id, created_at)`으로 찾아 있으면 `→ (그 행, False)` · 없으면 `DB: comments insert(본문 = 복원 자리표시)` · `→ (새 행, True)`

**한 행씩 부른다.** 부모-자식 사슬 때문이다 — 부르는 쪽이 새 id를 받아야 다음 행의 `parent_comment_id`를 채울 수 있다. **이미 있던 행도 돌려주는** 이유가 같다: 반쯤 복원된 상태에서 다시 눌러도 답글이 제 부모에 붙어야 한다

**[[#CommentService.add]]를 못 쓰는 이유.** `add`는 본문이 필수이고 `created_at`·`line_hash`·`is_resolved`를 지금 값으로 만든다. 복원은 그 셋을 **백업에 적힌 대로** 되살려야 한다

**본문은 자리표시다.** 백업에 본문이 없다(저장소가 public — 인프라 6.1). `body`가 NOT NULL이라 무언가 들어가야 하는데, 빈 문자열은 화면에 빈 칸으로 떠 사람이 버그로 읽는다. **"백업에서 복원 — 본문은 백업에 없습니다"**를 넣어 왜 비었는지가 화면에서 읽히게 한다

**테스트 관점** 빈 표에 넣으면 새 행 · 같은 열쇠로 두 번 부르면 둘째는 `(같은 행, False)` · `created_at`·`is_resolved`가 인자 그대로 들어간다 · 본문이 자리표시다

---

## 3. 미결사항

없음.
