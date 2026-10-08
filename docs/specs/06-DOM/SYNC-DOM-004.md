---
doc_id: SYNC-DOM-004
type: DOM
title: 클래스 명세 — 싱크독_로컬 (Rust)
status: approved
upstream: [SYNC-DOM-001, SYNC-DOM-002, SYNC-DOM-003, SYNC-INFRA-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# 클래스 명세: 싱크독_로컬 (Rust)

---

## 0. 이 문서가 다루는 것

싱크독의 **둘째 구현**(Rust, `local/`)을 코드 구조로 옮긴다 — [[SYNC-INFRA-001#C11]] · [[SYNC-INFRA-001]] 9장. 파이썬 판의 클래스 명세 [[SYNC-DOM-002]]와 **같은 묶음·같은 서비스·같은 메서드 이름**이고, 이 문서는 다른 점만 적는다. 도메인 모델([[SYNC-DOM-001]])과 테이블([[SYNC-DOM-003]])은 두 구현이 함께 쓴다([[SYNC-STD-001]] 1.9·2.6).

**카드마다 자란다.** 뼈대(2026-10-07)에 카드 L1이 켜기·끄기(4.1)와 로컬 사용자(4.5)를, 카드 L3가 토큰(4.5)·MCP 입구·파이썬 호환 층(1장)을 더했다. 층 표의 줄과 설계 클래스(그림·메서드 표)는 카드마다 그 카드의 MINISPEC과 함께 더한다 — MINISPEC은 카드의 첫 커밋이다([[SYNC-STD-004#DEV-13]]). 카드는 [[SYNC-CODE-002]].

---

## 1. 폴더 구조

저장소 루트는 [[SYNC-DOM-002]] 1장이다. 여기는 `local/` 안만 적는다. Rust 카드가 루트에 더하는 것 — `contract/`(공용 계약 시험, 카드 L2)와 `.github/workflows/`(설치 파일 빌드, 카드 L4) — 은 그 카드가 [[SYNC-DOM-002]] 1장 루트 트리에 적는다.

**기본형과 다른 점, 그리고 왜.** [[SYNC-STD-001]] 1.9의 Rust 기본형(층마다 crate 하나)을 따른다. 다른 점은 둘이다.
- **라우터를 도메인 밖 `server`에 둔다** — 파이썬 판과 같은 이유다. 입구(웹·MCP·git)가 여럿이고 같은 저장 파이프라인을 타야 한다([[SYNC-INFRA-001#C4]] · [[SYNC-DOM-002]] 1장)
- **infra가 `core` 안에 있다** — 파이썬은 `app/infra/`가 core 밖에 있고 core가 부른다. crate 의존은 한 방향(`app → server → core → codegraph`)이라 core가 부르는 것은 core 안이나 그 아래에 있어야 한다

```
local/                          싱크독_로컬 (Rust) — 실행 파일 하나 (INFRA 9.1)
├── Cargo.toml · Cargo.lock     작업 공간 — crate 넷 + xtask. 의존 판은 여기 한곳에
├── rust-toolchain.toml         Rust 판 고정 — 1.99.0 (STD-001 1.9)
├── .cargo/config.toml          `cargo xtask` 별칭 · 개발용 PostgreSQL 자리(SYNCDOC_LOCAL_PG_DIR)
├── crates/                     층마다 crate 하나. 의존은 app → server → core → codegraph 한 방향
│   ├── app/                    실행 파일 syncdoc-local — 켜기·끄기·설정·데이터 자리·PostgreSQL 자식 프로세스 ·
│   │                           한 번만 실행·트레이·자동 시작·백업·주기 일
│   ├── server/                 axum 한 서버 — REST·SSE·MCP(/mcp)·git 입구(/git) · 화면과 /specs(실행 파일에 담음)
│   ├── core/                   도메인 묶음과 조율 — 파이썬 core/와 같은 묶음·같은 서비스 + infra · 이전
│   └── codegraph/              코드 그래프의 순수 부분 — 추출·줄이기·보강·대조·커뮤니티. DB 없음
├── migrations/                 이전 SQL — 원본은 backend/alembic. `cargo xtask migrations`가 리비전마다
│                               `alembic upgrade --sql`로 만든다. 손으로 고치지 않는다 (STD-004 DEV-7)
├── xtask/                      개발 도구 — pg-fetch(개발용 PostgreSQL 바이너리) · migrations [--check] ·
│                               schema-check(두 판의 스키마 같음) · test-db-clean · mcp-tools [--check](L3) ·
│                               package windows|linux · icon · pg-fetch --target(L4) · 속도 재기(L17)
├── packaging/                  설치 파일 재료 (L4) — `cargo xtask package`가 실행 파일·PostgreSQL·MinGit과 함께 모은다
│   ├── icon.svg                앱 아이콘 원본 — `cargo xtask icon`이 icon.ico·icon.png·tray.rgba(32×32 RGBA)를 만든다(생성물)
│   ├── NOTICE.txt              함께 담은 것과 라이선스·원본 주소(PostgreSQL · MinGit GPL)
│   ├── windows/installer.nsi   NSIS — 사용자 범위 설치·시작 메뉴·바탕화면(기본)·자동 시작(기본 끔)·제거는 프로그램만
│   └── linux/                  .desktop · AppRun — .deb(/opt/syncdoc-local)와 AppImage
└── target/                     빌드 결과 (gitignore). target/pg/16.15.0 — pg-fetch가 받은 PostgreSQL
```

**crate 이름** — 패키지 `syncdoc_app`(실행 파일 `syncdoc-local`) · `syncdoc_server` · `syncdoc_core` · `syncdoc_codegraph`. Rust 표준 `core`와 겹치지 않게 앞에 `syncdoc_`를 붙인다 — 이 문서의 `crates/core`는 `syncdoc_core`다.

crate마다 `src/`와 거울 `tests/`를 둔다. 단위 시험은 그 모듈의 `#[cfg(test)]`도 된다([[SYNC-STD-004]] 1장). DB가 드는 시험은 시험 컨테이너(5434)에 시험마다 DB 하나를 만든다 — 공용 도우미는 `crates/core/tests/support/`.

**app/ 안** — 켜기·끄기 (4.1)

```
crates/app/src/
├── main.rs                     진입 — 관리자 권한 내려놓기 → 인자를 읽어 runtime.run, 끝 코드 · 일꾼 스레드 스택(파이썬 판의 1만 겹 JSON을 받으려고, L3)
├── lib.rs                      공개 모듈
├── runtime.rs                  켠다·포트에 묶는다·끈다
├── tray.rs                     트레이 — 열기·끝내기 (윈도 메시지 루프 · 리눅스 StatusNotifierItem, L4)
├── privilege.rs                윈도 관리자 권한 내려놓기 — 관리자 그룹을 뺀 토큰으로 다시 켠다 (L4 · 저장소의 unsafe는 여기뿐)
├── paths.rs                    데이터 자리 · PostgreSQL 바이너리 자리
├── settings.rs                 settings.toml — INFRA 5.2와 같은 이름
├── logs.rs                     logs/ — 날마다 한 파일, 최근 14개
├── instance.rs                 한 번만 실행 — 잠금 · instance.json · 두 번째 실행
└── pg.rs                       함께 담은 PostgreSQL — initdb · postgres --single · pg_ctl
```

**server/ 안** — 입구. 파이썬 `web/`에 해당한다

```
crates/server/src/
├── lib.rs                      라우터 조립 · /health
├── state.rs                    AppState — 연결 풀 · 로컬 사용자 설정 · 공개 주소
├── web/
│   ├── guard.rs                Host·Origin 가드 (SEQ-C3) — 라우팅 바깥에서 모든 요청에
│   ├── auth.rs                 현재 사용자 — 로컬 사용자
│   ├── problem.rs              problem+json 응답 · 405 · 패닉
│   ├── static_files.rs         화면 빌드(rust-embed) · 캐시 규칙 · 304 (INFRA 4.1)
│   ├── schemas.rs              응답 형태 (API-001 4장)
│   └── routes/                 API-001 경로 — account(/api/me · /api/me/tokens) · specs(/specs)
├── mcp/                        /mcp — 파이썬 mcp SDK의 핸드셰이크 경로를 옮긴 것 (API-002 1장, 카드 L3)
│   ├── auth.rs                 Bearer → AccountService.authenticate_token, 통과하면 응답 전에 커밋 (SEQ-C2)
│   ├── transport.rs            streamable HTTP, 세션 없음 — Accept·Content-Type·본문 읽기·SSE 쓰기
│   ├── dispatch.rs             JSON-RPC 봉투 검증 · 메서드 표(판마다) · 요청·알림 나누기 · 오류 꼴
│   ├── handlers.rs             initialize·ping·tools·resources·prompts — MCPServer와 같은 답
│   ├── tools.rs                도구 13개 — 인자 검증 후 카드마다 처리기, 없으면 not-implemented
│   └── declarations.json       도구 선언·안내문·서버 이름 — `cargo xtask mcp-tools`가 파이썬 판에서 만든다. 손으로 안 고친다
└── compat/                     파이썬 호환 층 — 오류 문장·값 꼴을 파이썬 판과 바이트로 같게 (INFRA 9.8)
    ├── pyvalue.rs              JSON → 파이썬 값(dict 순서·큰 정수·inf·nan·짝 없는 서로게이트) · repr
    ├── pyjson.rs               파이썬 `json.loads`(`_json.c`) — FastAPI 본문·도구 인자 미리 읽기의 오류 위치·C 재귀 한도
    ├── pydantic/               검증 — 파이썬 판이 내보낸 core schema를 읽어(schema) lax 규칙으로 검증하고(validate)
    │                           같은 오류 줄·문장·`N validation errors for …` 꼴을 낸다(errors). smart union의 고르기까지
    ├── printable.rs            파이썬 `str.isprintable()` 표(유니코드 15.0) — repr이 이스케이프할 글자. 생성물
    ├── fastapi.rs              요청 본문(Content-Type·json.loads)·경로 값 → invalid-request(loc·msg) · 400
    └── uvicorn.rs              요청 경로를 `unquote`로 풀어 라우팅한다(`/api/m%65` = `/api/me`)
```

**옮긴 판** — `mcp/`와 `compat/`는 파이썬 판이 쓰는 꾸러미의 동작을 옮긴다(사용자 결정 2026-10-08 — 검증 문장까지 바이트로 같다, MCP는 핸드셰이크 경로 전부). 기준 판은 `backend/uv.lock`의 mcp 2.2.0 · pydantic 2.13.5(pydantic-core 2.46.5) · FastAPI 0.141.1 · starlette 1.6.0 · sse-starlette 3.4.11과 Python 3.12다. JSON 읽기는 pydantic-core와 같은 `jiter` crate를 같은 판으로 쓴다. 파이썬 쪽이 판을 올리면 계약 시험의 두 판 차이 시험이 어긋남을 잡는다 — 그때 이 층을 따라 고친다. 2026-07-28 새 프로토콜(`_streamable_http_modern`)은 카드 L18이다

**core/ 안** — 묶음은 파이썬 `core/`와 같다.

```
crates/core/
├── build.rs                    local/migrations/*.sql을 실행 파일에 담는 목록을 만든다
└── src/
    ├── lib.rs                      공개 모듈
    ├── project/ · spec/ · reference/ · account/ · conversation/ · codegraph/
    │   ├── model.rs                행 = 도메인 객체(`…Row`). 속성은 DOM-003 그대로
    │   ├── repo.rs                 조회·저장. DB만 안다
    │   └── service.rs              규칙. 여기서만 모델을 만진다
    ├── types.rs                    열거형·DTO (DOM-002 2.7·2.8)
    ├── clock.rs                    저장 시각 — 프로세스 안에서 뒤로 안 간다 (STD-004 DEV-18)
    ├── markdown.rs                 순수 — frontmatter·코드 마스킹·헤딩·참조·항목 블록
    ├── errors.rs                   Problem 열거형 하나에 problem+json 종류 전부 (STD-004 DEV-5)
    ├── migrate.rs                  이전 SQL을 올린다 (4.1) — 모든 crate의 시험도 이것으로 DB를 만든다
    ├── pipeline.rs                 쓰기 조율 — 프로젝트마다 읽기·쓰기 락, 순서는 파이썬과 같다
    ├── queries.rs                  읽기 조합
    └── infra/                      바깥 — git 자식 프로세스 · upload-pack·receive-pack · 모델 호출
```

지금(카드 L3) 있는 것은 `account`·`types.rs`·`clock.rs`·`errors.rs`·`migrate.rs`다. 나머지 묶음과 `codegraph`·`app`·`server`의 다음 파일은 그 카드가 만들고 여기에 적는다.

**층** — 함수 단위 명세(MINISPEC 카드·API 엔드포인트·UI 화면)가 없는 코드가 어느 층이고 그 층을 무슨 문서가 정하는지([[SYNC-STD-001]] 2.6). 코드 그래프가 읽는다. 위에서부터 첫 줄이 이긴다. **줄은 카드마다 더한다** — 코드가 없는 줄은 검사기(`check_calls`)가 「안 맞는 줄」로 잡는다. 함수가 없는 파일(구조체만 — `state.rs`·`model.rs`)은 적지 않는다.

| 경로 | 층 | 명세 |
|---|---|---|
| `local/crates/app/src/main.rs` | 실행 파일 진입 | [[SYNC-INFRA-001]] 9.1 · [[SYNC-MS-012]] |
| `local/crates/server/src/lib.rs` | 서버 조립·`/health` | [[SYNC-INFRA-001]] 4.1·9.1 |
| `local/crates/server/src/web/guard.rs` · `local/crates/server/src/web/auth.rs` · `local/crates/server/src/mcp/auth.rs` | 인증 | [[SYNC-INFRA-001]] 5장·9.4 · [[SYNC-SEQ-001#SEQ-C2]] · [[SYNC-SEQ-001#SEQ-C3]] |
| `local/crates/server/src/mcp/**` | MCP 입구 | [[SYNC-API-002]] 1장·2장 · [[SYNC-INFRA-001]] 9.8 |
| `local/crates/server/src/compat/**` | 파이썬 호환 | [[SYNC-INFRA-001]] 9.8 · [[SYNC-DOM-004]] 1장 |
| `local/crates/server/src/web/problem.rs` · `local/crates/core/src/errors.rs` | 에러 | [[SYNC-STD-004#DEV-5]] · [[SYNC-API-001]] 2장 |
| `local/crates/server/src/web/static_files.rs` | 정적 파일 | [[SYNC-INFRA-001]] 4.1 |
| `local/crates/core/src/types.rs` | 열거형·DTO | [[SYNC-DOM-002]] 2.7·2.8 |
| `local/crates/server/src/web/schemas.rs` | 응답 형태 | [[SYNC-API-001]] 4장 |
| `local/crates/core/src/clock.rs` | 시각 | [[SYNC-STD-004#DEV-18]] |
| `local/crates/core/src/*/repo.rs` | 리포지토리 | [[SYNC-DOM-004]] 4장 · [[SYNC-DOM-003]] |
| `local/crates/*/build.rs` | 빌드 설정 | [[SYNC-STD-004#DEV-7]] · [[SYNC-INFRA-001]] 9.2 |
| `local/xtask/**` | 개발 도구 | [[SYNC-STD-004#DEV-7]] · [[SYNC-STD-004#DEV-14]] |

---

## 2. 엔티티

테이블과 속성은 [[SYNC-DOM-003]] 그대로다 — 두 구현이 같은 표를 쓴다(이전의 원본은 Alembic 하나, [[SYNC-STD-004#DEV-7]]). 여기는 Rust 타입과 자리만 적는다 — DB 행 타입은 `…Row`다([[SYNC-STD-004#DEV-2]]). 관계·규칙은 [[SYNC-DOM-002]] 2장 그대로다.

### 2.1 프로젝트

#### Project 프로젝트

테이블: [[SYNC-DOM-003#projects]] · 도메인: [[SYNC-DOM-001#Project]]

`syncdoc_core::project::ProjectRow` — [[SYNC-DOM-002#Project]]

#### Repository 저장소

테이블: [[SYNC-DOM-003#repositories]] · 도메인: [[SYNC-DOM-001#Repository]]

`syncdoc_core::project::RepositoryRow` — [[SYNC-DOM-002#Repository]]

### 2.2 명세

#### Document 문서

테이블: [[SYNC-DOM-003#documents]] · 도메인: [[SYNC-DOM-001#Document]]

`syncdoc_core::spec::DocumentRow` — [[SYNC-DOM-002#Document]]

#### Item 항목

테이블: [[SYNC-DOM-003#items]] · 도메인: [[SYNC-DOM-001#Item]]

`syncdoc_core::spec::ItemRow` — [[SYNC-DOM-002#Item]]

#### Version 버전

테이블: [[SYNC-DOM-003#versions]] · 도메인: [[SYNC-DOM-001#Version]]

`syncdoc_core::spec::VersionRow` — [[SYNC-DOM-002#Version]]

#### StatusChange 상태변경

테이블: [[SYNC-DOM-003#status_changes]] · 도메인: [[SYNC-DOM-001#StatusChange]]

`syncdoc_core::spec::StatusChangeRow` — [[SYNC-DOM-002#StatusChange]]

### 2.3 참조

#### Reference 참조

테이블: [[SYNC-DOM-003#references]] · 도메인: [[SYNC-DOM-001#Reference]]

`syncdoc_core::reference::ReferenceRow` — [[SYNC-DOM-002#Reference]]

### 2.4 계정

#### User 사용자

테이블: [[SYNC-DOM-003#users]] · 도메인: [[SYNC-DOM-001#User]]

`syncdoc_core::account::UserRow` — [[SYNC-DOM-002#User]]. 싱크독_로컬에는 `kind=local` 사용자 하나뿐이다 — 커밋 작성자도 늘 그 사람이다([[SYNC-PRD-001#R15]] · [[SYNC-MS-006#AccountService.user_for_commit]] 0)

#### CommitEmail 커밋이메일

테이블: [[SYNC-DOM-003#commit_emails]] · 도메인: [[SYNC-DOM-001#CommitEmail]]

`syncdoc_core::account::CommitEmailRow` — [[SYNC-DOM-002#CommitEmail]]

#### AccessToken 액세스토큰

테이블: [[SYNC-DOM-003#access_tokens]] · 도메인: [[SYNC-DOM-001#AccessToken]]

`syncdoc_core::account::AccessTokenRow` — [[SYNC-DOM-002#AccessToken]]

### 2.5 대화

#### Conversation 대화

테이블: [[SYNC-DOM-003#conversations]] · 도메인: [[SYNC-DOM-001#Conversation]]

`syncdoc_core::conversation::ConversationRow` — [[SYNC-DOM-002#Conversation]]

#### Turn 턴

테이블: [[SYNC-DOM-003#turns]] · 도메인: [[SYNC-DOM-001#Turn]]

`syncdoc_core::conversation::TurnRow` — [[SYNC-DOM-002#Turn]]

#### Attachment 첨부

테이블: [[SYNC-DOM-003#attachments]] · 도메인: [[SYNC-DOM-001#Attachment]]

`syncdoc_core::conversation::AttachmentRow` — [[SYNC-DOM-002#Attachment]]

### 2.6 코드 그래프

#### CodeGraph 코드 그래프

테이블: [[SYNC-DOM-003#code_graphs]] · 도메인: [[SYNC-DOM-001#CodeGraph]]

`syncdoc_core::codegraph::CodeGraphRow` — [[SYNC-DOM-002#CodeGraph]]. 그래프를 만드는 순수 부분은 `codegraph` crate다

### 2.7 열거형·DTO

[[SYNC-DOM-002]] 2.7·2.8 그대로 — `syncdoc_core::types`. 직렬화 이름(JSON 키·열거형 값)도 같다. 화면과 에이전트가 두 판을 가리지 않는다.

---

## 3. 의존 관계

[[SYNC-DOM-002]] 3장과 같다 — Boundary → Control 선은 3.1, Control 사이의 선은 3.2 그대로다. 다른 점만 적는다.

- **crate가 층을 지킨다** — `app → server → core → codegraph` 한 방향이다. 거꾸로 부르면 컴파일이 안 된다. 파이썬 판은 규칙([[SYNC-DOM-002]] 1장 「규칙」)과 검사기로 지키던 것이다
- **입구가 셋이다** — 웹·MCP·git이 `server`에 있고, 셋 다 `core`의 서비스·`pipeline`·`queries`만 부른다
- **켜기·끄기·백업·주기 일은 `app`이 쥔다** — PostgreSQL과 git 자식 프로세스를 띄우고 멈추는 순서가 여기 있다([[SYNC-INFRA-001]] 9.1). 백업은 `core`의 쓰기 락을 쥐고 뜬다(9.6)
- **두 구현은 서로 부르지 않는다**([[SYNC-STD-001]] 1.9) — 같은 표와 같은 화면 빌드를 쓸 뿐이다

---

## 4. 설계 클래스

서비스·메서드 이름은 파이썬 판과 같다 — MINISPEC 항목 ID가 언어와 상관없이 점 꼴이다([[SYNC-STD-001]] 2.10). 서비스는 연결을 빌려 받는다(`SpecService { db: &mut PgConnection }` 꼴) — 트랜잭션은 입구가 쥔다([[SYNC-STD-004#DEV-10]]).

묶음 하나 = 절 하나 = MINISPEC 하나다. 절(그림·메서드 표)은 그 MINISPEC을 쓰는 카드가 더한다.

| 절 | 묶음 | MINISPEC | 자리 | 파이썬 판 |
|---|---|---|---|---|
| 4.1 | runtime — 켜기·끄기·설정·PostgreSQL·한 번만 실행 | [[SYNC-MS-012]] | `crates/app` · `crates/core/src/migrate.rs` | `main.py` · `config.py` · `db.py` |
| 4.2 | project | MS-013 | `crates/core/src/project` | [[SYNC-MS-001]] |
| 4.3 | spec · markdown | MS-014 | `crates/core/src/spec` · `markdown.rs` | [[SYNC-MS-002]] |
| 4.4 | reference | MS-015 | `crates/core/src/reference` | [[SYNC-MS-003]] |
| 4.5 | account | [[SYNC-MS-016]] | `crates/core/src/account` | [[SYNC-MS-006]] |
| 4.6 | pipeline · scheduler | MS-017 | `crates/core/src/pipeline.rs` · `crates/app` | [[SYNC-MS-007]] |
| 4.7 | queries | MS-018 | `crates/core/src/queries.rs` | [[SYNC-MS-008]] |
| 4.8 | git · git_rpc | MS-019 | `crates/core/src/infra` · `crates/server`(git 입구) | [[SYNC-MS-009]] |
| 4.9 | llm | MS-020 | `crates/core/src/infra` | [[SYNC-MS-009]] |
| 4.10 | conversation | MS-021 | `crates/core/src/conversation` | [[SYNC-MS-010]] |
| 4.11 | codegraph | MS-022 | `crates/codegraph` · `crates/core/src/codegraph` | [[SYNC-MS-011]] |
| 4.12 | 데이터 자리 옮기기 · 백업 | MS-023 | `crates/app` | — (Docker 판은 `scripts/backup.sh`, [[SYNC-CODE-001#BR]]) |


데이터 자리의 **기본값 찾기**는 4.1(MS-012 `paths.data_dir`)이고, 옮기기와 그 자리를 가리키는 파일은 4.12다.

### 4.1 runtime — 켜기·끄기 (MS-012)

클래스가 아니라 모듈 함수다 — 파이썬 판의 `main.py` lifespan·`config.py`·`db.py`와 Dockerfile의 `alembic upgrade head`가 하던 일을 한 프로세스가 한다.

| 함수 | 하는 일 | 부르는 곳 |
|---|---|---|
| [[SYNC-MS-012#runtime.run]] | 켠다 — 끌 때까지 | `main` |
| [[SYNC-MS-012#runtime.bind]] | 127.0.0.1의 8010, 못 쓰면 8011~8019 | `runtime.run` |
| [[SYNC-MS-012#runtime.shutdown]] | 끈다 | `runtime.run` |
| [[SYNC-MS-012#tray.run]] | 트레이 — 열기·끝내기 | `main`(트레이가 있을 때) |
| [[SYNC-MS-012#privilege.drop_admin]] | 윈도 관리자 권한을 내려놓고 다시 켠다 | `main`(맨 처음) |
| [[SYNC-MS-012#paths.data_dir]] · [[SYNC-MS-012#paths.pg_dir]] | 데이터 자리 · PostgreSQL 바이너리 자리 | `runtime.run` |
| [[SYNC-MS-012#settings.load]] | `settings.toml` | `runtime.run` |
| [[SYNC-MS-012#logs.init]] | 로그 | `runtime.run` |
| [[SYNC-MS-012#instance.acquire]] · [[SYNC-MS-012#instance.publish]] · [[SYNC-MS-012#instance.open_running]] | 한 번만 실행 | `runtime.run` |
| [[SYNC-MS-012#pg.start]] · [[SYNC-MS-012#pg.stop]] | 함께 담은 PostgreSQL | `runtime.run` · `runtime.shutdown` |
| [[SYNC-MS-012#migrate.apply]] | 이전 SQL | `runtime.run` · 모든 crate의 DB 시험 |

규칙
- 켜는 순서는 [[SYNC-INFRA-001]] 9.1 그대로다 — 잠금 → 로그 → 설정 → PostgreSQL → 이전 → 로컬 사용자 → 포트 → 서빙. 끄는 순서는 거꾸로
- PostgreSQL은 따로 프로세스 묶음으로 띄운다 — 터미널 신호가 먼저 닿지 않고, 멈추는 순서를 앱이 쥔다
- 트레이가 있으면 메인 스레드는 트레이 차지다(윈도 메시지 루프) — 서버·PostgreSQL은 tokio 일꾼 스레드에서 돈다. 「끝내기」는 Ctrl+C와 같은 끄는 순서를 탄다(L4)
- 켜는 중 실패는 `Problem::Internal`의 로그 문장으로 돌려주고 `main`이 끝 코드 1로 끝난다
- 윈도에서 관리자 권한으로 켜졌으면 맨 처음 관리자 그룹을 뺀 토큰으로 자신을 다시 켠다 — PostgreSQL은 관리자 권한으로 돌지 않는다. `unsafe`는 이 모듈의 Win32 호출뿐이다(작업 공간 lint `unsafe_code = "deny"`, 이 모듈만 허용, L4)

### 4.5 account (MS-016)

#### AccountService

```mermaid
classDiagram
    class AccountService {
        +db: PgConnection
        +ensure_local_user(login, display_name) UserRow
        +local_user(login, display_name) UserRow
        +list_tokens(user) Vec~AccessTokenRow~
        +issue_token(user, label) IssuedToken
        +revoke_token(user, token_id)
        +authenticate_token(raw) Option~UserRow~
    }
    class UserRow {
        +i32 id
        +String github_login
        +Option~i64~ github_user_id
        +String display_name
        +Option~Vec~ github_token_encrypted
        +OffsetDateTime created_at
        +String kind
    }
    class AccessTokenRow {
        +i32 id
        +i32 user_id
        +String token_hash
        +String label
        +OffsetDateTime issued_at
        +Option~OffsetDateTime~ expires_at
        +Option~OffsetDateTime~ revoked_at
        +Option~OffsetDateTime~ last_used_at
    }
    class IssuedToken {
        +AccessTokenRow token
        +String raw
    }
    AccountService --> UserRow
    AccountService --> AccessTokenRow
    IssuedToken --> AccessTokenRow
```

| 메서드 | 부르는 곳 | 근거 | 던지는 에러 |
|---|---|---|---|
| [[SYNC-MS-016#AccountService.ensure_local_user]] | 켤 때 `runtime.run` | [[SYNC-MS-006#AccountService.ensure_local_user]] | `internal`(아이디가 남의 것) |
| [[SYNC-MS-016#AccountService.local_user]] | 웹 입구의 현재 사용자(`web/auth`) — 모든 웹 경로 | [[SYNC-SEQ-001#SEQ-C3]] | — |
| [[SYNC-MS-016#AccountService.list_tokens]] | `GET /api/me/tokens` | [[SYNC-MS-006#AccountService.list_tokens]] | — |
| [[SYNC-MS-016#AccountService.issue_token]] | `POST /api/me/tokens` | [[SYNC-MS-006#AccountService.issue_token]] | — |
| [[SYNC-MS-016#AccountService.revoke_token]] | `DELETE /api/me/tokens/{id}` | [[SYNC-MS-006#AccountService.revoke_token]] | `not-found` |
| [[SYNC-MS-016#AccountService.authenticate_token]] | MCP 입구(`mcp/auth`) | [[SYNC-SEQ-001#SEQ-C2]] | — |

규칙 — [[SYNC-DOM-002]] 4.6과 같다. 로컬 사용자는 `kind=local` 행 하나뿐이다. 서비스는 연결을 빌려 받고 트랜잭션은 부르는 쪽이 쥔다. 토큰 원문은 발급 응답에만 있고 DB·로그에는 해시만 남는다. 커밋 작성자(L11)는 그 카드가 더한다.

---

## 5. 미결사항

없음. 카드에서 정할 것은 [[SYNC-CODE-002]] 4장에 있다.
