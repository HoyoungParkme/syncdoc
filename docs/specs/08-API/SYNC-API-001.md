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
- 목록은 페이지 없음. 한 사람이 쓰는 프로젝트의 문서가 수십 개다
- **프로젝트는 등록한 사람의 것이다**([[SYNC-PRD-001#R12]]). 목록(`GET /api/projects`·`GET /api/admin/repos`)은 내가 소유한 것만 준다. 소유하지 않은 프로젝트를 코드나 문서 ID로 열면 **없는 것과 같다** — `404 urn:syncdoc:not-found {resource: "project", id: code}`. 403이 아니다: 남의 프로젝트가 있다는 사실이 새지 않고, 에러 종류가 늘지 않는다. 프로젝트나 문서를 고르는 모든 엔드포인트가 그렇다 — 아래 각 정의의 404는 「없음」과 「남의 것」을 구분하지 않는다

- **스트리밍은 `POST /api/docs/{docId}/ask` 하나다**(SSE, `text/event-stream`). 첫 이벤트(`start`) 전에 난 오류는 지금처럼 HTTP 상태 코드로, 뒤에 난 오류는 `error` 이벤트로 온다. 규칙 한 줄 — **첫 이벤트 전은 상태 코드, 뒤는 이벤트**

**웹이 쓰지 않는 것** — 본문 생성·수정 엔드포인트는 없다. 본문 쓰기는 MCP와 GitHub push뿐이다(PRD R9). 웹의 쓰기는 상태 토글·되돌리기·휴지통·토큰·재구축까지다.

---

## 2. 에러

`application/problem+json`. 공통 필드 `type`, `title`, `status`, `detail`. 종류별 확장 필드:

**표에 없는 예외도 problem+json으로 나간다.** 서버는 포괄 핸들러로 `urn:syncdoc:internal`(500)을 만든다. `detail`에는 짧은 고정 문구만 담고 예외 종류·메시지·스택은 로그로만 보낸다 — 클라이언트가 problem+json을 전제로 파싱하는데 평문 500이 나가면 오류를 읽지도 못한다.

| type | status | 언제 | 확장 필드 | 유스케이스 |
|---|---|---|---|---|
| `urn:syncdoc:unauthorized` | 401 | 세션 없음 | — | — |
| `urn:syncdoc:not-found` | 404 | 문서·항목·프로젝트·파일 없음 | `resource`, `id` | [[SYNC-UC-001#UC-A2]] 1a |
| `urn:syncdoc:item-deleted` | 410 | 삭제된 항목 조회 | `deleted_at` | [[SYNC-UC-001#UC-A3]] 1a |
| `urn:syncdoc:convention-violation` | 422 | 규약 위반 (되돌리기 시) | `violations: [{line, rule, message}]`, `warnings: [{rule, message}]` | [[SYNC-UC-001#UC-S1]] 4a, [[SYNC-UC-001#UC-H7]] 4a |
| `urn:syncdoc:version-conflict` | 409 | 버전 불일치 | `current_version`, `current_body` | [[SYNC-UC-001#UC-A6]] 4a |
| `urn:syncdoc:status-blocked` | 409 | 규약 오류·미완성 경고·끊어진 참조가 있는 문서를 `approved`로 | `convention_error_detail`, `warnings` — `warnings`에는 `ref.missing: {대상}`이 섞일 수 있다. **컬럼에 있는 값이 아니라 읽을 때 센 값이다**([[SYNC-STD-001]] 4장) | [[SYNC-UC-001#UC-H8]] 1a |
| `urn:syncdoc:item-deletion-needs-confirm` | 409 | 되돌리기로 항목이 사라지고 하위 참조 있음 | `deleted_items: [{item_id, downstream}]` | [[SYNC-UC-001#UC-H7]], [[SYNC-UC-001#UC-A6]] 4b |
| `urn:syncdoc:project-code-conflict` | 409 | 코드 중복 | `code` | [[SYNC-UC-001#UC-A1]] 2a |
| `urn:syncdoc:project-code-invalid` | 422 | 코드 형식 | `rule` | [[SYNC-UC-001#UC-A1]] 2b |
| `urn:syncdoc:existing-specs` | 409 | `docs/specs/` 이미 있음 | `doc_count` | [[SYNC-UC-001#UC-A1]] 3a |
| `urn:syncdoc:repo-create-failed` | 502 | `create_repo`로 저장소를 못 만듦 — 이름 규칙·권한·다른 소유자 점유 | `reason` | [[SYNC-CODE-001#F]] |
| `urn:syncdoc:push-failed` | 502 | GitHub push 실패 | `reason` | [[SYNC-UC-001#UC-A1]] 4a, [[SYNC-UC-001#UC-S7]] 2b |
| `urn:syncdoc:already-current` | 422 | 현재 버전으로 되돌리기 | — | [[SYNC-UC-001#UC-H7]] |
| `urn:syncdoc:document-has-history` | 409 | 휴지통의 문서를 완전 삭제하려는데 아직 다른 문서가 가리킴 | `inbound_refs: [문서ID#항목ID…]` | [[SYNC-UC-001#UC-H18]] 7 |
| `urn:syncdoc:document-trashed` | 409 | 휴지통에 있는 문서를 저장·상태 변경·다시 휴지통에 넣으려 함 | `trashed_at` | [[SYNC-UC-001#UC-A7]] 1a |
| `urn:syncdoc:document-not-trashed` | 409 | 휴지통에 없는 문서를 되살리거나 완전 삭제하려 함 | — | [[SYNC-UC-001#UC-A8]] 1a |
| `urn:syncdoc:rebuild-failed` | 500 | 재구축 중 실패, 롤백됨 | `reason` | [[SYNC-UC-001#UC-S6]] |
| `urn:syncdoc:repository-already-registered` | 409 | 이미 등록된 저장소 | `code` (그 저장소를 쓰는 프로젝트) | [[SYNC-UC-001#UC-A1]] 2d |
| `urn:syncdoc:email-taken` | 409 | 남이 이미 등록한 커밋 이메일 | `email` | UI-13 2.6 |
| `urn:syncdoc:not-implemented` | 501 | 카드 스텁 — 아직 구현 안 된 경로 (`import_existing` 등). 슬라이스 진행 중에만 존재 | `card` | [[SYNC-STD-004#DEV-12]] |
| `urn:syncdoc:llm-not-configured` | 503 | 모델 키가 없다 — 읽는 중 질의가 꺼져 있다 | — | [[SYNC-UC-001#UC-H19]] 2a |
| `urn:syncdoc:llm-unavailable` | 502 | 모델 호출 실패. **사용량 초과도 여기 접힌다.** 스트림 중이면 `error` 이벤트로 온다(1장) | `reason` | [[SYNC-UC-001#UC-H19]] 4a |
| `urn:syncdoc:internal` | 500 | **예상 못 한 오류.** 위 어느 것도 아닌 예외가 라우터에서 샜다 | — | — |

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

화면 [[SYNC-UI-001#UI-2]] · 유스케이스 [[SYNC-UC-001#UC-H14]] · 서비스 [[SYNC-MS-001#ProjectService.list_owned]] → [[SYNC-MS-008#queries.project_summary]]

```yaml
/api/projects:
  get:
    summary: 프로젝트 목록과 단계 요약 (UI-2). 내가 소유한 것만 — 없으면 빈 배열
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
    summary: "프로젝트 초기화 (UI-3, [[SYNC-UC-001#UC-A1]]). 등록하는 사람이 소유자가 된다 ([[SYNC-PRD-001#R12]])"
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
              create_repo:
                type: boolean
                default: false
                description: "저장소가 없으면 공개 저장소로 만든다. 이미 있으면 만들지 않는다 ([[SYNC-CODE-001#F]])"
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

#### DELETE/api/projects/{code} 프로젝트 등록 해제

화면 [[SYNC-UI-002#UI-14]] 7(해제) · 유스케이스 [[SYNC-UC-001#UC-H17]] · 서비스 [[SYNC-MS-001#ProjectService.delete_project]] · GitHub 저장소는 손대지 않는다

```yaml
/api/projects/{code}:
  delete:
    summary: 프로젝트 등록을 지우고 작업 사본을 회수한다
    parameters:
    - $ref: '#/components/parameters/code'
    responses:
      '204':
        description: 지워짐
      '404':
        $ref: '#/components/responses/Problem'
```

**저장소는 건드리지 않는다.** 지우는 것은 싱크독 쪽 등록과 색인, 그리고 노트북의 작업 사본이다.
`docs/specs/`는 원격에 그대로 남고, 다시 등록하면 `import_existing`으로 돌아온다.

**돌아오지 않는 것이 있다.** 상태 변경 이력은 원본에 없는 정보라 등록을 지우면 사라진다(인프라 6장).
상태 자체는 frontmatter에 있어 돌아온다.

이 엔드포인트가 없을 때는 한 번 등록한 저장소가 디스크에서 사라지지 않았다. 작업 사본은 전체
이력 clone이라 쌓이면 노트북 디스크를 채운다(인프라 9장).

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

#### GET/api/projects/{code}/flags 프로젝트의 끊어진 참조·규약 오류·미완성 목록

화면 [[SYNC-UI-001#UI-4]] · 유스케이스 [[SYNC-UC-001#UC-H14]] · 서비스 [[SYNC-MS-008#queries.project_items]]

```yaml
/api/projects/{code}/flags:
  get:
    summary: 프로젝트의 끊어진 참조·규약 오류·미완성 목록 (UI-4 다이얼로그 6)
    parameters:
    - $ref: '#/components/parameters/code'
    - in: query
      name: kind
      required: true
      schema:
        type: string
        enum:
        - broken_ref
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
                - $ref: '#/components/schemas/BrokenRefSummary'
                - $ref: '#/components/schemas/DocumentSummary'
                discriminator:
                  propertyName: type
```

**두 스키마에 판별 필드 `type`이 있다.** `BrokenRefSummary`는 `"broken_ref"`, `DocumentSummary`는 `"document"`. 고정값이고 서버가 늘 채운다.

이게 없으면 클라이언트가 `kind` 문자열로 어느 타입인지 되짚어야 한다 — 그 지식이 서버와 클라이언트 두 곳에 생기고, 서버가 `kind`를 늘려도 컴파일이 못 잡는다. 엔드포인트를 쪼개는 것보다 이쪽이 싸다([[SYNC-API-001]] 6장).

**경로 이름은 `flags`로 남았다.** 플래그가 사라진 뒤에도 바꾸지 않았다 — 경로가 곧 항목 ID라 바꾸면 은퇴와 신설이 되고, 화면·미니스펙·React가 같이 움직인다. 끊어진 참조는 `references.is_missing`에서 센다([[SYNC-MS-003#ReferenceService.mark_missing]]).

#### GET/api/projects/{code}/files/{path} 첨부 파일

화면 [[SYNC-UI-001#UI-5]](배치 iframe 안의 이미지·폰트) · 요구사항 [[SYNC-PRD-001#R5]] · 서비스 [[SYNC-MS-001#ProjectService.asset_path]]

```yaml
/api/projects/{code}/files/{path}:
  get:
    summary: "첨부 파일 — 작업 사본 docs/specs/ 아래 (카드 Z)"
    parameters:
    - $ref: '#/components/parameters/code'
    - in: path
      name: path
      required: true
      schema:
        type: string
      description: >
        docs/specs/ 기준 상대 경로. 슬래시를 포함한다(path:path).
        허용 확장자는 png jpg jpeg gif webp svg css woff woff2 ttf —
        문서(.md)는 이 길로 주지 않는다
    responses:
      '200':
        description: 파일 그대로. Content-Type은 확장자로 정한다
        headers:
          Cache-Control:
            schema:
              type: string
            description: "private, max-age=60"
          Content-Security-Policy:
            schema:
              type: string
            description: "svg일 때만 sandbox — 직접 열어도 스크립트가 앱 출처에서 돌지 않는다"
      '401':
        $ref: '#/components/responses/Problem'
      '404':
        $ref: '#/components/responses/NotFound'
```

**문서 폴더 기준 상대 경로가 그대로 통한다.** 화면 배치를 그리는 iframe에 `<base href="/api/projects/{code}/files/07-UI/">`가 들어가므로, 문서가 `../assets/x.png`라고 쓰면 브라우저가 `/api/projects/{code}/files/assets/x.png`로 푼다([[SYNC-STD-002]] V-UI). 경로 밖(`..`으로 `docs/specs/`를 벗어남·바깥 심볼릭 링크)은 `404 not-found {resource: "file"}` — 있는지 없는지를 구분하지 않는다. 남의 프로젝트는 여느 엔드포인트처럼 `not-found {resource: "project"}`.

#### GET/api/projects/{code}/graph 참조 그래프

화면 [[SYNC-UI-001#UI-8]] · 유스케이스 [[SYNC-UC-001#UC-H4]] · 서비스 [[SYNC-MS-008#queries.graph_view]]

```yaml
/api/projects/{code}/graph:
  get:
    summary: "참조 그래프 (UI-8, [[SYNC-UC-001#UC-H4]])"
    parameters:
    - $ref: '#/components/parameters/code'
    - in: query
      name: scope
      schema:
        type: string
        enum: [all, approved]
        default: all
      description: >
        무엇을 그릴지 고른다 (2b). all=전체 ·
        approved=문서 상태가 완료인 문서의 항목만.
        범위 밖 항목을 가리키는 참조는 그리지 않는다 — 미존재 참조와 다르다
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Graph'
```

**`stage`·`doc`은 v1.2에서 없앴다.** 단계로 좁혀도 한 걸음이면 문서 대부분에 닿아 좁힌 의미가
없었다([[SYNC-UI-001#UI-8]] 7장 3). 범위는 잘라내는 조작에서 **골라내는** 조작이 됐다.

#### GET/api/docs/{docId}/items/{itemId}/chain 항목의 11단계 체인

화면 [[SYNC-UI-001#UI-15]] · 유스케이스 [[SYNC-UC-001#UC-H4]] 기본 흐름 3 · 서비스 [[SYNC-MS-008#queries.item_chain]]

```yaml
/api/docs/{docId}/items/{itemId}/chain:
  get:
    summary: "한 항목의 상·하위 전이적 폐포를 11단계로 (UI-15)"
    parameters:
    - $ref: '#/components/parameters/docId'
    - $ref: '#/components/parameters/itemId'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ItemChain'
      '404':
        $ref: '#/components/responses/NotFound'
```

**직접 참조가 아니라 전이적 폐포다.** 상위 방향과 하위 방향으로 각각 너비 우선 탐색을 돌린다.
응답은 **항상 11행**이고 항목이 없는 단계도 빈 채로 온다 — 체인이 어디서 끊겼는지 화면이 보여야
하기 때문이다. 각 항목의 역할(`upstream`/`self`/`downstream`)은 **어느 폐포에서 나왔는지**로
정한다. 단계 번호로 정하면 되돌아오는 참조에서 근거를 파생으로 잘못 적는다.

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

#### GET/api/docs/{docId}/items/{itemId}/references 항목의 상위·하위 참조

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H3]] · 서비스 `ReferenceService`

```yaml
/api/docs/{docId}/items/{itemId}/references:
  get:
    summary: "항목의 상위·하위 참조 (UI-5 패널 8.1, [[SYNC-UC-001#UC-H3]])"
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

#### POST/api/docs/{docId}/status 상태 변경

화면 [[SYNC-UI-001#UI-5]] · 유스케이스 [[SYNC-UC-001#UC-H8]] · 서비스 [[SYNC-MS-007#pipeline.change_status]]

```yaml
/api/docs/{docId}/status:
  post:
    summary: "상태 토글 — 초안 ⇄ 완료 (UI-5 요소 3, [[SYNC-UC-001#UC-H8]])"
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
                description: 선택. 이력(UI-7)에 남는다
    responses:
      '200':
        description: 바뀐 상태. frontmatter 갱신 커밋(status 접두어)이 함께 생긴다. 완료로 올릴 때 규약 오류·미완성·끊어진 참조가 있으면 409 status-blocked
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

#### DELETE/api/docs/{docId} 휴지통에 넣기

화면 [[SYNC-UI-002#UI-5]] 12·13 · 유스케이스 [[SYNC-UC-001#UC-H18]] 1~3 · 서비스 [[SYNC-MS-007#pipeline.trash_document]] · 확인은 화면(13)이 받으므로 인자가 없다

```yaml
/api/docs/{docId}:
  delete:
    summary: 파일을 저장소에서 지우고 문서를 휴지통에 표시한다. 행·버전은 남는다 (PRD N3)
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TrashResult'
      '404':
        $ref: '#/components/responses/Problem'
      '409':
        description: document-trashed (이미 휴지통)
        $ref: '#/components/responses/Problem'
      '502':
        $ref: '#/components/responses/Problem'
```

이 문서를 가리키던 참조는 미존재(`is_missing`)로 돌아간다 — 참조 패널과 UI-4 수치가 그것을 보여준다. 되살리면 다시 이어진다.

#### POST/api/docs/{docId}/restore 휴지통에서 되살리기

화면 [[SYNC-UI-002#UI-4]] 8.2 · [[SYNC-UI-002#UI-5]] 4b.1 · 유스케이스 [[SYNC-UC-001#UC-H18]] 4~5 · 서비스 [[SYNC-MS-007#pipeline.restore_document]]

```yaml
/api/docs/{docId}/restore:
  post:
    summary: 휴지통 커밋 직전 내용으로 새 버전을 만들고 휴지통 표시를 지운다
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '201':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SaveResult'
      '404':
        $ref: '#/components/responses/Problem'
      '409':
        description: document-not-trashed
        $ref: '#/components/responses/Problem'
      '422':
        description: convention-violation — 옛 본문이 지금 규약을 위반
        $ref: '#/components/responses/Problem'
      '502':
        $ref: '#/components/responses/Problem'
```

#### POST/api/docs/{docId}/purge 완전 삭제

화면 [[SYNC-UI-002#UI-4]] 8.3·8.4 · 유스케이스 [[SYNC-UC-001#UC-H18]] 6~8 · 서비스 [[SYNC-MS-007#pipeline.purge_document]] · 휴지통 안에서만

```yaml
/api/docs/{docId}/purge:
  post:
    summary: 휴지통의 문서를 행까지 지운다. 되돌릴 수 없다
    parameters:
    - $ref: '#/components/parameters/docId'
    responses:
      '204':
        description: 행이 사라짐. 번호는 다시 쓰일 수 있다 (STD-001 1.1)
      '404':
        $ref: '#/components/responses/Problem'
      '409':
        description: document-not-trashed · document-has-history
        $ref: '#/components/responses/Problem'
```

**막는 것** — 다른 문서에서 들어오는 참조(미존재로 남아 있는 것 포함). 있으면 `409 document-has-history`에 그 목록. 그 문서에 딸린 나머지(상태 변경·버전·항목·이 문서에서 나가는 참조)는 문서와 함께 지운다.

#### GET/api/projects/{code}/trash 휴지통 목록

화면 [[SYNC-UI-002#UI-4]] 8 · 서비스 [[SYNC-MS-008#queries.trash_list]]

```yaml
/api/projects/{code}/trash:
  get:
    summary: 휴지통에 있는 문서 (trashed_at 내림차순)
    parameters:
    - $ref: '#/components/parameters/code'
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/DocumentSummary'
```

#### POST/api/docs/{docId}/ask 읽다가 묻는다 — 모델이 관계도를 따라 읽는다

화면 [[SYNC-UI-001#UI-5]] 8.5~8.9 · 유스케이스 [[SYNC-UC-001#UC-H19]] · 서비스 `queries.ask_item`

**문서가 시작점이고 항목은 힌트다.** `item_id`를 주면 「지금 보는 항목」으로 맥락에 한 줄 실릴 뿐, 없어도 묻는다. 모델은 같은 프로젝트의 문서·항목·참조를 읽기 도구로 스스로 읽고([[SYNC-INFRA-001]] 5.3), 무엇을 왜 읽는지가 이벤트로 차례로 온다. 도구 호출은 8번, 전체 120초까지 — 넘으면 그때까지 읽은 것으로 답한다.

**아무것도 저장하지 않는다.** 대화는 클라이언트가 들고 있다가 요청마다 `history`로 통째로 보낸다. 서버는 `LLM_MAX_TURNS`턴까지만 받는다. 키가 없으면 `llm-not-configured`이고 화면은 탭 자체를 감춘다(`GET /api/me`의 `llm_enabled`).

**응답은 SSE다.** `200 text/event-stream`, 헤더 `Cache-Control: no-cache` · `X-Accel-Buffering: no`. 프레임은 `event: {이름}\ndata: {JSON}\n\n`. 이벤트 다섯:

| 이벤트 | data | 언제 |
|---|---|---|
| `start` | `AskStart {doc_id, item_id}` | 시작 맥락 조립 직후, 첫 모델 호출 전. **이 앞의 오류(404·503·401)는 HTTP 상태 코드** |
| `note` | `AskNote {text}` | 모델이 읽기 전에 쓴 한 줄(도구 인자 `reason`). 도구마다 하나 |
| `read` | `AskRead {tool, target}` | 도구 실행이 끝났다. `target`은 `DOC#ITEM`·`DOC`, 목록이면 null |
| `answer` | `AskAnswer {answer, context_item_ids}` | 마지막. 스트림 종료 |
| `error` | problem+json 본문 그대로 `{type, title, status, detail, reason?}` | 루프 중 실패(`llm-unavailable` 등). 스트림 종료 |

```yaml
/api/docs/{docId}/ask:
  post:
    summary: "읽는 중 질의 ([[SYNC-UC-001#UC-H19]]) — SSE"
    parameters:
    - $ref: '#/components/parameters/docId'
    requestBody:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/AskRequest'
    responses:
      '200':
        description: 이벤트 스트림. start → (note·read)* → answer | error
        content:
          text/event-stream:
            schema:
              oneOf:
              - $ref: '#/components/schemas/AskStart'
              - $ref: '#/components/schemas/AskNote'
              - $ref: '#/components/schemas/AskRead'
              - $ref: '#/components/schemas/AskAnswer'
      '404':
        description: 문서 없음 · 소유하지 않은 프로젝트 · item_id가 이 문서에 없음
      '503':
        description: llm-not-configured
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
              $ref: '#/components/schemas/Me'
```

#### GET/api/me/emails 내 커밋 이메일 목록

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 [[SYNC-UC-001#UC-G1]] · 서비스 `AccountService.commit_emails`

```yaml
/api/me/emails:
  get:
    summary: 내 커밋 이메일 목록 (UI-13 요소 2.3)
    responses:
      '200':
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/CommitEmail'
```

#### POST/api/me/emails 커밋 이메일 등록

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 [[SYNC-UC-001#UC-G1]] · 서비스 `AccountService.add_commit_email`

```yaml
/api/me/emails:
  post:
    summary: 커밋 이메일 등록 (UI-13 요소 2.6). 이미 내 것이면 그 행을 돌려준다
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
            - email
            properties:
              email:
                type: string
                format: email
                maxLength: 255
    responses:
      '201':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CommitEmail'
      '409':
        $ref: '#/components/responses/Problem'
      '422':
        $ref: '#/components/responses/Problem'
```

#### DELETE/api/me/emails/{id} 커밋 이메일 삭제. 행이 사라진다

화면 [[SYNC-UI-001#UI-13]] · 유스케이스 [[SYNC-UC-001#UC-G1]] · 서비스 `AccountService.remove_commit_email`

```yaml
/api/me/emails/{id}:
  delete:
    summary: 커밋 이메일 삭제 (UI-13 요소 2.4). 남의 것이면 404 — 있는지 없는지 안 알려준다
    parameters:
    - in: path
      name: id
      required: true
      schema:
        type: integer
    responses:
      '204':
        description: 삭제됨
      '404':
        $ref: '#/components/responses/Problem'
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

화면 [[SYNC-UI-001#UI-14]] · 유스케이스 [[SYNC-UC-001#UC-G1]] · 서비스 [[SYNC-MS-001#ProjectService.repo_status]]

```yaml
/api/admin/repos:
  get:
    summary: 저장소 동기화 상태 (UI-14). 내가 소유한 저장소만
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

화면 [[SYNC-UI-001#UI-14]] · 유스케이스 [[SYNC-UC-001#UC-S6]] · 서비스 [[SYNC-MS-001#ProjectService.rebuild_index]]

```yaml
/api/admin/repos/{code}/rebuild:
  post:
    summary: "인덱스 재구축 (UI-14, [[SYNC-UC-001#UC-S6]]). 저장소의 README가 낡았으면 새 판으로 커밋한 뒤, 참조·버전·항목을 저장소에서 다시 만든다. 소유자만"
    parameters:
    - $ref: '#/components/parameters/code'
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RebuildResult'
      '404':
        $ref: '#/components/responses/Problem'
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
      - approved
      description: 초안 · 완료. 값 이름은 옛것을 그대로 쓴다 — 저장소 frontmatter가 그 값이다
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
    Me:
      description: 내 계정. User에 화면이 켜고 끌 것을 얹는다 — llm_enabled가 거짓이면 UI-5 질문 탭(8.4)이 없다([[SYNC-INFRA-001]] 5.3)
      allOf:
      - $ref: '#/components/schemas/User'
      - type: object
        properties:
          llm_enabled:
            type: boolean
            description: 서버에 LLM_API_KEY가 있는가. 로그인 때 이미 부르는 응답이라 요청이 늘지 않는다
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
          description: 앞 단계에 미완료가 있는데 문서가 있다(1b)
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
            broken_ref:
              type: integer
              description: 대상이 없는 참조(references.is_missing) 수
            convention_errors:
              type: integer
            incomplete:
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
          last_processed_commit:
            type: string
            nullable: true
            description: 파이프라인이 마지막으로 처리한 커밋 (UI-4 요소 7.1)
          behind_by:
            type: integer
            nullable: true
            description: >
              원격이 앞선 커밋 수 (UI-4 요소 7.2). 폴링이 DB에 적어 둔 값을 그대로 읽는다 —
              이 응답을 만들 때 git fetch를 돌리지 않는다
    DocumentSummary:
      type: object
      properties:
        trashed_at:
          type: string
          format: date-time
          nullable: true
          description: 휴지통에 넣은 시각. 목록(GET …/docs)에는 안 나오고 GET …/trash와 문서 조회에만 값이 찬다
        type:
          type: string
          enum: [document]
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
            broken_ref:
              type: integer
              description: 이 문서에서 나가는 참조 중 대상이 없는 것
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
            description: 항목 ID·표시이름·미존재 참조. 유저용 뷰가 목차(UI-5 6.1)와 뱃지를 만들 때 쓴다
            items:
              type: object
              properties:
                item_id:
                  type: string
                display_name:
                  type: string
                missing_refs:
                  type: array
                  items:
                    type: string
                  description: 이 항목에서 나간 참조 중 대상이 없는 것의 raw_target. 비어 있으면 뱃지 없음
          prev_doc_id:
            type: string
            nullable: true
            description: 단계 이동(UI-5 요소 9)
          next_doc_id:
            type: string
            nullable: true
          project_name:
            type: string
            description: 브레드크럼 첫 조각(UI-5 요소 1). 코드가 아니라 사람이 부르는 이름
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
    Graph:
      type: object
      properties:
        project_name:
          type: string
          description: 브레드크럼(UI-8 요소 1)
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
        warnings:
          type: array
          items:
            type: string
        next_step:
          type: string
          nullable: true
          description: 에이전트가 다음에 할 일 한 문장 — 사람에게 웹에서 읽으라고 하고 멈춘다(STD-001 1.8). MCP 경로만. 웹 되돌리기는 null
    TrashResult:
      type: object
      properties:
        doc_id:
          type: string
        commit_hash:
          type: string
        broken_refs:
          type: integer
          description: 이 문서 항목을 가리키던 참조 중 미존재로 돌아간 수
        next_step:
          type: string
          nullable: true
          description: 미완성 경고(STD-001 4장). 저장은 됐고 approved만 막힌다

    BrokenRefSummary:
      type: object
      description: 대상이 없는 참조 하나. UI-4 다이얼로그 6의 행
      properties:
        type:
          type: string
          enum: [broken_ref]
        source:
          $ref: '#/components/schemas/ItemRef'
          description: 참조하는 쪽 — 이 프로젝트의 항목
        raw_target:
          type: string
          description: 본문에 적힌 대상 그대로. 아직 안 쓰였거나 지워진 것
    CommitEmail:
      type: object
      description: >
        내가 git 커밋에 쓰는 이메일. GitHub 직접 push로 들어온 커밋을 내 계정으로 잇는 단서다.
        등록만으로는 이미 쌓인 버전이 안 옮겨진다 — 인덱스 재구축을 한 번 돌려야 한다
      properties:
        id:
          type: integer
        email:
          type: string
          format: email
        added_at:
          type: string
          format: date-time
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
        last_used_at:
          type: string
          format: date-time
          nullable: true
          description: >
            이 토큰으로 마지막에 들어온 시각 (UI-13 요소 3.5). null이면 한 번도 안 씀.
            만료가 없으므로 안 쓰는 토큰을 찾는 단서가 이것뿐이다
    ItemChain:
      type: object
      properties:
        item:
          $ref: '#/components/schemas/ItemRef'
        upstream_count:
          type: integer
          description: 상위 방향으로 전이적으로 닿는 항목 수
        downstream_count:
          type: integer
          description: 하위 방향으로 전이적으로 닿는 항목 수
        rows:
          type: array
          description: >
            항상 11개. 1단계부터 11단계까지 차례로.
            항목이 없는 단계도 빈 배열로 온다 — 체인이 어디서 끊겼는지 화면이 보여야 한다
          items:
            type: object
            properties:
              stage:
                type: integer
              doc_type:
                type: string
              items:
                type: array
                items:
                  type: object
                  properties:
                    ref:
                      $ref: '#/components/schemas/ItemRef'
                    role:
                      type: string
                      enum: [upstream, self, downstream]
                      description: >
                        어느 폐포에서 나왔는지. 단계 번호로 정하지 않는다 —
                        되돌아오는 참조가 있으면 근거가 오른쪽 단계에 놓인다
                    status:
                      $ref: '#/components/schemas/DocStatus'
    RepoStatus:
      type: object
      properties:
        code:
          type: string
        name:
          type: string   # UI-14 표가 「[코드] 이름」(UI-002 1.6)으로 적는다
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
          nullable: true
          description: >
            처리 안 한 원격 커밋 수. 0이면 최신, null이면 아직 못 받아봄.
            폴링이 DB에 적어 둔 값이다 — 이 응답을 만들 때 git fetch를 돌리지 않는다
        fetched_at:
          type: string
          format: date-time
          nullable: true
          description: behind_by를 잰 시각. 화면이 "언제 기준인지" 보여준다
    RebuildResult:
      type: object
      properties:
        readme_updated:
          type: boolean
          description: "docs/specs/README.md를 새 판으로 커밋했나 (카드 AB). 이미 같으면 false"
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
    AskRequest:
      type: object
      required:
      - question
      properties:
        question:
          type: string
        item_id:
          type: string
          description: 지금 보고 있는 항목. 힌트일 뿐이라 없어도 된다. 이 문서에 없는 ID면 404
        history:
          type: array
          description: 앞선 대화. 클라이언트가 들고 있다가 통째로 보낸다 — 앞 턴에서 모델이 읽은 본문은 안 실리므로 필요하면 다시 읽는다
          items:
            type: object
            required:
            - role
            - text
            properties:
              role:
                type: string
                enum: [user, assistant]
              text:
                type: string
    AskStart:
      type: object
      description: 첫 이벤트. 이 앞의 오류는 HTTP 상태 코드로 온다
      required:
      - doc_id
      properties:
        doc_id:
          type: string
        item_id:
          type: string
          nullable: true
    AskNote:
      type: object
      description: 모델이 읽기 전에 쓴 한 줄 — 무엇을 왜 읽는지. 화면 8.9
      required:
      - text
      properties:
        text:
          type: string
    AskRead:
      type: object
      description: 도구 실행이 끝났다
      required:
      - tool
      properties:
        tool:
          type: string
          enum: [get_item, get_references, item_chain, list_documents, get_document]
        target:
          type: string
          nullable: true
          description: DOC#ITEM 또는 DOC. list_documents는 대상이 없어 null
    AskAnswer:
      type: object
      required:
      - answer
      - context_item_ids
      properties:
        answer:
          type: string
        context_item_ids:
          type: array
          description: 모델이 실제로 읽은 대상, 부른 순서(중복은 접는다). 화면이 「본 것」으로 보여준다. list_documents는 대상이 없어 안 실린다
          items:
            type: string
```

---

## 5. 판단이 필요한 지점

**1. `/api/docs/{docId}`가 원본과 뷰 데이터를 한 번에 준다.** `body`(원본)와 `items`(뱃지용)를 같이 보내고 렌더링은 React가 한다. 문서가 커지면 분리할 수 있으나 지금은 한 번에.

**3. 되돌리기(revert)가 웹에 남은 유일한 본문 쓰기다.** MCP `update_document`와 같은 파이프라인·같은 에러(`convention-violation`, `push-failed`)를 낸다. 다른 응답 형식을 만들지 않는다.

**4. 그래프 응답에 좌표가 없다.** 배치는 브라우저가 한다. 서버는 노드·간선만.

**5. 읽는 중 질의가 아무것도 저장하지 않는다.** 대화는 클라이언트가 들고 요청마다 통째로 보낸다. 표를 만들면 백업([[SYNC-INFRA-001]] 6.1)과 재구축([[SYNC-UC-001#UC-S6]])과 완전 삭제가 전부 그것을 알아야 한다. 그런데 **저장해도 DB 유실에는 대비하지 못한다** — 저장소가 공개라 자유 텍스트를 백업에 못 싣는 것이 댓글 본문과 같은 이유로 여기에도 걸리고, 그러면 남는 것이 「질문이 있었다」는 껍데기뿐이다. 휘발하는 것에 치를 값이 아니라고 봤다. 답은 화면에만 있다 — 남길 값이 있으면 사람이 자기 에이전트에게 옮겨 말한다.

**6. 429를 만들지 않는다.** 모델 쪽이 사용량 초과를 주면 `llm-unavailable`(502)의 `reason`으로 접는다 — GitHub 실패를 `push-failed`로 접는 것과 같은 모양이다. **우리가 한도를 세지 않으므로 우리 429가 생길 일이 없다.** 비용은 **도구 호출 수(8번)와 시간(120초)** 상한과 대화 길이 상한으로 눌리고 — 맥락 글자 상한은 두지 않는다(카드 Y) — 회수 경로는 키를 비우는 것이다([[SYNC-INFRA-001]] 5.3). 디스크 한도를 「한도보다 회수 경로가 먼저다」로 닫은 것과 같은 판단이다.

---

## 6. 미결사항

- [x] `/api/projects/{code}/flags` 응답이 `oneOf`라 클라이언트가 `kind`별로 분기해야 한다. 엔드포인트를 쪼갤지 — 결정: 쪼개지 않고 응답에 **판별 필드**를 넣는다. 스키마마다 고정값 `type`을 두면 클라이언트가 구분 유니온으로 받는다
- [x] 되돌리기·상태 변경의 `Author.via`를 `web`으로 기록할 때 `kind`는 `human`. `agent`는 MCP·GitHub push(에이전트 커밋)에서만 — 결정: 그대로 간다. `types.fold_via`가 `web_revert`·`web_status`를 `web`으로 접고 `kind=human`으로 기록
