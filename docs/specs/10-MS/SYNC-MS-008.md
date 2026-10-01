---
doc_id: SYNC-MS-008
type: MS
title: MINISPEC — queries — 읽기 조합
status: approved
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — queries — 읽기 조합

## 0. 이 문서가 다루는 것

`core/queries.py`의 함수 14개. 클래스 명세 [[SYNC-DOM-002]] 4.8의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`queries`는 `pipeline`과 대칭이다. 서비스는 자기 테이블만 알고, `queries`가 pk·ID로 이어 붙여 응답 형태([[SYNC-API-001]] 4장)를 만든다. **절대 쓰지 않는다.**

**사람용 조회는 전부 `user: User`를 받는다** — 여기 14개 전부가 그렇다. 첫 단계에서 [[SYNC-MS-001#ProjectService.get_owned]](목록은 `list_owned`)로 소유를 가르고, 남의 프로젝트는 문서·항목을 **읽기 전에** `not-found {resource: project}`로 끝난다([[SYNC-PRD-001#R12]]). 프로젝트 코드는 `code` 인자 또는 `doc_id.split("-")[0]`. **`user`의 자리는 마지막 필수 인자다** — 기본값이 있는 선택 인자(`stage`·`status`·`scope`) 앞. `user`는 필수라 기본값 뒤에 올 수 없고, 필수 인자 중 맨 뒤에 두면 열네 함수가 같은 모양이 된다. 라우터는 `Depends(current_user)`를, MCP는 `_user(session)`을 그 자리에 넣는다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#queries.project_summary]] | 프로젝트 목록 + 단계 11칸 + 건수 |
| [[#queries.project_detail]] | + 문서 목록 + 최근 변경 |
| [[#queries.document_list]] | 문서 목록 + 문서별 건수 |
| [[#queries.trash_list]] | 휴지통 목록 |
| [[#queries.document_view]] | 문서 + 미존재 참조 + 이웃 |
| [[#queries.item_view]] | 항목 블록 |
| [[#queries.item_references_view]] | 상위·하위 참조 + 표시 이름 |
| [[#queries.graph_view]] | 노드·간선 |
| [[#queries.item_chain]] | 항목의 11단계 체인 |
| [[#queries.diff_with_impact]] | diff + 하위 건수 |
| [[#queries.project_items]] | 프로젝트 끊어진 참조·오류·미완성 목록 |
| [[#queries.downstream_view]] | 이 문서를 참조하는 것 (추적표) |
| [[#queries.ask_item]] | 문서를 읽다가 묻는다 — 모델이 관계도를 따라 읽는다 |
| [[#queries.ask_tool]] | 모델이 부른 읽기 도구 하나를 실행한다 |
| [[#queries.code_view]] | 코드 탭 — 항목의 코드 대조 |
| [[#queries.code_calls]] | 관계도 코드 호출 — MINISPEC 사이 호출 선 |
| [[#queries.code_nodes]] | 코드 그래프 노드 — 함수 전부·커뮤니티·대조 상태 (UI-17) |
| [[#queries.code_source]] | 코드 보기 — 함수 본문 |
| [[#queries.code_text]] | 코드 그래프의 코드 — 파일·줄로 함수 본문 (UI-17 4.6, 카드 BF) |

---

## 2. 함수

#### queries.trash_list 휴지통 목록

**시그니처** `async def trash_list(code: str, user: User) -> list[DocumentSummary]`

근거: [[SYNC-API-001#GET/api/projects/{code}/trash]] · [[SYNC-UI-002#UI-4]] 8

**처리** `project = ProjectService.get_owned(code, user)` (남의 것 → `not-found`) · `SpecService.list_trashed(project_id)` · 작성자 이름은 `users_by_ids`로(`trashed_by`). 건수는 안 센다 — 휴지통 목록에는 수치가 없다 · `→ docs`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-002#SpecService.list_trashed]] · [[SYNC-MS-006#AccountService.users_by_ids]]

---

#### queries.ask_item 문서를 읽다가 묻는다 — 모델이 관계도를 따라 읽는다

**시그니처** `async def ask_item(doc_id: str, item_id: str | None, conversation_id: int, question: str, attachment_ids: list[int], user: User) -> AsyncIterator[AskEvent]`

근거: [[SYNC-PRD-001#R11]] · [[SYNC-UC-001#UC-H19]] · [[SYNC-SEQ-001#SEQ-24]] · [[SYNC-INFRA-001]] 5.3 · 사용자 결정 2026-09-22(카드 Y — [[SYNC-CODE-001#Y]]) · 사용자 결정 2026-09-29(대화·첨부 보관 — [[SYNC-CODE-001#AQ]]·[[SYNC-CODE-001#AR]])

**입력** `doc_id` 지금 열린 문서 — 시작 맥락 · `item_id` 보고 있는 항목. 힌트일 뿐이라 `None`이면 문서 전체로 시작한다 · `conversation_id` 쌓을 대화. 앞 대화는 여기서 읽는다 — 클라이언트가 보내지 않는다 · `question` 사람이 쓴 질문 · `attachment_ids` 이 대화에 올려 두고 아직 안 보낸 첨부. 이 질문의 턴에 붙는다

**처리** — ReAct 루프. 모델이 읽기 도구를 스스로 부르고, 진행이 이벤트로 흘러 나간다. 쓰는 것은 대화 표뿐이다
0. `if not settings.LLM_API_KEY → ! LlmNotConfigured`(네트워크 전) · `ProjectService.get_owned(doc_id.split("-")[0], user)` — 남의 것이면 `! not-found {resource: project}` · [[SYNC-MS-010#ConversationService.get]]`(conversation_id, user)` — 내 것이 아니거나 그 프로젝트가 아니면 `! not-found {resource: conversation}`
1. 세션 하나에서 `history = ConversationService.history(conversation_id, settings.LLM_MAX_TURNS)` · `turn = ConversationService.add_turn(conversation_id, question, attachment_ids)` · `images = ConversationService.pending_images(turn.id)` · `doc = SpecService.get_document(doc_id)` + `describe_documents([doc.id])`(제목) → 시작 맥락: 제목·상태·버전 + 이 문서의 **모든 항목 `ID 이름`** + `item_id`가 있으면 `[지금 보는 항목] {item_id} {display_name}` + 이 대화의 첨부가 있으면 `[첨부] {id} {name} ({종류}, {크기})` 줄들(글자·PDF는 「read_attachment로 읽을 수 있다」, 이미지는 「이 질문에 보인다」) · `item_id`가 이 문서에 없으면 `! not-found {resource: item}`(턴은 `error`로 닫는다) · **본문은 싣지 않는다** — 필요한 본문은 모델이 도구로 읽는다
2. `yield AskStart(doc_id, item_id)` — 이 앞의 예외는 HTTP 상태로, 이 뒤는 `error` 이벤트로 나간다([[SYNC-API-001]] 1장). 이 뒤의 예외는 **`finish_turn(turn.id, error=…)`로 턴을 닫은 뒤** 던진다
3. `t0 = monotonic()` · `calls = 0` · `reads: list[str] = []` · `progress: list[dict] = []`(yield하는 note·read를 그대로 모은다) · 대화록 = `history` + `{role: user, text: question, images}`
4. [[SYNC-MS-009#llm.step_stream]]`(system, 대화록, _ASK_TOOLS)`을 돈다 — `str` 조각이면 `yield AskDelta(text)`(모델이 지금 쓰는 글자, `progress`에 안 넣는다), `LlmStep`이면 `step`(카드 AW) · usage 누적 · `if not step.tool_calls → answer = step.text → 7`
5. `if step.text → yield AskNote(step.text)` · 도구 호출마다: `yield AskNote(args["reason"])` → `r = ask_tool(name, args, code, user, conversation_id)` → `yield AskRead(name, r.target)` · `r.target`이 있고 `reads`에 없으면 `reads.append` · 대화록에 `{role: assistant, text: step.text, tool_calls}`와 `{role: tool, tool_call_id, text: r.text}` 추가 · `calls += 1`(호출마다)
6. `if calls >= _ASK_MAX_CALLS or monotonic() - t0 >= _ASK_TIME_LIMIT` → 대화록에 마무리 문장(아래)을 `user`로 추가 → `llm.step_stream(system, 대화록, _ASK_TOOLS, tool_choice="none")` **한 번**(조각은 4단계처럼 `AskDelta`로) → `step.text`가 비면 `! LlmUnavailable("상한 뒤에도 답이 없다")` → `answer = step.text` → 7 · 아니면 4로
7. `ConversationService.finish_turn(turn.id, answer, progress, reads)` — 세션 하나에서. 대화 `title`이 「새 대화」면 `question[:40]`으로, `updated_at` 갱신 · `log.info("ask doc=%s item=%s conv=%s user=%s calls=%d prompt=%d completion=%d elapsed=%.1fs", …)` — 한 줄, 본문·질문·답은 로그에 안 남긴다(DEV-6) · `yield AskAnswer(answer, context_item_ids=reads)`

**상수** `_ASK_MAX_CALLS = 8` · `_ASK_TIME_LIMIT = 120.0`(초). 설정값이 아니라 코드 상수다 — 회수 경로는 키를 비우는 것 하나로 둔다([[SYNC-INFRA-001]] 5.3). 시간은 **호출 사이**에서만 본다 — 한 호출의 60초 타임아웃이 더해져 최악 180초(마무리 호출 포함)

**대화록 항목** — 우리 키로 쌓고 와이어 형식은 어댑터가 옮긴다([[SYNC-MS-009#llm.step]]): `{role: user|assistant, text}` · `{role: assistant, text, tool_calls: [ToolCall]}` · `{role: tool, tool_call_id, text}`

**DB 세션** 도구 실행([[#queries.ask_tool]]) 안에서만 잠깐 연다. 모델을 기다리는 동안 세션을 쥐지 않는다

**지시문 원문** — 코드 `_ASK_SYSTEM`이 이것을 그대로 옮긴다. `{items}`는 줄마다 `ID 이름`, `{viewing}`은 `[지금 보는 항목] {item_id} {display_name}` 또는 빈 줄. 「모른다」 조건이 [[SYNC-UC-001#UC-H19]] 확장 3a를 실행하는 문장이라 명세 쪽에 산다.

```
당신은 명세를 읽는 사람 옆에서 그 자리를 설명한다. 문서 하나가 열려 있고, 당신은 도구로
같은 프로젝트의 다른 문서와 항목을 읽을 수 있다. 읽기만 한다 — 쓰는 도구는 없다.

읽은 것만으로 답한다. 처음에는 아래 문서의 항목 목록만 있고 본문은 없다. 답에 필요한
본문은 도구로 읽는다. 보고 있는 항목 자체를 묻는 질문(이게 뭐야·왜 이렇게 했어)은 그
항목을 get_item으로 읽고 본문으로 답한다. 근거·영향을 물으면 get_references나
item_chain으로 관계를 따라간 뒤 필요한 항목만 get_item으로 읽는다. get_document는
문서 전체를 훑어야 할 때만 쓴다 — 크다. 앞 대화에서 읽은 것은 다시 실리지 않으므로
필요하면 다시 읽는다.

도구를 부를 때마다 reason에 한 줄로 무엇을 왜 읽는지 적는다. 그 줄이 사람에게 보인다.

도구는 여덟 번까지, 전체 두 분 안이다. 「지금까지 읽은 것으로 답하라」는 말을 받으면
더 읽지 않고 그때까지 읽은 것으로 답한다.

근거나 참조를 물으면 먼저 보고 있는 항목을 get_item으로 읽는다 — 본문의 [[문서#항목]]
링크가 정확한 문서 ID다. 항목 ID만으로 지금 문서를 짚지 않는다.

모른다는 읽어도 정말 없을 때만 말하고, 그때는 어느 명세 단계(RFQ~CODE)가 아직 안
쓰였는지 짚어 준다 — item_chain의 빈 단계나 「아직 없음」 참조가 그 근거다.
지어내지 않는다.

답에 근거를 댈 때는 읽은 항목 ID(문서ID#항목ID)를 그대로 쓴다. 없는 ID를 만들지 않는다.

명세를 고치라고 하지 않는다. 당신은 읽기를 돕는 자리이고, 본문을 쓰는 것은 사람과
그 사람의 에이전트가 한다.

구조·관계·흐름을 묻거나 그림·마인드맵·그래프를 청하면 mermaid 코드블록으로
그린다 — 코드블록의 언어 표시는 반드시 mermaid이고(mindmap·flowchart가 아니다) 첫 줄이
그림 종류다. 관계는 flowchart, 가지치기는 mindmap, 항목 사이 참조는 classDiagram, 순서는
sequenceDiagram. 노드 라벨에는 읽은 항목 ID(문서ID#항목ID)와 이름을 쓴다. 안 읽은 항목은
그리지 않는다. mindmap은 들여쓰기만으로 가지를 만든다 — 중괄호·화살표·따옴표를 쓰지 않고
라벨 안에 괄호·대괄호도 쓰지 않는다(이름에 괄호가 있으면 그 부분은 뺀다). 꼴은 이렇다:
  mindmap
    root((SYNC-PRD-001#R1 이름))
      근거
        Q1[SYNC-RFQ-001#Q1 이름]
      파생
        S1[SYNC-SCN-001#S1 이름]
flowchart·classDiagram은 노드 id를 영문·숫자·_로만 만들고 라벨을 큰따옴표로 감싼다.
그림 아래에 한두 문장으로 무엇을 그렸는지 적는다.

답은 짧게 쓴다 — 문장은 한 뜻에 하나, 소제목은 굵은 한 줄, 목록은 한 줄씩. 항목을 댈 때는
문서ID#항목ID 이름 한 번이고 그 이름을 풀어 다시 쓰지 않는다. 번호 목록은 1·2·3으로 이어서
쓴다.

구현을 물으면(「명세대로 구현됐어?」 「이 함수가 실제로 뭘 부르나」) code_graph로 그 항목의
대조(같음·코드만·명세만)를 먼저 보고, 필요하면 read_code로 함수 본문을 읽는다. 코드 근거는
파일:줄로 댄다. 코드 그래프가 없다고 하면 그렇다고 말하고 지어내지 않는다.

[문서] {doc_id} {title} · 상태 {status} · v{version_no}
[이 문서의 항목]
{items}
{viewing}
```

**마무리 문장 원문** — 6단계에서 `user` 역할로 대화록에 넣는다.

```
도구 호출 상한(또는 시간 상한)에 닿았다. 지금까지 읽은 것으로 답하라. 못 읽은 것이 있으면 무엇을 못 읽었는지 말한다.
```

**출력** `AskEvent`의 비동기 흐름 — `AskStart` 하나 → `AskDelta`·`AskNote`·`AskRead` 0개 이상 → `AskAnswer` 하나. `AskDelta`는 모델이 지금 쓰는 글자 조각이고 **답인지 메모인지는 뒤 이벤트가 정한다** — 그 호출이 도구로 끝나면 `AskNote`(전체 글)가, 답으로 끝나면 `AskAnswer`(전체 본문)가 다시 온다. 조각은 저장하지 않는다(카드 AW). `context_item_ids`는 모델이 **실제로 읽은 대상**(`DOC#ITEM`·`DOC`)을 부른 순서로, 중복 없이

**예외** 남의 프로젝트·없는 `item_id` → `not-found`(`AskStart` 전이라 HTTP 상태) · 키 없음 → `llm-not-configured`(전) · 모델 실패·마무리 뒤에도 답 없음 → `llm-unavailable`(`AskStart` 뒤라 `error` 이벤트) · 도구 안의 「없음」은 예외가 아니라 결과다([[#queries.ask_tool]])

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-002#SpecService.get_document]] · [[SYNC-MS-002#SpecService.describe_documents]] · [[SYNC-MS-009#llm.step_stream]] · [[#queries.ask_tool]] · [[SYNC-MS-010#ConversationService.add_turn]] · [[SYNC-MS-010#ConversationService.finish_turn]] · [[SYNC-MS-010#ConversationService.get]] · [[SYNC-MS-010#ConversationService.history]] · [[SYNC-MS-010#ConversationService.pending_images]]

**테스트 관점** 가짜 `llm.step`에 대본을 주어 돈다 · 지시문에 mermaid 그림 안내가 있다(카드 AS) · 지시문에 답 양식(「답은 짧게」)이 있다(카드 AU) · 지시문에 code_graph·read_code 안내가 있다(카드 AZ) · 대본이 `str` 조각을 주면 `delta`가 `note`/`answer` 앞에 그 순서로 나오고 `progress`에는 안 들어간다(카드 AW) · 대본 [도구 2번 → 답] → 이벤트 순서가 `start·note·read·note·read·answer`이고 `context_item_ids`가 read 순서·중복 접힘 · 대본이 도구만 9번 → 8번째 뒤 마무리 호출이 `tool_choice="none"`이고 그 뒤 호출이 없다 · `monotonic`을 패치해 120초 → 같은 마무리 · 마무리도 답이 비면 `llm-unavailable` · 시작 맥락에 항목 ID·이름은 있고 **본문은 없다** · `item_id=None`이면 「지금 보는 항목」 줄이 없다 · 없는 `item_id` → `not-found`가 `start` 전 · **DB에 아무것도 안 쓴다**(호출 전후 행 수가 같다) · `history`가 상한을 넘으면 뒤에서부터 잘린다 · usage 로그 한 줄에 calls·tokens·elapsed가 있고 본문이 없다 · 키가 비면 `SpecService`를 부르기도 전에 막힌다 · **MINISPEC이 빈 프로젝트**에서 물으면 `item_chain`의 빈 단계로 「아직 안 쓰였다」고 답할 재료를 받는다

---

#### queries.ask_tool 모델이 부른 읽기 도구 하나를 실행한다

**시그니처** `async def ask_tool(name: str, args: dict, code: str, user: User, conversation_id: int) -> ToolResult`

근거: [[SYNC-PRD-001#R11]] · [[SYNC-UC-001#UC-H19]] · [[SYNC-API-002]] 3장(같은 이름·같은 모양) · [[SYNC-INFRA-001]] 5.3 첨부

**입력** `name` 도구 이름 · `args` 모델이 준 인자 · `code` 지금 열린 문서의 프로젝트 · `user` 묻는 사람 · `conversation_id` 이 대화 — `read_attachment`가 이 대화의 첨부만 읽게

**도구 여덟** — 전부 읽기. 쓰기 도구는 어떤 경우에도 없다([[SYNC-PRD-001]] 2장 비목표). 모든 도구에 필수 인자 `reason: str`(무엇을 왜 읽는지 한 줄 — 진행 줄이 된다. 모델이 `tool_calls`와 함께 본문을 비우는 일이 잦아 인자로 못 박는다)

| 도구 | 인자 | 부르는 것 | 돌려주는 JSON | target |
|---|---|---|---|---|
| `get_item` | `doc_id, item_id, reason` | [[SYNC-MS-002#SpecService.get_item]] | `{doc_id, item_id, display_name, doc_status, doc_version_no, body}` — [[SYNC-API-002#get_item]]과 같은 키 | `DOC#ITEM` |
| `get_references` | `doc_id, item_id, reason` | [[#queries.item_references_view]] + 문서 참조는 `SpecService.get_document(doc_id).status`로 상태 보강 | `{upstream: [{id, name} \| {doc_id, title, status} \| {raw_target, note: "아직 없음"}], downstream: [{id, name} \| {doc_id, title}]}` — 하위의 `{doc_id, title}`은 항목 밖에서 건 참조의 출발 문서(#160) | `DOC#ITEM` |
| `item_chain` | `doc_id, item_id, reason` | [[#queries.item_chain]] | `{item, rows: [{stage, doc_type, items: [{id, name, role, status}]}]}` — **빈 단계도 그대로**(어느 단계가 안 쓰였는지의 근거) | `DOC#ITEM` |
| `list_documents` | `reason` | [[#queries.document_list]] + [[SYNC-MS-002#SpecService.describe_documents]](제목) | `[{doc_id, stage, doc_type, title, status, version_no}]` | 없음 |
| `get_document` | `doc_id, reason` | [[SYNC-MS-002#SpecService.get_document]] + 제목 | `{doc_id, title, status, version_no, items: [{item_id, display_name}], body}` 전문 | `DOC` |
| `read_attachment` | `attachment_id, reason` | [[SYNC-MS-010#ConversationService.attachment_text]] | `{attachment_id, name, mime, text}` — 글자 파일은 본문 그대로, PDF는 뽑은 글자. 이 대화의 첨부가 아니거나 이미지면 `{"error": "없음"}`(이미지엔 `hint`: 「이미지는 붙인 질문에 이미 보였다」) | `첨부:{name}` |
| `code_graph` | `doc_id, item_id, reason` | [[#queries.code_view]] | `{graph: {commit, source, error}, item, is_ms, missing, function: {qual, file, line, end, calls: [{id, status, qual, file, line}], callers: [{id, qual, file, line}]}, functions: [{id, qual, file, line, same, code_only, spec_only}]}` — [[SYNC-API-002#get_code_graph]]과 같은 뜻. 그래프가 없으면 `{"error": "코드 그래프 없음"}`(카드 AZ) | `코드:DOC#ITEM` |
| `read_code` | `target, reason` — `target`은 MINISPEC 항목 ID(`문서#항목`) · 함수 이름(`Class.fn`) · 파일 경로(`path` 또는 `path:시작-끝`) | [[SYNC-MS-011#CodeGraphService.read]] — 항목 ID는 [[SYNC-MS-011#codegraph.compare]]로 함수 자리를, 함수 이름은 그래프의 `qual`로 찾는다 | `{path, start, end, commit, truncated, text}` — `text`는 줄마다 `번호: 내용`. 300줄까지 · 비밀 꼴·저장소 밖·없는 파일·모르는 함수는 `{"error": "없음", hint}`(카드 AZ) | `코드:path:시작-끝` |

**처리**
1. `name`이 여섯 밖 → `ToolResult(None, {"error": "없는 도구"})` · 필수 인자가 빠짐 → `{"error": "인자 X가 없다"}`
2. `args["doc_id"]`가 있고 `doc_id.split("-")[0] != code` → `{"error": "없음", "doc_id": …}` — 소유한 다른 프로젝트여도 같다. 이 대화는 같은 프로젝트 안이다
3. 세션을 열고 `ProjectService.get_owned(code, user)` → 위 표의 함수 → JSON 조립 → 세션 닫기
4. `NotFound`·`ItemDeleted`는 **던지지 않고** `{"error": "없음", …}` 텍스트로 — 모델이 되짚는다. `NotFound`에는 `hint`를 붙인다: 「이 문서에 그 항목이 없다. 다른 문서의 항목일 수 있다 — 보고 있는 항목을 get_item으로 읽어 본문의 참조 링크(문서ID#항목ID)에서 문서 ID를 확인하거나, get_references로 실제 위치를 찾아라」 — 모델이 항목 ID만으로 지금 문서를 짚었다가 포기하던 것을 막는다(#110). 그 밖의 예외는 전파(`error` 이벤트)
5. `→ ToolResult(target, json.dumps(결과, ensure_ascii=False))`

**결과 형식** JSON 문자열. MCP 도구([[SYNC-API-002]])와 같은 모양이라 에이전트가 이미 보는 것과 같고, 마크다운 본문을 안에 그대로 담아도 경계가 안 흐트러진다. 크기 상한 없음(사용자 결정) — 큰 문서 전문이 맥락을 넘기면 모델이 400을 주고 `llm-unavailable`로 접힌다

**`_ASK_TOOLS`** — `ToolSpec` 여덟. `description`은 [[SYNC-API-002]] 3장의 도구 설명 문장을 가져다 쓴다(`read_attachment`는 MCP에 없다 — 「이 대화에 붙인 글자·PDF 첨부의 글자를 읽는다. 시작 맥락의 [첨부] 줄에 있는 id로」. `code_graph`는 `get_code_graph`의 문장이고, `read_code`도 MCP에 없다 — 「그래프를 만든 커밋의 코드를 읽는다. target은 MINISPEC 항목 ID(문서ID#항목ID) · 함수 이름(Class.fn) · 파일 경로(path 또는 path:시작-끝). 300줄까지, 줄마다 번호가 붙는다. 키·인증서 같은 비밀 파일은 읽을 수 없다.」). `parameters`는 JSON Schema `{type: object, properties: {doc_id: {type: string}, item_id: {type: string}, attachment_id: {type: integer}, reason: {type: string}}, required: [...]}` — 도구마다 위 표의 인자가 `required`

**출력** `ToolResult(target, text)` — `target`은 「본 것」에 실을 `DOC#ITEM`·`DOC`, 목록 도구는 `None`

**예외** 남의 프로젝트 → `not-found`(전파) · 도구 안의 없음·삭제·인자 오류는 예외가 아니라 결과

**테스트 관점(추가, #110)** 없는 항목의 「없음」에 `hint`가 있다 · 지시문에 「먼저 보고 있는 항목을 get_item으로 읽는다」가 있다

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] [[SYNC-MS-002#SpecService.get_document]] [[SYNC-MS-002#SpecService.describe_documents]] · [[#queries.item_references_view]] [[#queries.item_chain]] [[#queries.document_list]] · [[#queries.code_view]] · [[SYNC-MS-011#CodeGraphService.get]] · [[SYNC-MS-011#codegraph.compare]] · [[SYNC-MS-011#CodeGraphService.read]] · [[SYNC-MS-010#ConversationService.attachment_text]] · [[#queries.document_view]] · [[#queries.item_view]]

**호출되는 것** [[#queries.ask_item]] 5단계

**테스트 관점** `code_graph` — 그래프가 없으면 error, 있으면 function·calls(카드 AZ) · `read_code` 세 꼴(항목 ID·함수 이름·`경로:시작-끝`)이 같은 줄을 읽고 줄 번호가 붙는다 · `read_code(".env")` → 없음 · 다섯 도구 각각 돌려주는 JSON의 키 집합 · 다른 프로젝트 문서 ID(소유해도) → `없음` 텍스트, 예외 아님 · 남의 프로젝트 → `not-found` 전파 · 끊어진 참조 → `note: "아직 없음"` · `item_chain` 빈 단계 행 유지 · `list_documents`에 제목이 있다 · `reason` 빠짐 → `인자 reason이 없다` · 없는 도구 이름 → `없는 도구` · **DB에 아무것도 안 쓴다**

---
#### queries.project_summary 프로젝트 목록 + 단계 11칸 + 건수

**시그니처** `async def project_summary(user: User) -> list[ProjectSummary]`

근거: [[SYNC-SEQ-001#SEQ-9]] · [[SYNC-UC-001#UC-H14]] 1~2 · [[SYNC-API-001#GET/api/projects]] · [[SYNC-PRD-001#R12]]

**처리**
1. `projects = ProjectService.list_owned(user)` — 내가 소유한 것만. 없으면 빈 목록(UI-2 빈 상태)
2. 프로젝트마다:
   - `docs = SpecService.list_by_project(project_id)`
   - **단계 11칸**: 단계 `1..11`마다 `stage_docs = [d for d in docs if d.stage == n]`
     - if 비어 있음 → `status=None, doc_count=0`
     - else → `status = min(stage_docs.status, key=순서 draft<approved)` (UC-H14 1a) — 둘뿐이라 「하나라도 초안이면 초안」이다, `doc_count`
     - `gate_warning` = `doc_count > 0 and any(앞 단계 k<n 중 status != approved and doc_count > 0)` (1b)
     - `broken_count` = 그 단계 문서들의 미존재 참조 합 (UI-2 요소 2.2 테두리). `per_doc = ReferenceService.count_missing_by_document([d.id for d in docs])`를 **프로젝트당 한 번** 부르고 단계별로 더한다 — 단계마다 부르면 같은 프로젝트를 11번 훑는다
   - `std_docs = [d for d in docs if d.doc_type == STD]`
   - `counts.broken_ref = sum(per_doc.values())` — 위에서 뜬 것을 다시 쓴다
   - `counts.convention_errors = sum(d.has_convention_error for d in docs)` · `counts.incomplete = sum(bool(d.incomplete_warnings))`
   - `updated_at = max(d.updated_at)`
   - `storage = repository.storage` · `remote_url = repository.remote_url if storage == github else None` — 서버 저장소의 서버 안 경로는 밖으로 안 낸다([[SYNC-PRD-001#R14]])
3. `→` 정렬 `updated_at desc`

**출력** `ProjectSummary[]`. `stages`는 항상 11개. `counts`는 세 칸 — `broken_ref`·`convention_errors`·`incomplete`

**호출하는 것** [[SYNC-MS-001#ProjectService.list_owned]] · `SpecService.list_by_project` · [[SYNC-MS-003#ReferenceService.count_missing_by_document]]

**테스트 관점** 문서 없는 프로젝트 → 11칸 전부 null · 승인 2 + 초안 1인 단계 → `draft` · 3단계가 초안인데 4단계에 문서 → 4단계 `gate_warning=True` · STD 문서는 11칸에 안 세고 `std_docs`에 · 한 단계에 미존재 참조 있는 문서 둘 → 그 단계 `broken_count`가 둘의 합 · `counts.broken_ref`가 전 단계 합과 같다 · **두 사람이 각자 등록 → 각자 자기 것만** · 등록한 적 없는 사람 → 빈 목록 · **서버 저장 프로젝트 → `storage=server`, `remote_url=None`**

---

#### queries.project_detail + 문서 목록 + 최근 변경

**시그니처** `async def project_detail(code: str, user: User) -> ProjectDetail`

근거: [[SYNC-SEQ-001#SEQ-9]] · [[SYNC-API-001#GET/api/projects/{code}]]

**처리**
1. `project = ProjectService.get_owned(code, user)` · if 없거나 남의 것 → `! not-found`
2. `summary = project_summary(user)`에서 이 프로젝트 것 (단계·건수 계산 공유)
3. `docs = document_list(code, user)` (문서별 건수 포함)
4. `recent = SpecService.recent_changes(project_id, 10)`
5. `repo = project.repository` — `last_processed_commit`·`behind_by`를 **DB에서 그대로 읽는다.** `git fetch`를 돌리지 않는다(UI-4 요소 7)
6. `→ ProjectDetail(summary, remote_url, docs, recent_changes=recent, last_processed_commit, behind_by)` — `storage`·`remote_url`은 요약(2)의 것 그대로. 서버 저장이면 `remote_url=None`

**호출하는 것** [[#queries.project_summary]] [[#queries.document_list]] · `SpecService.recent_changes` · [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-006#AccountService.users_by_ids]]

**테스트 관점** 남의 프로젝트 → `not-found`(문서 없음과 같은 모양) · 폴링이 `behind_by=2`를 적어 두면 응답도 2 · 아직 한 번도 못 받아봤으면 `behind_by=null` · 이 함수가 `git.fetch`를 부르지 않는다

---

#### queries.document_list 문서 목록 + 문서별 건수

**시그니처** `async def document_list(code: str, user: User, stage: int | None = None, status: DocStatus | None = None) -> list[DocumentSummary]`

근거: [[SYNC-SEQ-001#SEQ-10]] · [[SYNC-API-001#GET/api/projects/{code}/docs]] · [[SYNC-API-002#list_documents]]

**처리**
1. `project = ProjectService.get_owned(code, user)`
2. `docs = SpecService.list_by_project(project_id, stage, status)`
3. `ids = [d.id for d in docs]` · `missing = ReferenceService.count_missing_by_document(ids)` — **쿼리 한 번** (N+1 금지)
4. 문서마다 `counts = {broken_ref ← missing[id]}`, 없으면 0
5. `→ docs`. MCP `list_documents`는 이걸 `stages`로 다시 묶는다(단계마다 `docs[]`)

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.list_by_project` · [[SYNC-MS-003#ReferenceService.count_missing_by_document]] · [[SYNC-MS-006#AccountService.users_by_ids]]

**테스트 관점** 남의 프로젝트 → `not-found` · 문서 30개 → DB 쿼리 2번(문서·참조) · 미존재 참조 없는 문서 → `broken_ref=0`

---

#### queries.document_view 문서 + 미존재 참조 + 이웃

**시그니처** `async def document_view(doc_id: str, user: User) -> Document`

근거: [[SYNC-SEQ-001#SEQ-11]] · [[SYNC-UC-001#UC-H2]] · [[SYNC-API-001#GET/api/docs/{docId}]] · [[SYNC-API-002#get_document]]

**처리**
0. `project = ProjectService.get_owned(doc_id.split("-")[0], user)` — **본문을 읽기 전에.** v1은 5a에서 브레드크럼 이름을 얻으려 `get`을 불렀는데 그때는 이미 본문을 다 읽은 뒤였다
1. `doc = SpecService.get_document(doc_id)` · if 없음 → `! not-found` (전파)
2~3. 없음 — 항목 플래그를 붙이던 자리. 카드 V에서 걷어냈다
4. `doc.prev_doc_id, doc.next_doc_id = SpecService.neighbors(doc_id)`
4a. `doc.missing_refs = 중복 접은 [e.raw_target for e in ReferenceService.upstream_of_document(doc.id, include_missing=True) if e.is_missing]` — 유저용 탭이 링크를 회색 `?`로 그리는 근거이고, **UI-5 미완성 배너(4a)가 보여주는 값**이다. 한 문서 안 여러 항목이 같은 대상을 가리키면 같은 `raw_target`이 여러 번 오므로 접는다. **완료 전환 검사가 보는 값과 같아야 한다**([[SYNC-MS-007#pipeline.change_status]] 2단계) — 한쪽만 막거나 한쪽만 보여주면 사람이 이유 없이 막힌다
5. `names = AccountService.users_by_ids([doc.last_author.user_id, doc.last_author.instructed_by_id])` → API `Author{kind, user: UserRef, instructed_by, via}`로 채움
5a. `doc.project_name = project.name` (0단계의 것) — 브레드크럼 첫 조각(UI-5 요소 1)은 코드가 아니라 이름이다
6. `→ doc`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.get_document` · [[SYNC-MS-003#ReferenceService.upstream_of_document]] · `SpecService.neighbors` · `AccountService.users_by_ids`

**테스트 관점** **남의 프로젝트 문서 → `not-found`(project)이고 본문이 응답에 없다** · 미존재 참조 있는 문서 → `missing_refs`에 그 대상, 같은 대상 둘이면 하나 · 규약 오류 문서 → 정상 반환 · 첫 단계 문서 → `prev_doc_id=None`

---

#### queries.item_view 항목 블록

**시그니처** `async def item_view(doc_id: str, item_id: str, user: User) -> ItemView`

**처리** `ProjectService.get_owned(doc_id.split("-")[0], user)` (남의 것 → `not-found`) · `v = SpecService.get_item(doc_id, item_id)` (없음·삭제 예외 전파) · `→ v`. 소유 검사 말고는 `SpecService`를 그대로 넘기는 자리다 — 라우터·MCP가 `queries`만 보게 하는 대칭 때문에 둔다

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-002#SpecService.get_item]]

---

#### queries.item_references_view 상위·하위 참조 + 표시 이름

**시그니처** `async def item_references_view(doc_id: str, item_id: str, user: User) -> ItemReferences`

근거: [[SYNC-SEQ-001#SEQ-13]] · [[SYNC-UC-001#UC-H3]] · [[SYNC-UC-001#UC-A4]] · [[SYNC-API-002#get_references]]

**처리**
0. `ProjectService.get_owned(doc_id.split("-")[0], user)` — 남의 것 → `not-found`
1. `pk = SpecService.resolve_item(doc_id, item_id)` · 예외 전파 (`not-found` · `item-deleted`)
2. `up = ReferenceService.upstream(pk)` · `down = ReferenceService.downstream(pk)` — 이 항목을 가리키는 참조 하나하나. 어디서 걸었든(항목 블록 안이든, 절 본문·표처럼 항목 밖이든) 다 든다. **문서 전체를 가리킨 참조는 항목의 하위가 아니다** — 전에는 그 문서 모든 항목 아래에 섞여 카드·관계도와 수가 달랐다(#160). 화면은 그것을 `GET …/downstream`의 `(문서)`로 따로 보인다([[SYNC-UI-002#UI-5]] 8.10)
3. `need = {e.to_item_pk for e in up} ∪ {e.from_item_pk for e in down}` · `names = SpecService.describe_items(need)` — **한 번**. 문서 쪽(상위의 `to_document_id`·하위의 출발 항목 없는 `from_document_id`)은 `SpecService.describe_documents`로 따로
4. `RefEdge` → `ItemRef`: 상위는 `to_item_pk`가 있으면 `names[pk]` · `to_document_id`만 있으면 `ItemRef(doc_id, item_id=None, display_name=문서 제목)` · `is_missing`이면 `ItemRef(raw_target만, is_missing=True)`. 하위는 `from_item_pk`가 있으면 `names[pk]` · 없으면(항목 밖) **출발 문서** `ItemRef(doc_id, item_id=None, display_name=문서 제목)` — 전에는 건너뛰어 패널이 「고립 항목」이라 했다(#160). 항목·문서 id 공간이 겹치므로 따로 · `raw_target`은 둘 다 싣는다
5. `→ ItemReferences(doc_id, item_id, upstream, downstream)`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.resolve_item` `SpecService.describe_items` `SpecService.describe_documents` · `ReferenceService.upstream` `ReferenceService.downstream`

**테스트 관점** 남의 프로젝트 → `not-found` · 미존재 참조 → `upstream`에 `is_missing=True, raw_target` · 문서 전체를 가리킨 참조 → `upstream`에 `item_id=None` · 항목 밖(절 본문·표)에서 이 항목을 건 참조 → `downstream`에 출발 문서(`item_id=None`, 문서 제목) · 이 문서 전체를 가리킨 참조(`[[문서]]`)는 어느 항목의 `downstream`에도 없다(#160) · 고립 항목 → 둘 다 빈 목록

---

#### queries.graph_view 노드·간선

**시그니처** `async def graph_view(code: str, user: User, scope: GraphScope = GraphScope.all) -> Graph`

근거: [[SYNC-SEQ-001#SEQ-14]] · [[SYNC-UC-001#UC-H4]] · [[SYNC-API-001#GET/api/projects/{code}/graph]]

**처리**
1. `project = ProjectService.get_owned(code, user)` (남의 것 → `not-found`)
2. `nodes = SpecService.list_items_by_project(project_id)` — 항목 + 문서 노드(`item_id=None`). 단계는 항상 11개 다 나온다
3. 범위로 거른다 (UC-H4 2b) — `approved`면 **문서 상태가 `approved`인 문서의 항목**만. `all`이면 그대로. 범위는 이 둘뿐이다
4. `pks = {n.pk}` · `edges = ReferenceService.references_among(pks, include_document_targets=True)`
5. **끝점이 `pks` 밖인 간선은 버린다.** 범위를 좁혀 대상 노드가 빠진 것과, 대상 항목이 애초에 없는 것은 다르다 — 앞은 안 그리고 뒤만 `to=None`으로 그린다
6. `isolated = {n.pk} - {e.from} - {e.to}` (UC-H4 2a)
7. 노드 `id = f"{doc_id}#{item_id}"` (문서 노드는 `doc_id`만) · 노드에 `stage`(1~11)
8. `→ Graph(nodes, edges, project_name=project.name)`. **좌표 없음** — 열 안 순서 정렬은 브라우저가 한다(UI-002 UI-8 규칙). `project_name`은 브레드크럼용(UI-8 요소 1)

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.list_items_by_project` · `ReferenceService.references_among` · [[SYNC-MS-002#SpecService.list_by_project]]

**테스트 관점** `all` → 항목 수 = 노드 수(문서 노드 포함) · `approved` → 완료 문서의 항목만, 그 밖으로 나가는 간선은 없음 · 참조 없는 항목 → `isolated=True` · **범위 밖 대상 간선이 미존재 참조로 새지 않는다**

---

#### queries.item_chain 항목의 11단계 체인

**시그니처** `async def item_chain(doc_id: str, item_id: str, user: User) -> ItemChain`

근거: [[SYNC-UC-001#UC-H4]] 기본 흐름 3 · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/chain]] · [[SYNC-UI-001#UI-15]]

**처리**
0. `ProjectService.get_owned(doc_id.split("-")[0], user)` — 남의 것 → `not-found`
1. `pk = SpecService.resolve_item(doc_id, item_id)` · 없으면 `! not-found`
2. `ups = 폐포(pk, ReferenceService.upstream)` — 너비 우선. 방문 표시로 사이클을 멈춘다. 자기 자신은 뺀다
3. `downs = 폐포(pk, ReferenceService.downstream)` — 같은 방식, 반대 방향
4. `SpecService.describe_items(ups | downs | {pk})`로 문서·제목·상태를 한 번에 채운다
5. 항목마다 **역할을 폐포 소속으로 정한다** — `ups`에 있으면 `upstream`, `downs`면 `downstream`, 자기면 `self`. **단계 번호로 정하지 않는다**: 되돌아오는 참조가 있으면 근거가 더 오른쪽 단계에 놓여 `downstream`으로 잘못 적힌다
6. 11단계로 나눠 담는다. **항목이 없는 단계도 빈 배열로 남긴다** — 체인이 어디서 끊겼는지가 이 화면의 목적이다
7. `→ ItemChain(item, upstream_count, downstream_count, rows[11])`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.resolve_item` `SpecService.describe_items` `SpecService.get_document` · `ReferenceService.upstream` `ReferenceService.downstream`

**테스트 관점** 남의 프로젝트 → `not-found` · 직접 참조만 있는 항목 → 상위 1·하위 0 · 3단계 건너 이어진 항목이 폐포에 들어옴 · 사이클이 있어도 안 멈춰 있음 · 항목 없는 단계도 행이 옴(길이 항상 11) · 되돌아오는 참조의 상위가 `upstream`으로 적힘

---

#### queries.diff_with_impact diff + 하위 건수

**시그니처** `async def diff_with_impact(doc_id: str, from_no: int, to_no: int, user: User) -> Diff`

근거: [[SYNC-SEQ-001#SEQ-15]] · [[SYNC-UC-001#UC-H6]] 3a

**처리**
0. `ProjectService.get_owned(doc_id.split("-")[0], user)` — 남의 것 → `not-found`
1. `d = SpecService.diff(doc_id, from_no, to_no)`
2. `ids = [h.item_id for h in d.hunks if h.item_id]` · `pks = SpecService.resolve_items(doc_id, ids)` (없는 건 건너뜀)
3. `counts = ReferenceService.count_downstream(pks)`
4. hunk마다 `downstream_count = counts.get(pk, 0)` · 새로 생긴 항목(pk 없음)은 0
5. `→ d`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.diff` `SpecService.resolve_items` `SpecService.describe_items` · `ReferenceService.count_downstream`

---

#### queries.project_items 프로젝트 끊어진 참조·오류·미완성 목록

**시그니처** `async def project_items(code: str, kind: str, user: User) -> list`

근거: [[SYNC-SEQ-001#SEQ-18]] · [[SYNC-UC-001#UC-H14]] 4 · [[SYNC-API-001#GET/api/projects/{code}/flags]]

**처리**
1. `project = ProjectService.get_owned(code, user)` (남의 것 → `not-found`)
2. if `kind == broken_ref` → `edges = ReferenceService.missing_in_project(project_id)` → `describe_items`·`describe_documents`로 출발점 이름을 채워 `BrokenRefSummary[]`(`type="broken_ref"` · `source: ItemRef` — 항목 밖 참조면 `item_id=None` · `raw_target`) — 항목 밖(절 본문·frontmatter upstream)의 참조는 `item_id=None`
3. if `kind == convention_errors` → `SpecService.list_by_project(project_id, has_convention_error=True)` → `DocumentSummary[]`
4. if `kind == incomplete` → `list_by_project` 중 `incomplete_warnings` 있는 것
5. else → `! ValueError` — 라우터가 `kind`를 enum으로 검증해 422를 내므로 여기까지 오지 않는다. 방어용

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-003#ReferenceService.missing_in_project]] · `SpecService.describe_items` `SpecService.describe_documents` `SpecService.list_by_project`

**테스트 관점** `broken_ref` → 미존재 참조마다 한 행, 출발 항목 이름이 있다 · 항목 밖 참조 → `item_id=None` · 상대가 들어오면 그 행이 사라진다 · 모르는 kind → `ValueError`

---

#### queries.downstream_view 이 문서를 참조하는 것

**시그니처** `async def downstream_view(doc_id: str, user: User) -> DownstreamView`

근거: [[SYNC-API-001#GET/api/docs/{docId}/downstream]] · [[SYNC-STD-002]] V-PRD 추적표

**처리**
0. `ProjectService.get_owned(doc_id.split("-")[0], user)` — 남의 것 → `not-found`
1. `doc = SpecService.get_document(doc_id)` · `pks = SpecService.item_pks(doc.id)`
2. `edges = ReferenceService.references_among(set(pks.values()) ∪ {문서}, include_document_targets=True)`에서 `to`가 이 문서인 것만
3. `from` pk를 `describe_items`로, 문서를 `describe_documents`로
4. `by_item = {item_id: [ItemRef…]}` (문서 단위는 키 `"(문서)"`) · `by_document = [{doc_id, title, items: [이 문서 항목 ID들]}]` 문서 단계순
5. `→ DownstreamView(by_item, by_document)`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · `SpecService.get_document` `SpecService.item_pks` `SpecService.describe_items` `SpecService.describe_documents` · `ReferenceService.references_among`

---


#### queries.code_view 코드 탭 — 항목의 코드 대조

**시그니처** `async def code_view(doc_id: str, item_id: str | None, user: User) -> CodeView`

근거: [[SYNC-UC-001#UC-H20]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code]] · [[SYNC-API-001#GET/api/docs/{docId}/code]] · [[SYNC-SEQ-001#SEQ-27]] · 사용자 결정 2026-09-30(모든 문서에 코드 탭, 다른 항목은 하위 체인)

**처리**
0. `project = ProjectService.get_owned(doc_id.split("-")[0], user)` — 남의 것이면 `! not-found` · `doc = SpecService.get_document(doc_id)` · if `item_id` → `SpecService.resolve_item(doc_id, item_id)`(없으면 `! not-found`)
1. `row = CodeGraphService.get(project.id)` · if None → `CodeView(graph=None, …, functions=[])` (UC-H20 1a)
2. `items` = 프로젝트의 MINISPEC 문서마다(`SpecService.list_by_project(stage=MS)`) `SpecService.get_document` → `SpecService.item_blocks(본문)` → `(문서ID#항목ID, 블록)` · `spec = codegraph.spec_calls(items)` · `diffs = codegraph.compare(row.graph, spec)`
3. if MINISPEC 문서이고 `item_id` → 그 항목의 diff로 `CodeFunction` — `calls`: 코드만 → 명세만 → 같음 순, 줄마다 `CodeRef`(상대 항목의 함수가 있으면 qual·파일·줄) · `callers`: 다른 항목의 diff에서 이 항목이 같음·코드만에 든 것 · 함수가 없으면 `function=None, missing=True`(2b)
4. if MINISPEC가 아닌 문서이고 `item_id` → `chain = `[[#queries.item_chain]]`(doc_id, item_id, user)` · 하위(`downstream`)이면서 MINISPEC 단계인 항목 → `functions = [CodeBrief]`(어긋남 수)
5. if MINISPEC 문서이고 `item_id` 없음 → 그 문서 항목 전부의 `CodeBrief`(블록 순서)
6. `→ CodeView(graph=머리(row), doc_id, item_id, is_ms, missing, function, functions)`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-002#SpecService.get_document]] · [[SYNC-MS-002#SpecService.resolve_item]] · [[SYNC-MS-002#SpecService.list_by_project]] · [[SYNC-MS-002#SpecService.item_blocks]] · [[SYNC-MS-011#CodeGraphService.get]] · [[SYNC-MS-011#codegraph.spec_calls]] · [[SYNC-MS-011#codegraph.compare]] · [[#queries.item_chain]]

**테스트 관점** 그래프 없음 → `graph` None · MINISPEC 항목 → `calls`가 코드만·명세만·같음 순이고 `callers`가 있다 · 코드에 없는 MINISPEC 항목 → `missing` · PRD 항목 → 하위 체인의 MINISPEC 함수와 어긋남 수 · MINISPEC 문서 단위 → 그 문서 함수 전부 · 남의 프로젝트 → `not-found` · 명세의 「호출하는 것」만 바꾸면 그래프를 안 바꿔도 결과가 바뀐다

---

#### queries.code_calls 관계도 코드 호출

**시그니처** `async def code_calls(code: str, user: User) -> CodeCalls`

근거: [[SYNC-UC-001#UC-H20]] · [[SYNC-API-001#GET/api/projects/{code}/code-calls]] · UI-8 2.6

**처리**
0. `project = ProjectService.get_owned(code, user)`
1. `row = CodeGraphService.get(project.id)` · if None → `CodeCalls(graph=None, edges=[])`
2. `code_view` 2단계와 같이 `spec`·`diffs`
3. `edges` = diff마다 같음·코드만·명세만 각각 `CodeCallEdge(from_=diff.ms_id, to=상대, status)` — MINISPEC 항목끼리만
4. `→ CodeCalls(graph=머리(row), edges)`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-011#CodeGraphService.get]] · [[SYNC-MS-002#SpecService.list_by_project]] · [[SYNC-MS-002#SpecService.get_document]] · [[SYNC-MS-002#SpecService.item_blocks]] · [[SYNC-MS-011#codegraph.spec_calls]] · [[SYNC-MS-011#codegraph.compare]]

**테스트 관점** 선이 셋으로 갈린다 · 그래프 없음 → 빈 선 · 남의 프로젝트 → `not-found`

---

#### queries.code_nodes 코드 그래프 노드 — 함수 전부·커뮤니티·대조 상태

**시그니처** `async def code_nodes(code: str, user: User) -> CodeNodes`

근거: [[SYNC-UC-001#UC-H20]] 기본 흐름 5 · [[SYNC-API-001#GET/api/projects/{code}/code-graph]] · [[SYNC-SEQ-001#SEQ-31]] · UI-17 · 사용자 결정 2026-10-01(함수·커뮤니티 노드, 처음은 접힘)

**처리**
0. `project = ProjectService.get_owned(code, user)`
1. `row = CodeGraphService.get(project.id)` · if None → `CodeNodes(graph=None, communities=[], functions=[], calls=[])`
2. `code_view` 2단계와 같이 `spec`·`diffs` — `by_key = {d.function: d for d in diffs if d.function}`
3. 함수마다 `CodeNode(key, name, qual, file, line, community=f.get("community"), ms, status)` — `d = by_key.get(key)` · 없으면 `ms`·`status` None · `status` = if `d.code_only` → `code_only` · elif `d.spec_only` → `spec_only` · else `same`
4. `communities = [CodeCommunity(id, label, size) for c in row.graph.get("communities", [])]` — 옛 그래프는 빈 목록 · `calls = [[a, b] for a, b, _ in row.graph["calls"]]`
5. `→ CodeNodes(graph=머리(row), communities, functions, calls)`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-011#CodeGraphService.get]] · [[SYNC-MS-002#SpecService.list_by_project]] · [[SYNC-MS-002#SpecService.get_document]] · [[SYNC-MS-002#SpecService.item_blocks]] · [[SYNC-MS-011#codegraph.spec_calls]] · [[SYNC-MS-011#codegraph.compare]]

**테스트 관점** 항목 있는 함수에 `ms`·`status`(코드만 > 명세만 > 같음) · 도우미는 `ms` None · 커뮤니티 목록과 함수의 `community`가 그래프 그대로 · 옛 그래프(`communities` 없음) → 빈 목록, `community` None · 그래프 없음 → `graph` None · 남의 프로젝트 → `not-found`

---

#### queries.code_source 코드 보기

**시그니처** `async def code_source(doc_id: str, item_id: str, user: User) -> CodeText`

근거: [[SYNC-UC-001#UC-H20]] 기본 흐름 3 · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code/source]] · UI-5 8.21

**처리**
0. `project = ProjectService.get_owned(…)` · `SpecService.resolve_item(doc_id, item_id)`
1. `row = CodeGraphService.get(project.id)` · if None → `! not-found {resource: code_graph}`
2. `d = codegraph.compare(row.graph, {항목: ∅})[0]` — 그 항목의 함수 자리(docstring ID 먼저, 없으면 이름) · if `d.function` None → `! not-found {resource: function}`
3. `start = 함수.line` · `end = 함수.end` — 없으면(파이썬 밖) 같은 파일 다음 함수 앞 줄, 그것도 없으면 `start + 59`
4. `→ `[[SYNC-MS-011#CodeGraphService.read]]`(project.id, workdir, 함수.file, start, end)`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-002#SpecService.resolve_item]] · [[SYNC-MS-011#CodeGraphService.get]] · [[SYNC-MS-011#codegraph.compare]] · [[SYNC-MS-011#CodeGraphService.read]]

**테스트 관점** 함수 본문이 그래프 커밋의 것 · 파이썬 함수는 끝 줄까지 · 그래프 없음·함수 없음 → `not-found`

---

#### queries.code_text 코드 그래프의 코드 — 파일·줄로

**시그니처** `async def code_text(code: str, file: str, line: int, user: User) -> CodeText`

근거: [[SYNC-UC-001#UC-H20]] 기본 흐름 5, 확장 5c · [[SYNC-API-001#GET/api/projects/{code}/code/source]] · UI-17 4.6 · 사용자 결정 2026-10-01(그래프 옆에 코드 — 항목 없는 함수도 그 자리에서 읽는다, 카드 BF)

**처리**
0. `project = ProjectService.get_owned(code, user)`
1. `row = CodeGraphService.get(project.id)` · if None → `! not-found {resource: code_graph}`
2. `f = row.graph.functions 중 file == file and line == line` · 없으면 → `! not-found {resource: function}` — 자리는 그래프 커밋 기준이라 화면이 준 값이 그대로 맞는다
3. `start = f.line` · `end = f.end` — 없으면 같은 파일 다음 함수 앞 줄, 그것도 없으면 `start + 59`([[#queries.code_source]] 3과 같은 규칙, 같은 도우미)
4. `→ `[[SYNC-MS-011#CodeGraphService.read]]`(project.id, workdir, f.file, start, end)` — 비밀 꼴·그 커밋에 없는 파일은 `read`가 `not-found {resource: file}`

**호출하는 것** [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-011#CodeGraphService.get]] · [[SYNC-MS-011#CodeGraphService.read]]

**테스트 관점** 그래프의 함수를 파일·줄로 → 본문이 그래프 커밋의 것, 파이썬 함수는 끝 줄까지 · `end` 없는 함수는 다음 함수 앞 줄까지 · 없는 자리·그래프 없음·남의 것 → `not-found`

---

## 3. 미결사항

- [x] `graph_view` 범위 좁힘 시 "직접 이어진 것"을 몇 단계까지 (지금은 1) — 결정: **물음 자체가 없어졌다.** v1.2 디자인이 단계·문서로 좁히는 방식을 버리고 11단계를 열로 놓고 항상 다 그리되 전체·완료만으로 고르는 방식으로 바꿨다 ([[SYNC-UI-001#UI-8]] 7장 3). `graph_view`는 `stage`·`doc` 대신 `scope`를 받는다
