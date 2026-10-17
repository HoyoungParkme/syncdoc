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

**진행 상황**: 카드 21장(L1~L21). 완료 21(L1·L2 2026-10-07, L3~L6 2026-10-08, L7~L18 2026-10-11, L19~L21 2026-10-12). 첫 릴리즈 `local-v0.1.0`(L4), 리눅스 출시 판정 통과 뒤 `local-v0.2.0`(L17) — 윈도 판정은 못 미쳐 카드 L19, 두 판정 통과 뒤 `local-v0.3.0`(L19). 설치본을 사람 확인(DEV-17) 차례로 눌러 본 결함 — 윈도 PostgreSQL 콘솔 창(#392)·같은 문서 안 이동(#393)·관리 카드(#394) — 을 고쳐 `local-v0.3.1`(2026-10-12). 사람 확인에서 정한 것 — 코드 그래프 커뮤니티(L20)·UI-8 문서 노드(#398) — 을 담아 `local-v0.3.2`(2026-10-12). 그래프를 읽기 쉽게 — UI-17 커뮤니티 이름·나누기·멈춘 배치(BY·BZ), UI-15 문서별 접기(CA), UI-8 찾기·고르기·선은 고른 것만(CB·L21) — `local-v0.3.3`(2026-10-12). L1은 계약 시험 없이 병합하고 완료란은 L2 뒤에 적었다(사용자 결정 2026-10-07)

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
| 구현 | [[SYNC-MS-019#Git.init_bare]] · `Git.clone`(L19에서 뺐다 — [[SYNC-MS-019]] 0장) · [[SYNC-MS-019#Git.exists]] · [[SYNC-MS-019#Git.list]] · [[SYNC-MS-019#Git.read]] · `Git.commit_push`(L19에서 뺐다 — [[SYNC-MS-019]] 0장) · [[SYNC-MS-019#Git.init_specs]] · [[SYNC-MS-013#ProjectService.init_project]] · [[SYNC-MS-013#ProjectService.delete_project]] · [[SYNC-MS-013#ProjectService.get]] · [[SYNC-MS-013#ProjectService.get_owned]] · [[SYNC-MS-013#ProjectService.list_owned]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.count_missing_by_document]] · [[SYNC-MS-018#queries.project_summary]] · [[SYNC-MS-012#paths.git]] · 층 코드 — `types.rs` 요약 DTO · `errors.rs` 프로젝트 문제 다섯·`not-implemented`·git 실패 · server: MCP가 상태·인증된 사용자를 받는다, 도구 `init_project`·`get_template`, 경로 셋, `InitProject` 검증(pattern 더함) |
| API | [[SYNC-API-002#init_project]] · [[SYNC-API-002#get_template]] · [[SYNC-API-001#GET/api/projects]] · [[SYNC-API-001#POST/api/projects]] · [[SYNC-API-001#DELETE/api/projects/{code}]] |
| 테스트 | `cargo test`(git 어댑터는 임시 자리의 진짜 git과 사용자 설정 흉내 · 서비스·요약은 시험 DB) · 계약 L6 — MCP 만들기·중복·나쁜 코드·github 저장·`get_template` 타입·서브타입·없는 것, REST 만들기·422·지우기 → 다시 만들기 `existing-specs` · 두 판 차이 시험이 두 도구를 바이트로(`archived_at` 가림) · 워크플로 — 윈도 MinGit으로 만들기·지우기 |
| 선행 | L3 · L5 · #349 |
| 완료 | 2026-10-08 · 브랜치 `card/L6-server-storage`(8654495 #351) · 선행 #349(#350 — 파이썬 판 보관본 정렬·`git.exists` 언어·quotepath) · spec 12 + code 25 · `cargo test` 98(git 어댑터는 임시 자리의 진짜 git — pre-push 훅으로 rebase·충돌까지 · 서비스·요약은 시험 DB) · 계약 `--target both --with-card L6` 344 통과·2 건너뜀(get_document L7 · 보관본 재구축 L11) · 두 판 차이 시험이 이제 `init_project`·`get_template`까지 — 씨앗 1·2·3 × 2000 다른 것 0 · 워크플로 녹색 — 윈도(MinGit, 권한을 내린 토큰)·리눅스(.deb, 시스템 git)에서 만들고 지우기 · clippy(리눅스·윈도) · 윈도 `cargo check` · xtask `--check` 넷·`schema-check` · `check_code` Rust 47/47 · `check_calls` 0 · 사람 확인(윈도에서 에이전트로 init_project → get_template)은 따로 · 되먹임: MS-018 `project_summary`가 `repos`를 받는다, MS-013 init_project의 호출하는 것에 `get`(check_calls), git은 `self.repos.git`으로 바로(지역 변수면 그래프가 놓친다), 도구 성공 결과의 `isError:false`·지우기 204의 `application/json`(계약 시험), `GET /api/projects`를 L6에서 함께(요약이 있어 L8 몫을 당김) |

#### L7 저장 파이프라인 — 에이전트가 MCP로 명세를 쌓고 읽는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-MS-007]] · [[SYNC-MS-002]] · [[SYNC-MS-003]] · [[SYNC-MS-008]] · [[SYNC-SEQ-001#SEQ-1]] · [[SYNC-UC-001#UC-A6]] · [[SYNC-SCN-001#S1]] · [[SYNC-SCN-001#S3]] · [[SYNC-SCN-001#S4]] · [[SYNC-INFRA-001]] 4.3·9.1 · [[SYNC-API-002#create_document]] · [[SYNC-API-002#update_document]] · [[SYNC-API-002#list_documents]] · [[SYNC-API-002#get_document]] · [[SYNC-API-002#get_item]] · [[SYNC-API-002#get_references]] · 사용자 결정 2026-10-08(밀린 커밋이 있으면 `not-implemented(L11)` · 파이썬 어긋남은 파이썬 먼저(#353)) |
| 구현 | [[SYNC-MS-017#pipeline.write_lock]] · [[SYNC-MS-017#pipeline.read_lock]] · [[SYNC-MS-017#pipeline.wait_idle]] · [[SYNC-MS-017#pipeline.read_pending]] · [[SYNC-MS-017#pipeline.save_pipeline]] · [[SYNC-MS-014#SpecService.issue_doc_id]] · [[SYNC-MS-014#SpecService.precondition]] · [[SYNC-MS-014#SpecService.get_document]] · [[SYNC-MS-014#SpecService.get_item]] · [[SYNC-MS-014#SpecService.detect_deleted_items]] · [[SYNC-MS-014#SpecService.describe_items]] · [[SYNC-MS-014#SpecService.describe_documents]] · [[SYNC-MS-014#SpecService.create]] · [[SYNC-MS-014#SpecService.save]] · [[SYNC-MS-014#SpecService.item_pks]] · [[SYNC-MS-014#SpecService.neighbors]] · [[SYNC-MS-014#SpecService.resolve_item]] · [[SYNC-MS-015#ReferenceService.extract]] · [[SYNC-MS-015#ReferenceService.upstream]] · [[SYNC-MS-015#ReferenceService.downstream]] · [[SYNC-MS-015#ReferenceService.upstream_of_document]] · [[SYNC-MS-015#ReferenceService.resolve_missing]] · [[SYNC-MS-015#ReferenceService.mark_missing]] · [[SYNC-MS-016#AccountService.users_by_ids]] · [[SYNC-MS-018#queries.document_list]] · [[SYNC-MS-018#queries.document_view]] · [[SYNC-MS-018#queries.item_view]] · [[SYNC-MS-018#queries.item_references_view]] · `Git.fetch`(L19에서 뺐다 — [[SYNC-MS-019]] 0장) · [[SYNC-MS-019#Git.rev_list_count]] · [[SYNC-MS-012#runtime.shutdown]](쓰기 락 기다림) · 층 코드 — `types.rs` 문서·항목·참조 DTO · `errors.rs` 저장 문제 다섯·`not-found`의 `available_items` · `spec`의 `check`·`validate`·`apply_frontmatter`가 타입을 문자열로 · server: 도구 여섯 |
| API | [[SYNC-API-002#create_document]] · [[SYNC-API-002#update_document]] · [[SYNC-API-002#list_documents]] · [[SYNC-API-002#get_document]] · [[SYNC-API-002#get_item]] · [[SYNC-API-002#get_references]] |
| 테스트 | `cargo test`(서비스·파이프라인은 시험 DB + 임시 자리의 진짜 git — 동시 저장 둘이면 둘째가 `version-conflict`, 부른 쪽을 버려도 저장이 끝까지) · 계약 L7 — 만들기(경고·`next_step`)·고치기 v2·`version-conflict`·규약 위반·하위 있는 항목 삭제 → 확인 → `ref.broken`·끊긴 참조 → 되살리면 이어짐·모르는 타입·DOM 선행조건·목록·문서·항목(`~`)·위아래 참조·`available_items` · 두 판 차이 시험이 여섯 도구까지(커밋 해시·`+00:00` 시각 가림) · `spec-golden --check`·`spec-diff` 그대로 |
| 선행 | L6 · #353 |
| 완료 | 2026-10-08 · 브랜치 `card/L7-save-pipeline`(4a56078 #355) · 선행 #353(#354 — 파이썬 판 참조 조회 차례·`get_references`의 `raw_target` 덮어쓰기) · spec 14 + code 45 · `cargo test` 111(파이프라인 끝에서 끝 — 시험 DB + 진짜 git: 동시 저장 둘이면 둘째가 `version-conflict`, 부른 쪽을 버려도 저장이 끝까지, 밖의 커밋은 `not-implemented(L11)`, 쓰기 락 기다림) · 계약 `--target both --with-card L7` 447 통과·1 건너뜀(보관본 재구축 L11) — 스냅숏 `documents_closed` 51 사례가 파이썬 판과 바이트로 같다(해시·시각만 가림) · 문서 도구만 겨냥한 두 판 차이 시험(상태를 쌓으며 무작위 본문·참조·항목) 씨앗 1·2·3·77 × 1000 다른 것 0(씨앗 2 — 저장 165·삭제 확인 23·참조 조회 111) · L3 차이 시험 씨앗 1·2·3 × 2000 다른 것 0 · `spec-golden --check`·`spec-diff`(4692 사례) 다른 것 0 · xtask `--check` 넷·`schema-check` · clippy(리눅스·윈도) · 윈도 `cargo check` · 워크플로 녹색 · `check_code` Rust 77/77 · `check_calls` 0 · 되먹임: MCP 도구의 예상 밖 실패(git·DB)는 mcp 2.2.0처럼 「Error executing tool {name}」뿐(L6부터 글을 붙이고 있었다 — 빈 커밋 메시지 사례가 찾음), MS-017 테스트 관점 — 에이전트가 지운 ID를 다시 쓰면 `item.reused`(되살리기는 웹, L9), 「호출하는 것」 빠진 것(check_calls — MS-014 다섯·MS-015 extract·MS-017), L3 계약의 JSON 깊이 「넘음」을 9988로(파이썬 판이 같은 프로세스에서도 9987겹을 읽기도 못 읽기도 한다) |

#### L8 웹 읽기 — 화면이 프로젝트·문서·이력·관계도·체인을 읽는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-MS-008]] · [[SYNC-MS-002]] · [[SYNC-MS-003]] · [[SYNC-MS-001#ProjectService.asset_path]] · [[SYNC-SCN-001#S2]] · [[SYNC-SCN-001#S3]] · [[SYNC-SCN-001#S4]] · [[SYNC-SCN-001#S6]] · [[SYNC-UI-002]] UI-2·4·5·7·8·9·15·18 · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」 — 묻지 않고 진행, 끝에 모아 보고): 휴지통 **목록**(읽기)은 L8 — UI-4가 처음부터 부른다, 휴지통 쓰기는 L9 · 커밋 이메일은 L11 · 파이썬 `set` 차례까지 바이트로(`pycompat::pyset`) · 첨부 content-type은 파이썬 판 컨테이너(/etc/mime.types 없음)의 답 그대로 · `versions`는 파이썬 경로처럼 소유 검사가 없다 |
| 구현 | [[SYNC-MS-014#SpecService.resolve_items]] · [[SYNC-MS-014#SpecService.list_versions]] · [[SYNC-MS-014#SpecService.recent_changes]] · [[SYNC-MS-014#SpecService.list_items_by_project]] · [[SYNC-MS-015#ReferenceService.references_among]] · [[SYNC-MS-015#ReferenceService.count_downstream]] · [[SYNC-MS-015#ReferenceService.missing_in_project]] · [[SYNC-MS-013#ProjectService.asset_path]] · [[SYNC-MS-018#queries.project_detail]] · [[SYNC-MS-018#queries.project_items]] · [[SYNC-MS-018#queries.graph_view]] · [[SYNC-MS-018#queries.item_chain]] · [[SYNC-MS-018#queries.diff_with_impact]] · [[SYNC-MS-018#queries.downstream_view]] · [[SYNC-MS-018#queries.trash_list]] · [[SYNC-MS-014#SpecService.list_trashed]] · 층 코드 — `types.rs` 이력·관계도·체인·추적표 DTO · `pycompat/pyset.rs` · server: 경로 열셋, `schemas.rs` 응답 꼴(작성자 이름까지), `compat/fastapi.rs` 질의 문자열 검증 |
| API | [[SYNC-API-001#GET/api/projects/{code}]] · [[SYNC-API-001#GET/api/projects/{code}/docs]] · [[SYNC-API-001#GET/api/projects/{code}/flags]] · [[SYNC-API-001#GET/api/projects/{code}/graph]] · [[SYNC-API-001#GET/api/projects/{code}/files/{path}]] · [[SYNC-API-001#GET/api/projects/{code}/trash]] · [[SYNC-API-001#GET/api/docs/{docId}]] · [[SYNC-API-001#GET/api/docs/{docId}/versions]] · [[SYNC-API-001#GET/api/docs/{docId}/diff]] · [[SYNC-API-001#GET/api/docs/{docId}/downstream]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/references]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/chain]] |
| 테스트 | `cargo test`(조회는 시험 DB + 진짜 git, `pyset`은 파이썬에서 뜬 차례와 비교) · 계약 L8 — MCP로 쌓은 프로젝트를 REST로 읽어 파이썬 판과 바이트로(해시·시각 가림): 상세·목록(단계·상태 조건과 422)·문제 목록 셋·관계도(범위)·첨부 not-found·문서·이력·diff(422·not-found)·추적표·항목·참조·체인 · 사람 확인 — 화면 UI-2·4·5·7·8·9·15·18을 data-el대로 |
| 선행 | L7 |
| 완료 | 2026-10-11 · 브랜치 `card/L8-web-read`(0958593 #357) · spec 10 + code 38 · `cargo test` 121(조회는 시험 DB + 진짜 git으로 PRD ← SCN ← UC를 쌓아 · `pycompat::pyset`은 파이썬 3.12에서 뜬 404 사례와 같다) · 계약 `--target both --with-card L7 --with-card L8` 574 통과·1 건너뜀 — L8 63 사례가 파이썬 판과 바이트로 같다(해시·시각만 가림 · 체인 행 안 차례는 정렬해 비교) · clippy(리눅스·윈도) · 윈도 `cargo check` · 워크플로 녹색 · xtask `--check` 넷·`schema-check` · `check_code` Rust 93/93 · `check_calls` 0 · 브라우저로 훑음(Rust 판·임시 데이터) — UI-4·5·7·8·9 콘솔 오류 없음 · 사람 확인(화면 data-el대로)은 따로 · 되먹임: 휴지통 **목록**을 L8로 당김(UI-4가 처음부터 불러 404 — 브라우저로 찾음), 파이썬 판은 int4 밖 판 번호의 diff에서 DB 거절로 500(계약이 찾음 — 같게), CPython set의 `add`는 지나온 빈 표시 가운데 **마지막** 것을 다시 쓴다(setobject.c — 정답 사례가 찾음), 체인 행 안 차례는 pk 값(=앞선 이력)에 매여 판끼리 비교하려면 이력이 같아야 한다 |

#### L9 상태·되돌리기·휴지통 — 사람이 웹에서 완료로 올리고, 되돌리고, 치운다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-MS-007#pipeline.change_status]] · [[SYNC-MS-007#pipeline.revert]] · [[SYNC-MS-007#pipeline.trash_document]] · [[SYNC-MS-007#pipeline.restore_document]] · [[SYNC-MS-007#pipeline.purge_document]] · [[SYNC-SCN-001#S2]] · [[SYNC-UC-001#UC-H7]] · [[SYNC-UC-001#UC-H8]] · [[SYNC-UC-001#UC-A7]] · [[SYNC-UC-001#UC-A8]] · [[SYNC-UC-001#UC-H18]] · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): 파이썬 판과 같은 차례·같은 문장, 휴지통 넣기도 따로 띄운 작업에서(push 뒤 DB까지) |
| 구현 | [[SYNC-MS-017#pipeline.change_status]] · [[SYNC-MS-017#pipeline.revert]] · [[SYNC-MS-017#pipeline.trash_document]] · [[SYNC-MS-017#pipeline.restore_document]] · [[SYNC-MS-017#pipeline.purge_document]] · [[SYNC-MS-017#pipeline.save_pipeline]](웹 갈래) · [[SYNC-MS-014#SpecService.apply_status]] · [[SYNC-MS-014#SpecService.trash]] · [[SYNC-MS-014#SpecService.trash_commit]] · [[SYNC-MS-014#SpecService.version_body]] · [[SYNC-MS-014#SpecService.delete_document]] · [[SYNC-MS-015#ReferenceService.inbound_of_document]] · 층 코드 — `types.rs` `TrashResult` · `errors.rs` 문제 다섯 · server: 경로 다섯, MCP 도구 셋, 요청 본문 `ChangeStatus`·`Revert` |
| API | [[SYNC-API-001#POST/api/docs/{docId}/status]] · [[SYNC-API-001#POST/api/docs/{docId}/revert]] · [[SYNC-API-001#DELETE/api/docs/{docId}]] · [[SYNC-API-001#POST/api/docs/{docId}/restore]] · [[SYNC-API-001#POST/api/docs/{docId}/purge]] · [[SYNC-API-002#change_status]] · [[SYNC-API-002#delete_document]] · [[SYNC-API-002#restore_document]] |
| 테스트 | `cargo test`(시험 DB + 진짜 git) · 계약 L9 — 웹·MCP로 상태 올리기(막힘·풀림)·되돌리기(already-current·422)·휴지통 넣기(확인·끊긴 참조)·되살리기·완전 삭제(문지기·번호 재발급)를 파이썬 판과 바이트로 · 사람 확인 — UI-5·7의 완료·되돌리기·휴지통 버튼 |
| 선행 | L8 |
| 완료 | 2026-10-11 · 브랜치 `card/L9-status-trash`(af7a06d #359) · spec 5 + code 25 · `cargo test` 124(시험 DB + 진짜 git — 완료로·막힘·내리기, 되돌리기, 휴지통·문지기·되살리기·완전 삭제와 번호 재발급) · 계약 `--target both --with-card L7 --with-card L8 --with-card L9` 666 통과·1 건너뜀 — L9 46 사례가 파이썬 판과 바이트로 같다 · L3 두 판 차이 시험 씨앗 1·2 × 2000 다른 것 0(세 도구가 실제로 돈다) · clippy(리눅스·윈도) · 윈도 `cargo check` · 워크플로 녹색 · `check_code` Rust 104/104 · `check_calls` 0 · 사람 확인(UI-5·7의 완료·되돌리기·휴지통 버튼)은 따로 · 되먹임: 파이썬 판은 int4 밖 `to_version`도 DB 거절로 500(diff와 같다 — 같게), 문제의 확장 필드 `title`(휴지통 확인의 문서 제목)이 problem 제목을 덮는 파이썬 꼴 그대로 |

#### L10 git 입구 — 서버 저장소에 git으로 clone·push한다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UC-001#UC-H21]] · [[SYNC-SEQ-001#SEQ-29]] · [[SYNC-MS-009#git.http_backend]] · [[SYNC-MS-001#ProjectService.server_origin]] · [[SYNC-INFRA-001]] 9.1 · [[SYNC-SCN-001#S10]] · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): `upload_code`는 L11로 — 올린 뒤 밀린 커밋 처리(`process_commit`)를 타야 끝난다 · push 뒤 밀린 커밋 읽기는 L11 전까지 `not-implemented`를 로그로만(파이썬처럼 배치 — 폴링이 메운다) · git 판(파이썬 컨테이너 2.47·이 PC 2.43·MinGit)마다 광고 바이트가 달라 계약은 상태·머리와 진짜 clone·push로 본다 |
| 구현 | [[SYNC-MS-013#ProjectService.server_origin]] · [[SYNC-MS-019#Git.advertise_refs]] · [[SYNC-MS-019#Git.service_rpc]] · server: `/git/{*rest}`를 `^(?P<code>[^/]+)\.git/(info/refs|git-upload-pack|git-receive-pack)$`로 가르는 입구 · Basic 인증(비밀번호 칸 = 개인 토큰) · 401 challenge · http-backend 머리·415 |
| API | [[SYNC-API-001#GET/git/{code}.git/info/refs]] · [[SYNC-API-001#POST/git/{code}.git/git-upload-pack]] · [[SYNC-API-001#POST/git/{code}.git/git-receive-pack]] |
| 테스트 | `cargo test`(임시 자리 진짜 git으로 광고·rpc) · 계약 L10 — 두 판에 진짜 `git clone`·`git push`(main·다른 가지·되감기·지우기), 인증 없음·틀린 토큰·남의 것·dumb·틀린 Content-Type·틀린 메서드는 바이트로 |
| 선행 | L9 |
| 완료 | 2026-10-11 · 브랜치 `card/L10-git-entrance`(31c9973 #365) · spec 9 + code 9 · `cargo test` 128(임시 자리 진짜 git — 광고·v2 판 판별·rpc·`server_origin`, 서버 시험은 진짜 git 클라이언트로 clone·main push·다른 가지·되감기 거절·지우기 거절·틀린 토큰) · 계약 `--target both --with-card L10` 800 통과·1 건너뜀 — L10 67 사례(401·404·405·415·Basic 해석·gzip)가 파이썬 판과 바이트로 같고 두 판에 진짜 clone·push · L3 두 판 차이 시험 씨앗 셋 · clippy(리눅스·윈도) · 윈도 `cargo check` · 워크플로 녹색 · `check_code` Rust 107/107 · `check_calls` 0 · 사람 확인(윈도 싱크독_로컬에 `git clone`·`git push`)은 따로 · 되먹임: 계약이 파이썬 판 버그 둘을 찾아 먼저 고쳤다 — #361(http-backend가 먼저 끝나면 약 1% 500) · #363(Basic 칸에 ASCII 아닌 글자면 500). 파이썬 3.12.13의 `b64decode(validate=True)`는 엄격(정규 `=`만, 남는 비트는 받음) — 로컬 3.12.3과 다르다 · 4장 미결(main 아닌 가지) 닫음 |

#### L11 따라잡기·재구축 — 서버 저장소에 민 것이 문서가 된다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S7]] · [[SYNC-SCN-001#S10]] 6 · [[SYNC-UC-001#UC-G1]] · [[SYNC-UC-001#UC-G2]] · [[SYNC-UC-001#UC-S6]] · [[SYNC-UC-001#UC-A10]] · [[SYNC-SEQ-001#SEQ-2]] · [[SYNC-SEQ-001#SEQ-21]] · [[SYNC-SEQ-001#SEQ-29]] · [[SYNC-SEQ-001#SEQ-30]] · [[SYNC-INFRA-001]] 9.1 켜기 · 파이썬 #325(재구축이 지운 커밋에서 실패 — #366으로 먼저 고침) · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): 코드 그래프 만들기(`schedule_code_graph`)는 L12 — 커밋 처리·재구축·코드 올리기가 부르지 않는다 · 주기 확인은 300초 고정(설정 키는 다섯뿐) · 파이썬 `scheduler`의 둘은 pipeline에 · 옮기기 둘은 서버 저장뿐이라 늘 거절 · 작성자는 늘 로컬 사용자 |
| 구현 | [[SYNC-MS-017#pipeline.read_pending]](밀린 커밋 처리까지) · [[SYNC-MS-017#pipeline.save_pipeline]](`github` 갈래 — 강등 커밋 포함) · [[SYNC-MS-017#pipeline.process_commit]] · [[SYNC-MS-017#pipeline.type_of_dir]] · [[SYNC-MS-017#pipeline.rebuild]] · [[SYNC-MS-017#pipeline.upload_code]] · [[SYNC-MS-017#pipeline.move_to_server]] · [[SYNC-MS-017#pipeline.move_to_github]] · [[SYNC-MS-017#pipeline.catch_up]] · [[SYNC-MS-017#pipeline.poll_loop]] · [[SYNC-MS-013#ProjectService.list_projects]] · [[SYNC-MS-013#ProjectService.repo_status]] · [[SYNC-MS-013#ProjectService.ensure_hook]] · [[SYNC-MS-013#ProjectService.sync_now]] · [[SYNC-MS-013#ProjectService.rebuild_index]] · [[SYNC-MS-013#ProjectService.init_project]](보관본 가져오기의 재구축) · [[SYNC-MS-014#SpecService.save]](재구축·상태 커밋) · [[SYNC-MS-014#SpecService.mark_deleted]] · [[SYNC-MS-014#SpecService.clear_index]] · [[SYNC-MS-014#SpecService.mark_convention_error]] · [[SYNC-MS-015#ReferenceService.clear]] · [[SYNC-MS-016#AccountService.user_for_commit]] · [[SYNC-MS-019#Git.changed_files]] · [[SYNC-MS-019#Git.log]] · `Git.checkout`(L19에서 뺐다 — [[SYNC-MS-019]] 0장) · [[SYNC-MS-019#Git.sync_readme]] · [[SYNC-MS-012#runtime.run]](켜기에 따라잡기·주기 확인) · [[SYNC-MS-012#runtime.shutdown]] · pycompat `is_digit`(파이썬 `str.isdigit` 표) |
| API | [[SYNC-API-001#GET/api/admin/repos]] · [[SYNC-API-001#POST/api/admin/repos/{code}/rebuild]] · [[SYNC-API-001#POST/api/admin/repos/{code}/hook]] · [[SYNC-API-001#POST/api/admin/repos/{code}/sync]] · [[SYNC-API-001#POST/api/admin/repos/{code}/move-to-server]] · [[SYNC-API-001#POST/api/admin/repos/{code}/move-to-github]] · [[SYNC-API-002#upload_code]] |
| 테스트 | `cargo test`(시험 DB · 임시 자리 · 진짜 git — 밀린 커밋 처리·파일 삭제·되살리기·앱 커밋 거르기·강등 커밋·재구축·코드 올리기·따라잡기) · 계약 L11 — 두 판에 진짜 `git push`로 명세를 넣어 문서·버전·참조가 바이트로 같고, 관리 경로 여섯·`upload_code`·보관본 가져오기를 바이트로 |
| 선행 | L10 · #325 |
| 완료 | 2026-10-11 · 브랜치 `card/L11-catch-up`(59f809a #369) · spec 10 + code 30 · `cargo test` 153(시험 DB · 임시 자리 · 진짜 git — 밀린 커밋 처리·파일 삭제·되살리기·앱 커밋 거르기·강등 커밋·재구축·코드 올리기·따라잡기·주기 확인, 실행 파일 시험: 꺼진 동안 민 명세가 켜면 문서) · 계약 `--target both --with-card L11` 887 통과·건너뜀 0 — L11 43 사례(진짜 push 흐름·관리 경로 여섯·upload_code)가 파이썬 판과 바이트로 같고 L6의 보관본 가져오기 시험도 Rust에서 돈다 · L3 두 판 차이 시험 씨앗 셋 · clippy(리눅스·윈도) · 윈도 `cargo check` · 워크플로 녹색 · `check_code` Rust 129/129 · `check_calls` 0 · 사람 확인(윈도 싱크독_로컬에 git push → 화면에 문서, UI-14 동기화·재구축·지금 가져오기)은 따로 · 되먹임: 파이썬 #325를 #366으로 먼저 고침(`git.log --diff-filter=d`) · 같은 항목 ID 둘을 git으로 밀면 두 판 모두 처리 지점이 멈춘다 — #368 · MCP 본문 한도(4MiB)가 올리기 한도(5MiB)보다 작아 크기 초과는 MCP로 닿지 않는다 · 저장 ↔ 커밋 처리의 future 고리는 사설 `process_file`을 상자에 담아 끊었다 |

#### L12 코드 그래프 — 코드가 명세대로인지 본다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S9]] · [[SYNC-UC-001#UC-S8]] · [[SYNC-UC-001#UC-H20]] · [[SYNC-PRD-001#R13]] · [[SYNC-INFRA-001]] 9.2 · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): 4장 미결 「커밋된 graph.json」 — 파이썬 판처럼 따른다(그때 두 판이 같은 원형에서 바이트까지 같다) · graph.json이 없으면 graphify 대신 tree-sitter로 원형을 뽑는다 — graphify의 이름 풀이를 다 옮기지 않아 호출 선이 파이썬 판보다 적을 수 있다 · 파이썬 `ast` 대신 tree-sitter-python · 커뮤니티는 L13(그 전엔 `community` 없음) · 코드에 묻기(`code/ask`)는 L14 · 재구축·프로젝트 만들기·재구축 위임이 연결 풀을 받는다 — 그래프 만들기를 따로 띄우려고. REST·MCP의 프로젝트 만들기는 트랜잭션 없이 연결을 넘겨 가져오기의 그래프 만들기가 커밋 뒤에 걸린다 |
| 구현 | [[SYNC-MS-022#codegraph.touches_code]] · [[SYNC-MS-022#codegraph.load]] · [[SYNC-MS-022#codegraph.extract]] · [[SYNC-MS-022#codegraph.reduce]] · [[SYNC-MS-022#codegraph.enrich]] · [[SYNC-MS-022#codegraph.spec_calls]] · [[SYNC-MS-022#codegraph.compare]] · [[SYNC-MS-022#codegraph.item_function]] · [[SYNC-MS-022#codegraph.item_neighbors]] · [[SYNC-MS-022#codegraph.layer_table]] · [[SYNC-MS-022#codegraph.layers]] · [[SYNC-MS-022#CodeGraphService.get]] · [[SYNC-MS-022#CodeGraphService.save]] · [[SYNC-MS-022#CodeGraphService.fail]] · [[SYNC-MS-022#CodeGraphService.read]] · [[SYNC-MS-017#pipeline.schedule_code_graph]] · [[SYNC-MS-017#pipeline.build_code_graph]] · [[SYNC-MS-017#pipeline.process_commit]] 5a · [[SYNC-MS-017#pipeline.rebuild]] 10 · [[SYNC-MS-013#ProjectService.init_project]](가져오기 뒤) · [[SYNC-MS-019#Git.changed_paths]] · [[SYNC-MS-019#Git.archive]] · [[SYNC-MS-018#queries.code_view]] · [[SYNC-MS-018#queries.code_calls]] · [[SYNC-MS-018#queries.code_source]] · [[SYNC-MS-018#queries.code_text]] |
| API | [[SYNC-API-001#GET/api/docs/{docId}/code]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code/source]] · [[SYNC-API-001#GET/api/projects/{code}/code-calls]] · [[SYNC-API-001#GET/api/projects/{code}/code/source]] · [[SYNC-API-002#get_code_graph]] |
| 테스트 | `cargo test`(정답 파일 — 파이썬 판이 같은 원형·같은 파일로 낸 줄이기·보강 결과와 바이트로 같다, 싱크독 저장소의 graphify 원형으로 · 시험 DB · 임시 자리 · 진짜 git — 코드 push 뒤 그래프·출처·실패 남기기) · 계약 L12 — 두 판에 같은 `graphify-out/graph.json`과 코드를 push해 코드 탭·관계도 코드 호출·코드 보기·`get_code_graph`가 바이트로 같고, graph.json 없는 프로젝트는 꼴만 |
| 선행 | L11 |
| 완료 | 2026-10-11 · 브랜치 `card/L12-code-graph`(5ef2d58 #371) · spec 11 + code 12 · `cargo test` 166(정답 파일 — 고정 저장소의 줄이기·보강이 파이썬 판과 바이트로 같다 · 시험 DB · 임시 자리 · 진짜 git — 그래프 행·코드 읽기·풀기·만들기·걸기·코드 조회) · `cargo xtask codegraph-diff` — 싱크독 저장소 전체(함수 1986·선 3404, 대조·층·항목 함수까지)가 파이썬 판과 같다 · 계약 `--target both --with-card L12` 975 통과·건너뜀 0 — L12 88 사례(같은 코드·graph.json push → 코드 탭·코드 보기·관계도·코드 그래프의 코드·get_code_graph, graph.json 없는 프로젝트는 꼴만) · L3 두 판 차이 시험 씨앗 셋 · clippy · 워크플로 녹색(윈도 빌드·설치·실행) · `check_code` Rust 152/152 · `check_calls` 0 · 사람 확인(윈도 싱크독_로컬에 코드 push → UI-5 코드 탭·UI-8 관계도 코드 호출)은 따로 · 되먹임: 검사기(코드 그래프)는 crate 밖에서 다시 내보낸 이름(`syncdoc_codegraph::load`)을 못 풀어 모듈 경로로 부른다 · 리눅스의 윈도 교차 검사는 L12부터 tree-sitter C 때문에 못 돈다 — PR 워크플로가 본다 · pycompat 집합 시험의 정답 자리를 crate 안으로 고침 |

#### L13 커뮤니티·노드 — 코드 그래프를 무리로 묶어 본다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S9]] · [[SYNC-UC-001#UC-S8]] 3 · [[SYNC-UC-001#UC-H20]] · [[SYNC-PRD-001#R13]] · [[SYNC-INFRA-001]] 9.2 · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): graphrs가 아니라 파이썬 판이 부르는 networkx 3.7 Louvain을 옮긴다 — 섞기는 파이썬 `random.Random(42)`(MT19937), modularity 합은 파이썬 3.12 `sum`(Neumaier 보정), graphify `load_node_link_graph`(다중 그래프 기본 — 차수에 겹친 선)·허브 라벨까지. 같은 원형이면 커뮤니티 번호·라벨이 바이트로 같다(INFRA 9.2의 「조금 다를 수 있다」를 쓰지 않는다) |
| 구현 | [[SYNC-MS-022#codegraph.communities]] · [[SYNC-MS-017#pipeline.build_code_graph]] 3 · [[SYNC-MS-018#queries.code_nodes]] |
| API | [[SYNC-API-001#GET/api/projects/{code}/code-graph]] |
| 테스트 | `cargo test`(pycompat 정답 — 섞기·합이 파이썬 3.12와 비트까지 · codegraph 정답 파일의 커뮤니티 · 시험 DB — 그래프 행의 커뮤니티·코드 그래프 노드) · `cargo xtask codegraph-diff`(싱크독 저장소 전체 커뮤니티) · 계약 L13 — L12의 고정 저장소로 코드 그래프 노드가 바이트로 같다 |
| 선행 | L12 |
| 완료 | 2026-10-11 · 브랜치 `card/L13-communities`(0d5b9a3 #373) · spec 3 + code 5 · `cargo test` 169(pycompat 정답 — 섞기·getrandbits·float 합이 파이썬 3.12와 비트까지 · codegraph 정답 파일의 커뮤니티 · 시험 DB — 그래프 행의 커뮤니티·코드 그래프 노드) · `cargo xtask codegraph-diff` — 싱크독 저장소 전체(함수 1986·커뮤니티 34)가 번호·라벨까지 파이썬 판과 같다 · 계약 `--target both --with-card L13` 987 통과·건너뜀 0 — L13: 코드 그래프 노드 바이트 같음, graph.json 없는 프로젝트는 꼴만 · clippy · 워크플로 녹색 · `check_code` Rust 154/154 · `check_calls` 0 · 사람 확인(윈도 싱크독_로컬 UI-17 코드 그래프의 커뮤니티 노드)은 따로 · 되먹임: graphify 원형에는 `multigraph` 키가 없어 networkx가 다중 그래프로 읽는다(라벨의 차수에 겹친 선이 든다) · L12 계약 고정 graph.json에서 graphify의 절대 경로 키를 뺐다 |

#### L14 대화·질문 탭 — 읽다가 묻고, 모델이 관계도를 따라 읽는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S3]] · [[SYNC-SCN-001#S9]] · [[SYNC-UC-001#UC-H19]] · [[SYNC-PRD-001#R11]] · [[SYNC-INFRA-001]] 5.3 · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): PDF 글자는 pypdf 대신 `lopdf`로 — 쪽 잇기·빈 쪽·깨진 PDF 규칙은 같고 글자는 다를 수 있다(모델만 읽는다) · 모델 호출은 `reqwest`(rustls, 운영체제 인증서) · 질문 스트림은 따로 띄운 작업이 이벤트를 통로로 넘긴다(시작 전 실패는 상태 코드, 뒤는 `error` 이벤트, `internal`은 끊김) · 받는 쪽이 끊기면 턴을 `CancelledError`로 닫는다 · 앞 대화 10턴은 상수(설정 키는 다섯뿐) · 대화·코드 그래프 행의 `delete_by_project`를 두고 프로젝트 해제가 부른다 |
| 구현 | [[SYNC-MS-020#Llm.step_stream]] · [[SYNC-MS-020#Llm.step]] · [[SYNC-MS-021#ConversationService.list]] · [[SYNC-MS-021#ConversationService.create]] · [[SYNC-MS-021#ConversationService.get]] · [[SYNC-MS-021#ConversationService.delete]] · [[SYNC-MS-021#ConversationService.delete_by_project]] · [[SYNC-MS-021#ConversationService.add_turn]] · [[SYNC-MS-021#ConversationService.finish_turn]] · [[SYNC-MS-021#ConversationService.history]] · [[SYNC-MS-021#ConversationService.add_attachment]] · [[SYNC-MS-021#ConversationService.remove_attachment]] · [[SYNC-MS-021#ConversationService.attachment_meta]] · [[SYNC-MS-021#ConversationService.attachment_bytes]] · [[SYNC-MS-021#ConversationService.attachment_text]] · [[SYNC-MS-021#ConversationService.pending_images]] · [[SYNC-MS-018#queries.ask_item]] · [[SYNC-MS-018#queries.ask_tool]] · [[SYNC-MS-018#queries.ask_code]] · [[SYNC-MS-018#queries.conversation_view]] · [[SYNC-MS-022#CodeGraphService.delete_by_project]] · [[SYNC-MS-013#ProjectService.delete_project]] 2 |
| API | [[SYNC-API-001#GET/api/projects/{code}/conversations]] · [[SYNC-API-001#GET/api/conversations/{id}]] · [[SYNC-API-001#POST/api/conversations/{id}/attachments]] · [[SYNC-API-001#GET/api/attachments/{id}]] · [[SYNC-API-001#POST/api/docs/{docId}/ask]] · [[SYNC-API-001#POST/api/projects/{code}/code/ask]] |
| 테스트 | `cargo test`(모델 스트림·단발·오류 접기를 작은 가짜 서버로 · 시험 DB — 대화·턴·첨부·종류·상한·소유 · 질문 루프 — 도구 아홉·상한·마무리·턴 닫기·답 속 링크) · 계약 L14 — 같은 가짜 모델(대본: 도구 호출 → 답, 조각 스트림)을 두 판이 불러 SSE 이벤트 바이트·대화 응답·첨부 응답이 같고 **두 판이 모델에 보낸 요청 본문도 같다** |
| 선행 | L8 · L12 |
| 완료 | 2026-10-11 · 브랜치 `card/L14-conversations`(417068f #375) · spec 6 + code 6 · `cargo test` 178(모델 스트림·단발·오류 접기를 작은 가짜 서버로 · 시험 DB — 대화·턴·첨부·종류·상한·소유·PDF 글자 · 질문 루프 — 도구·상한·마무리·턴 닫기·답 속 링크) · 계약 `--target both --with-card L14` 1083 통과 — L14 96: 같은 대본의 가짜 모델로 SSE 이벤트 바이트·대화·첨부 응답이 같고 두 판이 모델에 보낸 요청 본문도 같다 · clippy · 워크플로 녹색(리눅스·윈도) · `check_code` Rust 175/175 · `check_calls` 0 · 사람 확인(윈도 싱크독_로컬 UI-5·UI-17 묻기 탭 — 사내 모델로)은 따로 · 되먹임: 경계 없는 multipart의 제목은 starlette 문장(`Missing boundary in multipart.`) · 파이썬 판은 묻기 시작 전 실패(항목 없음 등)를 `session_scope`가 되돌려 턴이 남지 않는다 — Rust도 준비를 트랜잭션 하나로 · `check_calls`는 경로로 쓴 구조체 리터럴의 메서드를 못 따라간다(타입을 `use`하고 이름으로) · ask_tool의 「호출하는 것」에 `list_by_project`·`parse_frontmatter`를 더했다 |

#### L15 번들 가져오기 — 다른 곳의 저장소를 서버 저장 프로젝트로

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UC-001#UC-A1]] 1c · [[SYNC-PRD-001#R14]] · [[SYNC-INFRA-001]] 9.7 · 파이썬 판 카드 BX([[SYNC-CODE-001]], #376) · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): 입구는 `/api/projects/{code}` 경로에 POST를 붙여 `code`가 `bundle`일 때만 가져오기 — 정적 경로를 따로 두면 axum은 `GET /api/projects/bundle`을 405로 막지만 파이썬 판은 `{code}`의 GET으로 떨어져 `not-found`다. 그 밖의 코드로 POST하면 파이썬 판처럼 405(`Allow: GET, DELETE`) · 폼은 starlette·FastAPI 꼴 그대로 — multipart와 urlencoded, 같은 이름은 뒤의 것, 빈 문자열은 없는 것, 파일 아닌 칸 1MB 넘음·이름 없는 칸은 400(starlette 문장), 칸 오류는 선언 차례(`code`·`name`·`bundle`) · 폼 해석은 multer를 빼고 python-multipart 0.0.32 파서를 옮긴다(`compat/form.rs`) — 깨진 본문(경계·머리·끝 없음)의 답까지 같고 L14 첨부도 같은 길을 탄다. 문자 집합은 UTF-8·latin-1·ASCII 이름만 안다(그 밖은 latin-1 — 계약 밖) · 크기 상한 없음(파이썬 판과 같다) |
| 구현 | [[SYNC-MS-013#ProjectService.import_bundle]] · [[SYNC-MS-019#Git.clone_bare]] · `errors.rs` `BundleInvalid` · `compat/form.rs` · `compat/fastapi.rs` 폼 칸 · `routes/projects.rs` |
| API | [[SYNC-API-001#POST/api/projects/bundle]] |
| 테스트 | `cargo test`(폼 정답 — `xtask/py/form_cases.py`가 starlette에 넣어 얻은 답과 같다, 상한 넷 · git — 번들의 가지·태그 해시·원격 없음·HEAD·받기 규칙 · 시험 DB — 번들 → 문서·상태 이력·처리 지점, 골격 커밋 없음 · 번들 아님·main 없음 → `bundle-invalid`, 아무것도 안 남음 · 코드 형식·중복 · 남은 원본은 보관으로) · 계약 L15 — 같은 번들(고정 저장소를 시험이 git으로 묶는다)로 두 판의 응답·문서 목록·이력이 같고, 폼 오류·405가 바이트로 같다 |
| 선행 | L11 · BX |
| 완료 | 2026-10-11 · 브랜치 `card/L15-bundle`(7f15f04 #379) · spec 6 + code 5 · `cargo test` 183(폼 정답 748 — starlette에 넣어 얻은 답과 같다 · 상한 넷 · git `clone_bare` · 시험 DB — 번들 → 문서·상태·처리 지점, 골격 커밋 없음 · 번들 아님·main 없음 → 아무것도 안 남음) · 계약 `--target both --with-card L15` 1149 통과 — L15 66: 응답·가져온 뒤 프로젝트·문서·판 목록·폼 오류·405·404 바이트 같음 · clippy · 워크플로 녹색(리눅스·윈도) · `check_code` Rust 177/177 · `check_calls` 0 · 사람 확인(윈도 싱크독_로컬 UI-3 2.9 번들 파일로 가져오기)은 따로 · 되먹임: 폼 해석을 multer에서 python-multipart 옮김으로 바꿔 L14 첨부도 같은 길 · 계약 목록 응답은 다른 모듈이 만든 프로젝트가 섞여 그 시험의 코드만 거른다 |

#### L16 데이터 보호·「이 PC」 — 백업·되살리기·데이터 자리·자동 시작·같은 망 열기

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R15]] · [[SYNC-INFRA-001]] 9.3·9.4·9.5·9.6 · [[SYNC-UI-002#UI-13]] 10·11·12 · 사용자 결정 2026-10-07(같은 망 열기는 설정 파일만) · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): **Docker 묶음의 백업도 되살린다** — 백업 꼴을 카드 BR과 같게(tar에 `db.dump`·`origins.tar`, 이름 `syncdoc-{날짜}-{시각}.tar.gpg`), 암호는 OpenPGP 대칭(rpgp — `gpg --symmetric`과 서로 풀린다), 시각은 지역(jiff) · 백업은 켠 채로 — 덤프 먼저, 서버 저장소는 저장소마다 `git clone --mirror --no-local`(쓰기 멈춤 없이 일관, 앞선 커밋은 켤 때 따라잡기가 메운다) · 되살리기·옮기기·설정 저장은 **같은 프로세스 안 다시 켜기** — runtime이 두 고리(데이터 자리 · 켜기)를 돌고, 처리기는 검사 뒤 202. 트레이·포트는 그대로 · 처리기(server)와 일(app)은 server의 `LocalOps` 트레이트로 잇는다 · DB 되살리기는 `public` 스키마를 비우고 `pg_restore --single-transaction`(덤프에 없는 표가 남지 않는다) · 켤 때마다 `ProjectService.rehome`이 서버 저장소·작업 사본 자리를 맞추고 없는 작업 사본을 만든다 · 옮긴 자리를 가리키는 파일은 기본 자리 옆 `{이름}.location` · 설정 쓰기는 toml_edit(주석 보존) · 남기는 수 14 고정 · `/api/local*`은 Rust 판만(계약 밖) |
| 구현 | [[SYNC-MS-023#Local.info]] · [[SYNC-MS-023#Local.save_settings]] · [[SYNC-MS-023#Local.set_autostart]] · [[SYNC-MS-023#Local.backup_now]] · [[SYNC-MS-023#Local.restore]] · [[SYNC-MS-023#Local.move_to]] · [[SYNC-MS-023#backup.make]] · [[SYNC-MS-023#backup.list]] · [[SYNC-MS-023#backup.open]] · [[SYNC-MS-023#backup.restore]] · [[SYNC-MS-023#backup.daily]] · [[SYNC-MS-023#datadir.check]] · [[SYNC-MS-023#datadir.copy]] · [[SYNC-MS-023#autostart.enabled]] · [[SYNC-MS-023#autostart.set]] · [[SYNC-MS-012#runtime.run]] · [[SYNC-MS-012#runtime.bind]] · [[SYNC-MS-012#runtime.shutdown]] · [[SYNC-MS-012#tray.run]] · [[SYNC-MS-012#paths.data_dir]] · [[SYNC-MS-012#paths.set_data_dir]] · [[SYNC-MS-012#settings.load]] · [[SYNC-MS-012#settings.save]] · [[SYNC-MS-012#logs.init]] · [[SYNC-MS-012#logs.retarget]] · [[SYNC-MS-012#pg.start]] · [[SYNC-MS-013#ProjectService.rehome]] · `server/src/local.rs` · `routes/local.rs` · `SettingsDialog.tsx` 10·11·12 |
| API | [[SYNC-API-001#GET/api/local]] · [[SYNC-API-001#PUT/api/local/settings]] · [[SYNC-API-001#PUT/api/local/autostart]] · [[SYNC-API-001#POST/api/local/backups]] · [[SYNC-API-001#POST/api/local/restore]] · [[SYNC-API-001#POST/api/local/move]] |
| 테스트 | `cargo test`(진짜 PostgreSQL·git — 백업 꼴·암호·gpg와 서로 풀기(gpg가 있으면)·14개·되살리기와 되돌리기·옮기기 복사·확인·설정 값만 쓰기·자동 시작 파일·rehome) · 실행 파일 시험(설정 저장 → 같은 포트로 다시 뜸 · 백업 → 되살리기 · 옮기기) · 계약 L16 — **파이썬 판 컨테이너에서 `scripts/backup.sh`와 같은 차례로 뜬 백업을 새 Rust 판이 되살려** 프로젝트 목록·문서·판 목록이 파이썬 판과 바이트로 같다 · `check_ui` UI-13 · `tsc`·`oxlint`·`build` |
| 선행 | L4 · L11 · L15 |
| 완료 | 2026-10-11 · 브랜치 `card/L16-local`(bbf27b4 #381) · spec 11 + code 8 · `cargo test` 197(진짜 PostgreSQL·git — 백업 꼴·암호·gpg와 서로 풀기·14개·되살리기와 되돌리기·옮기기 복사 확인·설정 값만 쓰기·자동 시작·rehome·mirror · 실행 파일 — 설정 저장 → 같은 포트로 다시 뜸 · 백업 → 되살리기 · 옮기기) · 계약 `--target both --with-card L16` 1150 통과 — L16: 파이썬 판 컨테이너에서 BR 차례로 뜬 gpg 백업을 새 Rust 판이 되살려 프로젝트 목록·문서 목록·문서·판 목록·diff가 바이트로 같고 이어서 셋째 판을 쓴다 · clippy · 워크플로 녹색(리눅스·윈도) · `check_code` Rust 197/197 · `check_calls` 0 · `check_ui` 14/14 · 브라우저(playwright)로 UI-13 저장 → 다시 켜기 → 지금 백업 → 되살리기 · 사람 확인(윈도 UI-13 이 PC·백업·옮기기·자동 시작·트레이 지금 백업)은 따로 · 되먹임: `tokio::select!` 안의 호출은 코드 그래프가 못 본다(runtime.run 「호출하는 것」에서 뺐다) · `Git`의 `clone`(작업 사본 받기)이 `Clone::clone`을 가린다 — `Clone::clone(&git)` · 화면 줄의 이름표가 한 글자씩 접혀 줄 꾸밈을 더했다 |

#### L18 새 MCP 프로토콜 — 2026-07-28, 핸드셰이크 없는 요청 하나짜리 봉투

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-API-002]] 1장 · [[SYNC-INFRA-001]] 9.2·9.8 · 사용자 결정 2026-10-08(파이썬 SDK의 `_streamable_http_modern`을 옮긴다) · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): `MCP-Protocol-Version`이 핸드셰이크 판이 아니면(모르는 값까지) 새 입구 — 보안(Content-Type)·메서드(405 `Allow: POST`, 본문 없음 — 바깥 405 변환을 비켜 간다)·Accept·`json.loads`·알림 202·봉투(`JSONRPCRequest`/`JSONRPCNotification`)·머리 중복·분류 사다리(_meta·머리 줄·판)를 파이썬 판 차례·문장 그대로 · 디스패치는 핸드셰이크 경로와 같은 `dispatch`에 그 판의 표면 검증기와 고정 결과(`server/discover`·목록들 — 캐시 힌트·serverInfo 도장까지)를 파이썬 판에서 뽑아 쓴다(`cargo xtask mcp-tools`) · `tools/call` 결과에 `resultType`·serverInfo 도장 · 처리기의 그 밖의 예외는 `INTERNAL_ERROR` · 응답은 `json.dumps(…, separators=(",", ":"))`(ASCII)라 pycompat에 `dumps_compact` · 15초 안에 알림 없이 끝나면 JSON, 넘기면 SSE로 바꾸고 15초마다 `: ping` · `subscriptions/listen`은 확인 프레임 뒤 ping(앱이 사건을 내지 않는다), 상한 1024 · `Mcp-Param-*` 머리 검증은 옮기지 않는다 — 도구 스키마에 `x-mcp-header`가 없어 파이썬 판도 늘 통과한다 · 본문 JSON 깊이는 파이썬이 9987겹 언저리에서 한 겹쯤 흔들려 많은 쪽(9986까지 받음)을 따른다 |
| 구현 | `mcp/modern.rs` · `mcp/dispatch.rs`(판별 표면·`server/discover`·`subscriptions/listen`·`tools/call` 꼴) · `mcp/decl.rs` · `xtask/py/export_mcp.py`(`results_modern`·`surface_modern`·봉투·도장) · `web/problem.rs` `Bare405` · pycompat `dumps_compact` |
| API | [[SYNC-API-002]] 1장(전송·판) |
| 테스트 | `cargo test`(머리 값 base64 표지 · 상태 표 · 멈춘 시계로 15초 넘긴 처리기의 SSE·ping·마지막 사건 · 듣기 확인 프레임·ping·자리 돌려주기) · 계약 L18 — 사례 표 69(입구·알림·봉투·머리 중복·사다리·문지기·표면·처리기·목록·`tools/call`·듣기 첫 프레임)가 파이썬 판과 바이트로 같고, 무작위 차이 시험(씨앗 셋 × 1500)과 JSON 깊이 경계(한 겹 안, 경계 ±3 바이트 같음) |
| 선행 | L3 |
| 완료 | 2026-10-11 · 브랜치 `card/L18-mcp-modern`(d81e2c2 #383) · spec 4 + code 4 · `cargo test` 201(머리 값 base64 표지·상태 표·멈춘 시계로 15초 넘긴 처리기의 SSE·ping·마지막 사건·듣기 프레임과 자리) · `cargo xtask mcp-tools --check` · 계약 `--target both --with-card L18` 1286 통과 — L18 136: 사례 표 69 바이트 같음 · 무작위 차이(따로 씨앗 셋 × 1500 — 0) · JSON 깊이 경계 한 겹 안 · clippy · 워크플로 녹색(리눅스·윈도) · `check_code` Rust 197/197 · `check_calls` 0 · 되먹임: 파이썬 판에 새 프로토콜로 물어 갈래를 모았다(검증 실패는 pydantic 문장이 아니라 `Invalid request parameters` 고정 — 유무만 맞추면 된다) · 처리기가 일부러 낸 빈 405를 바깥 405 변환이 problem으로 바꿔 `Bare405` 표지를 두었다 · 파이썬의 JSON 깊이 경계는 9987·9988로 흔들린다 |

#### L17 속도·출시 판정 — 두 판을 같은 PC에서 잰다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R15]] 「빠르다」 · [[SYNC-INFRA-001]] 9.8 · 에이전트 판단 2026-10-11(사용자 목표 「끝까지」): **재는 법** — 같은 PC에서 Rust 판(release 실행 파일)과 파이썬 판(작업 트리 이미지 — 폐쇄망판 Docker 묶음과 같은 구성)을 나란히 띄워 같은 일을 시킨다. 켜기 — 첫 실행은 빈 데이터 자리(파이썬은 빈 컨테이너), 다시 켜기는 세 번의 가운데 · 싱크독 저장소 `main`을 번들로 가져오기(재구축 포함) · 그 코드 그래프가 생길 때까지 · 화면 조회 9경로(경로마다 가운데값, 그 가운데 가장 느린 것) · 문서 저장(MCP `update_document`, git 커밋 포함, 가운데값) · 켜 둔 메모리(Rust는 실행 파일과 그 PostgreSQL의 PSS 합, 파이썬은 두 컨테이너의 `docker stats`) · **출시 판정** — 모든 항목이 R15 목표 안이고 파이썬 판보다 느린 것이 없으면 통과 → `local/Cargo.toml` 판을 0.2.0으로 올려 병합하고 태그 `local-v0.2.0`(INFRA 9.5 — 워크플로가 윈도·리눅스에서 만들고 깔아 켜 본 뒤 올린다) · 윈도 수치도 같은 PC의 윈도에서 잰다(윈도 디스크의 사본 — #387. 처음엔 「사람이 잰다(이 PC에 윈도 도구가 없다)」로 남겼으나 이 PC의 윈도에 rustup·VS Build Tools·Docker Desktop이 있었다) |
| 구현 | `contract/speed.py` · `cargo xtask speed` · `local/Cargo.toml` 판 |
| 테스트 | `cargo xtask speed` — 표와 판정(목표에 못 미치거나 파이썬 판보다 느린 항목이 있으면 실패) |
| 선행 | L14~L16 · L18 |
| 완료 | 2026-10-11 · 브랜치 `card/L17-speed`(c2ebf3e #385) · spec 3 + code 2 · `cargo xtask speed --rounds 20`(WSL2 리눅스) — 첫 켜기 1.00초(파이썬 7.82, 목표 15) · 다시 켜기 0.19초(4.74, 목표 3) · 화면 조회 가장 느린 경로의 가운데값 31ms(530ms, 목표 0.1초) · 문서 저장 78ms(261ms, 목표 0.3초) · 코드 그래프 1.16초(8.56, 목표 10) · 켜 둔 메모리 265MB(486MB, 목표 300MB) · 번들 가져오기 27초(61초) — **리눅스 판정 통과** → 판 0.2.0, 태그 `local-v0.2.0` · 워크플로 녹색(리눅스·윈도) · **윈도(#387, 같은 PC, 두 번 — Rust/파이썬)**: 첫 켜기 7.84·10.48초/12.67·9.78 · 다시 1.33·1.42초/4.50·5.39 · 조회 86·95ms/529·691ms · **저장 2.23·2.52초**/0.55·0.70(목표 0.3) · 그래프 3.67·4.73초/9.28·12.23 · 메모리 65MB/513MB(윈도는 개인 작업 집합) · **가져오기 221·271초**/70·87초 — **윈도 판정 못 미침**: git 프로세스 하나가 윈도에서 50~100ms(Defender 켜짐)인데 저장 한 번에 ~22개(fetch 둘·push·maintenance), 재구축은 판마다 `git show` · 첫 켜기는 `initdb` → 카드 L19(사용자 결정 2026-10-11: git 프로세스를 줄인다 · 0.2.0은 두고 두 판정을 통과하면 0.3.0) · 윈도 `cargo test` 192 통과·clippy 0(#387) · 되먹임: 저장 측정은 판이 오를 때마다 본문 머리의 상태·판을 그 문서의 지금 값으로 맞춰야 `frontmatter.status_change`에 걸리지 않는다 · 깃발 조회(`/flags`)는 `kind`가 있어야 한다(`?kind=broken_ref`) |

#### L19 윈도 속도 — git 프로세스 줄이기 · 첫 켜기 · 조회

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R15]] 「빠르다」 · [[SYNC-INFRA-001]] 9.2·9.8 · 카드 L17 윈도 수치(#387 — 저장 2.2~2.5초, 가져오기 221~271초, 첫 켜기가 파이썬보다 느릴 때가 있고, 조회 95ms) · 사용자 결정 2026-10-11·12: **git 프로세스를 줄인다**(명령줄 git 유지) — 작업 사본은 git이 아닌 폴더(서버 저장소 `main`의 `docs/specs/`, 첨부 파일 읽기만), git은 늘 서버 저장소에서 · 커밋은 `git fast-import` 하나(`git commit`과 같은 객체 — 저장 도중 밖에서 같은 파일을 밀면 `conflict`, 계약 밖) · 읽기는 저장소마다 오래 사는 `git cat-file --batch` · 윈도 git은 MinGit의 `ucrt64/bin/git.exe`를 바로 · 자동 gc·maintenance는 끄고 저장소마다 하루 한 번 `gc --auto`(백업과 따로, 백업 폴더가 없어도) · 첫 켜기는 `initdb --no-sync` + 서버가 뜬 뒤 `initdb --sync-only`(표식 `pgdata.sync`로 끝까지) · 조회는 작성자 한 번에·상세는 그 프로젝트만·DB 연결 유지 · 0.2.0은 두고 윈도·리눅스 두 판정을 통과하면 0.3.0 |
| 구현 | [[SYNC-MS-019#Git.new]] · [[SYNC-MS-019#Git.commit]] · [[SYNC-MS-019#Git.head]] · [[SYNC-MS-019#Git.read]] · [[SYNC-MS-019#Git.exists]] · [[SYNC-MS-019#Git.materialize]] · [[SYNC-MS-019#Git.sync_readme]] · [[SYNC-MS-019#Git.close]] · [[SYNC-MS-019#Git.close_all]] · [[SYNC-MS-019#Git.gc]] · [[SYNC-MS-017#pipeline.read_pending]] · [[SYNC-MS-017#pipeline.save_pipeline]] · [[SYNC-MS-017#pipeline.process_commit]] · [[SYNC-MS-017#pipeline.rebuild]] · [[SYNC-MS-017#pipeline.upload_code]] · [[SYNC-MS-017#pipeline.catch_up]] · [[SYNC-MS-013#ProjectService.init_project]] · [[SYNC-MS-013#ProjectService.import_bundle]] · [[SYNC-MS-013#ProjectService.delete_project]] · [[SYNC-MS-013#ProjectService.rehome]] · [[SYNC-MS-022#CodeGraphService.read]] · [[SYNC-MS-018#queries.document_list]] · [[SYNC-MS-018#queries.project_summary_of]] · [[SYNC-MS-018#queries.project_detail]] · [[SYNC-MS-012#runtime.run]] · [[SYNC-MS-012#runtime.shutdown]] · [[SYNC-MS-012#paths.git]] · [[SYNC-MS-012#pg.start]] · [[SYNC-MS-023#backup.daily]] · `contract/speed.py`·`xtask speed`(윈도는 고정 MinGit) · `local/Cargo.toml` 판 |
| 테스트 | `cargo test`(리눅스·윈도 사본) — fast-import 커밋이 `git commit`과 해시가 같다(메시지 꼴·오프셋) · 읽기 프로세스가 뒤에 생긴 커밋·옮긴 `main`을 본다 · 경합 → 다른 파일은 그 위에, 같은 파일은 `conflict` · 작업 사본 폴더가 `main`의 `docs/specs/` · 옛 clone이 폴더로 · gc가 팩을 줄인다 · initdb 표식 · 계약 `--target both` 전체(응답 바이트 그대로) · **`cargo xtask speed` 리눅스와 윈도 둘 다 통과** |
| 선행 | L17 · #387 · #368 |
| 완료 | 2026-10-12 · 브랜치 `card/L19-windows-speed`(3a4e41d #390) · spec 16 + code 11 · `cargo test` 리눅스 208 · **윈도 사본 199**(처음 돌린 윈도에서 시험 둘을 바로잡았다 — 윈도 git의 시스템 `autocrlf=true`, 열린 팩의 os error 32) · 계약 `--target both` 1286(응답 바이트 그대로) · clippy(리눅스·윈도) · xtask `--check` 넷·`schema-check` · `check_code` Rust 201/201 · `check_calls` 0 · 워크플로 녹색(리눅스·윈도 — 설치판 MinGit으로 프로젝트 만들고 지우고 제거까지) · **판정(같은 PC, Rust/파이썬)** 윈도: 첫 켜기 5.66/7.67초 · 다시 1.42/4.41초 · 조회 72/512ms · 저장 109/259ms(전 2.2~2.5초) · 그래프 4.16/9.69초 · 메모리 116/504MB · 가져오기 31/59초(전 221~271초) / 리눅스: 1.24/9.17초 · 0.23/4.89초 · 30/606ms · 32/431ms · 1.05/10.9초 · 283/513MB(목표 300에 붙었다 — 연결을 닫지 않아 PostgreSQL 백엔드가 남는다) · 26/98초 → **두 판정 통과, 판 0.3.0, 태그 `local-v0.3.0`** · 되먹임: MinGit 2.56의 진짜 git은 `ucrt64/bin/git.exe`(`mingw64`가 아니다) · fast-import는 작은 커밋을 낱낱의 객체로 풀려고 `unpack-objects`를 하나 더 띄운다 → `fastimport.unpackLimit=0` · 저장 한 번을 나눠 보니 서버 안은 190~250ms였고 나머지는 시험 쪽 — 윈도에서 httpx 클라이언트를 새로 만들 때마다 인증서를 읽느라 ~300ms(두 판에 같이 붙었다) → 연결 재사용 · 윈도 CI 설치 시험: 강제로 끝낸 앱의 자식 `initdb --sync-only`가 남아 `postgresql` 폴더를 쥐었다 → 앱과 함께 끝내고 시험이 기다린다 · 시험 git의 자동 gc가 `gc.pid`를 쥐면 시험의 gc가 건너뛴다 · `pg_ctl start`·PowerShell `Start-Process -Wait`는 자손까지 기다린다 · 사람 확인(윈도에서 설치판으로 저장·git push·백업 되살리기·옮기기)은 따로 |

#### L20 커뮤니티 넓히기 — graph.json 없는 저장소의 Rust·TS 함수도 묶는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S9]] · [[SYNC-UC-001#UC-H20]] · [[SYNC-PRD-001#R13]] · [[SYNC-INFRA-001]] 9.2 · 사람 확인(DEV-17, 2026-10-12)에서 찾음 — UI-17 코드 그래프에서 싱크독 저장소의 Rust·TS 함수 1361개가 커뮤니티 없이 낱개 노드로 흩어지고 배치가 멈추는 데 54초. 추출 원형([[SYNC-MS-022#codegraph.extract]])이 TS/JS·Rust는 파일 노드만 만들어서다(파이썬 판의 graphify 원형은 모든 언어). 사용자 결정 2026-10-12: **Rust·TS도 묶는다** — 보강이 찾은 정의·호출을 원형에 더해 Louvain이 함께 묶는다. 커밋된 graph.json이 있으면 그대로(두 판이 바이트까지 같다), 없을 때만 커뮤니티 번호가 파이썬 판과 다를 수 있다(이미 계약 밖 — 꼴만 본다) · 에이전트 판단: 더하는 노드는 graphify 함수 노드 꼴(`{경로}:{줄}`·`L{줄}`·`_callable`), 선은 파일 → 함수 `contains`와 보강의 호출 `calls`(같은 쌍은 하나) |
| 구현 | [[SYNC-MS-022#codegraph.widen]] · [[SYNC-MS-017#pipeline.build_code_graph]] 3 |
| API | [[SYNC-API-001#GET/api/projects/{code}/code-graph]] — 모양 그대로 |
| 테스트 | `cargo test`(시험 저장소 추출 → 줄이기 → 보강 → 넓히기 → 커뮤니티: 함수가 다 커뮤니티 · 파이썬 노드는 다시 안 더함 · `contains`·`calls` · 같은 쌍 하나 · 원래 차례 그대로 · 시험 DB — Rust·TS를 민 커밋의 그래프 행) · 정답 파일·`cargo xtask codegraph-diff`(graph.json 경로 — 그대로 같다) · 계약 L12·L13(graph.json 없는 프로젝트는 꼴만) · 화면 UI-17 — 싱크독 저장소의 함수가 다 커뮤니티 안에 |
| 선행 | L13 · L19 |
| 완료 | 2026-10-12 · 브랜치 `card/L20-graph-communities`(b868b82 #400) · spec 4 + code 3 · `cargo test` 211(새 시험 셋 — 시험 저장소 추출 → 넓히기 → 함수가 다 커뮤니티 · 넓힌 원형의 노드·선 모양 · 시험 DB에서 Rust·TS를 민 커밋의 그래프 행. 고치기 전 코드로는 실패) · 계약 `--target both --with-card L20` L12·L13 100 · xtask `--check` 다섯 · `codegraph-diff` 같다(graph.json 길 그대로) · clippy · 워크플로 녹색(윈도 빌드·설치·실행) · `check_code` Rust 202/202 · `check_calls` 0 · 사람 확인(에이전트가 브라우저로) — 싱크독 저장소 번들을 릴리스 빌드에 넣어 UI-17: 함수 2284가 다 커뮤니티 65개 안(전엔 91개 + 커뮤니티 없음 1361), 그래프 1.2초, 배치가 멈추기까지 6.8초(전엔 54초) · 판 0.3.2 — 태그 `local-v0.3.2` |

#### L21 관계도 노드의 항목 제목 — UI-8 찾기

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UC-001#UC-H4]] 확장 2b · [[SYNC-UI-002#UI-8]] 2.7 · [[SYNC-CODE-001#CB]] · 사용자 결정 2026-10-12: UI-8 찾기는 ID와 항목 제목 — 그래프 응답 노드에 항목 제목을 더한다(두 판 서버·계약 스냅숏) |
| 구현 | [[SYNC-MS-018#queries.graph_view]] 5 · `types.rs` `GraphNode.display_name` |
| API | [[SYNC-API-001#GET/api/projects/{code}/graph]] — 노드에 `display_name` |
| 테스트 | `cargo test`(시험 DB — 항목 노드 제목·문서 노드 없음) · 계약 `--target both --with-card L21` L8 — graph 사례가 파이썬 판으로 다시 쓴 스냅숏과 바이트로 같다 |
| 선행 | L8 · CB |
| 완료 | 2026-10-12 · 브랜치 `card/L21-graph-titles`(c7a069f #406) · spec 2 + code 2 · `cargo test` 211 · fmt · clippy · 계약 `--target both --with-card L21` 전체 1286 통과(L8 graph 사례가 새 스냅숏과 바이트로 같다) · 파이썬 `pytest` 488 · `check_code` 374/374(파이썬 172·Rust 202) · `check_calls` 0 · 워크플로 녹색 · 판 0.3.3 — 태그 `local-v0.3.3` |

#### L22 흐름 보기 ① — 파일 목록·호출 순서 (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CC]] · [[SYNC-MS-024]] · 사용자 결정 2026-10-12(두 판 같은 그래프) |
| 구현 | [[SYNC-MS-026]] `flow.extend`·`files`·`steps` · `crates/codegraph/src/flow/mod.rs`·`steps.rs` · `core/src/pipeline.rs` 그래프 만들기 |
| 테스트 | `cargo test` · 정답 파일(`codegraph-golden`에 흐름 키) · `cargo xtask codegraph-diff` — 파이썬 판과 바이트로 같다 |
| 선행 | CC · L21 |
| 완료 | 2026-10-17 · 브랜치 `card/L22-flow-rust`(L23·L24와 한 브랜치) · spec 6 + code 5 · `cargo test` 213 · fmt · clippy · 정답 파일 `flow`(고정 시험 저장소) · 흐름 사례 22(파이썬 판 흐름 시험 입력) · `codegraph-diff` 같다(싱크독 함수 2745 — 그리고 임시로 다른 저장소 다섯 view_arc·video_agent·qbot-h·LastTalk·competition-crawler도 같다) · `check_code` Rust 209/209 · `check_calls` 흐름 0 · 되먹임: 모듈 꼬리 `infra`·`routes`가 core·server와 겹치면 코드 그래프가 경로를 못 풀어 → `codegraph/src/flow/` 아래로 · 파이썬 판 Nest `export class` 데코레이터를 놓치던 것을 정답 파일을 만들다 찾아 고쳤다 |

#### L23 흐름 보기 ② — 라우트·화면 요청 (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CD]] |
| 구현 | [[SYNC-MS-026]] `routes`·`http_links` · `crates/codegraph/src/flow/routes.rs` |
| 테스트 | `cargo test` · 정답 파일 · `codegraph-diff` |
| 선행 | CD · L22 |
| 완료 | 2026-10-17 · L22와 한 브랜치 — 정답 파일·흐름 사례(라우트 셋·화면 요청 다섯)·`codegraph-diff` 같다 |

#### L24 흐름 보기 ③ — 장비·실행 단위 (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CE]] |
| 구현 | [[SYNC-MS-026]] `units`·`infra` · `crates/codegraph/src/flow/infra.rs` |
| 테스트 | `cargo test` · 정답 파일 · `codegraph-diff` |
| 선행 | CE · L23 |
| 완료 | 2026-10-17 · L22와 한 브랜치 — 정답 파일·흐름 사례(실행 단위·장비 셋)·`codegraph-diff` 같다 · 그래프 만들기가 흐름 키를 더해 저장한다(시험 DB 시험) |

#### L25 흐름 보기 ④ — 조회 API (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CF]] |
| 구현 | [[SYNC-MS-018]] `queries.flow_view` · `types.rs` · `server/src/web/routes/code.rs`(모듈을 `flow`로 두면 코드 그래프가 `codegraph::flow`와 못 가른다) · `schemas.rs` |
| API | [[SYNC-API-001#GET/api/projects/{code}/flow]] |
| 테스트 | `cargo test` · 계약 `--target both --with-card L25` — 파이썬 판 스냅숏과 바이트로 같다 |
| 선행 | CF · L24 |
| 완료 | 2026-10-17 · 브랜치 `card/L25-flow-api-rust`(L26과 한 브랜치) · spec 4 + code 4 · 계약 `--target both --with-card L25 --with-card L26` `test_l25_flow.py` 16 통과(흐름 고정 저장소와 graph.json — `/flow` 응답이 파이썬 판과 바이트로 같다) · clippy · `check_code` Rust 212/212 · `check_calls` 0(흐름) · 되먹임: 서버 경로를 `routes/flow.rs`로 두면 모듈 꼬리 `flow`가 `codegraph::flow`와 겹쳐 그래프 만들기의 `flow.extend` 호출을 못 푼다 → `routes/code.rs` |

#### L26 흐름 보기 ⑥ — MCP get_flow (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CH]] |
| 구현 | [[SYNC-MS-018]] `queries.flow_of` · `server/src/mcp/tools.rs` · `cargo xtask mcp-tools` |
| 테스트 | 계약 `--with-card L26` |
| 선행 | CH · L25 |
| 완료 | 2026-10-17 · L25와 한 브랜치 — `cargo xtask mcp-tools`(선언 15개 — CH 때 다시 만들지 않았던 것을 함께) · `--check` 같다 · 계약 get_flow 넷(그래프 없음·열쇠·항목 ID·없는 함수) 바이트로 같다 · 판 0.4.0 — 태그 `local-v0.4.0` |

#### L27 실행 기록 ① — traces 표·TraceService (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CI]] · [[SYNC-MS-025]] |
| 구현 | `cargo xtask migrations`(Alembic 리비전에서) · [[SYNC-MS-027]] `TraceService` · `core/src/trace/` · `ProjectService.delete_project` |
| 테스트 | `cargo test`(시험 DB) · `cargo xtask schema-check` |
| 선행 | CI · L26 |
| 완료 | 2026-10-17 · 브랜치 `card/L27-trace-rust` · spec 2 + code 3 · `cargo test` trace 5(시험 DB) · `schema-check` 같다(alembic 0019) · `migrations --check` · clippy · `check_code` Rust 218/218 · 되먹임: 파이썬 판이 새로 넣은 기록의 `started_at`을 받은 시간대로 돌려주던 것(목록은 UTC)을 UTC로 맞췄다 |

#### L28 실행 기록 ② — 기록 API·토큰 경로 (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CJ]] |
| 구현 | [[SYNC-MS-018]] `queries.trace_spans` · `server/src/web/routes/traces.rs`·`code.rs` · `guard.rs` 토큰 경로 |
| 테스트 | 계약 `--with-card L28` |
| 선행 | CJ · L27 |
| 완료 | 2026-10-17 · 브랜치 `card/L28-trace-api-rust` · spec 2 + code 3 · 계약 `--target both --with-card L28` `test_l28_traces.py` 54 통과(trace-spans 토큰·로컬·틀린 토큰 401·올리기 201/200·꼴·시각·4MB 413·JSON 아님·남의 것·목록·하나·아주 큰 id·커버리지·지우기) · clippy · 되먹임: 파이썬 판이 DB 정수 범위 밖 기록 번호에 500을 내던 것을 404로 |

#### L29 실행 기록 ③ — 기록 도구 `syncdoc-local trace`·`trace-web`

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R17]] · [[SYNC-UC-001#UC-H25]] · [[SYNC-INFRA-001]] 9.9 · [[SYNC-INFRA-001#C12]]·C13 · 사용자 결정 2026-10-12(로컬 판 실행 파일의 하위 명령) · view_arc `trace.mts`·`web-proxy.mts`·`native/rust.mts`·`runtime/*` |
| 구현 | [[SYNC-MS-027]] 기록 도구 · `crates/app/src/trace/` · `crates/app/tracers/`(Python·Node·브라우저·Rust 기록기 — 사건의 `fn`을 그래프 열쇠로) |
| 테스트 | `cargo test`(언어 알아보기·환경 변수·올리기 다시 보내기·Rust 사본 계측) · E2E: 스크래치 FastAPI·Express·axum 앱을 기록 도구로 띄워 요청 → 두 판에 기록이 올라오고 대상 저장소 `git status`가 그대로 · 비밀 이름의 값이 `***` |
| 선행 | CJ · L28 |
| 완료 | 2026-10-17 · 브랜치 `card/L29-trace-tool` · spec 3 + code 2 · `cargo test` 기록 도구 7·사본 계측 3 · clippy · E2E(임시 싱크독_로컬 8011): 스크래치 FastAPI(기록 2 — 200·500, `password`는 `***`, 예외 남음) · 순수 Node http(기록 2, `token` 값 가림) · std Rust `--job`(계측 사본에서 `cargo run`, 작업 기록 1) · Vite 앱 `trace-web`(Playwright로 버튼 → 화면 기록 1) — 모두 사건의 함수가 그래프 열쇠, 작업 사본 그대로 · `check_code` Rust 230/230 · `check_calls` 0 · 되먹임: 생성기 식·람다(`<…>`)는 그래프 함수가 아니라 기록하지 않는다(안쪽 호출은 바깥 함수에) · 기록기마다 다른 꼴(ms 소수·kind 없음)은 도구가 올리기 전에 맞춘다(`trace.normalize`) · Rust 사본·빌드 폴더는 캐시에 남긴다 · trace-web은 Node 프록시 · Rust 도우미도 파일로(UDP 아님) |

#### L30 실행 기록 ④ — 요청 보내기 `POST /api/local/request`

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UC-001#UC-H26]] · [[SYNC-SEQ-001#SEQ-37]] · [[SYNC-INFRA-001#C14]] |
| 구현 | [[SYNC-MS-027]] `local.request` · `server/src/web/routes/local.rs` |
| API | [[SYNC-API-001#POST/api/local/request]] |
| 테스트 | `cargo test`(localhost 아님 → refused · 닿지 못함 → failed · 1MB 자르기 · 리다이렉트 안 따름) |
| 선행 | L29 |
| 완료 | 2026-10-17 · 브랜치 `card/L30-local-request` · spec 1 + code 1 · `cargo test` 4(localhost 아님 → refused · 닿지 못함 → failed · 1MB 자르기 · 리다이렉트 안 따름·머리 소문자) · clippy · `check_code` Rust 231/231 |

#### L31 실행 기록 ⑤ — MCP list_traces·get_trace (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CL]] |
| 구현 | `server/src/mcp/tools.rs` · `cargo xtask mcp-tools` |
| 테스트 | 계약 `--with-card L31` · 판 0.5.0 — 태그 `local-v0.5.0` |
| 선행 | CL · L30 |
| 완료 | 2026-10-17 · 브랜치 `card/L31-mcp-traces-rust` · code 3 · `cargo xtask mcp-tools --check` · 계약 `--target both --with-card L28 --with-card L31` + L3·L18 364 통과(MCP 도구 16개 스냅숏) · clippy · 판 0.5.0 — 태그 `local-v0.5.0` |

#### L32 흐름 보기 ⑦ — Java·Go 그래프 보강 (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CM]] · [[SYNC-MS-022]] |
| 구현 | `crates/codegraph/src/java.rs`·`go.rs` · 추출에 `.java`·`.go` 파일 노드 · `tree-sitter-java` 0.23.5·`tree-sitter-go` 0.25.0(파이썬 판과 같은 판) |
| 테스트 | 정답 파일(고정 시험 저장소에 Java·Go) · `codegraph-diff` |
| 선행 | CM · L31 |
| 완료 | 2026-10-17 · 같은 브랜치 · spec 3 + code 1 · 정답 파일 `enriched`·`communities` 같다 · `codegraph-diff` 이 저장소 같다 + 임시로 Go `net/http`(함수 1299·호출 1179)·Java `java.util.concurrent`+`java.net.http`(함수 5863·호출 8030)도 같다 |

#### L33 흐름 보기 ⑧ — Java·Go 호출 순서·라우트·장비 (Rust)

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-CODE-001#CN]] · [[SYNC-MS-026]] |
| 구현 | `crates/codegraph/src/flow/steps.rs`·`routes.rs`·`infra.rs` |
| 테스트 | 정답 파일(흐름 시험 저장소에 Spring·Go) · 흐름 사례(Java·Go 다섯) · `codegraph-diff` |
| 선행 | CN · L32 |
| 완료 | 2026-10-17 · 같은 브랜치 · code 1 · 정답 파일 `flow`(Spring·Go 단위·라우트·장비) · 흐름 사례 27 · `codegraph-diff` 같다 · `cargo test` 232 · clippy |

#### L34 실행 기록 ⑥ — Java·Go 기록기

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R17]] · [[SYNC-INFRA-001]] 9.9 · view_arc `native/java.mts`·`native/go.mts`·`runtime/VaJdi.java`·`runtime/go/viewarctrace.go` |
| 구현 | [[SYNC-MS-027#trace.java_setup]] · [[SYNC-MS-027#trace.go_overlay]] · [[SYNC-MS-027#trace.instrument_go]] · [[SYNC-MS-027#trace.detect]] · `crates/app/src/trace/jdi.rs`·`go_copy.rs` · `crates/app/tracers/java/SyncdocJdi.java`·`go/syncdoctrace.go` |
| 테스트 | `cargo test`(언어 알아보기·Go 계측) · E2E: Java(HttpServer + Spring 꼴 어노테이션, JDK 21)·Go(net/http 1.22 꼴)를 기록 도구로 띄워 요청 → 기록이 올라오고 사건의 함수가 그래프 열쇠 · 비밀 이름의 값 `***` · 작업 사본 그대로 · 판 0.6.0 — 태그 `local-v0.6.0` |
| 선행 | L33 |
| 완료 | 2026-10-17 · 같은 브랜치 · spec 1 + code 1 · `cargo test` 기록 도구(언어 알아보기·Go 계측 3) · E2E(임시 싱크독_로컬 8012, JDK 21·Go 1.23): Java HttpServer+Spring 꼴 어노테이션 — 기록 2(200·예외 500), `token` `***` · Go net/http 1.22 꼴 — 기록 2(200), 다른 패키지 함수까지 · 사건의 함수가 그래프 열쇠, 작업 사본 그대로 · 브라우저(Playwright)로 Java 기록 재생 · 되먹임: 기록기 시각은 밀리초까지(나노초는 서버가 시각으로 안 받는다) · JDI는 HTTP 상태를 못 읽어 예외 500·아니면 200 · Spring 실제 앱(Maven)은 이 PC WSL에 Maven이 없어 못 돌렸다 · 판 0.6.0 |

**다음 카드** — L22(흐름 보기, 2026-10-12 사용자 결정 — view_arc를 두 판의 기능으로). 1차 L22~L26 → `local-v0.4.0`, 2차 L27~L31 → `local-v0.5.0`, 3차 Java·Go L32~L34 → `local-v0.6.0`.

카드 BX는 파이썬 판에서 먼저 했다 — [[SYNC-CODE-001]](#376). #325(재구축이 파일을 지운 커밋에서 실패)는 #366으로 끝났다.

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

**계약 밖** — API-001에 없는 프레임워크 동작은 두 판이 달라도 된다(사용자 결정 2026-10-07): 끝 슬래시 리다이렉트(307) · `/docs`·`/redoc`·`/openapi.json` · GET 경로의 HEAD · Range(206) · ETag 값의 꼴 · Host 머리 없는 요청 · 응답의 `date`·`server`·`connection` 머리와 본문을 나눠 보내는 꼴(chunked·content-length). **Rust 판만 가진 것** — `/api/local*`(이 PC·백업, 카드 L16 — 파이썬 판은 없는 경로)는 비교하지 않는다. 대신 계약 L16이 파이썬 판의 백업을 Rust 판이 되살린 결과를 비교한다. 화면과 에이전트는 이것들을 쓰지 않는다. 새 프로토콜(2026-07-28)의 본문 JSON 깊이의 정확한 경계는 파이썬 판이 한 겹쯤 흔들려 바이트 비교 밖이다 — 계약 L18은 두 판 경계가 한 겹 안인지와 경계 ±3에서 같은지를 본다(카드 L18). 15초를 넘기는 처리기의 SSE 바꿈은 도구가 그만큼 걸리지 않아 계약에서 닿지 않는다 — `cargo test`의 멈춘 시계로 본다. 저장 도중 밖에서 같은 파일을 git으로 밀었을 때 파이썬 판은 rebase로 합치고 Rust 판은 `conflict`로 돌려준다(카드 L19 — 커밋을 서버 저장소에 바로 만든다, [[SYNC-MS-019#Git.commit]]) — 둘 사이의 경합이라 계약에서 닿지 않는다.

**명세 엔진**(카드 L5)은 HTTP로 닿기 전이라 계약 시험 대신 정답 파일(`cargo test`)과 `cargo xtask spec-diff`(두 판에 같은 본문을 돌려 바이트 비교)로 맞춘다 — 엔진을 고치면 둘 다 돌린다.

속도는 카드 L17이 잰다 — [[SYNC-PRD-001#R15]]의 수치를 같은 PC에서 두 판을 나란히(9.8).

---

## 3. 커밋·PR 목록

카드의 `완료` 행에 기록한다. PR 하나 = 카드 하나. 가지는 `card/L1-…`, 커밋은 `spec(SYNC-MS-012): …`(MINISPEC) 다음 `code(L1): Type.method — 요약`([[SYNC-STD-004#DEV-15]]).

| 카드 | 브랜치 | 커밋 | PR | 날짜 |
|---|---|---|---|---|

---

## 4. 미결사항

- [x] `main`이 아닌 가지를 push했을 때 — 파이썬 판처럼 받아 두기만 하나([[SYNC-UC-001#UC-H21]] 3a), git을 부르기 전에 거절하나. Rust 판은 ref 명령을 먼저 읽으므로 둘 다 된다([[SYNC-INFRA-001]] 9.1). 카드 L10 전에 정한다 — 결정(에이전트 판단 2026-10-11, 사용자 목표 「끝까지」): 파이썬 판처럼 받아 두기만 한다. ref 명령을 미리 읽지 않고 되감기·지우기는 파이썬 판과 같은 저장소 설정이 거절한다(INFRA 9.1을 바로잡음). 계약 L10이 두 판에 진짜 push로 본다
- [x] 저장소에 커밋된 `graphify-out/graph.json`을 따를지 — 파이썬 판은 그 파일이 있으면 그것을 쓴다([[SYNC-MS-011#codegraph.load]] 1). Rust 판에는 graphify가 없다. 카드 L12 전에 정한다 — 결정(에이전트 판단 2026-10-11, 사용자 목표 「끝까지」): 따른다. 같은 원형이면 두 판이 같은 줄이기·보강으로 바이트까지 같은 그래프를 낸다. 없으면 graphify 대신 tree-sitter로 뽑는다([[SYNC-MS-022]] 0장)
- [x] 되살리기가 Docker 판(파이썬 폐쇄망판)의 백업 파일도 받을지 — 두 판은 같은 표를 쓴다([[SYNC-INFRA-001]] 9.2). 카드 L16 전에 정한다 — 결정(에이전트 판단 2026-10-11, 사용자 목표 「끝까지」): 받는다. 백업 꼴을 카드 BR과 같게 하고(OpenPGP 대칭 암호 — gpg와 서로 풀린다) 켤 때 서버 저장소 자리를 맞춘다(`ProjectService.rehome`). 계약 L16이 파이썬 판 컨테이너의 백업을 Rust 판에 되살려 본다
