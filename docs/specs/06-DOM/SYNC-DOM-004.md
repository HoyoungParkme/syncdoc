---
doc_id: SYNC-DOM-004
type: DOM
title: 클래스 명세 — 싱크독_로컬 (Rust)
status: draft
upstream: [SYNC-DOM-001, SYNC-DOM-002, SYNC-DOM-003, SYNC-INFRA-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# 클래스 명세: 싱크독_로컬 (Rust)

---

## 0. 이 문서가 다루는 것

싱크독의 **둘째 구현**(Rust, `local/`)을 코드 구조로 옮긴다 — [[SYNC-INFRA-001#C11]] · [[SYNC-INFRA-001]] 9장. 파이썬 판의 클래스 명세 [[SYNC-DOM-002]]와 **같은 묶음·같은 서비스·같은 메서드 이름**이고, 이 문서는 다른 점만 적는다. 도메인 모델([[SYNC-DOM-001]])과 테이블([[SYNC-DOM-003]])은 두 구현이 함께 쓴다([[SYNC-STD-001]] 1.9·2.6).

**뼈대다(2026-10-07).** 아직 코드가 없다. 폴더 구조의 트리, 엔티티의 Rust 타입, 묶음 ↔ MINISPEC ↔ 자리 표까지만 둔다. 층 표의 줄과 설계 클래스(그림·메서드 표)는 카드마다 그 카드의 MINISPEC과 함께 더한다 — MINISPEC은 카드의 첫 커밋이다([[SYNC-STD-004#DEV-13]]). 카드는 [[SYNC-CODE-002]].

---

## 1. 폴더 구조

저장소 루트는 [[SYNC-DOM-002]] 1장이다. 여기는 `local/` 안만 적는다. Rust 카드가 루트에 더하는 것 — `contract/`(공용 계약 시험, 카드 L2)와 `.github/workflows/`(설치 파일 빌드, 카드 L4) — 은 그 카드가 [[SYNC-DOM-002]] 1장 루트 트리에 적는다.

**기본형과 다른 점, 그리고 왜.** [[SYNC-STD-001]] 1.9의 Rust 기본형(층마다 crate 하나)을 따른다. 다른 점은 둘이다.
- **라우터를 도메인 밖 `server`에 둔다** — 파이썬 판과 같은 이유다. 입구(웹·MCP·git)가 여럿이고 같은 저장 파이프라인을 타야 한다([[SYNC-INFRA-001#C4]] · [[SYNC-DOM-002]] 1장)
- **infra가 `core` 안에 있다** — 파이썬은 `app/infra/`가 core 밖에 있고 core가 부른다. crate 의존은 한 방향(`app → server → core → codegraph`)이라 core가 부르는 것은 core 안이나 그 아래에 있어야 한다

```
local/                          싱크독_로컬 (Rust) — 실행 파일 하나 (INFRA 9.1)
├── Cargo.toml · Cargo.lock     작업 공간 — crate 넷 + xtask
├── rust-toolchain.toml         Rust 판 고정 (STD-001 1.9)
├── crates/                     층마다 crate 하나. 의존은 app → server → core → codegraph 한 방향
│   ├── app/                    실행 파일 — 켜기·끄기·설정·데이터 자리·PostgreSQL 자식 프로세스 ·
│   │                           한 번만 실행·트레이·자동 시작·백업·주기 일
│   ├── server/                 axum 한 서버 — REST·SSE·MCP(/mcp)·git 입구(/git) · 화면과 /specs(실행 파일에 담음)
│   ├── core/                   도메인 묶음과 조율 — 파이썬 core/와 같은 묶음·같은 서비스 + infra
│   └── codegraph/              코드 그래프의 순수 부분 — 추출·줄이기·보강·대조·커뮤니티. DB 없음
├── migrations/                 이전 SQL — 원본은 backend/alembic. `alembic upgrade --sql`로 만든 것 (STD-004 DEV-7)
├── xtask/                      개발 도구 — 이전 SQL 만들기·스키마 같음 검사·속도 재기 (`cargo xtask …`)
├── packaging/                  설치 파일 — NSIS(setup.exe)·.deb·AppImage 설정 · MinGit·PostgreSQL 받기
└── target/                     빌드 결과 (gitignore)
```

crate마다 `src/`와 거울 `tests/`를 둔다. 단위 시험은 그 모듈의 `#[cfg(test)]`도 된다([[SYNC-STD-004]] 1장).

**core/ 안** — 묶음은 파이썬 `core/`와 같다.

```
crates/core/src/
├── lib.rs                      공개 모듈
├── project/ · spec/ · reference/ · account/ · conversation/ · codegraph/
│   ├── model.rs                행 = 도메인 객체. 속성은 DOM-003 그대로
│   ├── repo.rs                 조회·저장. DB만 안다
│   └── service.rs              규칙. 여기서만 모델을 만진다
├── types.rs                    열거형·DTO (DOM-002 2.7·2.8)
├── clock.rs                    저장 시각 — 프로세스 안에서 뒤로 안 간다 (STD-004 DEV-18)
├── markdown.rs                 순수 — frontmatter·코드 마스킹·헤딩·참조·항목 블록
├── errors.rs                   Problem 열거형 하나에 problem+json 종류 전부 (STD-004 DEV-5)
├── pipeline.rs                 쓰기 조율 — 프로젝트마다 읽기·쓰기 락, 순서는 파이썬과 같다
├── queries.rs                  읽기 조합
└── infra/                      바깥 — git 자식 프로세스 · upload-pack·receive-pack · 모델 호출
```

`app`·`server`·`codegraph` 안의 파일은 그 카드가 적는다.

**층** — 함수 단위 명세(MINISPEC 카드·API 엔드포인트·UI 화면)가 없는 코드가 어느 층이고 그 층을 무슨 문서가 정하는지([[SYNC-STD-001]] 2.6). 코드 그래프가 읽는다. 위에서부터 첫 줄이 이긴다. **줄은 카드마다 더한다** — 코드가 없는 줄은 검사기(`check_calls`)가 「안 맞는 줄」로 잡는다.

| 경로 | 층 | 명세 |
|---|---|---|

---

## 2. 엔티티

테이블과 속성은 [[SYNC-DOM-003]] 그대로다 — 두 구현이 같은 표를 쓴다(이전의 원본은 Alembic 하나, [[SYNC-STD-004#DEV-7]]). 여기는 Rust 타입과 자리만 적는다. 관계·규칙은 [[SYNC-DOM-002]] 2장 그대로다.

### 2.1 프로젝트

#### Project 프로젝트

테이블: [[SYNC-DOM-003#projects]] · 도메인: [[SYNC-DOM-001#Project]]

`core::project::Project` — [[SYNC-DOM-002#Project]]

#### Repository 저장소

테이블: [[SYNC-DOM-003#repositories]] · 도메인: [[SYNC-DOM-001#Repository]]

`core::project::Repository` — [[SYNC-DOM-002#Repository]]

### 2.2 명세

#### Document 문서

테이블: [[SYNC-DOM-003#documents]] · 도메인: [[SYNC-DOM-001#Document]]

`core::spec::Document` — [[SYNC-DOM-002#Document]]

#### Item 항목

테이블: [[SYNC-DOM-003#items]] · 도메인: [[SYNC-DOM-001#Item]]

`core::spec::Item` — [[SYNC-DOM-002#Item]]

#### Version 버전

테이블: [[SYNC-DOM-003#versions]] · 도메인: [[SYNC-DOM-001#Version]]

`core::spec::Version` — [[SYNC-DOM-002#Version]]

#### StatusChange 상태변경

테이블: [[SYNC-DOM-003#status_changes]] · 도메인: [[SYNC-DOM-001#StatusChange]]

`core::spec::StatusChange` — [[SYNC-DOM-002#StatusChange]]

### 2.3 참조

#### Reference 참조

테이블: [[SYNC-DOM-003#references]] · 도메인: [[SYNC-DOM-001#Reference]]

`core::reference::Reference` — [[SYNC-DOM-002#Reference]]

### 2.4 계정

#### User 사용자

테이블: [[SYNC-DOM-003#users]] · 도메인: [[SYNC-DOM-001#User]]

`core::account::User` — [[SYNC-DOM-002#User]]. 싱크독_로컬에는 `kind=local` 사용자 하나와 커밋으로 알려진 자리표시만 있다([[SYNC-PRD-001#R15]])

#### CommitEmail 커밋이메일

테이블: [[SYNC-DOM-003#commit_emails]] · 도메인: [[SYNC-DOM-001#CommitEmail]]

`core::account::CommitEmail` — [[SYNC-DOM-002#CommitEmail]]

#### AccessToken 액세스토큰

테이블: [[SYNC-DOM-003#access_tokens]] · 도메인: [[SYNC-DOM-001#AccessToken]]

`core::account::AccessToken` — [[SYNC-DOM-002#AccessToken]]

### 2.5 대화

#### Conversation 대화

테이블: [[SYNC-DOM-003#conversations]] · 도메인: [[SYNC-DOM-001#Conversation]]

`core::conversation::Conversation` — [[SYNC-DOM-002#Conversation]]

#### Turn 턴

테이블: [[SYNC-DOM-003#turns]] · 도메인: [[SYNC-DOM-001#Turn]]

`core::conversation::Turn` — [[SYNC-DOM-002#Turn]]

#### Attachment 첨부

테이블: [[SYNC-DOM-003#attachments]] · 도메인: [[SYNC-DOM-001#Attachment]]

`core::conversation::Attachment` — [[SYNC-DOM-002#Attachment]]

### 2.6 코드 그래프

#### CodeGraph 코드 그래프

테이블: [[SYNC-DOM-003#code_graphs]] · 도메인: [[SYNC-DOM-001#CodeGraph]]

`core::codegraph::CodeGraph` — [[SYNC-DOM-002#CodeGraph]]. 그래프를 만드는 순수 부분은 `codegraph` crate다

### 2.7 열거형·DTO

[[SYNC-DOM-002]] 2.7·2.8 그대로 — `core::types`. 직렬화 이름(JSON 키·열거형 값)도 같다. 화면과 에이전트가 두 판을 가리지 않는다.

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
| 4.1 | runtime — 켜기·끄기·설정·PostgreSQL·한 번만 실행 | MS-012 | `crates/app` | `main.py` · `config.py` · `db.py` |
| 4.2 | project | MS-013 | `crates/core/src/project` | [[SYNC-MS-001]] |
| 4.3 | spec · markdown | MS-014 | `crates/core/src/spec` · `markdown.rs` | [[SYNC-MS-002]] |
| 4.4 | reference | MS-015 | `crates/core/src/reference` | [[SYNC-MS-003]] |
| 4.5 | account | MS-016 | `crates/core/src/account` | [[SYNC-MS-006]] |
| 4.6 | pipeline · scheduler | MS-017 | `crates/core/src/pipeline.rs` · `crates/app` | [[SYNC-MS-007]] |
| 4.7 | queries | MS-018 | `crates/core/src/queries.rs` | [[SYNC-MS-008]] |
| 4.8 | git · git_rpc | MS-019 | `crates/core/src/infra` · `crates/server`(git 입구) | [[SYNC-MS-009]] |
| 4.9 | llm | MS-020 | `crates/core/src/infra` | [[SYNC-MS-009]] |
| 4.10 | conversation | MS-021 | `crates/core/src/conversation` | [[SYNC-MS-010]] |
| 4.11 | codegraph | MS-022 | `crates/codegraph` · `crates/core/src/codegraph` | [[SYNC-MS-011]] |
| 4.12 | 데이터 자리 · 백업 | MS-023 | `crates/app` | — (Docker 판은 `scripts/backup.sh`, [[SYNC-CODE-001#BR]]) |

---

## 5. 미결사항

없음. 카드에서 정할 것은 [[SYNC-CODE-002]] 4장에 있다.
