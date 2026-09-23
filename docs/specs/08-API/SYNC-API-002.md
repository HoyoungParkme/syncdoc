---
doc_id: SYNC-API-002
type: API
title: API 명세 MCP — 싱크독
status: draft
upstream: [SYNC-UC-001, SYNC-DOM-002, SYNC-DOM-003, SYNC-STD-001]
---

# API 명세 — MCP 도구: 싱크독 (SyncDoc)

---

## 0. 이 문서가 다루는 것

에이전트(Claude Code · Codex · Gemini 등)가 싱크독에 붙을 때 쓰는 MCP 도구 8개. 유스케이스 [[SYNC-UC-001#UC-A1]]~A6에 대응하고, 쓰기는 create/update 둘로 나눈다. `get_template`은 [[SYNC-STD-001]] 규약을 에이전트에게 전달하는 통로다.

**이 문서의 독자는 에이전트다.** 각 도구의 `description`이 에이전트가 도구를 고를 때 읽는 문장이므로, 언제 쓰고 언제 쓰지 않는지를 거기에 담는다.

## 1. 규칙

- 전송: MCP streamable HTTP. 엔드포인트 `POST /mcp`
- 인증: `Authorization: Bearer {토큰}`. 토큰은 사람이 웹 설정(UI-13)에서 발급한다. 요청은 발급자 계정으로 기록된다
- **발급자가 소유한 프로젝트만 열린다**([[SYNC-PRD-001#R12]]). 남의 프로젝트 코드나 문서 ID를 주면 `not-found {resource: "project"}` — 없는 것과 같다. `init_project`로 등록한 사람이 그 프로젝트의 소유자다
- 에러: 도구 결과의 `isError: true` + 본문에 [[SYNC-API-001]]과 **같은 problem+json**. 에이전트가 `type`으로 분기한다
- 모든 조회 결과에 문서 상태와 버전이 담긴다(PRD R9). 에이전트는 이걸로 확정 명세와 초안을 구분한다
- 상태 변경은 MCP에 **없다**. 초안인지 완료인지는 사람의 판단이라 웹에서만 한다([[SYNC-UC-001#UC-H8]] 주 액터 사람)
- 쓰기의 단위는 **문서 하나**다([[SYNC-STD-001]] 1.8). `create_document`·`update_document`의 결과에 `next_step`이 실린다 — 에이전트는 그것을 사람에게 그대로 전하고 멈춘다. DOM 셋의 순서(STD-001 2.6)만은 서버가 `precondition-unmet`으로 막는다

## 2. 도구 이름


| 도구 | 유스케이스 | 서비스 | 쓰기 |
|---|---|---|---|
| `init_project` | [[SYNC-UC-001#UC-A1]] | ProjectService.init_project | ○ |
| `list_documents` | [[SYNC-UC-001#UC-A5]] | ProjectService.get_stage_summary | |
| `get_document` | [[SYNC-UC-001#UC-A2]] | SpecService.get_document | |
| `get_item` | [[SYNC-UC-001#UC-A3]] | SpecService.get_item | |
| `get_references` | [[SYNC-UC-001#UC-A4]] | ReferenceService.upstream/downstream | |
| `create_document` | [[SYNC-UC-001#UC-A6]] (생성) | SpecService.create | ○ |
| `update_document` | [[SYNC-UC-001#UC-A6]] (수정) | SpecService.save | ○ |
| `delete_document` | [[SYNC-UC-001#UC-A7]] | pipeline.trash_document | ○ |
| `restore_document` | [[SYNC-UC-001#UC-A8]] | pipeline.restore_document | ○ |
| `get_template` | (STD-001 전달) | — 내장 템플릿 · 저장소 `STD/` 읽기 | |

---

## 3. 도구 정의

### init_project

```json
{
  "name": "init_project",
  "description": "GitHub 저장소를 싱크독 프로젝트로 등록한다. docs/specs/ 아래 11단계 디렉터리와 템플릿을 만들어 커밋한다. 새 프로젝트를 시작할 때 한 번만 부른다. 이미 등록된 저장소면 project-code-conflict, 저장소에 docs/specs/가 이미 있으면 existing-specs 에러가 나며 import_existing=true로 다시 부르면 기존 명세를 가져와 등록한다. **저장소가 아직 없으면 create_repo=true로 부른다** — 공개 저장소를 만들어 주고 이어서 등록까지 한다. 사람이 저장소를 만들어 달라고 했을 때만 이 인자를 붙인다.",
  "inputSchema": {
    "type": "object",
    "required": ["remote_url", "code", "name"],
    "properties": {
      "remote_url": { "type": "string", "format": "uri", "description": "GitHub 저장소 주소" },
      "code": { "type": "string", "pattern": "^[A-Z]{1,4}$", "description": "프로젝트 코드. 영문 대문자 4자 이내. 문서 ID 앞부분이 된다" },
      "name": { "type": "string", "maxLength": 100, "description": "표시 이름" },
      "import_existing": { "type": "boolean", "default": false, "description": "docs/specs/가 이미 있을 때 덮어쓰지 않고 가져와 등록" },
      "create_repo": { "type": "boolean", "default": false, "description": "저장소가 없으면 공개로 만든다. 이미 있으면 만들지 않는다" }
    }
  }
}
```

**결과**
```json
{ "code": "SYNC", "name": "싱크독", "remote_url": "...", "stages": [ { "stage": 1, "doc_type": "RFQ", "status": null, "doc_count": 0 }, "..." ] }
```

**에러**: `project-code-conflict`(2a), `project-code-invalid`(2b), `existing-specs`(3a, 확장 필드 `doc_count`), `push-failed`(4a). 등록한 토큰의 발급자가 소유자가 된다(1장)

---

### list_documents

```json
{
  "name": "list_documents",
  "description": "프로젝트의 11단계별 문서 목록과 각 문서의 상태·버전을 돌려준다. 프로젝트에 처음 붙었거나 어느 단계까지 채워졌는지 알아야 할 때 부른다. 문서 본문은 포함하지 않는다. 본문은 get_document로.",
  "inputSchema": {
    "type": "object",
    "required": ["project_code"],
    "properties": {
      "project_code": { "type": "string", "pattern": "^[A-Z]{1,4}$" },
      "stage": { "type": "integer", "minimum": 1, "maximum": 11, "description": "한 단계만 보려면" },
      "status": { "type": "string", "enum": ["draft", "approved"], "description": "특정 상태만 보려면. 예: 완료 문서만" }
    }
  }
}
```

**결과**
```json
{
  "project_code": "SYNC",
  "stages": [
    { "stage": 2, "doc_type": "PRD", "status": "approved", "doc_count": 1,
      "docs": [ { "doc_id": "SYNC-PRD-001", "status": "approved", "version_no": 7, "has_convention_error": false, "updated_at": "..." } ] },
    { "stage": 7, "doc_type": "UI", "status": null, "doc_count": 0, "docs": [] }
  ]
}
```

문서가 없는 단계는 `status: null`, `docs: []`([[SYNC-UC-001#UC-A5]] 2a).

**에러**: `not-found` — 발급자가 소유하지 않은 프로젝트(`resource: project`, 1장). 없는 프로젝트와 같은 답이다

---

### get_document

```json
{
  "name": "get_document",
  "description": "문서 원본 MD 전체와 상태·버전을 돌려준다. 명세를 근거로 작업하기 전에 부른다. 응답의 version_no를 기억했다가 update_document에 expected_version으로 보내야 한다. status가 approved가 아니면 확정 명세가 아니다. 본문 안 [[문서ID#항목ID]]는 다른 항목 참조이며 get_item으로 따라갈 수 있다.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id"],
    "properties": {
      "doc_id": { "type": "string", "description": "예: SYNC-PRD-001" }
    }
  }
}
```

**결과**
```json
{
  "doc_id": "SYNC-PRD-001", "doc_type": "PRD", "stage": 2,
  "status": "approved", "version_no": 7, "commit_hash": "a1b2c3d",
  "has_convention_error": false, "convention_error_detail": null,
  "last_author": { "kind": "agent", "user": "hoyoung-park", "instructed_by": "hoyoung-park", "via": "mcp" },
  "body": "---\ndoc_id: SYNC-PRD-001\n...",
  "items": [ { "item_id": "R1", "display_name": "에이전트용 원본과 사람용 뷰", "missing_refs": [] } ]
}
```

`items[].missing_refs`는 그 항목에서 나간 참조 중 대상이 없는 것(`raw_target`). 에이전트가 "이 항목이 가리키는 것이 아직 안 쓰였거나 지워졌다"를 알 수 있다.

**에러**: `not-found`([[SYNC-UC-001#UC-A2]] 1a) — 문서가 없거나 **발급자가 소유하지 않은 프로젝트**(`resource: project`, 1장). 규약 오류 문서는 에러가 아니라 `has_convention_error: true`와 함께 정상 반환(2a).

---

### get_item

```json
{
  "name": "get_item",
  "description": "문서 안 항목 하나의 본문 블록과 소속 문서의 상태·버전을 돌려준다. get_document로 문서 전체를 받는 대신 필요한 항목만 볼 때, 또는 본문에서 발견한 [[문서ID#항목ID]] 참조를 따라갈 때 부른다. 삭제된 항목이면 item-deleted 에러에 삭제 시점이 담긴다.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id", "item_id"],
    "properties": {
      "doc_id": { "type": "string" },
      "item_id": { "type": "string", "description": "'#' 없이. 예: R12, [[SYNC-UC-001#UC-A6]], POST/orders" }
    }
  }
}
```

**결과**
```json
{
  "doc_id": "SYNC-PRD-001", "item_id": "R12", "display_name": "...",
  "doc_status": "approved", "doc_version_no": 7,
  "body": "#### R12 ...\n본문 블록만"
}
```

**에러**: `not-found`(문서 없음 · 남의 프로젝트는 `resource: project`), `item-deleted`(1a, 확장 필드 `deleted_at`), 문서는 있는데 항목이 없으면 `not-found` + 확장 필드 `available_items: [...]`(1b).

---

### get_references

```json
{
  "name": "get_references",
  "description": "항목의 상위 참조(이 항목이 근거로 삼은 것)와 하위 참조(이 항목을 근거로 삼은 것)를 나눠 돌려준다. 이 항목이 왜 있는지, 바꾸면 어디에 영향이 가는지 알아야 할 때 부른다. 목록만 주고 본문은 펼치지 않는다. 필요한 항목만 get_item으로 다시 요청한다. 빈 목록이면 고립 항목이다.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id", "item_id"],
    "properties": {
      "doc_id": { "type": "string" },
      "item_id": { "type": "string" }
    }
  }
}
```

**결과**
```json
{
  "doc_id": "SYNC-PRD-001", "item_id": "R1",
  "upstream": [ { "doc_id": "SYNC-RFQ-001", "item_id": "Q03", "display_name": "...", "is_missing": false } ],
  "downstream": [
    { "doc_id": "SYNC-UC-001", "item_id": "[[SYNC-UC-001#UC-A6]]", "display_name": "...", "is_missing": false },
    { "doc_id": "SYNC-DOM-001", "item_id": null, "display_name": "도메인모델 (문서 전체)", "is_missing": false }
  ]
}
```

`item_id: null`은 문서 전체를 참조한 것. 미존재 참조는 `is_missing: true`에 `raw_target`만([[SYNC-UC-001#UC-A4]] 2a).

---

### create_document

```json
{
  "name": "create_document",
  "description": "새 문서를 만든다. 문서 ID는 서버가 발급한다({코드}-{타입}-{번호}). 서버는 템플릿을 적용하지 않는다 — body가 get_template으로 받은 뼈대를 따라야 한다. DOM·API는 subtype을 주고 받는다(서브타입마다 필수 절이 다르다). 항목 ID(#R12 같은 것)는 body에 직접 붙인다. 서버는 발급하지 않고 형식·유일성만 검사한다. 기존 문서를 고치려면 이 도구가 아니라 update_document를 써야 한다. 문서 하나를 만들면 결과의 next_step을 사람에게 그대로 전하고 멈춘다 — 같은 단계라도 다음 문서는 사람이 웹에서 읽고 난 뒤에 만든다. DOM 셋은 순서가 있다: 클래스 명세는 API 문서가, ERD는 클래스 명세가 같은 프로젝트에 있어야 받는다(precondition-unmet). DOM 제목에는 도메인·클래스·ERD 중, UI 제목에는 화면 설계·와이어프레임 중, API 제목에는 REST·MCP 중 하나가 들어가야 한다.",
  "inputSchema": {
    "type": "object",
    "required": ["project_code", "doc_type", "body", "message"],
    "properties": {
      "project_code": { "type": "string", "pattern": "^[A-Z]{1,4}$" },
      "message": { "type": "string", "description": "커밋 메시지. 첫 줄 요약, 둘째 줄부터 이유" },
      "doc_type": { "type": "string", "enum": ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE"] },
      "body": { "type": "string", "description": "원본 MD 전체. frontmatter 포함. doc_id는 서버가 채우므로 비워도 된다" }
    }
  }
}
```

**결과** — `SaveResult`
```json
{ "doc_id": "SYNC-PRD-002", "version_no": 1, "commit_hash": "...", "status": "draft", "warnings": [],
  "next_step": "SYNC-PRD-002 v1 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)" }
```

**에러**: `not-found`(남의 프로젝트 — `resource: project`, 1장), `convention-violation`([[SYNC-UC-001#UC-A6]] 2a, 확장 필드 `violations: [{line, rule, message}]`), `precondition-unmet`(3a, DOM 셋의 순서 — 확장 필드 `requires`: 먼저 있어야 하는 것 한 줄, `have`: 그 프로젝트의 DOM 문서 ID 목록. [[SYNC-STD-001]] 2.6), `push-failed`(5a).

**`next_step`은 매번 온다.** 규약(STD-001 1.8)을 에이전트가 잊어도 응답이 다시 말한다 — 사람에게 그대로 전하고 멈춘다.

**결과에 `warnings`가 실릴 수 있다** — 미완성 경고(STD-001 4장). 저장은 됐고 완료만 막힌다. 에이전트는 사람에게 "필수 절 N개가 비어 있다"고 알린다.


---

### get_template

```json
{
  "name": "get_template",
  "description": "문서 타입의 템플릿과 작성 규약을 돌려준다. create_document 전에 반드시 부른다. 반환에는 (1) 그 타입의 항목 ID 패턴·필수 절·항목 블록 구조, (2) 템플릿 MD 뼈대, (3) 채워진 예시가 담긴다. 항목은 ID로 시작하는 헤딩이어야 하고, 표 행은 항목이 아니며, 번호에 패딩을 두지 않는다는 공통 규약도 함께 온다. DOM·API·UI는 무엇을 쓸지 subtype으로 말한다 — DOM은 도메인·클래스·ERD, API는 REST·MCP, UI는 화면 설계·와이어프레임. DOM·API는 서브타입마다 필수 절과 뼈대가 다르므로 subtype 없이 받으면 필수 절이 비어 온다.",
  "inputSchema": {
    "type": "object",
    "required": ["project_code", "doc_type"],
    "properties": {
      "project_code": { "type": "string", "pattern": "^[A-Z]{1,4}$" },
      "doc_type": { "type": "string", "enum": ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE", "STD"] },
      "subtype": { "type": "string", "enum": ["도메인", "클래스", "ERD", "REST", "MCP", "화면 설계", "와이어프레임"], "description": "DOM·API·UI만. 그 타입의 서브타입이어야 한다" }
    }
  }
}
```

**결과**
```json
{
  "doc_type": "PRD",
  "common_rules": "…STD-001 1장 요약…",
  "type_rules": { "item_patterns": ["G\\d+", "R\\d+", "N\\d+"], "required_sections": ["목표", "비목표", "요구사항", "성공지표", "미결사항"], "block_structure": "…" },
  "template": "---\ndoc_id:\ntype: PRD\n…",
  "example": "…STD-001 5장 예시…"
}
```

**서브타입을 주면 그 서브타입의 것만 온다**(카드 AG, #114). `type_rules`의 항목 패턴·필수 절·항목 블록이 그 서브타입의 것이고, 템플릿은 `_templates/{TYPE}-{subtype}.md`가 있으면 그것, 없으면 `_templates/{TYPE}.md`다(UI는 두 서브타입의 필수 절이 같아 파일이 하나다). **서브타입이 있는 타입을 서브타입 없이 부르면** `required_sections`가 빈 배열이고 `subtypes`에 고를 수 있는 것이 온다 — 템플릿은 고르는 안내다. 예전에는 서브타입을 받을 자리가 없어 DOM의 필수 절이 늘 빈 배열로 왔고, 에이전트가 할 수 있는 것은 써서 올린 뒤 경고를 읽는 것뿐이었다. HB에서 클래스 명세·ERD가 그렇게 한 번씩 다시 올라갔다.

```json
{
  "doc_type": "DOM",
  "subtype": "클래스",
  "type_rules": { "item_patterns": ["[A-Z][A-Za-z]+"], "required_sections": ["폴더 구조", "엔티티", "의존 관계", "설계 클래스", "미결사항"], "block_structure": "클래스마다 헤딩 + mermaid classDiagram(그 클래스만) + 메서드 표 + 규칙" },
  "template": "---\ndoc_id:\ntype: DOM\ntitle: 클래스 명세 — …"
}
```

**템플릿은 앱에 내장된 원본을 준다**(#94, 카드 AB) — 사용자 저장소에는 사본이 없고, 있더라도 초기화 때 복사된 뒤 갱신되지 않아 낡는다. **규약**은 그 프로젝트 저장소의 `STD/{project_code}-STD-001.md`를 먼저 읽고, 없으면 내장 `SYNC-STD-001.md`로 대체한다 — 자기 규약을 따로 쓰는 프로젝트가 있을 수 있어서다. `project_code`는 그 규약 문서를 찾는 데 쓴다.

**규약 문서 이름에 프로젝트 코드가 들어간다.** 문서 ID 규칙은 `{프로젝트코드}-{TYPE}-{번호}`이고 STD도 예외가 아니다([[SYNC-STD-001]] 1.1) — `TST` 프로젝트의 규약 문서는 `TST-STD-001.md`다. 이름을 고정해 두면 싱크독이 아닌 프로젝트에서 늘 404가 난다(#8). 내장 사본으로 떨어질 때는 싱크독의 `SYNC-STD-001.md`를 쓴다 — 다른 프로젝트는 싱크독의 STD를 그대로 쓰기 때문이다([[SYNC-STD-001]] 2.12).

**에러**: `not-found` — 발급자가 소유하지 않은 프로젝트(`resource: project`, 1장). 없는 프로젝트와 같은 답이다 · 그 타입의 서브타입이 아닌 `subtype`(`resource: subtype`) — `doc_type`이 틀렸을 때와 같은 답이다

---

### update_document

```json
{
  "name": "update_document",
  "description": "기존 문서의 본문을 교체해 새 버전을 만든다. **반드시 get_document를 먼저 부르고, 그 응답의 body를 고쳐 보낸다 — version_no만 받아 오고 본문은 예전 것을 쓰면 안 된다.** create_document는 frontmatter의 doc_id가 비어도 받지만(서버가 발급한다) 그 본문을 그대로 update_document에 보내면 frontmatter.doc_id 위반이 된다. expected_version에는 get_document가 준 version_no를 넣는다. 그 사이 문서가 바뀌었으면 version-conflict 에러에 현재 버전과 본문이 담기니, 그것을 읽고 병합해 다시 부른다. 본문에서 항목 ID가 사라지면 item-deletion-needs-confirm 에러에 끊어질 하위 항목이 문서ID#항목ID와 이름으로 담겨 오며, 그것을 사람에게 보여주고 확인받은 뒤 confirm_item_deletion=true로 다시 부른다. 완료 상태 문서를 고치면 초안으로 내려간다. 저장 뒤에는 결과의 next_step을 사람에게 그대로 전하고 멈춘다 — 사람이 웹에서 읽기 전에 다음 문서로 가지 않는다.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id", "body", "expected_version", "message", "changed_items"],
    "properties": {
      "doc_id": { "type": "string" },
      "body": { "type": "string", "description": "원본 MD 전체. 부분 수정 없음" },
      "expected_version": { "type": "integer", "minimum": 1, "description": "get_document로 받은 version_no. body도 같은 응답의 것에서 시작한다" },
      "message": { "type": "string", "description": "커밋 메시지. 첫 줄 요약, 둘째 줄부터 왜 바꿨는지. 변경 이력은 여기에만 남는다 (STD-001 1.7)" },
      "changed_items": { "type": "array", "items": { "type": "string" }, "description": "이번에 바꾼 항목 ID 목록. 커밋 메시지와 함께 이력이 된다. 오탈자 수정이면 빈 배열" },
      "confirm_item_deletion": { "type": "boolean", "default": false, "description": "항목 삭제를 사람이 확인했을 때 true" }
    }
  }
}
```

**결과** — `SaveResult`
```json
{ "doc_id": "SYNC-PRD-001", "version_no": 8, "commit_hash": "...", "status": "draft", "warnings": [],
  "next_step": "SYNC-PRD-001 v8 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)" }
```

**에러**

| type | 언제 | 확장 필드 | 유스케이스 |
|---|---|---|---|
| `not-found` | 문서 없음 · 남의 프로젝트(`resource: project`) | `resource`, `id` | — |
| `convention-violation` | 규약 위반 | `violations`, `warnings` | [[SYNC-UC-001#UC-A6]] 2a |
| `version-conflict` | 버전 불일치 | `current_version`, `current_body` | [[SYNC-UC-001#UC-A6]] 4a |
| `item-deletion-needs-confirm` | 항목이 사라짐, 하위 있음 | `deleted_items: [{item_id, downstream: [...]}]` | [[SYNC-UC-001#UC-A6]] 4b |
| `push-failed` | push 실패 | `reason` | [[SYNC-UC-001#UC-A6]] 5a |

`item-deletion-needs-confirm`은 [[SYNC-API-001]]에 없는 MCP 전용 에러다. 웹에는 본문 편집이 없어 이 상황이 없다.

---

### delete_document

```json
{
  "name": "delete_document",
  "description": "문서를 휴지통에 넣는다 — 파일은 저장소에서 지워지고(커밋) 행·버전은 남아 restore_document로 되살릴 수 있다. 잘못 만든 문서를 치우는 길이다. 첫 호출은 document-deletion-needs-confirm 에러로 제목·버전 수·끊어질 참조 목록을 돌려주고 아직 넣지 않는다. 그것을 사람에게 보여주고 확인받은 뒤 confirm=true로 다시 부른다. 넣으면 이 문서를 가리키던 참조가 미존재로 돌아간다 — 되살리면 다시 이어진다. 행까지 지우는 완전 삭제는 웹에서만.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id"],
    "properties": {
      "doc_id": { "type": "string" },
      "confirm": { "type": "boolean", "default": false, "description": "사람이 확인했을 때 true" }
    }
  }
}
```

**결과** — `TrashResult`
```json
{ "doc_id": "VA-DOM-003", "commit_hash": "...", "broken_refs": 13, "next_step": "VA-DOM-003 휴지통에 넣음 — 끊어진 참조 13. 사람에게 알리고 멈춘다" }
```

**에러**

| type | 언제 | 확장 필드 | 유스케이스 |
|---|---|---|---|
| `not-found` | 문서 없음 · 남의 프로젝트(`resource: project`) | `resource`, `id` | — |
| `document-trashed` | 이미 휴지통 | `trashed_at` | [[SYNC-UC-001#UC-A7]] 1a |
| `document-deletion-needs-confirm` | `confirm=false` | `doc_id`, `title`, `version_count`, `inbound_refs` | [[SYNC-UC-001#UC-A7]] 2 |
| `push-failed` | 삭제 커밋 push 실패 | `reason` | [[SYNC-UC-001#UC-A7]] 5a |

`document-deletion-needs-confirm`은 `item-deletion-needs-confirm`과 같은 두 번 호출 패턴이다(5장 2). 에이전트가 첫 에러를 사람에게 안 보여주고 바로 `confirm=true`로 부르면 확인이 무의미해진다 — 도구 설명이 그러지 말라고 말하지만 강제할 방법은 없다. 휴지통이라 되살릴 수는 있다.

---

### restore_document

```json
{
  "name": "restore_document",
  "description": "휴지통의 문서를 되살린다 — 휴지통에 넣기 직전 내용으로 새 버전이 생기고 항목이 돌아오며, 그 항목을 가리키던 미존재 참조가 다시 이어진다. 휴지통에 없는 문서는 document-not-trashed. 옛 본문이 지금 규약을 위반하면 convention-violation으로 그대로 남는다.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id"],
    "properties": { "doc_id": { "type": "string" } }
  }
}
```

**결과** — `SaveResult` (되살린 버전, `next_step` 포함)

**에러**: `not-found`(문서 없음 · 남의 프로젝트는 `resource: project`) · `document-not-trashed`([[SYNC-UC-001#UC-A8]] 1a) · `convention-violation`(3a) · `push-failed`

---

## 4. 에이전트 순서

도구 설명에 흩어진 것을 한 번에 적는다. 이 절이 에이전트의 시스템 프롬프트나 스킬 파일에 들어갈 내용이다.

```
쓸 때 (신규)
  0. get_template(project, doc_type)  규약·뼈대·예시. 이걸 안 보고 쓰면 규약 위반이 난다
  1. create_document(project, doc_type, body, message)
     - precondition-unmet → DOM 셋의 순서다. requires에 적힌 것(API 문서 또는 클래스 명세)이 먼저다. 사람에게 말한다
  2. 멈춘다. 결과의 next_step을 사람에게 그대로 전한다. 사람이 웹에서 읽고 「다음」이라고 하기 전에는
     같은 단계라도 다음 문서를 만들지 않는다 (STD-001 1.8)
     DOM은 도메인 모델 → (7 화면 · 8 API) → 클래스 명세 → ERD. 한 대화에 셋을 만들지 않는다

읽을 때
  1. list_documents(project)          어느 단계에 뭐가 있나. approved인지 확인
  2. get_document(doc_id)              본문. version_no 기억
  3. 본문의 [[X#Y]]를 보면 get_item(X, Y)    필요한 것만
  4. 영향 범위가 궁금하면 get_references

쓸 때
  1. get_document(doc_id)              최신 version_no
  2. update_document(doc_id, body, expected_version=version_no, message, changed_items)
     message = "spec(doc_id): 요약\n\n왜 바꿨는지" · changed_items = 실제로 바꾼 항목 ID만
     - version-conflict            → current_body 읽고 병합 → 1부터 다시
     - item-deletion-needs-confirm → 사람에게 deleted_items 보여주고 확인
                                     → confirm_item_deletion=true로 다시
     - convention-violation        → violations 고치고 다시
  3. next_step을 전하고 멈춘다 — 신규와 같다. 완료 문서를 고쳤으면 초안으로 내려갔다고 말한다
  4. 이 변경이 상위 문서의 결정과 어긋난다는 걸 알면 사람에게 말한다 — 상위를 고치는 것도 사람이 시킨다
     예: API에서 "바뀐 항목은 에이전트가 지정"으로 정했는데 UC-A6는 "diff로 찾는다"라고 되어 있으면 그 둘을 짚어 준다

하지 말 것
  - update_document에 doc_id 오타 → not-found. 새 문서가 생기지 않는다
  - 남의 프로젝트 코드·문서 ID → not-found(project). 토큰 발급자가 소유한 프로젝트만 열린다 — list_documents로 코드를 다시 확인한다
  - expected_version 없이 update  → 스키마에서 거부
  - 상태를 바꾸려 하지 않는다    → 도구가 없다. 사람이 웹에서
  - get_references 결과를 전부 get_item으로 펼치지 않는다 → 필요한 것만
  - 한 대화에서 한 단계의 문서 여럿을 연달아 만들지 않는다 → 문서 하나가 단위다 (STD-001 1.8)

지울 때 (잘못 만든 문서)
  1. delete_document(doc_id)
     - document-deletion-needs-confirm → 제목·버전 수·끊어질 참조를 사람에게 보여주고 확인
  2. 확인되면 delete_document(doc_id, confirm=true). 휴지통이다 — 되살릴 수 있다
  3. 잘못 넣었으면 restore_document(doc_id). 완전 삭제는 사람이 웹에서

```

---

## 5. 판단이 필요한 지점

**1. `update_document`가 본문 전체를 받는다.** 부분 수정(특정 항목만 교체)이 없다. 에이전트가 get_document → 수정 → update_document로 전체를 다시 보내야 한다. 문서가 커지면 부담이지만, 부분 수정은 항목 경계 판정이 필요해 규약이 복잡해진다. 지금은 전체 교체.

**2. 항목 삭제 확인이 두 번 호출이다.** 에러 → 사람 확인 → 재호출. MCP에는 대화형 확인이 없어서 이 패턴이 표준이다. 에이전트가 첫 에러를 사람에게 안 보여주고 바로 `confirm=true`로 재호출하면 확인이 무의미해진다. 도구 설명에 "사람에게 확인받은 뒤"를 명시했으나 강제할 방법은 없다.

**3. 읽기 도구에 `project_code`가 없다.** 문서 ID에 코드가 들어 있어 불필요하다. `list_documents`만 프로젝트 코드를 받는다.

---

## 6. 미결사항

- [x] 부분 수정 도구(`update_item`) 필요 여부 — 문서가 커지면 — 결정: v1은 전체 교체. 문서가 커져 실제로 불편해지면 v2
- [x] 토큰 만료·회수 시 MCP 에러 형식 — 결정: 401 + `application/problem+json` `urn:syncdoc:unauthorized`. `mcp/auth.py`가 구현
