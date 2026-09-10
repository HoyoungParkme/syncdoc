---
doc_id: SYNC-CODE-001
type: CODE
title: 구현 계획 — 슬라이스 카드와 커밋 기록
status: draft
upstream: [SYNC-STD-004, SYNC-MS-001, SYNC-MS-002, SYNC-MS-003, SYNC-MS-004, SYNC-MS-005, SYNC-MS-006, SYNC-MS-007, SYNC-MS-008, SYNC-MS-009, SYNC-API-001, SYNC-API-002, SYNC-UI-002, SYNC-SCN-001]
---

# 구현 계획

## 0. 이 문서가 다루는 것

11단계 CODE. 개발 규약([[SYNC-STD-004]]) DEV-11~14대로 작업을 슬라이스 카드로 자르고, 각 카드에 커밋을 기록한다. **에이전트는 카드 하나를 받아 카드 안 참조만 따라간다.**

슬라이스는 시나리오([[SYNC-SCN-001]]) 우선순위 순서 — S1이 최우선이었으므로 B1이 첫 슬라이스. 기반 A가 끝나야 B가 시작되고, B1이 끝나면 에이전트가 MCP로 문서를 올릴 수 있어 그때부터 싱크독으로 싱크독을 만든다.

**진행 상황**: 카드 8개 중 완료 5 (A · B1 · B2 · B3 · B4).

---

## 1. 슬라이스

#### A 기반

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 3·4·8장 · [[SYNC-DOM-002]] 1장 · [[SYNC-DOM-003]] · [[SYNC-STD-004#DEV-7]] |
| 구현 | 폴더 구조(클래스 1장 그대로) · `pyproject.toml`(FastAPI·SQLAlchemy 2·Alembic·httpx·mcp) · `docker-compose.yml`(app + PostgreSQL) · `config.py`(환경 변수: DB URL·SECRET_KEY·GitHub OAuth·WEBHOOK_SECRET·REPOS_DIR) · `db.py`(엔진·세션) · 빈 FastAPI 앱 + `/health` |
| DB | 엔티티 12개 SQLAlchemy 모델(클래스 2장) · Alembic `0001_initial` — 테이블 12개 + 인덱스(ERD·DD 3장) 한 번에 |
| infra | [[SYNC-MS-009#git.clone]] ~ [[SYNC-MS-009#git.init_specs]] 11개 · [[SYNC-MS-009#github.verify_signature]] ~ [[SYNC-MS-009#github.get_user]] 3개 |
| 인증 | [[SYNC-MS-006#AccountService.login_github]] ~ [[SYNC-MS-006#AccountService.create_placeholder]] 8개 · `/auth/*` 라우터 · 세션 |
| 테스트 | 마이그레이션 up/down · git 어댑터는 임시 저장소로 · OAuth는 GitHub 응답 모킹 |
| 선행 | 없음 |
| 완료 | 2026-09-08 · 브랜치 `feat/a-foundation` · 커밋 `9d99b93`~`ad06e7a` (code 26 + spec 9, PR #1 `hoyoungparkme/syncdoc`) · 테스트 48 · MS-009 14/14 · MS-006 8/8 · 되먹임: [[SYNC-STD-004#DEV-16]] 신설, MS-009 `git.clone`·`commit_push`, MS-006 `login_github` async, DOM-002 1장 `core/types.py`·`errors.py` |

#### B1 대화하다가 명세가 쌓인다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S1]] · [[SYNC-UC-001#UC-A1]] · [[SYNC-UC-001#UC-A6]] · [[SYNC-UC-001#UC-S1]] · [[SYNC-UC-001#UC-S2]] · [[SYNC-UC-001#UC-S7]] |
| 구현 함수 | **project** [[SYNC-MS-001#ProjectService.init_project]] · [[SYNC-MS-001#ProjectService.get]] · [[SYNC-MS-001#ProjectService.list_projects]] · **spec** [[SYNC-MS-002#SpecService.validate]] · [[SYNC-MS-002#SpecService.item_blocks]] · [[SYNC-MS-002#SpecService.issue_doc_id]] · [[SYNC-MS-002#SpecService.apply_frontmatter]] · [[SYNC-MS-002#SpecService.detect_deleted_items]] · [[SYNC-MS-002#SpecService.create]] · [[SYNC-MS-002#SpecService.save]] · [[SYNC-MS-002#SpecService.get_document]] · [[SYNC-MS-002#SpecService.get_item]] · [[SYNC-MS-002#SpecService.list_by_project]] · [[SYNC-MS-002#SpecService.last_author]] · [[SYNC-MS-002#SpecService.neighbors]] · [[SYNC-MS-002#SpecService.resolve_item]] · **reference** [[SYNC-MS-003#ReferenceService.extract]] · [[SYNC-MS-003#ReferenceService.downstream]] · **tracking** [[SYNC-MS-004#TrackingService.raise_broken]] · [[SYNC-MS-004#TrackingService.raise_upstream]] · [[SYNC-MS-004#TrackingService.flags_for_items]] · [[SYNC-MS-004#TrackingService.count_flags]] · [[SYNC-MS-004#TrackingService.count_flags_by_document]] · **collab** [[SYNC-MS-005#CommentService.relocate]] · [[SYNC-MS-005#CommentService.count_unresolved]] · [[SYNC-MS-005#CommentService.count_unresolved_by_document]] · **account** [[SYNC-MS-006#AccountService.users_by_ids]] · **pipeline** [[SYNC-MS-007#pipeline.save_pipeline]] · **queries** [[SYNC-MS-008#queries.project_summary]] · [[SYNC-MS-008#queries.document_list]] · [[SYNC-MS-008#queries.document_view]] · [[SYNC-MS-008#queries.item_view]] — 32개. `core/markdown.py` 순수 함수 포함 |
| API | [[SYNC-API-002#init_project]] · [[SYNC-API-002#get_template]] · [[SYNC-API-002#list_documents]] · [[SYNC-API-002#get_document]] · [[SYNC-API-002#get_item]] · [[SYNC-API-002#create_document]] · [[SYNC-API-002#update_document]] · MCP 서버·인증([[SYNC-SEQ-001#SEQ-C2]]) |
| 화면 | 없음. 이 슬라이스는 MCP만 |
| 테스트 | 구현 함수의 테스트 관점 전부 · **E2E**: 에이전트가 `init_project` → `create_document` → `get_document` → `update_document`(버전 충돌·규약 위반·삭제 확인 세 갈래) → 저장소에 커밋이 있고 참조가 추출됨 |
| 스텁 (DEV-12) | `TrackingService.detect_impact → []` (B3 해제) · `ProjectService.init_project`의 `import_existing=true` → `! not-implemented`(501) (B4에서 `pipeline.rebuild`로 해제) · `save_pipeline`의 `entry=web_status` → `! not-implemented`(501) (B2 `apply_status`에서 해제) · `tracking.create_pending` → `! not-implemented`(501) (B3. `detect_impact` 스텁이 빈 목록이라 실제로는 안 불림). `changed_items`·`upstream_impact`는 받아서 `upstream_impact`는 실동작, `changed_items`는 저장만 |
| 선행 | A |
| 완료 | 2026-09-08 · 브랜치 `feat/a-foundation` · 커밋 `0697ad2`~`9070b2b` (code 24 + spec 21 + chore 0, PR #2 `hoyoungparkme/syncdoc`) · 테스트 104(E2E S1 포함) · `check_code.py` 32/32 · 스텁 둘 유지(`detect_impact → []`, `import_existing → 501`) · 되먹임: DOM-002 1장 `core/markdown.py`, `versions.via`(0002), MS-007 `project_code`, MS-005 `relocate(old_version_no)`, MS-001 `init_project → Project`, [[SYNC-STD-004#DEV-10]] 세션 소유자, DEV-12 카드 닫힘 |

#### B2 읽고 확정한다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S2]] · [[SYNC-SCN-001#S5]] · [[SYNC-SCN-001#S6]] · [[SYNC-UC-001#UC-H2]] · UC-H3 · UC-H8 · UC-H9 · UC-H14 · UC-H15(댓글·규약 오류 묶음만) |
| 구현 함수 | [[SYNC-MS-007#pipeline.change_status]] · [[SYNC-MS-002#SpecService.apply_status]] · [[SYNC-MS-002#SpecService.describe_items]] · [[SYNC-MS-002#SpecService.describe_documents]] · [[SYNC-MS-002#SpecService.versions_by_ids]] · [[SYNC-MS-002#SpecService.recent_changes]] · [[SYNC-MS-003#ReferenceService.upstream]] · [[SYNC-MS-003#ReferenceService.downstream_of_document]] · [[SYNC-MS-003#ReferenceService.upstream_of_document]] · [[SYNC-MS-005#CommentService.list]] · [[SYNC-MS-005#CommentService.add]] · [[SYNC-MS-005#CommentService.resolve]] · [[SYNC-MS-005#CommentService.unresolved_count]] · [[SYNC-MS-005#CommentService.unresolved_in]] · [[SYNC-MS-008#queries.project_detail]] · [[SYNC-MS-008#queries.item_references_view]] · [[SYNC-MS-008#queries.upstream_checklist]] · [[SYNC-MS-006#AccountService.issue_token]] · [[SYNC-MS-006#AccountService.list_tokens]] · [[SYNC-MS-006#AccountService.revoke_token]] |
| API | [[SYNC-API-001#GET/api/projects]] · [[SYNC-API-001#GET/api/projects/{code}]] · [[SYNC-API-001#GET/api/projects/{code}/docs]] · [[SYNC-API-001#GET/api/docs/{docId}]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/references]] · [[SYNC-API-001#GET/api/docs/{docId}/upstream]] · [[SYNC-API-001#POST/api/docs/{docId}/status]] · [[SYNC-API-001#GET/api/docs/{docId}/comments]] · [[SYNC-API-001#POST/api/docs/{docId}/comments]] · [[SYNC-API-001#POST/api/comments/{id}/resolve]] · [[SYNC-API-001#GET/api/me]] · [[SYNC-API-001#GET/api/me/tokens]] · [[SYNC-API-001#POST/api/me/tokens]] · [[SYNC-API-001#DELETE/api/me/tokens/{id}]] · [[SYNC-API-001#POST/api/projects]] |
| 화면 | [[SYNC-UI-002#UI-1]] · [[SYNC-UI-002#UI-2]] · [[SYNC-UI-002#UI-3]] · [[SYNC-UI-002#UI-4]] · [[SYNC-UI-002#UI-5]](유저용·원본 탭, 참조 패널, 댓글 패널, 상태 변경 + 상위 대조 다이얼로그) · [[SYNC-UI-002#UI-13]] · 유저용 탭 렌더링은 [[SYNC-STD-002]] V-* — `_tools/view_build.py`가 참조 구현 |
| 테스트 | 구현 함수의 테스트 관점 · **E2E**: 민준이 웹에서 로그인 → 프로젝트 목록 → 문서 뷰 → 댓글 → 승인(상위 대조 포함) → 토큰 발급 → 그 토큰으로 MCP `get_document` |
| 선행 | B1 |
| 완료 | 2026-09-08 · 브랜치 `feat/a-foundation` · 커밋 `6edc202`~`95fd483` (code 16 + spec 16, PR #3 `hoyoungparkme/syncdoc`) · 테스트 124(E2E S2·S5 포함) · `check_code.py` 20/20 · 화면 UI-1·2·3·4·5·13 (`frontend/`, 유저용 탭은 `view_build.py` 포트) · 되먹임: `versions.message`(0003), DEV-2 `*Row`, `change_status`→`pipeline`(같은 세션), MS-007 `reason`·`session`·8단계 모든 경로, `describe_documents`·`versions_by_ids`, MS-003 `include_missing`, API `GET /docs/{docId}/downstream`(B4) · 남긴 것: `Version` DTO에 `doc_id`(API 스키마에 없음), `create`는 경고를 안 남김(MS-002 → 되먹임으로 해소) · **화면 확인: 사용자 대기** (DEV-14 일곱째) |

#### B3 상위 변경 추적

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S4]] · [[SYNC-UC-001#UC-S3]] · UC-S4 · UC-H10 · UC-H11 · UC-H12 · UC-H13 · UC-H15 |
| 구현 함수 | [[SYNC-MS-004#TrackingService.detect_impact]](스텁 해제) · [[SYNC-MS-004#TrackingService.create_pending]] · [[SYNC-MS-004#TrackingService.get_decision]] · [[SYNC-MS-004#TrackingService.record_decision]] · [[SYNC-MS-004#TrackingService.raise_flags]] · [[SYNC-MS-004#TrackingService.get_flag]] · [[SYNC-MS-004#TrackingService.resolve]] · [[SYNC-MS-004#TrackingService.flags_for_assignee]] · [[SYNC-MS-004#TrackingService.flags_unassigned]] · [[SYNC-MS-004#TrackingService.flags_in_project]] · [[SYNC-MS-004#TrackingService.pending_decisions_for]] · [[SYNC-MS-002#SpecService.diff]] · [[SYNC-MS-002#SpecService.resolve_items]] · [[SYNC-MS-002#SpecService.versions_instructed_by]] · [[SYNC-MS-002#SpecService.convention_error_docs_by]] · [[SYNC-MS-002#SpecService.documents_authored_by]] · [[SYNC-MS-003#ReferenceService.count_downstream]] · [[SYNC-MS-008#queries.todo]] · [[SYNC-MS-008#queries.decision_view]] · [[SYNC-MS-008#queries.flag_view]] · [[SYNC-MS-008#queries.project_items]] · [[SYNC-MS-008#queries.diff_with_impact]] |
| API | [[SYNC-API-001#GET/api/todo]] · [[SYNC-API-001#GET/api/flags/{id}]] · [[SYNC-API-001#POST/api/flags/{id}/resolve]] · [[SYNC-API-001#GET/api/decisions/{versionId}]] · [[SYNC-API-001#POST/api/decisions/{versionId}]] · [[SYNC-API-001#GET/api/projects/{code}/flags]] · [[SYNC-API-001#GET/api/docs/{docId}/diff]] · MCP `update_document`의 `changed_items`·`upstream_impact` 실동작 |
| 화면 | [[SYNC-UI-002#UI-10]] · [[SYNC-UI-002#UI-11]] · [[SYNC-UI-002#UI-12]] |
| 테스트 | 구현 함수의 테스트 관점 · **E2E**: 에이전트가 PRD R12 수정(`changed_items`) → 호영 내 할 일에 전파 미결정 → 예 → 하위 4건 플래그 → 민준 내 할 일 → 확인 처리(수정 동반·수정 없음 둘 다) · 항목 삭제 → 끊어진 참조 · API가 UC-A6 어긋남 지정 → 하위 불일치 |
| 선행 | B2 |
| 완료 | 2026-09-09 · 브랜치 `feat/a-foundation` · 커밋 `021cded`~`193dcf6` (code 9, PR #4 `hoyoungparkme/syncdoc`) · 테스트 136(E2E S4 포함) · `check_code.py` 22/22 · 화면 UI-10·11·12 (`Todo.tsx`·`FlagView.tsx`·`DecisionDialog.tsx`, 요소 번호 = `data-el`) · 스텁 해제: `detect_impact`, `create_pending`(501) · 정한 것: `create_pending` 3인자(MS-004; MS-007 11단계는 1인자), `resolve → FlagSummary`는 `assignee_id`만 채우고 이름은 라우터가, `VersionBrief`에 commit_hash·author, `ItemRef.deleted_at`, `FlagDetail`에 cause_deleted_at·cause_body(API 스키마에 없음), 문서 단위 참조 대상은 원인 항목 없는 플래그 하나 · **화면 확인: 사용자 대기** (DEV-14 일곱째) |

#### B4 나머지 화면과 운영

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S3]] · [[SYNC-SCN-001#S7]] · [[SYNC-UC-001#UC-H4]] · UC-H6 · UC-H7 · UC-H16 · UC-G1 · UC-S6 |
| 구현 함수 | [[SYNC-MS-002#SpecService.list_versions]] · [[SYNC-MS-002#SpecService.mark_deleted]] · [[SYNC-MS-007#pipeline.revert]] · [[SYNC-MS-002#SpecService.list_items_by_project]] · [[SYNC-MS-002#SpecService.clear_index]] · [[SYNC-MS-002#SpecService.mark_convention_error]] · [[SYNC-MS-003#ReferenceService.references_among]] · [[SYNC-MS-003#ReferenceService.resolve_missing]] · [[SYNC-MS-003#ReferenceService.clear]] · [[SYNC-MS-001#ProjectService.repo_status]] · [[SYNC-MS-001#ProjectService.rebuild_index]] · [[SYNC-MS-007#pipeline.process_commit]] · [[SYNC-MS-007#pipeline.rebuild]] · [[SYNC-MS-008#queries.graph_view]] · [[SYNC-MS-008#queries.downstream_view]] · [[SYNC-MS-008#queries.document_view]] 4a `missing_refs`(유저용 탭 회색 `?`) · [[SYNC-API-002#get_references]] |
| API | [[SYNC-API-001#GET/api/projects/{code}/graph]] · [[SYNC-API-001#GET/api/docs/{docId}/versions]] · [[SYNC-API-001#GET/api/docs/{docId}/downstream]] · [[SYNC-API-001#POST/api/docs/{docId}/revert]] · [[SYNC-API-001#POST/hooks/github]] · [[SYNC-API-001#GET/api/admin/repos]] · [[SYNC-API-001#POST/api/admin/repos/{code}/rebuild]] · 폴링 스케줄러 |
| 화면 | [[SYNC-UI-002#UI-7]] · [[SYNC-UI-002#UI-8]] · [[SYNC-UI-002#UI-9]] · [[SYNC-UI-002#UI-14]] |
| 테스트 | 구현 함수의 테스트 관점 · **E2E**: GitHub에 직접 push → webhook → 문서 갱신 · 서버 꺼둔 뒤 push → 켜면 따라잡음 · DB 비우고 재구축 → 참조 복원, 플래그는 유지 · 되돌리기 → 새 버전 + 삭제 확인 |
| 선행 | B3 |
| 완료 | 2026-09-09 · 브랜치 `feat/a-foundation` · 커밋 `a592237`~`52b966c` (code 13 + chore 1, PR #5 `hoyoungparkme/syncdoc`) · 테스트 154(E2E S7 포함) · `check_code.py` 108/109(`pipeline.rebuild`의 `session` 인자 — 아래) · `check_ui.py` 13화면 중 12(UI-4 3.5는 UI-002 배치 누락) · 화면 UI-7·8·9·14 · 스텁 해제: `import_existing`(rebuild), `detect_impact`·`create_pending`은 B3 · 정한 것: `rebuild(code, session=None)`(init_project 3a2가 자기 세션을 넘김), github 신규 파일은 파일명이 doc_id, github 진입은 삭제 확인 없이 저장, process_commit은 11단계 순, `clear_index`는 `current_version_no`를 안 내리고 `save(rebuild)`가 남은 버전 수로 번호(DOM-003 ≥1), rebuild 첫 커밋은 `create`, `SpecService.version_body`, `RefEdge.from_document_id`, `scheduler.py`(POLL_INTERVAL_SECONDS), dagre 미사용(열 고정 규칙), process_commit이 앱 자신의 커밋을 건너뜀 · **화면 확인: 사용자 대기** (DEV-14 일곱째) |

#### C 통합·배포

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 5·7·8장 |
| 구현 | Cloudflare **Quick Tunnel**(도메인 없음·주소 가변, INFRA 5장) · GitHub OAuth 앱 등록(callback URL은 켤 때마다 갱신) · **webhook은 걸지 않는다**(주소가 바뀐다) · `docker compose up` 기동 스크립트 · 기동 시 따라잡기 · 5분 폴링 |
| 첫 사용 | 싱크독 저장소를 싱크독에 `init_project`(import_existing=true) → 문서·항목·참조가 인덱스되고 **validate 결과가 `tools/validate.py`와 일치** → 이 문서를 싱크독에서 승인 |
| 테스트 | 노트북 밖에서 접속 · 팀원 로그인 · 팀원 토큰으로 MCP |
| 선행 | B4 |
| 완료 | — (C-1 로컬 2026-09-09: `docker compose up --build`(Dockerfile 2단계) → 마이그레이션 0001~0004 → 실제 GitHub OAuth 로그인 → `HoyoungParkme/syncdoc` `import_existing=true` → 문서 27·항목 338·참조 963(미존재 0)·규약 오류 0 = `tools/validate.py`와 일치 → MCP 토큰으로 `get_document`·`get_references`. C-2 2026-09-09: Quick Tunnel `*.trycloudflare.com` → 노트북 밖에서 접속·로그인 확인, 세션 없으면 401 · 터널로 MCP(토큰 없이 401, 토큰으로 정상) · **폴링 확인**: PR #1 머지로 main 전진 → 5분 주기 폴링이 스스로 따라잡아(약 4분 40초) 바뀐 명세 10개에 v2 생성, 전부 `via=github`, `last_processed_commit`이 새 main과 일치 · OAuth는 앱 하나에 로컬·터널 콜백 둘 등록, `redirect_uri`로 각자 주소 복귀 · webhook 없음(주소 가변, 명세대로 폴링만) · **남은 것: 팀원 로그인·팀원 토큰 MCP(다른 GitHub 계정 필요)** · 미결: 비공개 저장소 fetch 토큰(v2, MS-009 8장)) |


#### D1 토큰과 셸

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-001]] 3장 디자인 토큰 · 4장 공통 틀 · [[SYNC-UI-002]] 1장 공통 컴포넌트 |
| 구현 | CSS 변수로 옮긴 토큰(색·타이포·간격·모서리·그림자) · Pretendard·IBM Plex Mono · 앱 셸(`height:100vh`, 페이지 전체 스크롤 없음) · 상단 바(프로젝트 선택 제거, 사용 방법·로그아웃 추가) · 공통 컴포넌트 다섯 — 다이얼로그 셸·툴팁·토스트·상태 필·항목 ID 뱃지 |
| 화면 | [[SYNC-UI-002#UI-16]] (공통 컴포넌트를 처음 쓰는 화면) |
| 테스트 | 토큰 값이 명세 3장과 일치 · 툴팁이 클릭·스크롤·화면 이동에 지워짐 · 다이얼로그 위 다이얼로그가 겹쳐 뜸 |
| 선행 | B4 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `4ad5870`~`c6d0761` (code 5 + spec 2) · `check_tokens.py` 어긋남 0 · `check_view_css.py` 같음 · `check_ui.py` UI-16 요소 10/10 (전체 6/14 — 나머지는 D2~D5 작업 목록) · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 테스트 163 · **브라우저 확인**: 상단 바 50px·페이지 전체 스크롤 없음·Pretendard/IBM Plex Mono 로드됨 · 툴팁이 아무 곳 클릭·스크롤·popstate 이동에 지워짐 · 토스트 2.6초 · `--depth:1`이면 다이얼로그 50→51·오버레이 45→46 · 정한 것: 뷰 CSS를 `styles.view.css`로 갈라 놓고 `check_view_css.py`가 지킨다, 셸이 `.screen` 하나로 감싼다(세로 flex 교차축에서 `margin:0 auto`가 늘어나지 않고, 화면이 조각으로 형제 여럿을 내놓기도 해서), `--docbar-h` 신설(목차·패널이 문서 바 아래에 붙게), 공통 컴포넌트를 만들면서 이미 같은 것을 그리던 자리를 맞바꿈(`title` 속성 넷 → 툴팁, `.st st-{status}` 다섯 → 상태 필, UI-14 재구축 완료 → 토스트) · **미룬 것**: 다이얼로그 위 다이얼로그의 실제 사례는 UI-13 위 재구축 확인이라 D5에서 뜬다. 여기서는 `--depth` 계산만 확인했다 · **화면 확인: 사용자 대기** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `c0eea3b`~`bfca1a9`)**: UI-13 카드 순서를 토큰 먼저로, 발급을 카드 머리 채운 버튼으로, 토큰 행 두 줄, 버튼 위계 셋(채움·테두리·빨강), 토큰 원문 상자를 주의색으로. `.btn.sm.solid`가 `.btn.solid`의 padding에 덮여 커져 있었다 |

#### D2 읽기 화면

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-1]] · [[SYNC-UI-002#UI-2]] · [[SYNC-UI-002#UI-4]] · [[SYNC-UI-002#UI-9]] |
| 구현 | 로그인 11단계 색 띠 · 히트맵 규격과 범례 · 프로젝트 상세 요약 수치 여섯·동기화 상태·11단계 아코디언 · 순서대로 읽기 단계 칩 |
| API | [[SYNC-API-001#GET/api/projects/{code}]] (동기화 상태·요약 수치 여섯) |
| 화면 | UI-1 · UI-2 · UI-4 · UI-9 |
| 테스트 | 요소 번호 대조(`check_ui`) · 요약 수치 여섯 칸이 플래그 세 종류를 다 셈 · 동기화 상태가 fetch 없이 DB 값을 보여줌 |
| 선행 | D1 · D6(동기화 컬럼) |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `19d043f`~`7410822` (code 2 + spec 1 + chore 1) · `check_ui.py` UI-1·2·4·9 전부 일치(전체 9/14, 나머지는 D3~D5) · `check_tokens.py` 어긋남 0 · `validate.py` 위반 0·경고 0 · `check_code.py` 114/114 · 테스트 165 · **브라우저 확인**(도커 이미지 재빌드 후 실물): 요약 여섯 칸 · 동기화 `eb30fd6`/밀림 0 · 하위 불일치 다이얼로그 · 플래그 테두리 `--danger` · 화면 아홉 곳 페이지 스크롤 없음 · **상의해서 정한 것 둘**: UI-1 11단계 색 띠를 뺐다(인증 없는 엔드포인트가 필요한데 그러면 프로젝트 진행도가 공개된다 — UI-001 7장 5), `StageSummary.flag_count`를 불리언 아닌 정수로 신설 · 정한 것: 칸 하나에 툴팁 하나(칸과 ▲에 따로 걸면 ▲ 위에서 둘이 같이 뜬다), UI-4는 상세 응답이 오기 전 목록 요약으로 그린다, UI-9 앞뒤 버튼이 갈 단계를 이름으로 말하고 갈 곳 없으면 비활성 · **고친 것**: `.warn`이 뷰 CSS에서는 배너라 ⚠가 빨간 상자로 떴다, mermaid가 body에 붙이는 6px 툴팁이 페이지 전체 스크롤을 만들고 있었다(`!important` 한 곳) · 셸 공용 다섯(`.btn` `.lbl` `.mono` `.phead` `.empty`)을 뷰 변수에서 앱 토큰으로 · **화면 확인: 사용자 대기** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `17108fa`~`8d3c6c4`)**: UI-8 치수를 핸드오프 값으로(열 150 · 노드 118×26 · 행 40 · 여백 18 — 차 32px가 간선 거터), 간선 화살촉, 헤더 브레드크럼. UI-9는 전폭 단계 레일 + 문서 머리 3단, 이동 줄을 카드 밖으로 |

#### D3 문서와 이력

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-5]] · [[SYNC-UI-002#UI-7]] |
| 구현 | 사이드바 드래그 리사이즈 둘 · 표시된 항목 블록 · 원본 탭 원문/렌더링 · 세 탭 본문 폭 일치 · 버전 A/B 비교 |
| API | [[SYNC-API-001#GET/api/docs/{docId}/diff]] (문맥 줄 수) |
| 화면 | UI-5 · UI-7 |
| 테스트 | 요소 번호 대조 · 탭을 오가도 본문이 좌우로 안 흔들림 · 세 번째 버전을 고르면 A가 밀려남 |
| 선행 | D1 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `1320d99` (code 1) · `check_ui.py` UI-5 34/34 · UI-7 16/16 (전체 11/14, 나머지는 D4·D5) · `check_tokens.py` 어긋남 0 · `validate.py` 위반 0·경고 0 · 테스트 165 · **브라우저 확인**(`dev_preview.py` 시드 — 버전 셋짜리 문서가 필요했다): 유저용·원본 본문이 같은 왼쪽 끝 253px·같은 폭 820px · 손잡이 200→300, 최소 140에서 멈춤, 새로고침 후 유지 · 원문/렌더링 선택 유지 · 표시된 항목 R1·R9·R10, 클릭 시 참조 탭 `#R1` · v3=B v2=A에서 v1을 고르면 A(v2)가 밀려나 v1=A v3=B · diff에 문맥 3줄 · 정한 것: 본문 폭 `--doc-w:820px`(명세는 "같아야 한다"만 말하고 값을 안 정했다 — 디자인 핸드오프 값을 썼다), **원본 탭이 목차·패널 자리를 비워 둔다**(폭만 맞추면 왼쪽 끝이 50px 어긋나 규칙이 막으려는 흔들림이 그대로 남는다), A·B는 고른 순서가 아니라 버전 번호로 정한다, 이력 diff 칸을 반반으로 · **고친 것**: 손잡이 드래그가 stale closure로 마지막 증분만 반영되던 것, `tools/dev_preview.py`가 사용자 생성 전에 `hoyoung.id`를 써서 시드가 죽던 것 · **이슈로 넘긴 것**: #18(`status` 행을 diff 대상으로 고르면 비교가 안 된다) · #19(명세 본문의 html 코드블록이 살아 있는 HTML로 그려져 `data-el`이 새어 나온다) · **화면 확인: 사용자 대기** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `150ae75`~`7eab1bd`, `45fe8e3`~`7373e23`)**: 3단이 화면 높이를 채우고 가운데 열만 스크롤한다. **원본 탭이 목차·패널을 그대로 쥔다**(D3에서 자리만 비워 두던 것을 뒤집었다 — 핸드오프가 유지하는 쪽이고, 그래야 탭 전환에 3단이 안 무너진다). 목차 한 줄 자르기로 `표시된 항목`이 화면 안에 들어왔다. 참조·댓글 패널을 카드로. `pre.code`가 뷰 CSS의 어두운 코드블록 색을 물려받아 원본 탭 글씨가 거의 안 보이던 것을 `pre.mdsrc`로 갈라놓음 |

#### D4 그래프

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-8]] · [[SYNC-UI-002#UI-15]] |
| 구현 함수 | [[SYNC-MS-008#queries.graph_view]](범위 교체) · [[SYNC-MS-008#queries.item_chain]](신설) |
| API | [[SYNC-API-001#GET/api/projects/{code}/graph]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/chain]] |
| 화면 | UI-8 · UI-15 |
| 테스트 | 구현 함수의 테스트 관점 전부 · **범위 밖 대상 간선이 미존재 참조로 새지 않음** · 되돌아오는 참조의 상위가 `upstream`으로 적힘 · 빈 단계도 행이 옴 |
| 선행 | D1 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `f24147a`~`15749ef` (code 1 + spec 1) · `check_ui.py` UI-8 15/15 · UI-15 11/11 (전체 13/15, 나머지는 D5) · `check_tokens.py` 어긋남 0 · `validate.py` 위반 0·경고 0 · 테스트 166 · **브라우저 확인**(`dev_preview` 시드): 전체 문서 27·항목 362·참조 1051 → 플래그 문서 1·항목 3(전부 `▲`) → 승인만 0 · `PRD-001#R10` 호버에 상위 1·하위 2만 남고 385개가 흐려짐 · 되돌아오는 간선이 열 사이로 나가 레인(y=3751)을 지나 열 사이로 들어옴 · `CODE-001#D1` 체인에 빈 단계 다섯 · 칩 클릭으로 다시 그림 · 전체보기가 body에서 0~900을 채우고 z-index 80 · 정한 것: **react-flow를 뺐다**(열 고정 + 간선 넷의 서로 다른 경로라 범용 엔진과 계속 싸운다. main 번들 663KB → 543KB, `@xyflow/react`·`dagre`·`@types/dagre` 제거), 되돌아오는 간선은 열 사이 빈 자리로 빠져나간다(열 안으로 내려가면 그 열 노드를 관통한다), UI-15 칩은 폭 320px에서 자르고 전체는 `title`로 · **명세 구멍 메움**: `SYNC-API-001` Graph.nodes[]에 `has_flag`가 없어 UI-8 3.1을 그릴 수 없었다 · **고친 것**: UI-2 범례 견본(`i.sw`)과 UI-8 범례 견본(`svg.sw`)이 이름이 같아 그래프 범례 선이 회색 네모로 떴다 · **화면 확인: 사용자 대기** (DEV-14 일곱째) · **핸드오프 대조**: UI-15 폭 720px · 이 항목 칩을 흰 칩 + 1.5px 테두리로 · 현재 단계 라벨에 주의색 · 칩에서 프로젝트 코드 접두 제거 (커밋 `c0eea3b`~`bfca1a9`) |

#### D5 처리와 설정

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-3]] · [[SYNC-UI-002#UI-10]] · [[SYNC-UI-002#UI-11]] · [[SYNC-UI-002#UI-12]] · [[SYNC-UI-002#UI-13]] · [[SYNC-UI-002#UI-14]] |
| 구현 | 초기화를 다이얼로그로(커밋될 것 박스) · 내 할 일 묶음 순서 고정 · 플래그 확인 버튼 하나(자동 판정 미리 보기) · 설정을 다이얼로그로(카드 넷, 관리 흡수) · 토큰 마지막 사용 |
| API | [[SYNC-API-001#GET/api/me/tokens]] (마지막 사용) |
| 화면 | UI-3 · UI-10 · UI-11 · UI-12 · UI-13 · UI-14 |
| 테스트 | 요소 번호 대조 · 설정을 닫으면 보던 화면 그대로 · 관리가 접힌 채로 열림 · 재구축 확인이 설정 위에 겹쳐 뜸 |
| 선행 | D1 · D6(마지막 사용 컬럼) |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `39cea75` (code 1) · **`check_ui.py` 15/15 — 화면 열다섯이 전부 일치** · `check_tokens.py` 어긋남 0 · `check_code.py` 114/114 · `validate.py` 위반 0·경고 0 · 테스트 166 · **브라우저 확인**(`dev_preview` 시드): 설정 카드 넷·관리 접힘 · 토큰 발급 → 원문 상자와 `마지막 사용 없음` 행 · 재구축 확인이 설정 위(z 50 → 51)에 겹쳐 뜸 · 닫으면 URL 그대로 `/p/SYNC` · UI-3에 커밋될 것 세 줄 · UI-11 안내가 `수정 동반`으로 3.2와 같은 판정 · 화면 여덟 곳 스크롤·넘침 없음 · 정한 것: 경로 셋(`/projects/new` `/settings` `/settings/admin`)을 지웠다(셋 다 명세가 "별도 경로 없음"이라 한다), 커밋될 것(2.5)은 기존 명세가 발견되면 감춘다(화면이 저장소가 빈지 미리 알 방법이 없어 "발견 = 빈 저장소 아님"으로 읽었다), 코드 입력 대문자 필터는 안 넣었다(규칙 "화면은 검사하지 않는다") · **이슈로 넘긴 것**: #20(토큰 행 `접두어`가 API 명세에만 있고 컬럼이 없다 — 빼고 그렸다) · **화면 확인: 사용자 대기** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `636656a`~`7f44943`, `c0eea3b`~`7373e23`)**: UI-10 카드 경계를 묶음에서 항목으로(두 줄 카드), UI-11 머리 두 줄 + 확인 액션도 카드 + 폭 880px, UI-12 결정 버튼을 고정 푸터로 + 하위 항목 3열 표, UI-16 인트로 문단과 소제목·문장형 설명. **`.flag`가 검토중 노랑이었다 — UI-001 3.1이 플래그를 경고색으로 못박았다**. `.dot.flag`가 그 필의 여백을 물려받아 6px 점이 16px 알약이던 것도 함께 |

#### D6 뒤늦은 개정

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-DOM-003]] 2장 · [[SYNC-INFRA-001]] 5.1·5.2 · [[SYNC-STD-001]] 4장 |
| 구현 함수 | [[SYNC-MS-001#ProjectService.repo_status]](DB만 읽기) · [[SYNC-MS-001#ProjectService.delete_project]](신설) · [[SYNC-MS-002#SpecService.diff]](문맥 인자) · [[SYNC-MS-006#AccountService.issue_token]] [[SYNC-MS-006#AccountService.authenticate_token]] [[SYNC-MS-006#AccountService.github_token_for]] · [[SYNC-MS-007#scheduler.catch_up]](behind_by 기록) · [[SYNC-MS-009#git.commit_push]](재시도·거부 판정) |
| 구현 | 마이그레이션 — `repositories.behind_by`·`fetched_at`, `access_tokens.last_used_at` · 설정값 넷(`DIFF_CONTEXT_LINES`·`PUSH_RETRIES`·`SECRET_KEY_OLD`·`SESSION_SECRET`) · `/flags` 세 스키마에 판별 필드 · 검사 규칙 둘(`section.unnumbered`·`dom.name`) · 교차 검사기 `tools/check_dom.py` |
| API | [[SYNC-API-001#DELETE/api/projects/{code}]] · [[SYNC-API-001#GET/api/projects/{code}/flags]](판별 필드) |
| 화면 | 없음 |
| 테스트 | 구현 함수의 테스트 관점 전부 · `repo_status`가 `git.fetch`를 안 부름 · 비밀키를 바꾼 뒤 옛 토큰이 500이 아니라 401 · `check_dom.py`가 지금 명세에서 경고 0 |
| 선행 | B4 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `3f0ab95`~`01afb3d` (code 8 + chore 0) · 테스트 163 · `check_code.py` 114/114 · `check_dom.py` 경고 0 · `validate.py` 위반 0·경고 0 · 마이그레이션 0005 · **실물 확인**: `scope=all` 노드 366·간선 949, `approved`·`flagged` 0(SYNC는 전부 draft·무플래그), `SYNC-PRD-001#R1` 체인이 11행에 상위 1·하위 147 · 정한 것: `_rejected`는 `push --porcelain`의 `!` 플래그로(로케일 무관), `delete_all_of`는 ORM cascade 대신 삭제 순서를 코드가 쥔다, `session_secret`은 비면 `SECRET_KEY`로 떨어져 기존 배포가 안 깨진다 · **컬럼 검사 보류**: 클래스 속성↔DD 표 대조는 경고 23건이라 뺐다 — DD 표가 어느 컬럼을 싣는지 규약을 먼저 정해야 한다 · 미결: 테스트 플래키(#17) |

---

## 2. 통합 테스트 시나리오

시나리오 S1~S7을 그대로 E2E 테스트로. 각 슬라이스의 `테스트` 행에 나눠 들어가 있다. 전부 통과하면 PRD 성공지표 측정을 시작한다.

| 시나리오 | 슬라이스 | 검증하는 것 |
|---|---|---|
| [[SYNC-SCN-001#S1]] | B1 | MCP로 문서가 쌓이고 커밋·참조가 생긴다 |
| [[SYNC-SCN-001#S2]] | B2 | 웹에서 읽고 댓글 달고 승인한다 |
| [[SYNC-SCN-001#S3]] | B1·B4 | 코딩 중 에이전트가 항목·참조를 조회한다 |
| [[SYNC-SCN-001#S4]] | B3 | 상위 변경이 하위 플래그로, 하위 불일치가 상위 플래그로 |
| [[SYNC-SCN-001#S5]] | B2 | 다른 툴 팀원이 토큰 발급 후 MCP로 붙는다 |
| [[SYNC-SCN-001#S6]] | B2·B4 | 그래프·순서 읽기·원본 탭 |
| [[SYNC-SCN-001#S7]] | B4 | 플랫폼 없이 push한 것이 반영된다 |

---

## 3. CODE 단계 전 결정

MINISPEC이 낸 미결 셋. 카드에 들어가기 전에 정해야 한다.

- [x] **삭제된 파일 push** → 문서는 남기고 `draft` + 규약 오류 `file.deleted`, 항목 전부 `is_deleted`, 하위에 끊어진 참조. `SpecService.mark_deleted` 신설 (B4)
- [x] **같은 문서 안 참조 전파** → 전파한다. 같은 문서 항목도 대상 (B3)
- [x] **원인 항목이 여럿일 때** → 원인마다 플래그 따로. 확인도 따로 (B3)

- [x] **원격 기본 브랜치** → `main` 고정 (B1)
- [x] **React 라이브러리** → react-markdown+remark-gfm · mermaid · react-flow+dagre · diff 직접 (B2·B4). 인프라 3장에 기록

결정 전부 끝. A 카드부터 시작할 수 있다.

## 4. 커밋·PR 목록

슬라이스 카드의 `완료` 행에 기록한다. PR 하나 = 슬라이스 하나(DEV-15).

| 슬라이스 | 브랜치 | 커밋 | 날짜 |
|---|---|---|---|
| A | `feat/a-foundation` | `9d99b93`~`ad06e7a` | 2026-09-08 |
| B1 | `feat/a-foundation` | `0697ad2`~`9070b2b` | 2026-09-09 |

## 5. 미결사항

- [x] B1에서 `detect_impact` 스텁 — B3에서 해제할 때 B1 카드를 미완으로 되돌리나 — 결정: 되돌리지 않는다. 앞 카드는 스텁 행에 어느 카드가 푸는지 적고 그대로 두며, 해제한 카드가 완료란에 해제 사실을 적는다. B1·B3·B4가 이미 그렇게 기록돼 있다 ([[SYNC-STD-004#DEV-12]])
