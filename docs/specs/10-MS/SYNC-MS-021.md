---
doc_id: SYNC-MS-021
type: MS
title: MINISPEC — ConversationService — 대화·턴·첨부 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-010, SYNC-INFRA-001, SYNC-STD-004]
---

# MINISPEC — ConversationService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/conversation`(`ConversationService`)의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.10. 파이썬 판 [[SYNC-MS-010]]과 **같은 이름·같은 처리·같은 표**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

**카드 L14 몫이다(2026-10-11)** — 읽는 중 질의의 보관(대화·턴·첨부). 명세 묶음과 선이 없다 — 문서·항목 표를 읽지도 쓰지도 않고 프로젝트·사용자를 ID로만 가리킨다. 소유 판정은 프로젝트로 한다([[SYNC-MS-013#ProjectService.get_owned]]) — 남의 것이면 있는지 없는지를 말하지 않는다(`not-found` `conversation`·`attachment`).

`ConversationService { db: &mut PgConnection, repos: &ServerRepos }` — 연결을 빌려 받고 트랜잭션은 부르는 쪽이 쥔다([[SYNC-STD-004#DEV-10]]). `repos`는 소유 판정([[SYNC-MS-013#ProjectService.get_owned]])에 넘긴다.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `DB:` 테이블 접근, `·` 같은 단계 안 구분.

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

**시그니처**
```rust
pub async fn list(&mut self, code: &str, user: &UserRow) -> Result<Vec<ConversationBrief>, Problem>
```

근거: [[SYNC-MS-010#ConversationService.list]]

**처리** [[SYNC-MS-010#ConversationService.list]]와 같다 — `get_owned(code, user)` · `DB: conversations where project_id and user_id order by updated_at desc, id desc`와 턴 수

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]]

**테스트 관점** 최근순 · 턴 수 · 남의 프로젝트 → `not-found`

---

#### ConversationService.create 새 대화

**시그니처**
```rust
pub async fn create(&mut self, code: &str, user: &UserRow, title: Option<&str>) -> Result<ConversationRow, Problem>
```

근거: [[SYNC-MS-010#ConversationService.create]]

**처리** [[SYNC-MS-010#ConversationService.create]]와 같다 — 제목은 `strip` 뒤 앞 80자, 비면 「새 대화」 · `created_at = updated_at = now`

**호출하는 것** [[SYNC-MS-013#ProjectService.get_owned]]

**테스트 관점** 빈 제목 → 「새 대화」 · 80자에서 자른다 · 남의 프로젝트 → `not-found`

---

#### ConversationService.get 대화 하나

**시그니처**
```rust
pub async fn get(&mut self, conv_id: i32, user: &UserRow) -> Result<ConversationView, Problem>
```

근거: [[SYNC-MS-010#ConversationService.get]]

**처리** [[SYNC-MS-010#ConversationService.get]]와 같다 — 소유 판정 · 첨부 메타(id 순, 바이트·글자 없이) · 턴(seq 순)마다 그 턴의 첨부 · `pending`은 턴 없는 첨부 · `project_code`

**호출하는 것** 없음 — 소유 판정은 대화 행의 프로젝트 행으로 바로 한다(파이썬 `_owned`)

**테스트 관점** 턴·첨부 차례 · 남의 대화 → `not-found`

---

#### ConversationService.delete 대화 지우기

**시그니처**
```rust
pub async fn delete(&mut self, conv_id: i32, user: &UserRow) -> Result<(), Problem>
```

근거: [[SYNC-MS-010#ConversationService.delete]]

**처리** 소유 판정 · `DB: delete conversations` — 턴·첨부는 FK cascade

**테스트 관점** 턴·첨부까지 없어진다 · 남의 대화 → `not-found`

---

#### ConversationService.delete_by_project 프로젝트 해제와 함께

**시그니처**
```rust
pub async fn delete_by_project(&mut self, project_id: i32) -> Result<(), Problem>
```

근거: [[SYNC-MS-010#ConversationService.delete_by_project]] · [[SYNC-MS-013#ProjectService.delete_project]] 2

**처리** `DB: delete conversations where project_id` — 소유 판정은 부르는 쪽이 했다

**테스트 관점** 그 프로젝트의 대화만

---

#### ConversationService.add_turn 턴을 만든다

**시그니처**
```rust
pub async fn add_turn(&mut self, conv_id: i32, question: &str, attachment_ids: &[i64]) -> Result<TurnRow, Problem>
```

근거: [[SYNC-MS-010#ConversationService.add_turn]]

**처리** [[SYNC-MS-010#ConversationService.add_turn]]와 같다 — 대화가 없으면 `! NotFound(conversation)` · `seq = max + 1` · 이 대화의 안 보낸 첨부 중 `attachment_ids`에 든 것만 이 턴에 붙인다 · 첫 턴이거나 제목이 「새 대화」면 제목 = 질문 `strip` 앞 40자(비면 「새 대화」) · `updated_at = now`

**다른 점** `attachment_ids`는 파이썬 정수(요청 본문)라 `i64`로 받는다 — int4 밖의 id는 어느 첨부와도 같지 않아 건너뛴다(파이썬은 DB가 거절해 500)

**테스트 관점** seq가 1·2·3 · 첫 질문이 제목 · 남의·보낸 첨부는 안 붙는다

---

#### ConversationService.finish_turn 턴을 닫는다

**시그니처**
```rust
pub async fn finish_turn(&mut self, turn_id: i32, answer: Option<&str>, progress: &[Progress], context_item_ids: &[String], error: Option<&str>) -> Result<TurnRow, Problem>
```

근거: [[SYNC-MS-010#ConversationService.finish_turn]]

**처리** [[SYNC-MS-010#ConversationService.finish_turn]]와 같다 — 턴이 없으면 `! NotFound(turn)` · 답도 오류도 없으면 오류 「답 없이 끊겼다」 · 오류가 있으면 답은 비운다 · 진행 줄·본 것 · 대화 `updated_at = now`

**테스트 관점** 답 → 저장 · 오류 → 답 없음 · 둘 다 없으면 「답 없이 끊겼다」

---

#### ConversationService.history 앞 대화

**시그니처**
```rust
pub async fn history(&mut self, conv_id: i32, limit: i64) -> Result<Vec<LlmMessage>, Problem>
```

근거: [[SYNC-MS-010#ConversationService.history]]

**처리** [[SYNC-MS-010#ConversationService.history]]와 같다 — `limit <= 0`이면 빈 것 · 오류 없고 답 있는 턴의 뒤에서 `limit`개를 `user`·`assistant` 쌍으로

**테스트 관점** 실패한 턴은 빠진다 · 뒤에서 limit턴

---

#### ConversationService.add_attachment 파일을 올린다

**시그니처**
```rust
pub async fn add_attachment(&mut self, conv_id: i32, user: &UserRow, name: &str, mime: &str, data: &[u8]) -> Result<AttachmentMeta, Problem>
```

근거: [[SYNC-MS-010#ConversationService.add_attachment]]

**처리** [[SYNC-MS-010#ConversationService.add_attachment]] 1~7과 같다 — 확장자 표 · 클라이언트 mime(`;` 앞, 소문자)이 비거나 `application/octet-stream`이면 확장자로, 표와 어긋나면 `! AttachmentType` · 상한(이미지 10MiB, 나머지 1MiB) · 안 보낸 첨부 8개 · 이름 앞 200자

**다른 점** PDF 글자는 `pypdf` 대신 `lopdf`로 쪽마다 뽑는다 — 쪽 글자를 `\n\n`으로 잇고(공백뿐인 쪽은 빼고) 깨진 PDF는 `""`인 규칙은 같지만 **뽑힌 글자는 파이썬 판과 다를 수 있다**(에이전트 판단 2026-10-11, 사용자 목표 「끝까지」 — pypdf의 글자 배치·폰트 해석을 옮기지 않는다. 글자는 모델만 읽고 API 응답에 나오지 않는다) · 메타(`AttachmentMeta`)를 돌려준다(파이썬은 행 — 라우터가 메타로 바꾼다)

**테스트 관점** 열 가지 종류 · `exe` → 415 · 상한 넘음 → 413 · 아홉째 → 409 · md의 글자가 본문과 같다 · 글자 있는 PDF는 쪽 글자가 다 있다 · 깨진 PDF는 `""` · 이미지는 글자 없음 · 남의 대화 → `not-found`

---

#### ConversationService.remove_attachment 안 보낸 첨부를 뺀다

**시그니처**
```rust
pub async fn remove_attachment(&mut self, att_id: i32, user: &UserRow) -> Result<(), Problem>
```

근거: [[SYNC-MS-010#ConversationService.remove_attachment]]

**처리** [[SYNC-MS-010#ConversationService.remove_attachment]]와 같다 — 없거나 남의 것 → `! NotFound(attachment)` · 보낸 것 → `! AttachmentSent` · 지운다

**테스트 관점** 안 보낸 것은 지워진다 · 보낸 것 → 409 · 남의 것 → `not-found`

---

#### ConversationService.attachment_meta 첨부 메타

**시그니처**
```rust
pub async fn attachment_meta(&mut self, att_id: i32, user: &UserRow) -> Result<AttachmentMeta, Problem>
```

근거: [[SYNC-MS-010#ConversationService.attachment_meta]]

**처리** 소유 판정 · `→ AttachmentMeta`

**테스트 관점** 남의 것 → `not-found`

---

#### ConversationService.attachment_bytes 첨부 바이트

**시그니처**
```rust
pub async fn attachment_bytes(&mut self, att_id: i32, user: &UserRow) -> Result<(String, String, Vec<u8>), Problem>
```

근거: [[SYNC-MS-010#ConversationService.attachment_bytes]]

**처리** 소유 판정 · `→ (name, mime, bytes)`

**테스트 관점** 올린 바이트가 그대로 · 남의 것 → `not-found`

---

#### ConversationService.attachment_text 모델이 읽을 글자

**시그니처**
```rust
pub async fn attachment_text(&mut self, conv_id: i32, att_id: i64) -> Result<Option<String>, Problem>
```

근거: [[SYNC-MS-010#ConversationService.attachment_text]]

**처리** [[SYNC-MS-010#ConversationService.attachment_text]]와 같다 — 이 대화의 첨부가 아니거나 이미지면 없음 · `text_cache`(없으면 `""`)

**다른 점** 모델이 준 id라 `i64`로 받는다 — int4 밖이면 없음(파이썬은 DB가 거절해 질문이 오류로 끝난다)

**테스트 관점** 다른 대화의 첨부 → 없음 · 이미지 → 없음 · md 글자가 그대로

---

#### ConversationService.pending_images 이 턴의 이미지

**시그니처**
```rust
pub async fn pending_images(&mut self, turn_id: i32) -> Result<Vec<(String, Vec<u8>)>, Problem>
```

근거: [[SYNC-MS-010#ConversationService.pending_images]]

**처리** `DB: attachments where turn_id and mime like 'image/%' order by id` · `→ [(mime, bytes)]`

**테스트 관점** 이미지만, 올린 순서

---

## 3. 미결사항

없음.
