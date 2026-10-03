---
doc_id: SYNC-MS-010
type: MS
title: MINISPEC — ConversationService — 대화·턴·첨부
status: approved
upstream: [SYNC-DOM-002, SYNC-DOM-003, SYNC-SEQ-001, SYNC-API-001, SYNC-STD-001]
---

# MINISPEC — ConversationService — 대화·턴·첨부

## 0. 이 문서가 다루는 것

`core/conversation/service.py`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-002]] 4.10의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

읽는 중 질의([[SYNC-PRD-001#R11]])의 **보관**을 맡는다 — 2026-09-29 사용자 결정으로 대화·첨부를 서버에 두기로 했다. 명세 묶음과 선이 없다: 문서·항목 표를 읽지도 쓰지도 않고, 프로젝트·사용자를 ID로만 가리킨다([[SYNC-DOM-001]] 4장 「대화」 묶음). 재구축(UC-S6)이 건드리지 않는다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`ConversationBrief`·`ConversationView`·`TurnView`·`AttachmentMeta`)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `·` 같은 단계 안 구분.

**소유 판정은 프로젝트로 한다.** 대화 ID로 들어오는 함수는 대화 행의 `project_id`로 프로젝트를 찾아 [[SYNC-MS-001#ProjectService.get_owned]]를 지난다. 남의 것이면 있는지 없는지를 말하지 않는다 — `! not-found {resource: "conversation"}`(첨부는 `"attachment"`).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ConversationService.list]] | 이 프로젝트의 내 대화, 최근순 |
| [[#ConversationService.create]] | 새 대화 |
| [[#ConversationService.get]] | 대화 하나 — 턴 전부 + 첨부 메타 |
| [[#ConversationService.delete]] | 대화 지우기(턴·첨부 cascade) |
| [[#ConversationService.delete_by_project]] | 프로젝트 해제와 함께 |
| [[#ConversationService.add_turn]] | 질문을 받자마자 턴을 만들고 첨부를 붙인다 |
| [[#ConversationService.finish_turn]] | 답이나 실패로 턴을 닫는다 |
| [[#ConversationService.history]] | 모델에 실을 앞 대화 |
| [[#ConversationService.add_attachment]] | 파일 하나를 올린다 — 종류·상한·글자 추출 |
| [[#ConversationService.remove_attachment]] | 아직 안 보낸 첨부를 뺀다 |
| [[#ConversationService.attachment_meta]] | 첨부 메타 하나 |
| [[#ConversationService.attachment_bytes]] | 첨부 바이트 — 미리보기·다운로드 |
| [[#ConversationService.attachment_text]] | 모델이 읽을 글자 |
| [[#ConversationService.pending_images]] | 이 턴에 붙은 이미지 |

---

## 2. 함수

#### ConversationService.list 이 프로젝트의 내 대화

**시그니처** `def list(code: str, user: User) -> list[ConversationBrief]`

근거: [[SYNC-API-001#GET/api/projects/{code}/conversations]] · [[SYNC-UI-002#UI-5]] 8.11

**입력** `code` 프로젝트 코드 · `user` 보는 사람

**처리**
1. `project = ProjectService.get_owned(code, user)` — 남의 것이면 `! not-found {resource: project}`
2. `DB: conversations where project_id and user_id` · 턴 수는 `count(turns)` · `updated_at` 내림차순
3. `→ [ConversationBrief(id, title, turn_count, updated_at)]`

**출력** 최근순 목록. 빈 프로젝트면 `[]`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]]

**테스트 관점** 최근순 · 다른 사용자의 대화는 안 보인다(같은 프로젝트라도 — 소유자는 한 명이라 실제로는 겹치지 않는다) · 남의 프로젝트 → `not-found` · `turn_count`가 실패한 턴도 센다

---

#### ConversationService.create 새 대화

**시그니처** `def create(code: str, user: User, title: str | None = None) -> Conversation`

근거: [[SYNC-API-001#GET/api/projects/{code}/conversations]] post · [[SYNC-UI-002#UI-5]] 8.12

**처리**
1. `project = ProjectService.get_owned(code, user)`
2. `DB: insert conversations(project_id, user_id, title=title or "새 대화", created_at=updated_at=clock.now())`
3. `→ Conversation`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]]

**테스트 관점** 제목이 비면 「새 대화」 · `updated_at == created_at` · 남의 프로젝트 → `not-found`

---

#### ConversationService.get 대화 하나

**시그니처** `def get(conv_id: int, user: User) -> ConversationView`

근거: [[SYNC-API-001#GET/api/conversations/{id}]] · [[SYNC-MS-008#queries.ask_item]] 0

**처리**
1. `DB: conversations by id` · 없으면 `! not-found {resource: conversation}` · `ProjectService.get_owned(project.code, user)` — 남의 것이면 같은 `not-found`
2. `DB: turns order by seq` · `attachments where conversation_id` — **`bytes`·`text_cache`는 읽지 않는다**(메타만 select)
3. 턴마다 `TurnView(…, attachments=[그 턴의 AttachmentMeta])` · `pending = [turn_id가 null인 AttachmentMeta]`
4. `→ ConversationView(brief, turns, pending)`

**테스트 관점** 턴이 `seq` 순 · 첨부가 자기 턴 밑에 · 안 보낸 첨부는 `pending` · 응답에 바이트·글자가 없다 · 남의 대화 → `not-found`

---

#### ConversationService.delete 대화 지우기

**시그니처** `def delete(conv_id: int, user: User) -> None`

근거: [[SYNC-API-001#GET/api/conversations/{id}]] delete · [[SYNC-UC-001#UC-H19]] 1c · [[SYNC-UI-002#UI-5]] 8.13

**처리**
1. `get(conv_id, user)`와 같은 소유 판정
2. `DB: delete conversations by id` — 턴·첨부는 `ON DELETE CASCADE`([[SYNC-DOM-003]] 규칙)
3. `→ None`

**테스트 관점** 지운 뒤 턴·첨부 행이 0 · 다른 대화는 그대로 · 남의 대화 → `not-found`, 아무것도 안 지워짐

---

#### ConversationService.delete_by_project 프로젝트 해제와 함께

**시그니처** `def delete_by_project(project_id: int) -> None`

근거: [[SYNC-MS-001#ProjectService.delete_project]] 2 · [[SYNC-UC-001#UC-H17]]

**처리** `DB: delete conversations where project_id` — cascade. 소유 판정은 부르는 쪽(`delete_project`)이 이미 했다 · `→ None`

**호출되는 것** [[SYNC-MS-001#ProjectService.delete_project]]

**테스트 관점** 프로젝트 해제 뒤 그 프로젝트의 대화·턴·첨부가 0 · 다른 프로젝트의 대화는 그대로

---

#### ConversationService.add_turn 턴을 만든다

**시그니처** `def add_turn(conv_id: int, question: str, attachment_ids: list[int]) -> Turn`

근거: [[SYNC-SEQ-001#SEQ-24]] · [[SYNC-MS-008#queries.ask_item]] 1

**입력** `conv_id` 소유 판정을 이미 지난 대화 · `question` · `attachment_ids` 이 대화에 올려 두고 아직 안 보낸 첨부

**처리**
1. `seq = (DB: max(turns.seq) where conversation_id) + 1`(없으면 1)
2. `DB: insert turns(conversation_id, seq, question, progress=[], context_item_ids=[], created_at)`
3. `DB: update attachments set turn_id where id in attachment_ids and conversation_id = conv_id and turn_id is null` — 다른 대화의 것·이미 보낸 것은 조용히 건너뛴다(모델에 안 실릴 뿐)
4. `if seq == 1 or 대화 title == "새 대화" → title = question[:40]` · `updated_at = now`
5. `→ Turn`

**테스트 관점** `seq`가 1부터 이어진다 · 첫 질문이 제목이 된다(40자 자름) · 남의 대화의 첨부 id를 섞어도 붙지 않는다 · 이미 보낸 첨부는 다시 안 붙는다

---

#### ConversationService.finish_turn 턴을 닫는다

**시그니처** `def finish_turn(turn_id: int, answer: str | None, progress: list[dict], context_item_ids: list[str], error: str | None = None) -> Turn`

근거: [[SYNC-SEQ-001#SEQ-24]] · [[SYNC-MS-008#queries.ask_item]] 2·7

**처리**
1. `DB: turns by id` · `answer`와 `error` 중 하나만 — 둘 다 없으면 `error = "답 없이 끊겼다"`
2. `update turns set answer, error, progress, context_item_ids` · 대화 `updated_at = now`
3. `→ Turn`

**테스트 관점** 답이 있으면 `error`가 null · 실패면 `answer`가 null · `progress`가 note·read 순서 그대로 · 두 번 닫으면 나중 것

---

#### ConversationService.history 앞 대화

**시그니처** `def history(conv_id: int, limit: int) -> list[dict]`

근거: [[SYNC-MS-008#queries.ask_item]] 1 · [[SYNC-INFRA-001]] 5.3(`LLM_MAX_TURNS`)

**처리**
1. `DB: turns where conversation_id and error is null and answer is not null order by seq` · 뒤에서 `limit`턴(`limit <= 0`이면 `[]`)
2. 턴마다 `{role: user, text: question}` · `{role: assistant, text: answer}`
3. `→ list[dict]` — 이미지·첨부·진행 줄은 안 실린다(앞 턴의 본문을 다시 안 싣는 규칙)

**테스트 관점** 실패한 턴은 빠진다 · `limit`이 뒤에서 센다 · 지금 만든(아직 안 닫힌) 턴은 빠진다

---

#### ConversationService.add_attachment 파일을 올린다

**시그니처** `def add_attachment(conv_id: int, user: User, name: str, mime: str, data: bytes) -> Attachment`

근거: [[SYNC-API-001#POST/api/conversations/{id}/attachments]] · [[SYNC-UC-001#UC-H19]] 1b · [[SYNC-INFRA-001]] 5.3 첨부

**입력** `name` 원래 파일 이름 · `mime` 클라이언트가 말한 종류 — 확장자로 다시 정한다 · `data` 바이트

**처리**
1. `get(conv_id, user)`와 같은 소유 판정
2. 종류: 확장자 → mime 표(`png jpg jpeg webp gif` → `image/*` · `md` → `text/markdown` · `txt` → `text/plain` · `csv` → `text/csv` · `json` → `application/json` · `yaml yml` → `application/yaml` · `pdf` → `application/pdf`). 표 밖이거나 클라이언트 mime이 표와 어긋나면 `! AttachmentType(mime)`(415)
3. 상한: 이미지 `10 * 1024 * 1024` · 나머지 `1024 * 1024`. 넘으면 `! AttachmentTooLarge(limit, size)`(413)
4. `DB: count attachments where conversation_id and turn_id is null` `>= 8` → `! AttachmentLimit(8)`(409)
5. 글자: `text/*`·`json`·`yaml`은 `data.decode("utf-8", errors="replace")` · PDF는 `pypdf.PdfReader` 쪽마다 `extract_text()`를 `\n\n`으로 이어 붙인다(예외·글자 없음 → `""`) · 이미지는 `None`
6. `DB: insert attachments(conversation_id, turn_id=null, user_id, name, mime, size=len(data), bytes=data, text_cache, created_at)`
7. `→ Attachment`

**예외** | 조건 | 에러 |
| 종류 밖 | `attachment-type` 415 |
| 상한 초과 | `attachment-too-large` 413 |
| 안 보낸 첨부 8개 | `attachment-limit` 409 |

**테스트 관점** 열 가지 종류 각각 통과 · `exe`·`docx` → 415 · 10MB+1 이미지 → 413, 1MB+1 md → 413 · 아홉째 → 409(보낸 뒤엔 다시 8개 가능) · md의 `text_cache`가 본문과 같다 · PDF 픽스처(글자 두 쪽)에서 두 쪽 글자가 다 있다 · 스캔 PDF(글자 없음)는 `""` · 이미지는 `text_cache` null · 남의 대화 → `not-found`

---

#### ConversationService.remove_attachment 안 보낸 첨부를 뺀다

**시그니처** `def remove_attachment(att_id: int, user: User) -> None`

근거: [[SYNC-API-001#GET/api/attachments/{id}]] delete · [[SYNC-UI-002#UI-5]] 8.14

**처리**
1. `DB: attachments by id` → 대화 → 소유 판정 · 없거나 남의 것이면 `! not-found {resource: attachment}`
2. `if turn_id is not None → ! AttachmentSent`(409 `attachment-sent`) — 보낸 첨부는 턴의 일부다
3. `DB: delete` · `→ None`

**테스트 관점** 안 보낸 것은 지워진다 · 보낸 것 → 409 · 남의 것 → `not-found`

---

#### ConversationService.attachment_meta 첨부 메타

**시그니처** `def attachment_meta(att_id: int, user: User) -> AttachmentMeta`

**처리** 소유 판정(위와 같음) · `→ AttachmentMeta` — 바이트·글자 없이

**테스트 관점** 남의 것 → `not-found`

---

#### ConversationService.attachment_bytes 첨부 바이트

**시그니처** `def attachment_bytes(att_id: int, user: User) -> tuple[str, str, bytes]`

근거: [[SYNC-API-001#GET/api/attachments/{id}]]

**처리** 소유 판정 · `→ (name, mime, bytes)` — 라우터가 `Content-Type`·`Content-Disposition: inline; filename*=`로 낸다

**테스트 관점** 올린 바이트가 그대로 돌아온다 · 남의 것 → `not-found`

---

#### ConversationService.attachment_text 모델이 읽을 글자

**시그니처** `def attachment_text(conv_id: int, att_id: int) -> str | None`

근거: [[SYNC-MS-008#queries.ask_tool]] `read_attachment` · [[SYNC-INFRA-001]] 5.3

**처리**
1. `DB: attachments by id where conversation_id = conv_id` · 없으면 `→ None`(모델에 「없음」) — **이 대화의 첨부만**. 소유 판정은 `ask_item` 0에서 대화 단위로 이미 했다
2. `if mime가 image/* → None`(도구로 못 읽는다 — 붙인 질문에 이미 보였다)
3. `→ text_cache`(`""`일 수 있다 — 스캔본)

**테스트 관점** 다른 대화의 첨부 id → None · 이미지 → None · md 글자가 그대로

---

#### ConversationService.pending_images 이 턴의 이미지

**시그니처** `def pending_images(turn_id: int) -> list[tuple[str, bytes]]`

근거: [[SYNC-MS-008#queries.ask_item]] 1·3 · [[SYNC-MS-009#llm.step]] `images`

**처리** `DB: attachments where turn_id and mime like 'image/%' order by id` · `→ [(mime, bytes)]`

**테스트 관점** 이미지만, 올린 순서 · 글자 첨부는 빠진다 · 다른 턴의 이미지는 안 실린다

---

## 3. 미결사항

- [x] 첨부 바이트가 DB를 무겁게 하면(수백 MB) 바이트 자리만 객체 저장소로 — 테이블·시그니처는 그대로([[SYNC-INFRA-001]] 3장) — 결정(2026-09-30): 지금은 bytea. **프로젝트의 첨부 합이 1GB를 넘으면** 그때 새 카드로 바이트 자리만 객체 저장소로 옮긴다. 표·시그니처는 그대로
