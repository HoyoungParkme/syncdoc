---
doc_id: SYNC-CODE-002
type: CODE
title: 구현 계획 — 싱크독_로컬 (Rust) 슬라이스 카드와 커밋 기록
status: approved
upstream: [SYNC-STD-004, SYNC-DOM-004, SYNC-PRD-001, SYNC-INFRA-001, SYNC-API-001, SYNC-API-002, SYNC-UI-002, SYNC-SCN-001]
---

# 구현 계획 — 싱크독_로컬 (Rust)

## 0. 이 문서가 다루는 것

11단계 CODE의 **둘째 구현** 것이다([[SYNC-STD-001]] 2.11 · [[SYNC-INFRA-001#C11]]). 파이썬 판(싱크독_깃허브)의 계획은 [[SYNC-CODE-001]]이다. 카드 ID는 이 문서에서 따로 센다 — `L1`·`L2`…. 카드 형식과 완료 조건은 파이썬 판과 같고([[SYNC-STD-004#DEV-12]] · [[SYNC-STD-004#DEV-14]]) Rust 카드는 계약 시험까지 통과해야 끝난다. 구조는 [[SYNC-DOM-004]].

**MINISPEC은 카드의 첫 커밋으로 쓴다**([[SYNC-STD-004#DEV-13]]). 그래서 L1만 표가 있고 나머지는 하는 일과 선행만 있다 — 카드를 받을 때 그 카드의 표를 쓴다. 아직 없는 MINISPEC 항목을 미리 가리키지 않는다.

**진행 상황**: 카드 17장(L1~L17). 완료 0(2026-10-07). L1은 계약 시험 없이 병합하고 완료란은 L2 뒤에 적는다(사용자 결정 2026-10-07).

---

## 1. 슬라이스

#### L1 걷는 뼈대 — 켜고, DB를 올리고, 화면과 /api/me가 뜬다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R15]] · [[SYNC-INFRA-001#C10]] · [[SYNC-INFRA-001#C11]] · [[SYNC-INFRA-001]] 4.1·9.1~9.4 · [[SYNC-SEQ-001#SEQ-C3]] · [[SYNC-API-001]] 2장 · [[SYNC-STD-004#DEV-7]] · [[SYNC-DOM-004]] 1장·4.1·4.5 · 사용자 결정 2026-10-07(PostgreSQL 16을 함께 담는다 · 데이터 자리 · 개발은 WSL · 계약 시험은 L2 뒤 · 설정 파일은 INFRA 5.2 이름 · 같은 망 열기는 L16 · 로그는 날마다 14개 · PostgreSQL은 앱이 직접 띄우고 크기는 기본값) |
| 구현 | [[SYNC-MS-012#runtime.run]] · [[SYNC-MS-012#runtime.bind]] · [[SYNC-MS-012#runtime.shutdown]] · [[SYNC-MS-012#paths.data_dir]] · [[SYNC-MS-012#paths.pg_dir]] · [[SYNC-MS-012#settings.load]] · [[SYNC-MS-012#logs.init]] · [[SYNC-MS-012#instance.acquire]] · [[SYNC-MS-012#instance.publish]] · [[SYNC-MS-012#instance.open_running]] · [[SYNC-MS-012#pg.start]] · [[SYNC-MS-012#pg.stop]] · [[SYNC-MS-012#migrate.apply]] · [[SYNC-MS-016#AccountService.ensure_local_user]] · [[SYNC-MS-016#AccountService.local_user]] · 층 코드 — `local/` 작업 공간(crate 넷 + xtask) · Host·Origin 가드 · problem+json · `/health` · 화면 정적 파일(같은 React 빌드)·캐시 규칙 · `local/migrations/`(`cargo xtask migrations`) · xtask `pg-fetch`·`migrations --check`·`schema-check`·`test-db-clean`. WSL에서 `--no-tray`로 돈다 |
| API | [[SYNC-API-001#GET/api/me]] · [[SYNC-API-001#GET/specs/{path}]] · `/health` |
| 화면 | 새로 만들지 않는다 — 같은 빌드를 담아 연다 |
| 테스트 | MS 테스트 관점 · `cargo test`(시험 DB 5434 `syncdoc_local_test*`) · `cargo fmt --check` · `cargo clippy --all-targets -- -D warnings` · `cargo check --target x86_64-pc-windows-msvc` · `cargo xtask migrations --check` · `cargo xtask schema-check` — Rust 판이 올린 표와 Alembic이 만든 표의 스키마 덤프가 같다 · 실행 파일 시험 — 두 번째 실행은 떠 있는 것을 연다, 다른 Host·Origin은 막힌다, `/api/me`가 로컬 사용자, SIGINT로 끈다 · 계약 시험은 L2가 L1 몫을 넣는다 — L1 완료란은 그 뒤에(사용자 결정 2026-10-07) |
| 스텁 | 없음 — 트레이(L4)·따라잡기와 주기 확인(L11)·백업(L16)은 그 카드가 켜기·끄기에 단계를 더한다 |
| 선행 | [[SYNC-CODE-001#BV]] · [[SYNC-CODE-001#BW]] |
| 완료 | — |

#### L2 계약 시험 틀 — 두 판을 띄워 같은 시나리오를 돌린다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 9.8 · [[SYNC-STD-004#DEV-14]] · [[SYNC-PRD-001#R15]](같은 화면·같은 API) · 사용자 결정 2026-10-07(시험이 두 판을 직접 띄운다 · 아직 없는 기능은 카드 표시로 건너뛴다 · 프레임워크 차이는 계약 밖 · `contract/`는 자기 uv 프로젝트) |
| 구현 | 저장소 루트 `contract/` — pytest·httpx·mcp, 앱을 import하지 않는다 · `--target python\|rust\|both` · 파이썬 판은 작업 트리로 만든 이미지를 Docker(폐쇄망판 구성, 빈 볼륨·임시 포트), Rust 판은 `syncdoc-local`을 임시 데이터 자리로 띄우고 끝나면 지운다 · 시험마다 카드 표시 `@pytest.mark.card("L1")` — Rust 판은 이 문서에서 완료된 카드만 돈다 · 가짜 모델 서버(OpenAI 호환) |
| 테스트 | 파이썬 판에서 전부 통과 · Rust 판에서 L1 몫 전부 통과(`/health`·`/api/me`·Host·Origin 가드·GitHub 경로·`/login`·API 앞머리 404·405·정적 파일 캐시와 304·`/specs`) · MCP 틀(L3 표시)은 파이썬만 |
| 선행 | L1 |
| 완료 | — |

**다음 카드** — 받을 때 표를 쓴다. 하는 일과 선행만 먼저 적는다.

| 카드 | 하는 일 | 선행 | 크기 |
|---|---|---|---|
| L3 토큰·MCP | 토큰 발급·폐기·인증 · `/mcp`(rmcp, 이름 `syncdoc_local`) · 도구 13 선언(못 만든 것은 `not-implemented`) · `get_template` | L1 | M |
| L4 설치형 껍데기 | 트레이·자동 시작·두 번째 실행 · NSIS(MinGit·PostgreSQL 포함)·.deb·AppImage · 릴리즈 워크플로 | L1 | L |
| L5 명세 엔진 | frontmatter·규약 검증·항목·diff — 파이썬이 만든 정답과 맞춘다 | L1 | L |
| L6 git·서버 저장 | git 어댑터 · 프로젝트 만들기·지우기(보관)·`init_project` | L3 · L5 | M |
| L7 저장 파이프라인 | 저장 파이프라인·대기열 읽기·락 · MCP 읽기·쓰기 도구 | L6 | XL |
| L8 웹 읽기 | 나머지 조회와 GET 경로(UI-2·4·5·7·8·9·15·18) | L7 | L |
| L9 상태·되돌리기·휴지통 | 상태 바꾸기·되돌리기·휴지통·되살리기·영구 삭제 | L7 | M |
| L10 git 입구·코드 올리기 | upload-pack·receive-pack(`main`) · `/git/*` · `upload_code` | L9 | L |
| L11 따라잡기·재구축 | 커밋 처리·재구축·주기 확인·관리 경로·기존 저장소 들이기 | L10 · #325 | L |
| L12 코드 그래프 | 파이썬·TS·JS·Rust 추출 · 명세 대조 · 코드 화면 · `get_code_graph` | L11 | L |
| L13 커뮤니티·노드 | graphrs Louvain(seed 42) · 허브 라벨 · 노드 목록 | L12 | M |
| L14 대화·질문 탭 | 대화·첨부(PDF) · 모델 스트리밍 · 질문 루프 · SSE | L8 · L12 | XL |
| L15 번들 가져오기 | 파이썬 판 카드 BX(git 번들 가져오기)의 Rust 쪽 | L11 · BX | S |
| L16 데이터 보호·「이 PC」 | 백업·되살리기·데이터 자리 옮기기 · UI-13 「이 PC」 묶음 · 같은 망 열기(`PUBLIC_BASE_URL`, 설정 파일만 — 사용자 결정 2026-10-07) | L4 · L11 | L |
| L17 속도·출시 판정 | 두 판을 같은 PC에서 잰다 — [[SYNC-PRD-001#R15]] 속도 목표와 「파이썬 판보다 느린 항목 없음」 | L14~L16 | M |

#325(재구축이 파일을 지운 커밋에서 실패)와 카드 BX는 파이썬 판에서 먼저 한다 — [[SYNC-CODE-001]].

---

## 2. 통합 테스트 — 공용 계약 시험

[[SYNC-INFRA-001]] 9.8. 저장소 루트의 `contract/`(카드 L2)는 **주소와 토큰만 받는** HTTP·MCP·git 시나리오다 — 어느 앱도 import하지 않는다. **기준은 파이썬 폐쇄망판**(Docker 싱크독_로컬 묶음, [[SYNC-INFRA-001]] 8.1)이고 Rust 판이 같은 결과를 내야 한다. 카드마다 그 카드가 닫는 시나리오를 더하고 파이썬 판에서 먼저 통과시킨다 — Rust 카드의 완료 조건이다([[SYNC-STD-004#DEV-14]]).

| 시나리오 | 카드 | 검증하는 것 |
|---|---|---|
| [[SYNC-SCN-001#S1]] | L3 · L7 | MCP로 문서가 쌓이고 커밋·참조가 생긴다 |
| [[SYNC-SCN-001#S2]] | L8 · L9 | 웹에서 읽고 완료로 올린다 |
| [[SYNC-SCN-001#S3]] | L7 · L8 | 코딩 중 에이전트가 항목·참조를 조회한다 |
| [[SYNC-SCN-001#S4]] | L7 · L8 | 상위 항목이 사라지면 하위 참조가 끊어진 것으로 보인다 |
| [[SYNC-SCN-001#S5]] | L3 · L6 | 토큰을 발급해 MCP로 붙고 자기 프로젝트를 만든다 |
| [[SYNC-SCN-001#S6]] | L8 | 그래프·순서 읽기·원본 탭 |
| [[SYNC-SCN-001#S7]] | L10 · L11 | 플랫폼 없이 push한 것이 반영된다 |
| [[SYNC-SCN-001#S8]] | L14 | 캡처를 붙여 묻고 다음 날 이어 간다 |
| [[SYNC-SCN-001#S9]] | L12 · L13 | 코드 그래프로 구현이 명세대로인지 본다 |
| [[SYNC-SCN-001#S10]] | L6 · L10 | GitHub 없이 서버에 명세를 쌓는다 |

**돌리는 법** — `cd contract && uv run pytest --target both`(기본). 파이썬 판은 지금 작업 트리로 이미지를 만들어 띄우고, Rust 판은 `local/`을 빌드해 띄운다(`cargo xtask pg-fetch` 먼저). 시험마다 그 기능을 닫는 카드를 적는다(`@pytest.mark.card("L3")`) — 파이썬 판은 전부 돌고, Rust 판은 이 문서의 완료란이 찬 카드만 돈다(나머지는 건너뜀으로 센다). 카드를 끝내기 전 확인은 `--with-card L3`.

**계약 밖** — API-001에 없는 프레임워크 동작은 두 판이 달라도 된다(사용자 결정 2026-10-07): 끝 슬래시 리다이렉트(307) · `/docs`·`/redoc`·`/openapi.json` · GET 경로의 HEAD · Range(206) · ETag 값의 꼴 · Host 머리 없는 요청. 화면과 에이전트는 이것들을 쓰지 않는다.

속도는 카드 L17이 잰다 — [[SYNC-PRD-001#R15]]의 수치를 같은 PC에서 두 판을 나란히(9.8).

---

## 3. 커밋·PR 목록

카드의 `완료` 행에 기록한다. PR 하나 = 카드 하나. 가지는 `card/L1-…`, 커밋은 `spec(SYNC-MS-012): …`(MINISPEC) 다음 `code(L1): Type.method — 요약`([[SYNC-STD-004#DEV-15]]).

| 카드 | 브랜치 | 커밋 | PR | 날짜 |
|---|---|---|---|---|

---

## 4. 미결사항

- [ ] `main`이 아닌 가지를 push했을 때 — 파이썬 판처럼 받아 두기만 하나([[SYNC-UC-001#UC-H21]] 3a), git을 부르기 전에 거절하나. Rust 판은 ref 명령을 먼저 읽으므로 둘 다 된다([[SYNC-INFRA-001]] 9.1). 카드 L10 전에 정한다
- [ ] 저장소에 커밋된 `graphify-out/graph.json`을 따를지 — 파이썬 판은 그 파일이 있으면 그것을 쓴다([[SYNC-MS-011#codegraph.load]] 1). Rust 판에는 graphify가 없다. 카드 L12 전에 정한다
- [ ] 되살리기가 Docker 판(파이썬 폐쇄망판)의 백업 파일도 받을지 — 두 판은 같은 표를 쓴다([[SYNC-INFRA-001]] 9.2). 카드 L16 전에 정한다
