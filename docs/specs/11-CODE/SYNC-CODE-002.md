---
doc_id: SYNC-CODE-002
type: CODE
title: 구현 계획 — 싱크독_로컬 (Rust) 슬라이스 카드와 커밋 기록
status: draft
upstream: [SYNC-STD-004, SYNC-DOM-004, SYNC-PRD-001, SYNC-INFRA-001, SYNC-API-001, SYNC-API-002, SYNC-UI-002, SYNC-SCN-001]
---

# 구현 계획 — 싱크독_로컬 (Rust)

## 0. 이 문서가 다루는 것

11단계 CODE의 **둘째 구현** 것이다([[SYNC-STD-001]] 2.11 · [[SYNC-INFRA-001#C11]]). 파이썬 판(싱크독_깃허브)의 계획은 [[SYNC-CODE-001]]이다. 카드 ID는 이 문서에서 따로 센다 — `L1`·`L2`…. 카드 형식과 완료 조건은 파이썬 판과 같고([[SYNC-STD-004#DEV-12]] · [[SYNC-STD-004#DEV-14]]) Rust 카드는 계약 시험까지 통과해야 끝난다. 구조는 [[SYNC-DOM-004]].

**MINISPEC은 카드의 첫 커밋으로 쓴다**([[SYNC-STD-004#DEV-13]]). 그래서 L1만 표가 있고 나머지는 하는 일과 선행만 있다 — 카드를 받을 때 그 카드의 표를 쓴다. 아직 없는 MINISPEC 항목을 미리 가리키지 않는다.

**진행 상황**: 카드 18장(L1~L18). 완료 6(L1·L2 2026-10-07, L3~L6 2026-10-08). 첫 릴리즈 `local-v0.1.0`(L4). L1은 계약 시험 없이 병합하고 완료란은 L2 뒤에 적었다(사용자 결정 2026-10-07).

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
| 완료 | 2026-10-07 · 브랜치 `card/L1-walking-skeleton`(a7cf251 #338) · `cargo test` 32 · clippy(리눅스·윈도) · 윈도 `cargo check` · `xtask migrations --check` · `schema-check` 같음 · `check_code` Rust 15/15 · `check_calls` 0/0 · 계약 시험(L2) Rust L1 몫 22/22 · 화면은 Playwright로 셸·`/api/me` 확인 · 되먹임: 그래프 `Cls.m` 해석(#336·#337) |

#### L2 계약 시험 틀 — 두 판을 띄워 같은 시나리오를 돌린다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 9.8 · [[SYNC-STD-004#DEV-14]] · [[SYNC-PRD-001#R15]](같은 화면·같은 API) · 사용자 결정 2026-10-07(시험이 두 판을 직접 띄운다 · 아직 없는 기능은 카드 표시로 건너뛴다 · 프레임워크 차이는 계약 밖 · `contract/`는 자기 uv 프로젝트) |
| 구현 | 저장소 루트 `contract/` — pytest·httpx·mcp, 앱을 import하지 않는다 · `--target python\|rust\|both` · 파이썬 판은 작업 트리로 만든 이미지를 Docker(폐쇄망판 구성, 빈 볼륨·임시 포트), Rust 판은 `syncdoc-local`을 임시 데이터 자리로 띄우고 끝나면 지운다 · 시험마다 카드 표시 `@pytest.mark.card("L1")` — Rust 판은 이 문서에서 완료된 카드만 돈다 · 가짜 모델 서버(OpenAI 호환) |
| 테스트 | 파이썬 판에서 전부 통과 · Rust 판에서 L1 몫 전부 통과(`/health`·`/api/me`·Host·Origin 가드·GitHub 경로·`/login`·API 앞머리 404·405·정적 파일 캐시와 304·`/specs`) · MCP 틀(L3 표시)은 파이썬만 |
| 선행 | L1 |
| 완료 | 2026-10-07 · 브랜치 `card/L2-contract`(47049c8 #339) · spec 6 + code 1 · `uv run pytest --target both --with-card L1` 46 통과·2 건너뜀(Rust L3) · 파이썬 판 24/24 · validate 0/0 · `check_calls` 층 없음 0·안 맞는 줄 0 · 되먹임: DOM-002 `contract/**` 층 줄을 거둠(그래프가 시험 파일을 뺀다) |

#### L3 토큰·MCP — 토큰을 발급해 에이전트가 `/mcp`로 붙는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-API-001#GET/api/me/tokens]] · [[SYNC-API-001#POST/api/me/tokens]] · [[SYNC-API-001#DELETE/api/me/tokens/{id}]] · [[SYNC-API-002]] 1장·2장 · [[SYNC-MS-016]] · [[SYNC-SEQ-001#SEQ-C2]] · [[SYNC-INFRA-001]] 9.8 · 사용자 결정 2026-10-08(`get_template`은 L6 · 도구 13개를 다 선언하고 못 만든 것은 `not-implemented` · 도구 선언·SSE 꼴·검증 문장까지 바이트로 같다 · MCP는 파이썬 SDK의 핸드셰이크 경로를 통째로 옮긴다, 2026-07-28 새 프로토콜은 L18) |
| 구현 | `core/account` 토큰 넷([[SYNC-MS-016]]) · `server/web` 토큰 세 경로 · `server/mcp` — 인증(Bearer, 통과하면 응답 전에 커밋)·전송(streamable HTTP, 세션 없음)·분배·처리기·도구 선언(`declarations.json` — `cargo xtask mcp-tools`가 파이썬 판에서 만든다) · `server/compat` — 파이썬 호환 층(값·repr·파이썬 json·jiter·pydantic 오류 문장·lax 검증). 옮긴 판은 [[SYNC-DOM-004]] 1장. 못 만든 도구와 그것을 만드는 카드 — `init_project`·`get_template` L6 · `list_documents`·`get_document`·`get_item`·`get_references`·`create_document`·`update_document` L7 · `delete_document`·`restore_document`·`change_status` L9 · `upload_code` L10 · `get_code_graph` L12 |
| 테스트 | `cargo test`(MS-016 테스트 관점 · 호환 층의 문장) · 계약 L3 — 토큰 세 경로의 모양과 값 · MCP 사례 표(인증·initialize·tools/list 바이트·SSE 꼴·Accept·Content-Type·봉투 오류·모르는 메서드·도구) · **두 판 차이 시험**(씨앗 고정 무작위 사례를 두 판에 보내 바이트로 비교, `--target both`) · 화면 UI-13 토큰 발급·폐기 |
| 선행 | L1 |
| 완료 | 2026-10-08 · 브랜치 `card/L3-token-mcp`(7276b48 #341) · spec 9 + code 9 · `cargo test`(core 토큰 7 · server MCP 4 · compat 18) · clippy(리눅스·윈도) · 윈도 `cargo check` · `xtask migrations --check`·`mcp-tools --check`·`schema-check` · 계약 `--target both --with-card L3` 263 통과·1 건너뜀(get_document L7) · 두 판 차이 시험 씨앗 1·2·3(2000)·77(10000) 전부 같음 · `check_code` Rust 19/19 · `check_calls` 0/0 · 화면 UI-13 토큰 발급·폐기는 Playwright로(사람 확인은 따로) · 되먹임: MS-016 `revoke_token` int4 밖은 internal(계약 시험이 찾음), DOM-002 층 표 `contract/**` 다시, 계약 밖에 `connection` 머리 |

#### L4 설치형 껍데기 — 깔아 쓰는 프로그램이 된다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 9.1·9.2·9.4·9.5 · [[SYNC-PRD-001#R15]] · [[SYNC-MS-012#tray.run]] · [[SYNC-MS-012#runtime.run]] · [[SYNC-MS-012#privilege.drop_admin]] · 사용자 결정 2026-10-08(트레이는 열기·끝내기 · 자동 시작 기본 끔, 리눅스는 XDG autostart(L16) · 바탕화면 바로 가기 기본 · 태그 → Release, 0.1.0 정식 · 아이콘은 새로 그린다 · x86_64, 바로 가기로 켜면 브라우저) |
| 구현 | `crates/app` — `tray.rs`(tray-icon: 윈도 메시지 루프, 리눅스 StatusNotifierItem), `main.rs`(트레이가 메인 스레드), `privilege.rs`(윈도 관리자 권한 내려놓기 — PostgreSQL이 관리자 권한을 거부한다), `runtime.run`(`--autostart`·첫 켜기의 브라우저·트레이 끝내기) · `packaging/` — 아이콘 원본·NOTICE·NSIS·.desktop·AppRun · `xtask` — `package windows\|linux`(재료를 모아 setup.exe·.deb·AppImage), `icon`, `pg-fetch --target` · `.github/workflows/local-release.yml` |
| 테스트 | `cargo test`(트레이 끝내기 → 끄는 순서, `--autostart`면 브라우저 안 엶) · 워크플로 — 윈도 setup.exe를 조용히 깔아 켜고(러너는 관리자 — 권한을 내려놓고 켠다) `/health`, 지운 뒤 데이터 자리가 남는지 · 리눅스 .deb·AppImage도 같이 · 계약(L1~L3) 그대로 · 사람 확인 — 윈도에서 깔아 트레이·바로 가기·제거 |
| 선행 | L1 |
| 완료 | 2026-10-08 · 브랜치 `card/L4-installable`(98dcf88 #343) · spec 11 + code 10 · `cargo test` 62 · clippy(리눅스·윈도) · 윈도 `cargo check` · `check_code` Rust 21/21 · `check_calls` 안 맞는 줄 0 · 계약 `--target rust` 130 통과 · 워크플로 — 윈도 setup.exe를 조용히 깔아 켜고 `/health`·`/api/me`, 지운 뒤 데이터 자리가 남는다(러너는 관리자 — 권한을 내려놓고 다시 켜 프로세스 둘) · 리눅스 .deb·AppImage 켜기·끄기 · 태그 `local-v0.1.0` → GitHub Release(정식, setup.exe·.deb·AppImage) · 사람 확인(윈도 트레이·바로 가기·제거)은 따로 · 되먹임: 윈도 관리자 토큰에서 PostgreSQL이 거부 — MS-012 `privilege.drop_admin`(줄인 토큰 + 기본 DACL에 사용자)·DOM-004·INFRA 9.4, `pg_ctl start` 출력은 파이프가 아니라 파일로(윈도에서 서버가 파이프를 물려받는다) |

#### L5 명세 엔진 — frontmatter·규약 검증·항목·diff가 파이썬 판과 바이트로 같다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-MS-002]] · [[SYNC-STD-001]] 1장·3장·4장 · [[SYNC-DOM-004]] 4.3 · [[SYNC-STD-004#DEV-7]] · [[SYNC-STD-004#DEV-16]] · 사용자 결정 2026-10-08(바이트까지·유니코드까지 · 파이썬 diff 버그는 파이썬을 먼저 고친다(#345) · 정답 파일 + 무작위 차이 시험 · 범위는 엔진 + DB 읽는 둘) |
| 구현 | [[SYNC-MS-014#markdown.parse_frontmatter]] · [[SYNC-MS-014#markdown.masked_lines]] · [[SYNC-MS-014#markdown.headings]] · [[SYNC-MS-014#markdown.cut_blocks]] · [[SYNC-MS-014#SpecService.item_blocks]] · [[SYNC-MS-014#SpecService.validate]] · [[SYNC-MS-014#SpecService.check]] · [[SYNC-MS-014#SpecService.apply_frontmatter]] · [[SYNC-MS-014#SpecService.diff]] · [[SYNC-MS-014#SpecService.diff_bodies]] · 층 코드 — `core/src/pycompat/`(유니코드 표 생성물·strip·repr — server/compat의 `printable.rs`를 내려 옮김·정규식 문자 클래스·difflib) · `spec/{model,repo}.rs` · `types.rs` 열거형·DTO · `Problem::ConventionViolation` · xtask `unicode-tables [--check]`·`spec-golden [--check]`·`spec-diff` |
| 테스트 | `cargo test` — 정답 파일(`crates/core/tests/golden/spec.json`, 꼴 모음 약 150) 전부 같다 · 지금의 명세 전부 위반 0·경고 0 · 시험 DB로 `item.reused`·복구 예외·`web_revert`·diff의 판 조회·`not-found` · `cargo xtask spec-diff` — 지금의 명세·템플릿 + 명세마다 git 이력 다섯 판 diff + 씨앗 고정 무작위 2000 차이 0 · 계약 몫 없음(HTTP로 닿는 것은 L7부터) — `--target both` 그대로 통과 |
| 선행 | L1 · #345 |
| 완료 | 2026-10-08 · 브랜치 `card/L5-spec-engine`(18cab61 #347) · 선행 #345(#346 — 파이썬 판 diff가 `---` 줄 삭제·`++` 줄 추가를 빠뜨리던 것) · spec 6 + code 15 · `cargo test` 76(정답 파일 122 사례 같음 · 실제 명세·템플릿 위반 0·경고 0 · 시험 DB로 item.reused·복구 예외·diff 판 조회·not-found) · `cargo xtask spec-diff` 기본 4671 사례·씨앗 1·2·3·77(5000) 각 11421 사례 다른 것 0 · `unicode-tables`·`spec-golden`·`migrations`·`mcp-tools --check` · `schema-check` 같음 · clippy(리눅스·윈도) · 윈도 `cargo check` · 워크플로 녹색 · `check_code` Rust 31/31 · `check_calls` 코드만·명세만·안 맞는 줄 0 · 계약 `--target both` 263 통과·1 건너뜀(L5 몫 없음) · 되먹임: MS-014 `validate`의 호출하는 것에 `parse_frontmatter`(check_calls가 찾음), STD-001 `item.pattern` 꼴을 검사기와 같게, server/compat의 `printable.rs`를 core `pycompat`으로 |

#### L6 git·서버 저장 — 서버 저장으로 프로젝트를 만들고 지운다(보관)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-MS-001]] · [[SYNC-MS-009]] · [[SYNC-UC-001#UC-A1]] · [[SYNC-UC-001#UC-H17]] · [[SYNC-SCN-001#S5]] · [[SYNC-SCN-001#S10]] · [[SYNC-INFRA-001]] 6장·9.1·9.2·9.3 · [[SYNC-API-002#init_project]] · [[SYNC-API-002#get_template]] · 사용자 결정 2026-10-08(`get_template`은 소유 프로젝트 · 저장소 `STD/`를 먼저 · 요약 전부 · 보관본 재구축 갈래만 L11 · Rust만 git 격리 · 파이썬 어긋남은 파이썬 먼저(#349)) |
| 구현 | [[SYNC-MS-019#Git.init_bare]] · [[SYNC-MS-019#Git.clone]] · [[SYNC-MS-019#Git.exists]] · [[SYNC-MS-019#Git.list]] · [[SYNC-MS-019#Git.read]] · [[SYNC-MS-019#Git.commit_push]] · [[SYNC-MS-019#Git.init_specs]] · [[SYNC-MS-013#ProjectService.init_project]] · [[SYNC-MS-013#ProjectService.delete_project]] · [[SYNC-MS-013#ProjectService.get]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-013#ProjectService.list_owned]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.count_missing_by_document]] · [[SYNC-MS-018#queries.project_summary]] · [[SYNC-MS-012#paths.git]] · 층 코드 — `types.rs` 요약 DTO · `errors.rs` 프로젝트 문제 다섯·`not-implemented`·git 실패 · server: MCP가 상태·인증된 사용자를 받는다, 도구 `init_project`·`get_template`, 경로 셋, `InitProject` 검증(pattern 더함) |
| API | [[SYNC-API-002#init_project]] · [[SYNC-API-002#get_template]] · [[SYNC-API-001#GET/api/projects]] · [[SYNC-API-001#POST/api/projects]] · [[SYNC-API-001#DELETE/api/projects/{code}]] |
| 테스트 | `cargo test`(git 어댑터는 임시 자리의 진짜 git과 사용자 설정 흉내 · 서비스·요약은 시험 DB) · 계약 L6 — MCP 만들기·중복·나쁜 코드·github 저장·`get_template` 타입·서브타입·없는 것, REST 만들기·422·지우기 → 다시 만들기 `existing-specs` · 두 판 차이 시험이 두 도구를 바이트로(`archived_at` 가림) · 워크플로 — 윈도 MinGit으로 만들기·지우기 |
| 선행 | L3 · L5 · #349 |
| 완료 | 2026-10-08 · 브랜치 `card/L6-server-storage`(8654495 #351) · 선행 #349(#350 — 파이썬 판 보관본 정렬·`git.exists` 언어·quotepath) · spec 12 + code 25 · `cargo test` 98(git 어댑터는 임시 자리의 진짜 git — pre-push 훅으로 rebase·충돌까지 · 서비스·요약은 시험 DB) · 계약 `--target both --with-card L6` 344 통과·2 건너뜀(get_document L7 · 보관본 재구축 L11) · 두 판 차이 시험이 이제 `init_project`·`get_template`까지 — 씨앗 1·2·3 × 2000 다른 것 0 · 워크플로 녹색 — 윈도(MinGit, 권한을 내린 토큰)·리눅스(.deb, 시스템 git)에서 만들고 지우기 · clippy(리눅스·윈도) · 윈도 `cargo check` · xtask `--check` 넷·`schema-check` · `check_code` Rust 47/47 · `check_calls` 0 · 사람 확인(윈도에서 에이전트로 init_project → get_template)은 따로 · 되먹임: MS-018 `project_summary`가 `repos`를 받는다, MS-013 init_project의 호출하는 것에 `get`(check_calls), git은 `self.repos.git`으로 바로(지역 변수면 그래프가 놓친다), 도구 성공 결과의 `isError:false`·지우기 204의 `application/json`(계약 시험), `GET /api/projects`를 L6에서 함께(요약이 있어 L8 몫을 당김) |

**다음 카드** — 받을 때 표를 쓴다. 하는 일과 선행만 먼저 적는다.

| 카드 | 하는 일 | 선행 | 크기 |
|---|---|---|---|
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
| L17 속도·출시 판정 | 두 판을 같은 PC에서 잰다 — [[SYNC-PRD-001#R15]] 속도 목표와 「파이썬 판보다 느린 항목 없음」 | L14~L16 · L18 | M |
| L18 새 MCP 프로토콜 | 2026-07-28 — 핸드셰이크 없는 요청 하나짜리 봉투 · `server/discover`·`subscriptions/listen`. 파이썬 SDK의 `_streamable_http_modern`을 옮긴다(사용자 결정 2026-10-08) | L3 | L |

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

**돌리는 법** — `cd contract && uv run pytest --target both`(기본). 파이썬 판은 지금 작업 트리로 이미지를 만들어 띄우고, Rust 판은 `local/`을 빌드해 띄운다(`cargo xtask pg-fetch` 먼저). 시험마다 그 기능을 닫는 카드를 적는다(`@pytest.mark.card("L3")`) — 파이썬 판은 전부 돌고, Rust 판은 이 문서의 완료란이 찬 카드만 돈다(나머지는 건너뜀으로 센다). 카드를 끝내기 전 확인은 `--with-card L3`. **두 판 차이 시험**(카드 L3~)은 같은 무작위 사례(씨앗 고정)를 두 판에 보내 상태·머리·본문을 바이트로 비교한다 — 두 판이 다 떠 있을 때(`--target both`)만 돈다.

**계약 밖** — API-001에 없는 프레임워크 동작은 두 판이 달라도 된다(사용자 결정 2026-10-07): 끝 슬래시 리다이렉트(307) · `/docs`·`/redoc`·`/openapi.json` · GET 경로의 HEAD · Range(206) · ETag 값의 꼴 · Host 머리 없는 요청 · 응답의 `date`·`server`·`connection` 머리와 본문을 나눠 보내는 꼴(chunked·content-length). 화면과 에이전트는 이것들을 쓰지 않는다. **MCP-Protocol-Version 머리가 핸드셰이크 판(2024-11-05~2025-11-25)이 아닌 요청**도 L18까지 계약 밖이다(사용자 결정 2026-10-08).

**명세 엔진**(카드 L5)은 HTTP로 닿기 전이라 계약 시험 대신 정답 파일(`cargo test`)과 `cargo xtask spec-diff`(두 판에 같은 본문을 돌려 바이트 비교)로 맞춘다 — 엔진을 고치면 둘 다 돌린다.

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
