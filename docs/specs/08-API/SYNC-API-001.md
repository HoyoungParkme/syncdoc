---
doc_id: SYNC-API-001
type: API
title: API 명세 REST — 싱크독
status: draft
upstream: [SYNC-UI-002, SYNC-DOM-002, SYNC-DOM-003]
---

# API 명세 — 웹 REST: 싱크독 (SyncDoc)

---

## 0. 이 문서가 다루는 것

브라우저(React)가 부르는 REST API. 와이어프레임의 화면마다 "이 화면이 뭘 받아야 하나"를 엔드포인트로 옮긴 것이다. MCP 도구는 [[SYNC-API-002]]에 따로 있다.


---

---

## 1. 규칙

- 인증은 세션 쿠키. GitHub OAuth로 로그인하면 서버가 세션을 만든다. 미인증이면 401
- 에러는 RFC 9457 `application/problem+json`. `type`은 `urn:syncdoc:{종류}`. 종류별 확장 필드는 2장
- 모든 시각은 ISO 8601 UTC
- 문서 ID(`SYNC-PRD-001`)는 프로젝트 코드를 포함해 전역 유일하므로 `/api/docs/{docId}`로 바로 접근한다
- 항목 ID는 `#` 없이 경로에 넣는다. `/items/R12`, `/items/POST~orders` (`/`는 `~`로)
- 목록은 페이지 없음. 2~3명 규모에서 한 프로젝트 문서가 수십 개다

**웹이 쓰지 않는 것** — 본문 생성·수정 엔드포인트는 없다. 본문 쓰기는 MCP와 GitHub push뿐이다(PRD R9). 웹의 쓰기는 상태 변경(승인 시 상위 대조 포함)·되돌리기·댓글·플래그 확인·전파 결정·토큰·재구축까지다.

---

## 2. 에러

`application/problem+json`. 공통 필드 `type`, `title`, `status`, `detail`. 종류별 확장 필드:

| type | status | 언제 | 확장 필드 | 유스케이스 |
|---|---|---|---|---|
| `urn:syncdoc:unauthorized` | 401 | 세션 없음 | — | — |
| `urn:syncdoc:not-found` | 404 | 문서·항목·프로젝트 없음 | `resource`, `id` | [[SYNC-UC-001#UC-A2]] 1a |
| `urn:syncdoc:item-deleted` | 410 | 삭제된 항목 조회 | `deleted_at` | [[SYNC-UC-001#UC-A3]] 1a |
| `urn:syncdoc:convention-violation` | 422 | 규약 위반 (되돌리기 시) | `violations: [{line, rule, message}]`, `warnings: [{rule, message}]` | [[SYNC-UC-001#UC-S1]] 4a, [[SYNC-UC-001#UC-H7]] 4a |
| `urn:syncdoc:version-conflict` | 409 | 버전 불일치 | `current_version`, `current_body` | [[SYNC-UC-001#UC-A6]] 4a |
| `urn:syncdoc:status-blocked` | 409 | 규약 오류 또는 미완성 문서를 `approved`로 | `convention_error_detail`, `warnings` | [[SYNC-UC-001#UC-H8]] 1a |
| `urn:syncdoc:item-deletion-needs-confirm` | 409 | 되돌리기로 항목이 사라지고 하위 참조 있음 | `deleted_items: [{item_id, downstream}]` | [[SYNC-UC-001#UC-H7]], [[SYNC-UC-001#UC-A6]] 4b |
| `urn:syncdoc:project-code-conflict` | 409 | 코드 중복 | `code` | [[SYNC-UC-001#UC-A1]] 2a |
| `urn:syncdoc:project-code-invalid` | 422 | 코드 형식 | `rule` | [[SYNC-UC-001#UC-A1]] 2b |
| `urn:syncdoc:existing-specs` | 409 | `docs/specs/` 이미 있음 | `doc_count` | [[SYNC-UC-001#UC-A1]] 3a |
| `urn:syncdoc:push-failed` | 502 | GitHub push 실패 | `reason` | [[SYNC-UC-001#UC-A1]] 4a, [[SYNC-UC-001#UC-S7]] 2b |
| `urn:syncdoc:reason-required` | 422 | skip인데 사유 없음 | — | [[SYNC-UC-001#UC-H10]] 2a |
| `urn:syncdoc:already-decided` | 409 | 이미 결정된 전파 | `choice`, `decided_at` | [[SYNC-UC-001#UC-H10]] |
| `urn:syncdoc:already-resolved` | 409 | 이미 확인된 플래그 | `resolved_at` | [[SYNC-UC-001#UC-H11]] |
| `urn:syncdoc:already-current` | 422 | 현재 버전으로 되돌리기 | — | [[SYNC-UC-001#UC-H7]] |
| `urn:syncdoc:upstream-review-required` | 422 | `approved`인데 `upstream_reviewed`가 아님 | — | [[SYNC-UC-001#UC-H8]] 3 |
| `urn:syncdoc:rebuild-failed` | 500 | 재구축 중 실패, 롤백됨 | `reason` | [[SYNC-UC-001#UC-S6]] |
| `urn:syncdoc:repository-already-registered` | 409 | 이미 등록된 저장소 | `code` (그 저장소를 쓰는 프로젝트) | [[SYNC-UC-001#UC-A1]] 2d |
| `urn:syncdoc:not-implemented` | 501 | 카드 스텁 — 아직 구현 안 된 경로 (`import_existing` 등). 슬라이스 진행 중에만 존재 | `card` | [[SYNC-STD-004#DEV-12]] |

---

---

## 3. 엔드포인트

항목 = `{METHOD}/{path}`. 엔드포인트마다 헤딩 + 그 오퍼레이션의 yaml 조각. 공통 스키마·파라미터·응답은 4장. 뷰가 조각을 합쳐 OpenAPI 전체를 만든다(뷰 규약 V-API).

### 3.1 인증

#### GET/auth/github GitHub OAuth 시작

화면 [[SYNC-UI-001#UI-1]] · 유스케이스 인프라 5 · 서비스 `AccountService.login_github`

```yaml
/auth/github:
  get:
    summary: GitHub OAuth 시작
    security: []
    parameters:
    - in: query
      name: next
      schema:
        type: string
      description: 로그인 후 돌아갈 경로
    responses:
      '302':
        description: GitHub 동의 화면으로
```

#### GET/auth/github/callback OAuth 콜백. 세션 생성, 토큰 암호화 저장

화면 [[SYNC-UI-001#UI-1]] · 유스케이스 인프라 5 · 서비스 `AccountService.login_github`

```yaml
/auth/github/callback:
  get:
    summary: OAuth 콜백. 세션 생성, 토큰 암호화 저장
    security: []
    parameters:
    - in: query
      name: code
      required: true
      schema:
        type: string
    - in: query
      name: state
      required: true
      schema:
        type: string
    responses:
      '302':
        description: next 또는 / 로
```

#### POST/auth/logout 세션 종료

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 — · 서비스 `—`

```yaml
/auth/logout:
  post:
    summary: 세션 종료
    responses:
      '204':
        description: 종료됨
```

### 3.2 webhook

#### POST/hooks/github GitHub push webhook

화면 — · 유스케이스 [[SYNC-UC-001#UC-G1]] · 서비스 `pipeline`

```yaml
/hooks/github:
  post:
    summary: "GitHub push webhook ([[SYNC-UC-001#UC-G1]])"
    security: []
    parameters:
    - in: header
      name: X-Hub-Signature-256
      required: true
      schema:
        type: string
    requestBody:
      content:
        application/json:
          schema:
            type: object
    responses:
      '202':
        description: 접수. 파이프라인은 비동기
      '401':
        description: 서명 불일치
```

### 3.3 프로젝트

#### GET/api/projects 프로젝트 목록과 단계 요약

화면 [[SYNC-UI-001#UI-2]] · 유스케이스 [[SYNC-UC-001#UC-H14]] · 서비스 `ProjectService.list_projects`

```yaml
/api/projects:
  get:
    summary: 프로젝트 목록과 단계 요약 (UI-2)
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/ProjectSummary'
```

#### POST/api/projects 프로젝트 초기화

화면 [[SYNC-UI-001#UI-3]] · 유스케이스 [[SYNC-UC-001#UC-A1]] · 서비스 `ProjectService.init_project`

```yaml
/api/projects:
  post:
    summary: "프로젝트 초기화 (UI-3, [[SYNC-UC-001#UC-A1]])"
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - remote_url
            - code
            - name
            properties:
              remote_url:
                type: string
                format: uri
              code:
                type: string
                pattern: ^[A-Z]{1,4}$
              name:
                type: string
                maxLength: 100
              import_existing:
                type: boolean
                default: false
                description: "docs/specs/가 이미 있을 때 true로 재요청하면 가져와서 등록 ([[SYNC-UC-001#UC-A1]] 3a2)"
    responses:
      '201':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProjectSummary'
      '409':
        $ref: '#/components/responses/Problem'
      '422':
        $ref: '#/components/responses/Problem'
      '502':
        $ref: '#/components/responses/Problem'
```

#### GET/api/projects/{code} 프로젝트 상세

화면 [[SYNC-UI-001#UI-4]] · 유스케이스 [[SYNC-UC-001#UC-H14]] · 서비스 `ProjectService.get_stage_summary`

```yaml
/api/projects/{code}:
  get:
    summary: 프로젝트 상세 (UI-4)
    parameters:
    - $ref: '#/components/parameters/code'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProjectDetail'
      '404':
        $ref: '#/components/responses/Problem'
```

#### GET/api/projects/{code}/docs 문서 목록

화면 [[SYNC-UI-001#UI-4]], [[SYNC-UI-001#UI-9]] · 유스케이스 [[SYNC-UC-001#UC-H14]], H16 · 서비스 `SpecService`

```yaml
/api/projects/{code}/docs:
  get:
    summary: 문서 목록 (UI-4, UI-9)
    parameters:
    - $ref: '#/components/parameters/code'
    - in: query
      name: stage
      schema:
        type: integer
        minimum: 1
        maximum: 11
    - in: query
      name: status
      schema:
        $ref: '#/components/schemas/DocStatus'
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/DocumentSummary'
```

#### GET/api/projects/{code}/flags 프로젝트의 플래그·댓글·규약 오류 목록

화면 [[SYNC-UI-001#UI-4]] · 유스케이스 [[SYNC-UC-001#UC-H14]] · 서비스 `TrackingService`

```yaml
/api/projects/{code}/flags:
  get:
    summary: 프로젝트의 플래그·댓글·규약 오류 목록 (UI-4 다이얼로그 6)
    parameters:
    - $ref: '#/components/parameters/code'
    - in: query
      name: kind
      required: true
      schema:
        type: string
        enum:
        - needs_check
        - broken_ref
        - upstream_impact
        - comments
        - convention_errors
        - incomplete
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                oneOf:
                - $ref: '#/components/schemas/FlagSummary'
                - $ref: '#/components/schemas/CommentSummary'
                - $ref: '#/components/schemas/DocumentSummary'
```

#### GET/api/projects/{code}/graph 참조 그래프

화면 [[SYNC-UI-001#UI-8]] · 유스케이스 [[SYNC-UC-001#UC-H4]] · 서비스 `ReferenceService.graph`

```yaml
/api/projects/{code}/graph:
  get:
    summary: "참조 그래프 (UI-8, [[SYNC-UC-001#UC-H4]])"
    parameters:
    - $ref: '#/components/parameters/code'
    - in: query
      name: stage
      schema:
        type: integer
      description: 단계로 좁힘 (2b)
    - in: query
      name: doc
      schema:
        type: string
      description: 문서로 좁힘 (2b)
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Graph'
```

### 3.4 문서

#### GET/api/docs/{docId} 문서

화면 [[SYNC-UI-001#UI-5]], [[SYNC-UI-001#UI-9]] · 유스케이스 [[SYNC-UC-001#UC-H2]] · 서비스 `SpecService.get_document`

```yaml
/api/docs/{docId}:
  get:
    summary: "문서 (UI-5 유저용·원본 탭 공통, [[SYNC-UC-001#UC-H2]])"
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Document'
      '404':
        $ref: '#/components/responses/Problem'
```

#### GET/api/docs/{docId}/items/{itemId}/references 항목의 상위·하위 참조와 플래그

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H3]] · 서비스 `ReferenceService`

```yaml
/api/docs/{docId}/items/{itemId}/references:
  get:
    summary: "항목의 상위·하위 참조와 플래그 (UI-5 패널 8.1, [[SYNC-UC-001#UC-H3]])"
    parameters:
    - $ref: '#/components/parameters/docId'
    - $ref: '#/components/parameters/itemId'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ItemReferences'
      '404':
        $ref: '#/components/responses/Problem'
      '410':
        $ref: '#/components/responses/Problem'
```

#### GET/api/docs/{docId}/downstream 이 문서를 참조하는 것

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H3]] · 서비스 `queries.downstream_view`

뷰 규약 V-PRD·V-RFQ의 **추적표**와 카드 바닥 "근거로 삼은 문서", 목표 표의 하위 참조 수가 이걸 쓴다.

```yaml
/api/docs/{docId}/downstream:
  get:
    summary: 이 문서(의 항목들)를 참조하는 다른 문서 항목 전부. 추적표용
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '200':
        content:
          application/json:
            schema:
              type: object
              properties:
                by_item:
                  type: object
                  additionalProperties:
                    type: array
                    items:
                      $ref: '#/components/schemas/ItemRef'
                  description: "이 문서의 item_id → 그것을 참조하는 항목들. 문서 단위 참조는 키 \"(문서)\""
                by_document:
                  type: array
                  items:
                    type: object
                    properties:
                      doc_id: { type: string }
                      title: { type: string }
                      items: { type: array, items: { type: string }, description: 참조한 이 문서의 항목 ID들 }
```

#### GET/api/docs/{docId}/upstream 상위 대조 목록

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H8]] 3 · 서비스 `queries.upstream_checklist`

```yaml
/api/docs/{docId}/upstream:
  get:
    summary: 이 문서가 참조하는 상위 항목 전부. 승인 전 대조용 (UC-H8 3)
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  target:
                    $ref: '#/components/schemas/ItemRef'
                  target_version_no:
                    type: integer
                  target_status:
                    $ref: '#/components/schemas/DocStatus'
                  referenced_from:
                    type: array
                    items:
                      type: string
                    description: 이 문서의 어느 항목이 참조하는지. frontmatter upstream이면 "(문서)"
```

#### POST/api/docs/{docId}/status 상태 변경

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H8]] · 서비스 `SpecService.change_status`

```yaml
/api/docs/{docId}/status:
  post:
    summary: "상태 변경 (UI-5 요소 3, [[SYNC-UC-001#UC-H8]])"
    parameters:
    - $ref: '#/components/parameters/docId'
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - to
            properties:
              to:
                $ref: '#/components/schemas/DocStatus'
              reason:
                type: string
              upstream_mismatch:
                type: array
                items:
                  type: string
                description: to=approved일 때. 상위 대조에서 어긋남으로 표시한 항목(SYNC-UC-001#UC-A6 형식). 각각에 하위 불일치 플래그 (UC-H8 3)
              upstream_reviewed:
                type: boolean
                description: to=approved면 필수 true. 상위 대조를 거쳤다는 확인. false·누락이면 422
    responses:
      '200':
        description: 바뀐 상태. frontmatter 갱신 커밋(status 접두어)이 함께 생긴다
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DocumentSummary'
      '409':
        $ref: '#/components/responses/Problem'
```

#### GET/api/docs/{docId}/versions 버전 목록

화면 [[SYNC-UI-001#UI-7]] · 유스케이스 [[SYNC-UC-001#UC-H6]] · 서비스 `SpecService`

```yaml
/api/docs/{docId}/versions:
  get:
    summary: "버전 목록 (UI-7, [[SYNC-UC-001#UC-H6]]). status 커밋도 포함"
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/Version'
```

#### GET/api/docs/{docId}/diff 두 버전 줄 단위 diff

화면 [[SYNC-UI-001#UI-7]] · 유스케이스 [[SYNC-UC-001#UC-H6]] · 서비스 `SpecService.diff`

```yaml
/api/docs/{docId}/diff:
  get:
    summary: "두 버전 줄 단위 diff (UI-7, [[SYNC-UC-001#UC-H6]]). 항목별로 묶고 하위 참조 건수 포함 (3a)"
    parameters:
    - $ref: '#/components/parameters/docId'
    - in: query
      name: from
      required: true
      schema:
        type: integer
    - in: query
      name: to
      required: true
      schema:
        type: integer
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Diff'
```

#### POST/api/docs/{docId}/revert 되돌리기

화면 [[SYNC-UI-001#UI-7]] · 유스케이스 [[SYNC-UC-001#UC-H7]] · 서비스 `SpecService.revert`

```yaml
/api/docs/{docId}/revert:
  post:
    summary: "되돌리기 (UI-7 다이얼로그 4, [[SYNC-UC-001#UC-H7]]). 새 버전 생성. 파이프라인 전부 탄다"
    parameters:
    - $ref: '#/components/parameters/docId'
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - to_version
            properties:
              to_version:
                type: integer
              confirm_item_deletion:
                type: boolean
                default: false
                description: "되돌린 본문에 지금 있는 항목이 없어 하위 참조가 끊길 때, 확인 후 true로 재요청 ([[SYNC-UC-001#UC-A6]] 4b)"
    responses:
      '201':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SaveResult'
      '409':
        $ref: '#/components/responses/Problem'
      '422':
        $ref: '#/components/responses/Problem'
      '502':
        $ref: '#/components/responses/Problem'
```

#### GET/api/docs/{docId}/comments 댓글 목록. 스레드 구조

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H9]] · 서비스 `CommentService`

```yaml
/api/docs/{docId}/comments:
  get:
    summary: 댓글 목록. 스레드 구조 (UI-5 패널 8.2)
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/Comment'
```

#### POST/api/docs/{docId}/comments 댓글 작성

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H9]] · 서비스 `CommentService.add`

```yaml
/api/docs/{docId}/comments:
  post:
    summary: "댓글 작성 ([[SYNC-UC-001#UC-H9]])"
    parameters:
    - $ref: '#/components/parameters/docId'
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - line_no
            - body
            properties:
              line_no:
                type: integer
                minimum: 1
              body:
                type: string
              parent_comment_id:
                type: integer
                nullable: true
    responses:
      '201':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Comment'
```

### 3.5 댓글

#### POST/api/comments/{id}/resolve 해결됨 표시 또는 되돌림

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H9]] · 서비스 `CommentService.resolve`

```yaml
/api/comments/{id}/resolve:
  post:
    summary: "해결됨 표시 또는 되돌림 ([[SYNC-UC-001#UC-H9]] 4, 4a)"
    parameters:
    - in: path
      name: id
      required: true
      schema:
        type: integer
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              resolved:
                type: boolean
                default: true
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Comment'
```

### 3.6 내 할 일·플래그·전파

#### GET/api/todo 내 할 일 여섯 묶음

화면 [[SYNC-UI-001#UI-10]] · 유스케이스 [[SYNC-UC-001#UC-H15]] · 서비스 `TrackingService.pending_for + 외`

```yaml
/api/todo:
  get:
    summary: "내 할 일 여섯 묶음 (UI-10, [[SYNC-UC-001#UC-H15]]). 별도 저장소 없이 직접 조회"
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Todo'
```

#### GET/api/flags/{id} 플래그 상세. 원인 diff(부여 시점 → 현재, 누적)와 내 항목 현재 본문

화면 [[SYNC-UI-001#UI-11]] · 유스케이스 [[SYNC-UC-001#UC-H11]] · 서비스 `TrackingService`

```yaml
/api/flags/{id}:
  get:
    summary: "플래그 상세. 원인 diff(부여 시점 → 현재, 누적)와 내 항목 현재 본문 (UI-11, [[SYNC-UC-001#UC-H11]])"
    parameters:
    - in: path
      name: id
      required: true
      schema:
        type: integer
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FlagDetail'
```

#### POST/api/flags/{id}/resolve 확인함

화면 [[SYNC-UI-001#UI-11]] · 유스케이스 [[SYNC-UC-001#UC-H11]] · 서비스 `TrackingService.resolve`

```yaml
/api/flags/{id}/resolve:
  post:
    summary: "확인함 (UI-11 요소 4.1, [[SYNC-UC-001#UC-H11]] 5~6). 수정 동반 여부는 서버가 판정"
    parameters:
    - in: path
      name: id
      required: true
      schema:
        type: integer
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FlagSummary'
```

#### GET/api/decisions/{versionId} 전파 미결정 상세. 변경 diff와 영향받는 하위 항목

화면 [[SYNC-UI-001#UI-12]] · 유스케이스 [[SYNC-UC-001#UC-H10]] · 서비스 `TrackingService`

```yaml
/api/decisions/{versionId}:
  get:
    summary: "전파 미결정 상세. 변경 diff와 영향받는 하위 항목 (UI-12, [[SYNC-UC-001#UC-H10]] 1)"
    parameters:
    - in: path
      name: versionId
      required: true
      schema:
        type: integer
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DecisionDetail'
```

#### POST/api/decisions/{versionId} 전파 결정

화면 [[SYNC-UI-001#UI-12]] · 유스케이스 [[SYNC-UC-001#UC-H10]] · 서비스 `TrackingService.record_decision`

```yaml
/api/decisions/{versionId}:
  post:
    summary: "전파 결정 (UI-12 요소 4·5, [[SYNC-UC-001#UC-H10]] 2·2a)"
    parameters:
    - in: path
      name: versionId
      required: true
      schema:
        type: integer
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - choice
            properties:
              choice:
                type: string
                enum:
                - propagate
                - skip
              reason:
                type: string
                description: skip이면 필수
    responses:
      '200':
        description: propagate면 붙은 플래그 수를 함께
        content:
          application/json:
            schema:
              type: object
              properties:
                choice:
                  type: string
                flags_raised:
                  type: integer
      '409':
        $ref: '#/components/responses/Problem'
      '422':
        $ref: '#/components/responses/Problem'
```

### 3.7 계정·토큰

#### GET/api/me 내 계정

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 — · 서비스 `—`

```yaml
/api/me:
  get:
    summary: 내 계정 (UI-13)
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/User'
```

#### GET/api/me/tokens 내 MCP 토큰 목록. 폐기된 것 포함, 원문 없음

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 인프라 5 · 서비스 `AccountService`

```yaml
/api/me/tokens:
  get:
    summary: 내 MCP 토큰 목록. 폐기된 것 포함, 원문 없음
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/AccessToken'
```

#### POST/api/me/tokens 토큰 발급. 원문은 이 응답에서만

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 인프라 5 · 서비스 `AccountService.issue_token`

```yaml
/api/me/tokens:
  post:
    summary: 토큰 발급. 원문은 이 응답에서만 (UI-13 다이얼로그 4)
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - label
            properties:
              label:
                type: string
                maxLength: 50
    responses:
      '201':
        content:
          application/json:
            schema:
              allOf:
              - $ref: '#/components/schemas/AccessToken'
              - type: object
                properties:
                  token:
                    type: string
                    description: 원문. 다시 볼 수 없다
```

#### DELETE/api/me/tokens/{id} 토큰 폐기. revoked_at 기록. 행은 남는다

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 인프라 5 · 서비스 `AccountService`

```yaml
/api/me/tokens/{id}:
  delete:
    summary: 토큰 폐기. revoked_at 기록. 행은 남는다
    parameters:
    - in: path
      name: id
      required: true
      schema:
        type: integer
    responses:
      '204':
        description: 폐기됨
```

### 3.8 관리

#### GET/api/admin/repos 저장소 동기화 상태

화면 [[SYNC-UI-001#UI-14]] · 유스케이스 [[SYNC-UC-001#UC-G1]] · 서비스 `—`

```yaml
/api/admin/repos:
  get:
    summary: 저장소 동기화 상태 (UI-14)
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/RepoStatus'
```

#### POST/api/admin/repos/{code}/rebuild 인덱스 재구축

화면 [[SYNC-UI-001#UI-14]] · 유스케이스 [[SYNC-UC-001#UC-S6]] · 서비스 `—`

```yaml
/api/admin/repos/{code}/rebuild:
  post:
    summary: "인덱스 재구축 (UI-14, [[SYNC-UC-001#UC-S6]]). 참조·버전·항목만. 플래그·전파결정·댓글은 그대로"
    parameters:
    - $ref: '#/components/parameters/code'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RebuildResult'
```

---

## 4. 스키마

엔드포인트 조각이 참조하는 `components`. 항목이 아니다.

```yaml
openapi: 3.1.0
info:
  title: SyncDoc Web API
  version: '1.0'
servers:
- url: /
security:
- session: []
components:
  securitySchemes:
    session:
      type: apiKey
      in: cookie
      name: syncdoc_session
  parameters:
    code:
      in: path
      name: code
      required: true
      schema:
        type: string
        pattern: ^[A-Z]{1,4}$
    docId:
      in: path
      name: docId
      required: true
      schema:
        type: string
        example: SYNC-PRD-001
    itemId:
      in: path
      name: itemId
      required: true
      schema:
        type: string
        example: R12
      description: '''#'' 없이. ''/''는 ''~''로'
  responses:
    Problem:
      description: RFC 9457
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
  schemas:
    DocStatus:
      type: string
      enum:
      - draft
      - review
      - approved
    DocType:
      type: string
      enum:
      - RFQ
      - PRD
      - SCN
      - UC
      - INFRA
      - DOM
      - UI
      - API
      - SEQ
      - MS
      - CODE
      - STD
    AuthorKind:
      type: string
      enum:
      - human
      - agent
    Problem:
      type: object
      required:
      - type
      - title
      - status
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
      additionalProperties: true
    UserRef:
      type: object
      properties:
        id:
          type: integer
        github_login:
          type: string
        display_name:
          type: string
    User:
      allOf:
      - $ref: '#/components/schemas/UserRef'
      - type: object
        properties:
          created_at:
            type: string
            format: date-time
    Author:
      type: object
      description: 버전의 작성 주체. 에이전트면 instructed_by가 있다
      properties:
        kind:
          $ref: '#/components/schemas/AuthorKind'
        user:
          $ref: '#/components/schemas/UserRef'
        instructed_by:
          $ref: '#/components/schemas/UserRef'
          nullable: true
        via:
          type: string
          enum:
          - mcp
          - web
          - github
          description: 어느 경로로 저장됐나
    StageSummary:
      type: object
      properties:
        stage:
          type: integer
        doc_type:
          $ref: '#/components/schemas/DocType'
        status:
          allOf:
          - $ref: '#/components/schemas/DocStatus'
          nullable: true
          description: "문서 여럿이면 가장 낮은 것([[SYNC-UC-001#UC-H14]] 1a). 없으면 null(3a)"
        doc_count:
          type: integer
        gate_warning:
          type: boolean
          description: 앞 단계에 미승인이 있는데 문서가 있다(1b)
    ProjectSummary:
      type: object
      properties:
        code:
          type: string
        name:
          type: string
        stages:
          type: array
          items:
            $ref: '#/components/schemas/StageSummary'
          minItems: 11
          maxItems: 11
          description: 11단계만. STD 문서는 여기 안 들어가고 std_docs로
        std_docs:
          type: array
          items:
            $ref: '#/components/schemas/DocumentSummary'
          description: 단계 밖 표준 문서. 싱크독 프로젝트에만 있다
        counts:
          type: object
          properties:
            needs_check:
              type: integer
            broken_ref:
              type: integer
            unresolved_comments:
              type: integer
            convention_errors:
              type: integer
        updated_at:
          type: string
          format: date-time
    ProjectDetail:
      allOf:
      - $ref: '#/components/schemas/ProjectSummary'
      - type: object
        properties:
          remote_url:
            type: string
          docs:
            type: array
            items:
              $ref: '#/components/schemas/DocumentSummary'
          recent_changes:
            type: array
            items:
              $ref: '#/components/schemas/Version'
            description: 최근 N건. status 커밋 포함
    DocumentSummary:
      type: object
      properties:
        doc_id:
          type: string
        doc_type:
          $ref: '#/components/schemas/DocType'
        stage:
          type: integer
        status:
          $ref: '#/components/schemas/DocStatus'
        current_version_no:
          type: integer
        has_convention_error:
          type: boolean
        incomplete_warnings:
          type: array
          items:
            type: string
          description: STD-001 4장 미완성 경고. 비어 있어야 approved 가능
        updated_at:
          type: string
          format: date-time
        last_author:
          $ref: '#/components/schemas/Author'
        counts:
          type: object
          properties:
            needs_check:
              type: integer
            broken_ref:
              type: integer
            unresolved_comments:
              type: integer
    Document:
      allOf:
      - $ref: '#/components/schemas/DocumentSummary'
      - type: object
        properties:
          body:
            type: string
            description: 원본 MD. 원본 탭이 그대로
            유저용 탭이 렌더링: null
          convention_error_detail:
            type: string
            nullable: true
          items:
            type: array
            description: 항목 ID·표시이름·플래그. 유저용 뷰가 뱃지를 붙일 때 쓴다
            items:
              type: object
              properties:
                item_id:
                  type: string
                display_name:
                  type: string
                flags:
                  type: array
                  items:
                    $ref: '#/components/schemas/FlagSummary'
          prev_doc_id:
            type: string
            nullable: true
            description: 단계 이동(UI-5 요소 9)
          next_doc_id:
            type: string
            nullable: true
    ItemRef:
      type: object
      properties:
        doc_id:
          type: string
        item_id:
          type: string
          nullable: true
          description: null이면 문서 전체 참조
        display_name:
          type: string
        raw_target:
          type: string
        is_missing:
          type: boolean
    ItemReferences:
      type: object
      properties:
        doc_id:
          type: string
        item_id:
          type: string
        upstream:
          type: array
          items:
            $ref: '#/components/schemas/ItemRef'
        downstream:
          type: array
          items:
            $ref: '#/components/schemas/ItemRef'
        flags:
          type: array
          items:
            $ref: '#/components/schemas/FlagSummary'
    Graph:
      type: object
      properties:
        nodes:
          type: array
          items:
            type: object
            properties:
              id:
                type: string
                example: SYNC-PRD-001#R1
              doc_id:
                type: string
              item_id:
                type: string
                nullable: true
              stage:
                type: integer
              isolated:
                type: boolean
                description: "참조 없음([[SYNC-UC-001#UC-H4]] 2a)"
        edges:
          type: array
          items:
            type: object
            properties:
              from:
                type: string
              to:
                type: string
                nullable: true
                description: 미존재면 null
              raw_target:
                type: string
              is_missing:
                type: boolean
    Version:
      type: object
      properties:
        doc_id:
          type: string
          description: 프로젝트 단위 목록(최근 변경)에서 문서를 가리키려고
        version_no:
          type: integer
          nullable: true
          description: status 커밋이면 null
        commit_hash:
          type: string
        message:
          type: string
          description: spec(...) 또는 status(...)
        author:
          $ref: '#/components/schemas/Author'
        created_at:
          type: string
          format: date-time
    Diff:
      type: object
      properties:
        from_version:
          type: integer
        to_version:
          type: integer
        hunks:
          type: array
          description: 항목 ID별로 묶음
          items:
            type: object
            properties:
              item_id:
                type: string
                nullable: true
              downstream_count:
                type: integer
                description: "[[SYNC-UC-001#UC-H6]] 3a"
              lines:
                type: array
                items:
                  type: object
                  properties:
                    op:
                      type: string
                      enum:
                      - add
                      - del
                      - ctx
                    text:
                      type: string
    SaveResult:
      type: object
      properties:
        doc_id:
          type: string
        version_no:
          type: integer
        commit_hash:
          type: string
        status:
          $ref: '#/components/schemas/DocStatus'
        pending_decision_version_id:
          type: integer
          nullable: true
          description: 하위 영향이 있어 전파 미결정이 생겼으면 그 버전 ID
        warnings:
          type: array
          items:
            type: string
          description: 미완성 경고(STD-001 4장). 저장은 됐고 approved만 막힌다

    Comment:
      type: object
      properties:
        id:
          type: integer
        doc_id:
          type: string
        line_no:
          type: integer
        original_location:
          type: string
          nullable: true
          description: 줄을 못 찾았을 때 "v3:12"
        body:
          type: string
        author:
          $ref: '#/components/schemas/UserRef'
        is_resolved:
          type: boolean
        created_at:
          type: string
          format: date-time
        replies:
          type: array
          items:
            $ref: '#/components/schemas/Comment'
    FlagSummary:
      type: object
      properties:
        id:
          type: integer
        kind:
          type: string
          enum:
          - needs_check
          - broken_ref
          - upstream_impact
        target:
          $ref: '#/components/schemas/ItemRef'
        cause:
          $ref: '#/components/schemas/ItemRef'
          nullable: true
        cause_version_no:
          type: integer
        assignee:
          $ref: '#/components/schemas/UserRef'
          nullable: true
        raised_at:
          type: string
          format: date-time
        resolved_at:
          type: string
          format: date-time
          nullable: true
    FlagDetail:
      allOf:
      - $ref: '#/components/schemas/FlagSummary'
      - type: object
        properties:
          cause_diff:
            allOf:
            - $ref: '#/components/schemas/Diff'
            description: "부여 시점 → 현재. 그 사이 또 바뀌었으면 누적([[SYNC-UC-001#UC-H11]] 3a)"
          cause_change_count:
            type: integer
          target_body:
            type: string
            description: 내 항목 블록의 현재 본문
          target_changed_since_raise:
            type: boolean
            description: 확인 시 수정 동반 여부로 기록된다(3b)
    DecisionDetail:
      type: object
      properties:
        version:
          $ref: '#/components/schemas/Version'
        doc_id:
          type: string
        change_diff:
          $ref: '#/components/schemas/Diff'
        affected:
          type: array
          items:
            allOf:
            - $ref: '#/components/schemas/ItemRef'
            - type: object
              properties:
                caused_by_items:
                  type: array
                  items:
                    type: string
                assignee:
                  $ref: '#/components/schemas/UserRef'
                  nullable: true
        choice:
          type: string
          enum:
          - propagate
          - skip
          - undecided
    CommentSummary:
      type: object
      properties:
        id:
          type: integer
        doc_id:
          type: string
        line_no:
          type: integer
        excerpt:
          type: string
        author:
          $ref: '#/components/schemas/UserRef'
        created_at:
          type: string
          format: date-time
    Todo:
      type: object
      description: UI-10 여섯 묶음. 각각 경과일 내림차순
      properties:
        needs_check:
          type: array
          items:
            $ref: '#/components/schemas/FlagSummary'
        broken_ref:
          type: array
          items:
            $ref: '#/components/schemas/FlagSummary'
        upstream_impact:
          type: array
          items:
            $ref: '#/components/schemas/FlagSummary'
          description: 내 항목이 하위와 어긋났다고 지목된 플래그 (UI-10 묶음 9)
        pending_decisions:
          type: array
          items:
            type: object
            properties:
              version_id:
                type: integer
              doc_id:
                type: string
              version_no:
                type: integer
              message:
                type: string
              affected_count:
                type: integer
              created_at:
                type: string
                format: date-time
        convention_errors:
          type: array
          items:
            $ref: '#/components/schemas/DocumentSummary'
        unresolved_comments:
          type: array
          items:
            $ref: '#/components/schemas/CommentSummary'
        unassigned:
          type: array
          items:
            $ref: '#/components/schemas/FlagSummary'
        total:
          type: integer
          description: unassigned 제외. 상단 바 배지
    AccessToken:
      type: object
      properties:
        id:
          type: integer
        label:
          type: string
        issued_at:
          type: string
          format: date-time
        expires_at:
          type: string
          format: date-time
          nullable: true
        revoked_at:
          type: string
          format: date-time
          nullable: true
    RepoStatus:
      type: object
      properties:
        code:
          type: string
        remote_url:
          type: string
        last_processed_commit:
          type: string
          nullable: true
        synced_at:
          type: string
          format: date-time
          nullable: true
        behind_by:
          type: integer
          description: 처리 안 한 원격 커밋 수. 0이면 최신
    RebuildResult:
      type: object
      properties:
        docs:
          type: integer
        items:
          type: integer
        references:
          type: integer
        versions:
          type: integer
        convention_errors:
          type: array
          items:
            type: object
            properties:
              doc_id:
                type: string
              detail:
                type: string
```

---

## 5. 판단이 필요한 지점

**1. `/api/docs/{docId}`가 원본과 뷰 데이터를 한 번에 준다.** `body`(원본)와 `items`(뱃지용)를 같이 보내고 렌더링은 React가 한다. 문서가 커지면 분리할 수 있으나 지금은 한 번에.

**2. `/api/todo`가 다섯 테이블을 조회한다.** 응답 하나에 여섯 묶음이 들어간다. 느리면 묶음별 엔드포인트로 쪼갤 수 있으나, UI-10이 한 화면이라 한 번에 받는 게 맞다.

**3. 되돌리기(revert)가 웹에 남은 유일한 본문 쓰기다.** MCP `update_document`와 같은 파이프라인·같은 에러(`convention-violation`, `push-failed`)를 낸다. 다른 응답 형식을 만들지 않는다.

**4. 그래프 응답에 좌표가 없다.** 배치는 브라우저가 한다. 서버는 노드·간선만.

---

## 6. 미결사항

- [x] `/api/projects/{code}/flags` 응답이 `oneOf`라 클라이언트가 `kind`별로 분기해야 한다. 엔드포인트를 넷으로 쪼갤지 — 결정: 쪼개지 않고 응답에 **판별 필드**를 넣는다. 세 스키마 (`FlagSummary`·`CommentSummary`·`DocumentSummary`)에 각각 고정값 `type`을 두면 클라이언트가 구분 유니온으로 받는다. 지금 프런트는 응답을 `unknown[]`으로 받아 `kind` 문자열로 갈라 세 번 강제 형변환한다
- [x] 되돌리기·상태 변경의 `Author.via`를 `web`으로 기록할 때 `kind`는 `human`. `agent`는 MCP·GitHub push(에이전트 커밋)에서만 — 결정: 그대로 간다. `types.fold_via`가 `web_revert`·`web_status`를 `web`으로 접고 `kind=human`으로 기록
- [x] `Todo.unresolved_comments`의 "내 문서" 기준 — 클래스 명세 미결(`flags.assignee`)과 같은 문제 — 결정: 최근 버전 작성자. `flags.assignee`와 같은 기준(DOM-002 5장 1). `SpecService.documents_authored_by`
