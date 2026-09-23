---
doc_id: 
type: API
title: API 명세 MCP — {프로젝트}
status: draft
upstream: []
---

# API 명세 MCP — {프로젝트}

<!-- 템플릿. [[SYNC-STD-001]] 2.8의 API 둘 중 MCP. doc_id는 서버가 채운다 -->
<!-- title에 「MCP」가 들어가야 한다 — 그것으로 둘 중 무엇인지 안다 (없으면 위반) -->
<!-- 필수 절 넷: 규칙 · 도구 · 에이전트 순서 · 미결사항. 아래 절 이름을 그대로 쓰면 미완성 경고가 안 난다 -->
<!-- 문서 하나를 만들면 멈춘다 (STD-001 1.8) -->

## 0. 이 문서가 다루는 것

…

## 1. 규칙

토큰 · 누구의 권한으로 도는가 · 남의 것은 없는 것과 같은가 같은, 모든 도구에 걸리는 약속.

## 2. 도구

<!-- 항목 = 도구. 헤딩은 도구 이름(소문자 snake_case). 아래에 inputSchema json + 결과 예시 + 에러 표 -->

#### get_example

```json
{
  "name": "get_example",
  "description": "…",
  "inputSchema": { "type": "object", "required": ["id"], "properties": { "id": { "type": "string" } } }
}
```

**결과**

```json
{ "id": "…" }
```

| 에러 | 언제 |
|---|---|
| `not-found` | … |

## 3. 에이전트 순서

에이전트가 도구를 어떤 차례로 부르나 — 무엇을 먼저 읽고, 쓴 뒤 무엇을 사람에게 전하고 멈추나.

## 4. 미결사항

- [ ] …
