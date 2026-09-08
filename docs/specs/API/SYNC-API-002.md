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
- 에러: 도구 결과의 `isError: true` + 본문에 [[SYNC-API-001]]과 **같은 problem+json**. 에이전트가 `type`으로 분기한다
- 모든 조회 결과에 문서 상태와 버전이 담긴다(PRD R9). 에이전트는 이걸로 확정 명세와 초안을 구분한다
- 상태 변경·댓글·플래그 확인·전파 결정은 MCP에 **없다**. 사람의 판단이라 웹에서만 한다([[SYNC-UC-001#UC-H8]]·H9·H10·H11 주 액터 사람)

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
| `get_template` | (STD-001 전달) | — 저장소 `_templates/` 읽기 | |

---

## 3. 도구 정의

### init_project

```json
{
  "name": "init_project",
  "description": "GitHub 저장소를 싱크독 프로젝트로 등록한다. docs/specs/ 아래 11단계 디렉터리와 템플릿을 만들어 커밋한다. 새 프로젝트를 시작할 때 한 번만 부른다. 이미 등록된 저장소면 project-code-conflict, 저장소에 docs/specs/가 이미 있으면 existing-specs 에러가 나며 import_existing=true로 다시 부르면 기존 명세를 가져와 등록한다.",
  "inputSchema": {
    "type": "object",
    "required": ["remote_url", "code", "name"],
    "properties": {
      "remote_url": { "type": "string", "format": "uri", "description": "GitHub 저장소 주소" },
      "code": { "type": "string", "pattern": "^[A-Z]{1,4}$", "description": "프로젝트 코드. 영문 대문자 4자 이내. 문서 ID 앞부분이 된다" },
      "name": { "type": "string", "maxLength": 100, "description": "표시 이름" },
      "import_existing": { "type": "boolean", "default": false, "description": "docs/specs/가 이미 있을 때 덮어쓰지 않고 가져와 등록" }
    }
  }
}
```

**결과**
```json
{ "code": "SYNC", "name": "싱크독", "remote_url": "...", "stages": [ { "stage": 1, "doc_type": "RFQ", "status": null, "doc_count": 0 }, "..." ] }
```

**에러**: `project-code-conflict`(2a), `project-code-invalid`(2b), `existing-specs`(3a, 확장 필드 `doc_count`), `push-failed`(4a)

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
      "status": { "type": "string", "enum": ["draft", "review", "approved"], "description": "특정 상태만 보려면. 예: 승인 문서만" }
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
  "items": [ { "item_id": "R1", "display_name": "에이전트용 원본과 사람용 뷰", "flags": ["needs_check"] } ]
}
```

`items[].flags`는 그 항목에 붙은 플래그 종류. 에이전트가 "이 항목은 상위가 바뀌어 확인 대기 중"임을 알 수 있다.

**에러**: `not-found`([[SYNC-UC-001#UC-A2]] 1a). 규약 오류 문서는 에러가 아니라 `has_convention_error: true`와 함께 정상 반환(2a).

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
  "body": "#### R12 ...\n본문 블록만",
  "flags": ["needs_check"]
}
```

**에러**: `not-found`(문서 없음), `item-deleted`(1a, 확장 필드 `deleted_at`), 문서는 있는데 항목이 없으면 `not-found` + 확장 필드 `available_items: [...]`(1b).

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
  ],
  "flags": [ { "kind": "needs_check", "cause": "SYNC-RFQ-001#Q03", "cause_version_no": 4, "raised_at": "..." } ]
}
```

`item_id: null`은 문서 전체를 참조한 것. 미존재 참조는 `is_missing: true`에 `raw_target`만([[SYNC-UC-001#UC-A4]] 2a).

---

### create_document

```json
{
  "name": "create_document",
  "description": "새 문서를 만든다. 문서 ID는 서버가 발급한다({코드}-{타입}-{번호}). 저장소의 docs/specs/_templates/ 템플릿이 적용되므로 body는 템플릿 구조를 따라야 한다. 항목 ID(#R12 같은 것)는 body에 직접 붙인다. 서버는 발급하지 않고 형식·유일성만 검사한다. 기존 문서를 고치려면 이 도구가 아니라 update_document를 써야 한다.",
  "inputSchema": {
    "type": "object",
    "required": ["project_code", "doc_type", "body", "message"],
    "properties": {
      "project_code": { "type": "string", "pattern": "^[A-Z]{1,4}$" },
      "message": { "type": "string", "description": "커밋 메시지. 첫 줄 요약, 둘째 줄부터 이유" },
      "upstream_impact": { "type": "array", "items": { "type": "string" }, "description": "새 문서가 상위 항목과 어긋남을 알면 지정" },
      "doc_type": { "type": "string", "enum": ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE"] },
      "body": { "type": "string", "description": "원본 MD 전체. frontmatter 포함. doc_id는 서버가 채우므로 비워도 된다" }
    }
  }
}
```

**결과** — `SaveResult`
```json
{ "doc_id": "SYNC-PRD-002", "version_no": 1, "commit_hash": "...", "status": "draft", "pending_decision_version_id": null }
```

**에러**: `convention-violation`([[SYNC-UC-001#UC-A6]] 2a, 확장 필드 `violations: [{line, rule, message}]`), `push-failed`(5a).

**결과에 `warnings`가 실릴 수 있다** — 미완성 경고(STD-001 4장). 저장은 됐고 승인만 막힌다. 에이전트는 사람에게 "필수 절 N개가 비어 있다"고 알린다.

신규 문서는 하위 참조가 없으므로 `pending_decision_version_id`가 항상 null([[SYNC-UC-001#UC-S3]] 1a).

---

### get_template

```json
{
  "name": "get_template",
  "description": "문서 타입의 템플릿과 작성 규약을 돌려준다. create_document 전에 반드시 부른다. 반환에는 (1) 그 타입의 항목 ID 패턴·필수 절·항목 블록 구조, (2) 템플릿 MD 뼈대, (3) 채워진 예시가 담긴다. 항목은 ID로 시작하는 헤딩이어야 하고, 표 행은 항목이 아니며, 번호에 패딩을 두지 않는다는 공통 규약도 함께 온다.",
  "inputSchema": {
    "type": "object",
    "required": ["project_code", "doc_type"],
    "properties": {
      "project_code": { "type": "string", "pattern": "^[A-Z]{1,4}$" },
      "doc_type": { "type": "string", "enum": ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE", "STD"] }
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

저장소 `docs/specs/_templates/{TYPE}.md`와 `STD/SYNC-STD-001.md`에서 읽는다. 프로젝트마다 템플릿 사본이 있으므로 `project_code`가 필요하다.

---

### update_document

```json
{
  "name": "update_document",
  "description": "기존 문서의 본문을 교체해 새 버전을 만든다. 반드시 get_document로 받은 version_no를 expected_version에 넣어야 한다. 그 사이 문서가 바뀌었으면 version-conflict 에러에 현재 버전과 본문이 담기니, 그것을 읽고 병합해 다시 부른다. 본문에서 항목 ID가 사라지면 하위 참조 목록과 함께 item-deletion-needs-confirm 에러가 나며, 사람에게 확인받은 뒤 confirm_item_deletion=true로 다시 부른다. 저장 후 하위에 영향이 있으면 결과의 pending_decision_version_id가 채워지고, 전파 여부는 지시한 사람이 웹에서 결정한다. 승인 상태 문서를 고치면 검토중으로 내려간다. 이 변경이 상위 항목과 어긋나게 됐음을 알면 upstream_impact에 그 상위 항목을 넣는다.",
  "inputSchema": {
    "type": "object",
    "required": ["doc_id", "body", "expected_version", "message", "changed_items"],
    "properties": {
      "doc_id": { "type": "string" },
      "body": { "type": "string", "description": "원본 MD 전체. 부분 수정 없음" },
      "expected_version": { "type": "integer", "minimum": 1, "description": "get_document로 받은 version_no" },
      "message": { "type": "string", "description": "커밋 메시지. 첫 줄 요약, 둘째 줄부터 왜 바꿨는지. 변경 이력은 여기에만 남는다 (STD-001 1.7)" },
      "changed_items": { "type": "array", "items": { "type": "string" }, "description": "이번에 바꾼 항목 ID 목록. 이 항목들의 하위 참조에 확인 필요가 걸린다. 오탈자 수정이면 빈 배열" },
      "upstream_impact": { "type": "array", "items": { "type": "string" }, "description": "이 변경으로 이 문서와 어긋나게 된 상위 항목. 예: [\"SYNC-UC-001#UC-A6\"]. 그 항목에 하위 불일치 플래그가 붙어 상위 담당자의 내 할 일에 뜬다. 모르면 생략 — 승인 때 사람이 대조한다" },
      "confirm_item_deletion": { "type": "boolean", "default": false, "description": "항목 삭제를 사람이 확인했을 때 true" }
    }
  }
}
```

**결과** — `SaveResult`
```json
{ "doc_id": "SYNC-PRD-001", "version_no": 8, "commit_hash": "...", "status": "review", "pending_decision_version_id": 4127, "warnings": [] }
```

**에러**

| type | 언제 | 확장 필드 | 유스케이스 |
|---|---|---|---|
| `not-found` | 문서 없음 | `resource`, `id` | — |
| `convention-violation` | 규약 위반 | `violations`, `warnings` | [[SYNC-UC-001#UC-A6]] 2a |
| `version-conflict` | 버전 불일치 | `current_version`, `current_body` | [[SYNC-UC-001#UC-A6]] 4a |
| `item-deletion-needs-confirm` | 항목이 사라짐, 하위 있음 | `deleted_items: [{item_id, downstream: [...]}]` | [[SYNC-UC-001#UC-A6]] 4b |
| `push-failed` | push 실패 | `reason` | [[SYNC-UC-001#UC-A6]] 5a |

`item-deletion-needs-confirm`은 [[SYNC-API-001]]에 없는 MCP 전용 에러다. 웹에는 본문 편집이 없어 이 상황이 없다.

---

## 4. 에이전트 순서

도구 설명에 흩어진 것을 한 번에 적는다. 이 절이 에이전트의 시스템 프롬프트나 스킬 파일에 들어갈 내용이다.

```
쓸 때 (신규)
  0. get_template(project, doc_type)  규약·뼈대·예시. 이걸 안 보고 쓰면 규약 위반이 난다

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
  3. 결과에 pending_decision_version_id가 있으면
     "하위 N건에 영향. 전파 여부는 내 할 일에서 결정하세요"라고 사람에게 알린다
  4. 이 변경이 상위 문서의 결정과 어긋난다는 걸 알면 upstream_impact에 그 항목을 넣는다
     예: API에서 "바뀐 항목은 에이전트가 지정"으로 정했는데 UC-A6는 "diff로 찾는다"라고 되어 있으면 ["SYNC-UC-001#UC-A6"]

하지 말 것
  - update_document에 doc_id 오타 → not-found. 새 문서가 생기지 않는다
  - expected_version 없이 update  → 스키마에서 거부
  - 상태를 바꾸려 하지 않는다    → 도구가 없다. 사람이 웹에서
  - get_references 결과를 전부 get_item으로 펼치지 않는다 → 필요한 것만
```

---

## 5. 판단이 필요한 지점

**1. `update_document`가 본문 전체를 받는다.** 부분 수정(특정 항목만 교체)이 없다. 에이전트가 get_document → 수정 → update_document로 전체를 다시 보내야 한다. 문서가 커지면 부담이지만, 부분 수정은 항목 경계 판정이 필요해 규약이 복잡해진다. 지금은 전체 교체.

**2. 항목 삭제 확인이 두 번 호출이다.** 에러 → 사람 확인 → 재호출. MCP에는 대화형 확인이 없어서 이 패턴이 표준이다. 에이전트가 첫 에러를 사람에게 안 보여주고 바로 `confirm=true`로 재호출하면 확인이 무의미해진다. 도구 설명에 "사람에게 확인받은 뒤"를 명시했으나 강제할 방법은 없다.

**3. 읽기 도구에 `project_code`가 없다.** 문서 ID에 코드가 들어 있어 불필요하다. `list_documents`만 프로젝트 코드를 받는다.

---

## 6. 미결사항

- [ ] 부분 수정 도구(`update_item`) 필요 여부 — 문서가 커지면
- [ ] 토큰 만료·회수 시 MCP 에러 형식
