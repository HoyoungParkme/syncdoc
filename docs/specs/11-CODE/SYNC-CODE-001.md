---
doc_id: SYNC-CODE-001
type: CODE
title: 구현 계획 — 슬라이스 카드와 커밋 기록
status: draft
upstream: [SYNC-STD-004, SYNC-MS-001, SYNC-MS-002, SYNC-MS-003, SYNC-MS-006, SYNC-MS-007, SYNC-MS-008, SYNC-MS-009, SYNC-API-001, SYNC-API-002, SYNC-UI-002, SYNC-SCN-001]
---

# 구현 계획

## 0. 이 문서가 다루는 것

11단계 CODE. 개발 규약([[SYNC-STD-004]]) DEV-11~14대로 작업을 슬라이스 카드로 자르고, 각 카드에 커밋을 기록한다. **에이전트는 카드 하나를 받아 카드 안 참조만 따라간다.**

슬라이스는 시나리오([[SYNC-SCN-001]]) 우선순위 순서 — S1이 최우선이었으므로 B1이 첫 슬라이스. 기반 A가 끝나야 B가 시작되고, B1이 끝나면 에이전트가 MCP로 문서를 올릴 수 있어 그때부터 싱크독으로 싱크독을 만든다.

**진행 상황**: 카드 43장. **A~AH 42장 완료**(2026-09-23), AI 진행 중.

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
| 구현 함수 | **project** [[SYNC-MS-001#ProjectService.init_project]] · [[SYNC-MS-001#ProjectService.get]] · [[SYNC-MS-001#ProjectService.list_projects]] · **spec** [[SYNC-MS-002#SpecService.validate]] · [[SYNC-MS-002#SpecService.item_blocks]] · [[SYNC-MS-002#SpecService.issue_doc_id]] · [[SYNC-MS-002#SpecService.apply_frontmatter]] · [[SYNC-MS-002#SpecService.detect_deleted_items]] · [[SYNC-MS-002#SpecService.create]] · [[SYNC-MS-002#SpecService.save]] · [[SYNC-MS-002#SpecService.get_document]] · [[SYNC-MS-002#SpecService.get_item]] · [[SYNC-MS-002#SpecService.list_by_project]] · [[SYNC-MS-002#SpecService.last_author]] · [[SYNC-MS-002#SpecService.neighbors]] · [[SYNC-MS-002#SpecService.resolve_item]] · **reference** [[SYNC-MS-003#ReferenceService.extract]] · [[SYNC-MS-003#ReferenceService.downstream]] · **tracking** `SYNC-MS-004#TrackingService.raise_broken` · `SYNC-MS-004#TrackingService.raise_upstream` · `SYNC-MS-004#TrackingService.flags_for_items` · `SYNC-MS-004#TrackingService.count_flags` · `SYNC-MS-004#TrackingService.count_flags_by_document` · **collab** `SYNC-MS-005#CommentService.relocate` · `SYNC-MS-005#CommentService.count_unresolved` · `SYNC-MS-005#CommentService.count_unresolved_by_document` · **account** [[SYNC-MS-006#AccountService.users_by_ids]] · **pipeline** [[SYNC-MS-007#pipeline.save_pipeline]] · **queries** [[SYNC-MS-008#queries.project_summary]] · [[SYNC-MS-008#queries.document_list]] · [[SYNC-MS-008#queries.document_view]] · [[SYNC-MS-008#queries.item_view]] — 32개. `core/markdown.py` 순수 함수 포함 |
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
| 구현 함수 | [[SYNC-MS-007#pipeline.change_status]] · [[SYNC-MS-002#SpecService.apply_status]] · [[SYNC-MS-002#SpecService.describe_items]] · [[SYNC-MS-002#SpecService.describe_documents]] · [[SYNC-MS-002#SpecService.versions_by_ids]] · [[SYNC-MS-002#SpecService.recent_changes]] · [[SYNC-MS-003#ReferenceService.upstream]] · [[SYNC-MS-003#ReferenceService.downstream_of_document]] · [[SYNC-MS-003#ReferenceService.upstream_of_document]] · `SYNC-MS-005#CommentService.list` · `SYNC-MS-005#CommentService.add` · `SYNC-MS-005#CommentService.resolve` · `SYNC-MS-005#CommentService.unresolved_count` · `SYNC-MS-005#CommentService.unresolved_in` · [[SYNC-MS-008#queries.project_detail]] · [[SYNC-MS-008#queries.item_references_view]] · `SYNC-MS-008#queries.upstream_checklist` · [[SYNC-MS-006#AccountService.issue_token]] · [[SYNC-MS-006#AccountService.list_tokens]] · [[SYNC-MS-006#AccountService.revoke_token]] |
| API | [[SYNC-API-001#GET/api/projects]] · [[SYNC-API-001#GET/api/projects/{code}]] · [[SYNC-API-001#GET/api/projects/{code}/docs]] · [[SYNC-API-001#GET/api/docs/{docId}]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/references]] · `SYNC-API-001#GET/api/docs/{docId}/upstream` · [[SYNC-API-001#POST/api/docs/{docId}/status]] · `SYNC-API-001#GET/api/docs/{docId}/comments` · `SYNC-API-001#POST/api/docs/{docId}/comments` · `SYNC-API-001#POST/api/comments/{id}/resolve` · [[SYNC-API-001#GET/api/me]] · [[SYNC-API-001#GET/api/me/tokens]] · [[SYNC-API-001#POST/api/me/tokens]] · [[SYNC-API-001#DELETE/api/me/tokens/{id}]] · [[SYNC-API-001#POST/api/projects]] |
| 화면 | [[SYNC-UI-002#UI-1]] · [[SYNC-UI-002#UI-2]] · [[SYNC-UI-002#UI-3]] · [[SYNC-UI-002#UI-4]] · [[SYNC-UI-002#UI-5]](유저용·원본 탭, 참조 패널, 댓글 패널, 상태 변경 + 상위 대조 다이얼로그) · [[SYNC-UI-002#UI-13]] · 유저용 탭 렌더링은 [[SYNC-STD-002]] V-* — `_tools/view_build.py`가 참조 구현 |
| 테스트 | 구현 함수의 테스트 관점 · **E2E**: 민준이 웹에서 로그인 → 프로젝트 목록 → 문서 뷰 → 댓글 → 승인(상위 대조 포함) → 토큰 발급 → 그 토큰으로 MCP `get_document` |
| 선행 | B1 |
| 완료 | 2026-09-08 · 브랜치 `feat/a-foundation` · 커밋 `6edc202`~`95fd483` (code 16 + spec 16, PR #3 `hoyoungparkme/syncdoc`) · 테스트 124(E2E S2·S5 포함) · `check_code.py` 20/20 · 화면 UI-1·2·3·4·5·13 (`frontend/`, 유저용 탭은 `view_build.py` 포트) · 되먹임: `versions.message`(0003), DEV-2 `*Row`, `change_status`→`pipeline`(같은 세션), MS-007 `reason`·`session`·8단계 모든 경로, `describe_documents`·`versions_by_ids`, MS-003 `include_missing`, API `GET /docs/{docId}/downstream`(B4) · 남긴 것: `Version` DTO에 `doc_id`(API 스키마에 없음), `create`는 경고를 안 남김(MS-002 → 되먹임으로 해소) · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) |

#### B3 상위 변경 추적

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S4]] · `SYNC-UC-001#UC-S3` · UC-S4 · UC-H10 · UC-H11 · UC-H12 · UC-H13 · UC-H15 |
| 구현 함수 | `SYNC-MS-004#TrackingService.detect_impact`(스텁 해제) · `SYNC-MS-004#TrackingService.create_pending` · `SYNC-MS-004#TrackingService.get_decision` · `SYNC-MS-004#TrackingService.record_decision` · `SYNC-MS-004#TrackingService.raise_flags` · `SYNC-MS-004#TrackingService.get_flag` · `SYNC-MS-004#TrackingService.resolve` · `SYNC-MS-004#TrackingService.flags_for_assignee` · `SYNC-MS-004#TrackingService.flags_unassigned` · `SYNC-MS-004#TrackingService.flags_in_project` · `SYNC-MS-004#TrackingService.pending_decisions_for` · [[SYNC-MS-002#SpecService.diff]] · [[SYNC-MS-002#SpecService.resolve_items]] · `SYNC-MS-002#SpecService.versions_instructed_by` · `SYNC-MS-002#SpecService.convention_error_docs_by` · `SYNC-MS-002#SpecService.documents_authored_by` · [[SYNC-MS-003#ReferenceService.count_downstream]] · `SYNC-MS-008#queries.todo` · `SYNC-MS-008#queries.decision_view` · `SYNC-MS-008#queries.flag_view` · [[SYNC-MS-008#queries.project_items]] · [[SYNC-MS-008#queries.diff_with_impact]] |
| API | `SYNC-API-001#GET/api/todo` · `SYNC-API-001#GET/api/flags/{id}` · `SYNC-API-001#POST/api/flags/{id}/resolve` · `SYNC-API-001#GET/api/decisions/{versionId}` · `SYNC-API-001#POST/api/decisions/{versionId}` · [[SYNC-API-001#GET/api/projects/{code}/flags]] · [[SYNC-API-001#GET/api/docs/{docId}/diff]] · MCP `update_document`의 `changed_items`·`upstream_impact` 실동작 |
| 화면 | `SYNC-UI-002#UI-10` · `SYNC-UI-002#UI-11` · `SYNC-UI-002#UI-12` |
| 테스트 | 구현 함수의 테스트 관점 · **E2E**: 에이전트가 PRD R12 수정(`changed_items`) → 호영 내 할 일에 전파 미결정 → 예 → 하위 4건 플래그 → 민준 내 할 일 → 확인 처리(수정 동반·수정 없음 둘 다) · 항목 삭제 → 끊어진 참조 · API가 UC-A6 어긋남 지정 → 하위 불일치 |
| 선행 | B2 |
| 완료 | 2026-09-09 · 브랜치 `feat/a-foundation` · 커밋 `021cded`~`193dcf6` (code 9, PR #4 `hoyoungparkme/syncdoc`) · 테스트 136(E2E S4 포함) · `check_code.py` 22/22 · 화면 UI-10·11·12 (`Todo.tsx`·`FlagView.tsx`·`DecisionDialog.tsx`, 요소 번호 = `data-el`) · 스텁 해제: `detect_impact`, `create_pending`(501) · 정한 것: `create_pending` 3인자(MS-004; MS-007 11단계는 1인자), `resolve → FlagSummary`는 `assignee_id`만 채우고 이름은 라우터가, `VersionBrief`에 commit_hash·author, `ItemRef.deleted_at`, `FlagDetail`에 cause_deleted_at·cause_body(API 스키마에 없음), 문서 단위 참조 대상은 원인 항목 없는 플래그 하나 · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) |

#### B4 나머지 화면과 운영

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S3]] · [[SYNC-SCN-001#S7]] · [[SYNC-UC-001#UC-H4]] · UC-H6 · UC-H7 · UC-H16 · UC-G1 · UC-S6 |
| 구현 함수 | [[SYNC-MS-002#SpecService.list_versions]] · [[SYNC-MS-002#SpecService.mark_deleted]] · [[SYNC-MS-007#pipeline.revert]] · [[SYNC-MS-002#SpecService.list_items_by_project]] · [[SYNC-MS-002#SpecService.clear_index]] · [[SYNC-MS-002#SpecService.mark_convention_error]] · [[SYNC-MS-003#ReferenceService.references_among]] · [[SYNC-MS-003#ReferenceService.resolve_missing]] · [[SYNC-MS-003#ReferenceService.clear]] · [[SYNC-MS-001#ProjectService.repo_status]] · [[SYNC-MS-001#ProjectService.rebuild_index]] · [[SYNC-MS-007#pipeline.process_commit]] · [[SYNC-MS-007#pipeline.rebuild]] · [[SYNC-MS-008#queries.graph_view]] · [[SYNC-MS-008#queries.downstream_view]] · [[SYNC-MS-008#queries.document_view]] 4a `missing_refs`(유저용 탭 회색 `?`) · [[SYNC-API-002#get_references]] |
| API | [[SYNC-API-001#GET/api/projects/{code}/graph]] · [[SYNC-API-001#GET/api/docs/{docId}/versions]] · [[SYNC-API-001#GET/api/docs/{docId}/downstream]] · [[SYNC-API-001#POST/api/docs/{docId}/revert]] · [[SYNC-API-001#POST/hooks/github]] · [[SYNC-API-001#GET/api/admin/repos]] · [[SYNC-API-001#POST/api/admin/repos/{code}/rebuild]] · 폴링 스케줄러 |
| 화면 | [[SYNC-UI-002#UI-7]] · [[SYNC-UI-002#UI-8]] · [[SYNC-UI-002#UI-9]] · [[SYNC-UI-002#UI-14]] |
| 테스트 | 구현 함수의 테스트 관점 · **E2E**: GitHub에 직접 push → webhook → 문서 갱신 · 서버 꺼둔 뒤 push → 켜면 따라잡음 · DB 비우고 재구축 → 참조 복원, 플래그는 유지 · 되돌리기 → 새 버전 + 삭제 확인 |
| 선행 | B3 |
| 완료 | 2026-09-09 · 브랜치 `feat/a-foundation` · 커밋 `a592237`~`52b966c` (code 13 + chore 1, PR #5 `hoyoungparkme/syncdoc`) · 테스트 154(E2E S7 포함) · `check_code.py` 108/109(`pipeline.rebuild`의 `session` 인자 — 아래) · `check_ui.py` 13화면 중 12(UI-4 3.5는 UI-002 배치 누락) · 화면 UI-7·8·9·14 · 스텁 해제: `import_existing`(rebuild), `detect_impact`·`create_pending`은 B3 · 정한 것: `rebuild(code, session=None)`(init_project 3a2가 자기 세션을 넘김), github 신규 파일은 파일명이 doc_id, github 진입은 삭제 확인 없이 저장, process_commit은 11단계 순, `clear_index`는 `current_version_no`를 안 내리고 `save(rebuild)`가 남은 버전 수로 번호(DOM-003 ≥1), rebuild 첫 커밋은 `create`, `SpecService.version_body`, `RefEdge.from_document_id`, `scheduler.py`(POLL_INTERVAL_SECONDS), dagre 미사용(열 고정 규칙), process_commit이 앱 자신의 커밋을 건너뜀 · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) |

#### C 통합·배포

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 5·7·8장 |
| 구현 | Cloudflare **Quick Tunnel**(도메인 없음·주소 가변, INFRA 5장) · GitHub OAuth 앱 등록(callback URL은 켤 때마다 갱신) · **webhook은 걸지 않는다**(주소가 바뀐다) · `docker compose up` 기동 스크립트 · 기동 시 따라잡기 · 5분 폴링 |
| 첫 사용 | 싱크독 저장소를 싱크독에 `init_project`(import_existing=true) → 문서·항목·참조가 인덱스되고 **validate 결과가 `tools/validate.py`와 일치** → 이 문서를 싱크독에서 승인 |
| 테스트 | 노트북 밖에서 접속 · 팀원 로그인 · 팀원 토큰으로 MCP |
| 선행 | B4 |
| 완료 | (C-1 로컬 2026-09-09: `docker compose up --build`(Dockerfile 2단계) → 마이그레이션 0001~0004 → 실제 GitHub OAuth 로그인 → `HoyoungParkme/syncdoc` `import_existing=true` → 문서 27·항목 338·참조 963(미존재 0)·규약 오류 0 = `tools/validate.py`와 일치 → MCP 토큰으로 `get_document`·`get_references`. C-2 2026-09-09: Quick Tunnel `*.trycloudflare.com` → 노트북 밖에서 접속·로그인 확인, 세션 없으면 401 · 터널로 MCP(토큰 없이 401, 토큰으로 정상) · **폴링 확인**: PR #1 머지로 main 전진 → 5분 주기 폴링이 스스로 따라잡아(약 4분 40초) 바뀐 명세 10개에 v2 생성, 전부 `via=github`, `last_processed_commit`이 새 main과 일치 · OAuth는 앱 하나에 로컬·터널 콜백 둘 등록, `redirect_uri`로 각자 주소 복귀 · webhook 없음(주소 가변, 명세대로 폴링만) · **팀원 검증 2026-09-14** (`hypark-df`, 저장소 `bbs-spec` 협력자): GitHub OAuth로 팀원 로그인 → 새 사용자 생성(id=9) · UI-13에서 토큰 발급(「한 번만 보입니다」·복사·목록 표시 확인) · 그 토큰으로 MCP `get_document`·`update_document` → **커밋이 `hypark-df <hypark-df@users.noreply.github.com>`로 push되고 GitHub 계정까지 이어짐**, DB는 `kind=agent·작성자=hypark-df·via=mcp` · 주인이 상위 `BBS-PRD-001#R1`을 고쳐 전파하니 플래그 6건 중 **팀원이 마지막에 고친 문서의 2건만 팀원 「내 할 일」에 뜨고** 나머지 4건은 주인에게 감(담당자 = 대상 문서 최근 버전 작성자) · 팀원이 둘을 해제하니 0건 · 미결: 비공개 저장소 fetch 토큰(v2, MS-009 8장)) |


#### D1 토큰과 셸

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-001]] 3장 디자인 토큰 · 4장 공통 틀 · [[SYNC-UI-002]] 1장 공통 컴포넌트 |
| 구현 | CSS 변수로 옮긴 토큰(색·타이포·간격·모서리·그림자) · Pretendard·IBM Plex Mono · 앱 셸(`height:100vh`, 페이지 전체 스크롤 없음) · 상단 바(프로젝트 선택 제거, 사용 방법·로그아웃 추가) · 공통 컴포넌트 다섯 — 다이얼로그 셸·툴팁·토스트·상태 필·항목 ID 뱃지 |
| 화면 | [[SYNC-UI-002#UI-16]] (공통 컴포넌트를 처음 쓰는 화면) |
| 테스트 | 토큰 값이 명세 3장과 일치 · 툴팁이 클릭·스크롤·화면 이동에 지워짐 · 다이얼로그 위 다이얼로그가 겹쳐 뜸 |
| 선행 | B4 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `4ad5870`~`c6d0761` (code 5 + spec 2) · `check_tokens.py` 어긋남 0 · `check_view_css.py` 같음 · `check_ui.py` UI-16 요소 10/10 (전체 6/14 — 나머지는 D2~D5 작업 목록) · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 테스트 163 · **브라우저 확인**: 상단 바 50px·페이지 전체 스크롤 없음·Pretendard/IBM Plex Mono 로드됨 · 툴팁이 아무 곳 클릭·스크롤·popstate 이동에 지워짐 · 토스트 2.6초 · `--depth:1`이면 다이얼로그 50→51·오버레이 45→46 · 정한 것: 뷰 CSS를 `styles.view.css`로 갈라 놓고 `check_view_css.py`가 지킨다, 셸이 `.screen` 하나로 감싼다(세로 flex 교차축에서 `margin:0 auto`가 늘어나지 않고, 화면이 조각으로 형제 여럿을 내놓기도 해서), `--docbar-h` 신설(목차·패널이 문서 바 아래에 붙게), 공통 컴포넌트를 만들면서 이미 같은 것을 그리던 자리를 맞바꿈(`title` 속성 넷 → 툴팁, `.st st-{status}` 다섯 → 상태 필, UI-14 재구축 완료 → 토스트) · **미룬 것**: 다이얼로그 위 다이얼로그의 실제 사례는 UI-13 위 재구축 확인이라 D5에서 뜬다. 여기서는 `--depth` 계산만 확인했다 · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `c0eea3b`~`bfca1a9`)**: UI-13 카드 순서를 토큰 먼저로, 발급을 카드 머리 채운 버튼으로, 토큰 행 두 줄, 버튼 위계 셋(채움·테두리·빨강), 토큰 원문 상자를 주의색으로. `.btn.sm.solid`가 `.btn.solid`의 padding에 덮여 커져 있었다 |

#### D2 읽기 화면

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-1]] · [[SYNC-UI-002#UI-2]] · [[SYNC-UI-002#UI-4]] · [[SYNC-UI-002#UI-9]] |
| 구현 | 로그인 11단계 색 띠 · 히트맵 규격과 범례 · 프로젝트 상세 요약 수치 여섯·동기화 상태·11단계 아코디언 · 순서대로 읽기 단계 칩 |
| API | [[SYNC-API-001#GET/api/projects/{code}]] (동기화 상태·요약 수치 여섯) |
| 화면 | UI-1 · UI-2 · UI-4 · UI-9 |
| 테스트 | 요소 번호 대조(`check_ui`) · 요약 수치 여섯 칸이 플래그 세 종류를 다 셈 · 동기화 상태가 fetch 없이 DB 값을 보여줌 |
| 선행 | D1 · D6(동기화 컬럼) |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `19d043f`~`7410822` (code 2 + spec 1 + chore 1) · `check_ui.py` UI-1·2·4·9 전부 일치(전체 9/14, 나머지는 D3~D5) · `check_tokens.py` 어긋남 0 · `validate.py` 위반 0·경고 0 · `check_code.py` 114/114 · 테스트 165 · **브라우저 확인**(도커 이미지 재빌드 후 실물): 요약 여섯 칸 · 동기화 `eb30fd6`/밀림 0 · 하위 불일치 다이얼로그 · 플래그 테두리 `--danger` · 화면 아홉 곳 페이지 스크롤 없음 · **상의해서 정한 것 둘**: UI-1 11단계 색 띠를 뺐다(인증 없는 엔드포인트가 필요한데 그러면 프로젝트 진행도가 공개된다 — UI-001 7장 5), `StageSummary.flag_count`를 불리언 아닌 정수로 신설 · 정한 것: 칸 하나에 툴팁 하나(칸과 ▲에 따로 걸면 ▲ 위에서 둘이 같이 뜬다), UI-4는 상세 응답이 오기 전 목록 요약으로 그린다, UI-9 앞뒤 버튼이 갈 단계를 이름으로 말하고 갈 곳 없으면 비활성 · **고친 것**: `.warn`이 뷰 CSS에서는 배너라 ⚠가 빨간 상자로 떴다, mermaid가 body에 붙이는 6px 툴팁이 페이지 전체 스크롤을 만들고 있었다(`!important` 한 곳) · 셸 공용 다섯(`.btn` `.lbl` `.mono` `.phead` `.empty`)을 뷰 변수에서 앱 토큰으로 · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `17108fa`~`8d3c6c4`)**: UI-8 치수를 핸드오프 값으로(열 150 · 노드 118×26 · 행 40 · 여백 18 — 차 32px가 간선 거터), 간선 화살촉, 헤더 브레드크럼. UI-9는 전폭 단계 레일 + 문서 머리 3단, 이동 줄을 카드 밖으로 |

#### D3 문서와 이력

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-5]] · [[SYNC-UI-002#UI-7]] |
| 구현 | 사이드바 드래그 리사이즈 둘 · 표시된 항목 블록 · 원본 탭 원문/렌더링 · 세 탭 본문 폭 일치 · 버전 A/B 비교 |
| API | [[SYNC-API-001#GET/api/docs/{docId}/diff]] (문맥 줄 수) |
| 화면 | UI-5 · UI-7 |
| 테스트 | 요소 번호 대조 · 탭을 오가도 본문이 좌우로 안 흔들림 · 세 번째 버전을 고르면 A가 밀려남 |
| 선행 | D1 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `1320d99` (code 1) · `check_ui.py` UI-5 34/34 · UI-7 16/16 (전체 11/14, 나머지는 D4·D5) · `check_tokens.py` 어긋남 0 · `validate.py` 위반 0·경고 0 · 테스트 165 · **브라우저 확인**(`dev_preview.py` 시드 — 버전 셋짜리 문서가 필요했다): 유저용·원본 본문이 같은 왼쪽 끝 253px·같은 폭 820px · 손잡이 200→300, 최소 140에서 멈춤, 새로고침 후 유지 · 원문/렌더링 선택 유지 · 표시된 항목 R1·R9·R10, 클릭 시 참조 탭 `#R1` · v3=B v2=A에서 v1을 고르면 A(v2)가 밀려나 v1=A v3=B · diff에 문맥 3줄 · 정한 것: 본문 폭 `--doc-w:820px`(명세는 "같아야 한다"만 말하고 값을 안 정했다 — 디자인 핸드오프 값을 썼다), **원본 탭이 목차·패널 자리를 비워 둔다**(폭만 맞추면 왼쪽 끝이 50px 어긋나 규칙이 막으려는 흔들림이 그대로 남는다), A·B는 고른 순서가 아니라 버전 번호로 정한다, 이력 diff 칸을 반반으로 · **고친 것**: 손잡이 드래그가 stale closure로 마지막 증분만 반영되던 것, `tools/dev_preview.py`가 사용자 생성 전에 `hoyoung.id`를 써서 시드가 죽던 것 · **이슈로 넘긴 것**: #18(`status` 행을 diff 대상으로 고르면 비교가 안 된다) · #19(명세 본문의 html 코드블록이 살아 있는 HTML로 그려져 `data-el`이 새어 나온다) · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `150ae75`~`7eab1bd`, `45fe8e3`~`7373e23`)**: 3단이 화면 높이를 채우고 가운데 열만 스크롤한다. **원본 탭이 목차·패널을 그대로 쥔다**(D3에서 자리만 비워 두던 것을 뒤집었다 — 핸드오프가 유지하는 쪽이고, 그래야 탭 전환에 3단이 안 무너진다). 목차 한 줄 자르기로 `표시된 항목`이 화면 안에 들어왔다. 참조·댓글 패널을 카드로. `pre.code`가 뷰 CSS의 어두운 코드블록 색을 물려받아 원본 탭 글씨가 거의 안 보이던 것을 `pre.mdsrc`로 갈라놓음 |

#### D4 그래프

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-8]] · [[SYNC-UI-002#UI-15]] |
| 구현 함수 | [[SYNC-MS-008#queries.graph_view]](범위 교체) · [[SYNC-MS-008#queries.item_chain]](신설) |
| API | [[SYNC-API-001#GET/api/projects/{code}/graph]] · [[SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/chain]] |
| 화면 | UI-8 · UI-15 |
| 테스트 | 구현 함수의 테스트 관점 전부 · **범위 밖 대상 간선이 미존재 참조로 새지 않음** · 되돌아오는 참조의 상위가 `upstream`으로 적힘 · 빈 단계도 행이 옴 |
| 선행 | D1 |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `f24147a`~`15749ef` (code 1 + spec 1) · `check_ui.py` UI-8 15/15 · UI-15 11/11 (전체 13/15, 나머지는 D5) · `check_tokens.py` 어긋남 0 · `validate.py` 위반 0·경고 0 · 테스트 166 · **브라우저 확인**(`dev_preview` 시드): 전체 문서 27·항목 362·참조 1051 → 플래그 문서 1·항목 3(전부 `▲`) → 승인만 0 · `PRD-001#R10` 호버에 상위 1·하위 2만 남고 385개가 흐려짐 · 되돌아오는 간선이 열 사이로 나가 레인(y=3751)을 지나 열 사이로 들어옴 · `CODE-001#D1` 체인에 빈 단계 다섯 · 칩 클릭으로 다시 그림 · 전체보기가 body에서 0~900을 채우고 z-index 80 · 정한 것: **react-flow를 뺐다**(열 고정 + 간선 넷의 서로 다른 경로라 범용 엔진과 계속 싸운다. main 번들 663KB → 543KB, `@xyflow/react`·`dagre`·`@types/dagre` 제거), 되돌아오는 간선은 열 사이 빈 자리로 빠져나간다(열 안으로 내려가면 그 열 노드를 관통한다), UI-15 칩은 폭 320px에서 자르고 전체는 `title`로 · **명세 구멍 메움**: `SYNC-API-001` Graph.nodes[]에 `has_flag`가 없어 UI-8 3.1을 그릴 수 없었다 · **고친 것**: UI-2 범례 견본(`i.sw`)과 UI-8 범례 견본(`svg.sw`)이 이름이 같아 그래프 범례 선이 회색 네모로 떴다 · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) · **핸드오프 대조**: UI-15 폭 720px · 이 항목 칩을 흰 칩 + 1.5px 테두리로 · 현재 단계 라벨에 주의색 · 칩에서 프로젝트 코드 접두 제거 (커밋 `c0eea3b`~`bfca1a9`) |

#### D5 처리와 설정

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-3]] · `SYNC-UI-002#UI-10` · `SYNC-UI-002#UI-11` · `SYNC-UI-002#UI-12` · [[SYNC-UI-002#UI-13]] · [[SYNC-UI-002#UI-14]] |
| 구현 | 초기화를 다이얼로그로(커밋될 것 박스) · 내 할 일 묶음 순서 고정 · 플래그 확인 버튼 하나(자동 판정 미리 보기) · 설정을 다이얼로그로(카드 넷, 관리 흡수) · 토큰 마지막 사용 |
| API | [[SYNC-API-001#GET/api/me/tokens]] (마지막 사용) |
| 화면 | UI-3 · UI-10 · UI-11 · UI-12 · UI-13 · UI-14 |
| 테스트 | 요소 번호 대조 · 설정을 닫으면 보던 화면 그대로 · 관리가 접힌 채로 열림 · 재구축 확인이 설정 위에 겹쳐 뜸 |
| 선행 | D1 · D6(마지막 사용 컬럼) |
| 완료 | 2026-09-10 · 브랜치 `feat/a-foundation` · 커밋 `39cea75` (code 1) · **`check_ui.py` 15/15 — 화면 열다섯이 전부 일치** · `check_tokens.py` 어긋남 0 · `check_code.py` 114/114 · `validate.py` 위반 0·경고 0 · 테스트 166 · **브라우저 확인**(`dev_preview` 시드): 설정 카드 넷·관리 접힘 · 토큰 발급 → 원문 상자와 `마지막 사용 없음` 행 · 재구축 확인이 설정 위(z 50 → 51)에 겹쳐 뜸 · 닫으면 URL 그대로 `/p/SYNC` · UI-3에 커밋될 것 세 줄 · UI-11 안내가 `수정 동반`으로 3.2와 같은 판정 · 화면 여덟 곳 스크롤·넘침 없음 · 정한 것: 경로 셋(`/projects/new` `/settings` `/settings/admin`)을 지웠다(셋 다 명세가 "별도 경로 없음"이라 한다), 커밋될 것(2.5)은 기존 명세가 발견되면 감춘다(화면이 저장소가 빈지 미리 알 방법이 없어 "발견 = 빈 저장소 아님"으로 읽었다), 코드 입력 대문자 필터는 안 넣었다(규칙 "화면은 검사하지 않는다") · **이슈로 넘긴 것**: #20(토큰 행 `접두어`가 API 명세에만 있고 컬럼이 없다 — 빼고 그렸다) · **화면 확인: 2026-09-11 전부 통과** (DEV-14 일곱째) · **핸드오프 대조(2026-09-10, 커밋 `636656a`~`7f44943`, `c0eea3b`~`7373e23`)**: UI-10 카드 경계를 묶음에서 항목으로(두 줄 카드), UI-11 머리 두 줄 + 확인 액션도 카드 + 폭 880px, UI-12 결정 버튼을 고정 푸터로 + 하위 항목 3열 표, UI-16 인트로 문단과 소제목·문장형 설명. **`.flag`가 검토중 노랑이었다 — UI-001 3.1이 플래그를 경고색으로 못박았다**. `.dot.flag`가 그 필의 여백을 물려받아 6px 점이 16px 알약이던 것도 함께 |

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

#### E 추적 데이터 백업

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 6.1 · [[SYNC-PRD-001#N3]] · [[SYNC-UI-002#UI-14]] 요소 2.4·6 · #16 |
| 구현 함수 | `SYNC-MS-007#pipeline.export_tracking` `SYNC-MS-007#pipeline.import_tracking` `SYNC-MS-007#scheduler.backup_loop` · `SYNC-MS-004#TrackingService.all_flags` `SYNC-MS-004#TrackingService.all_decisions` `SYNC-MS-004#TrackingService.restore_flags` `SYNC-MS-004#TrackingService.restore_decisions` · `SYNC-MS-005#CommentService.all_in_project` `SYNC-MS-005#CommentService.restore` · `SYNC-MS-009#git.last_commit_at` · [[SYNC-MS-002#SpecService.item_pks]](삭제 포함 인자) · [[SYNC-MS-001#ProjectService.repo_status]](마지막 백업) · [[SYNC-MS-007#scheduler.poll_loop]](반복 보호) |
| 구현 | 설정값 `BACKUP_INTERVAL_SECONDS` · `main` lifespan에 백업 태스크(폴링과 **별도 if** — 하나를 끄고 다른 하나를 볼 수 있어야 한다) · `Entry.backup` · DTO 셋(`RestoreFlag`·`RestoreDecision`·`RestoreResult`) · `BackupInvalid` 예외 · 리포지터리 다섯 |
| API | `SYNC-API-001#POST/api/admin/repos/{code}/restore` · `GET /api/admin/repos`에 `backed_up_at`·`backup_stale` |
| 화면 | UI-14 요소 2.4(마지막 백업)·6(백업에서 복원) — **`check_ui.py` 15/15 회복**. 명세를 먼저 고쳐 지금 14/15다 |
| 테스트 | 구현 함수의 테스트 관점 전부 · **내보내고 → 세 표를 비우고 → 복원** 왕복 · 두 번 복원해도 안 늘어남(`skipped`로 간다) · 파일에 댓글 본문·전파 사유·최상위 시각이 없음 · 두 번 내보내도 커밋이 하나 · 백업 커밋이 `changed_files`에 안 잡힘 · 재구축을 안 하고 복원하면 전부 `dropped`이고 예외는 없음 |
| 선행 | D5 |
| 완료 | 2026-09-11 · 브랜치 `card/E-backup` · 커밋 `c8f2749`~`e715423` (spec 6 + code 1) · 테스트 199 · `check_code.py` 131/131 · **`check_ui.py` 15/15 회복** · `validate.py` 위반 0·경고 0 · `check_dom.py` 경고 0 · `tsc`·`build` 통과 · **실물 확인**(도커 8000): `backup/tracking.json` 9,765바이트(341줄) — 플래그 2·전파결정 18·댓글 0 · **두 번 내보내도 같은 커밋**(`9c4abf0e`) · 복원은 20건 전부 건너뜀(`skipped=20`, 새로 넣은 것 0, 버린 것 0) · 삭제된 원인 항목(`SYNC-MS-002#SpecService.change_status`)이 자연키로 제대로 실림 · 정한 것: 댓글 자연키를 `{작성시각}|{작성자}` 합성키로(배열 index는 가운데 한 줄이 끼면 뒤 행의 부모가 전부 밀린다), 플래그 멱등 열쇠에 `raised_at`을 넣음(앞 넷만으로는 해제 후 재발한 플래그를 못 가른다) · **고친 것**: `git.last_commit_at`이 `HEAD`로도 떨어진다 — `commit_push`가 토큰 URL로 밀어 `refs/remotes/origin/*`이 안 따라온다 · `scheduler.poll_loop`에 반복 전체를 감싸는 예외 처리(테스트 관점은 "안 멈춘다"인데 `catch_up` 안쪽만 잡고 있어 우연히 성립하던 것) · **화면 확인: 2026-09-11 통과**(`dev_preview` 시드, Playwright로 직접 조작) — 동기화 칸에 `최신 / 백업 12분 전` · 백업 전에는 `백업 없음`(흐림) · `복원` 버튼 → 확인 다이얼로그(설정 z50 위 z51) → 결과 `이미 있어서 건너뜀 7`(멱등) · 토스트 · 페이지 스크롤 없음 · **화면에서 고친 것 둘**: 열을 여섯으로 늘리니 620px에서 머리글이 전부 두 줄로 꺾여(34px→55px) 동기화 칸 안으로 합쳤다 · 설정 위 확인 다이얼로그가 좌우 50px씩 잘려 있던 것(#43, D5부터 있던 버그)을 `.dialog`의 가운데 정렬에서 `transform`을 걷어 고쳤다 — 커밋 `cc5ebe2` |

**왜 카드인가.** `DEV-15`는 "**버그**를 고칠 때는 이슈가 단위이고 카드를 안 건드린다"고 적는다. #16은 버그가 아니라 인프라 6.1이 설계해 놓고 구현을 안 한 기능이다. 함수 열둘·엔드포인트 하나·화면 요소 둘이 걸리므로 `DEV-14` 일곱 조건을 거치는 카드가 맞다.

**왜 지금인가.** 2026-09-11에 실물에서 전파결정 39건을 잃었다(#38·#39). 그 백업이 있었으면 복구할 수 있었다 — 인프라 6.1이 "복구 불가 항목이 셋 있다. 그래서 이 셋을 저장소에 함께 커밋한다"고 적어 둔 바로 그 상황이다.

---

#### F 저장소를 앱이 만든다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UC-001#UC-A1]] 기본 흐름 3 · [[SYNC-API-002#init_project]] · [[SYNC-UI-002#UI-3]] |
| 구현 함수 | [[SYNC-MS-009#github.create_repo]](신설) · [[SYNC-MS-001#ProjectService.init_project]](인자 추가) |
| 구현 | `init_project`에 `create_repo: bool = False` 인자. 참이고 저장소가 없으면 등록자의 GitHub 토큰으로 **공개 저장소**를 만들고 이어서 지금 흐름대로 간다 |
| API | [[SYNC-API-001#POST/api/projects]]에 `create_repo` · [[SYNC-API-002#init_project]] 스키마에 `create_repo` |
| 화면 | UI-3에 체크박스 하나 — 「없으면 새로 만든다」 |
| 테스트 | 없는 저장소 + `create_repo=false` → `push-failed`(지금 동작 유지) · 없는 저장소 + `true` → 만들어지고 골격 커밋까지 · 이미 있는 저장소 + `true` → **만들지 않고 그대로 쓴다** · 이름이 GitHub 규칙에 안 맞으면 `repo-create-failed` · 만든 뒤 등록이 실패해도 **저장소는 남는다** |
| 선행 | C |
| 완료 | 2026-09-14 · 브랜치 `card/F-repo-create` · 테스트 211 · `check_ui.py` 15/15 회복 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · **실물 확인**(도커 8000, MCP 한 번 호출): 없던 `HoyoungParkme/cardf-demo`가 **공개·기본 브랜치 main**으로 생기고 이어서 `chore(CF): init syncdoc` 골격 커밋까지 — `docs/specs/` 11단계 + `STD` + `_templates` + `assets` + README · **가드 셋 실측**: ① `create_repo` 생략 + 없는 저장소 → `push-failed`(지금 동작 유지), 저장소 안 생김 ② 이미 있는 저장소 + `create_repo=true` → 저장소 수 23 → 23, 만들지 않고 `repository-already-registered`로 막힘 ③ 코드에 숫자를 넣으면 `project-code-invalid`가 먼저 걸려 저장소를 만들기 전에 멈춘다 · 정한 것: `auto_init=false`(GitHub이 README를 만들면 "빈 저장소" 경로가 아니라 "내용 있는 저장소" 경로를 타 흐름이 갈린다) · `_split_remote`가 https·ssh·끝 슬래시·`.git`을 다 받는다 |

**왜 카드인가.** 새 기능이다. 함수 하나가 늘고 MCP 도구·REST·화면의 입력이 함께 바뀐다. `DEV-15`의 "버그는 이슈, 기능은 카드"에서 뒤쪽이다.

**왜 지금인가.** 지금은 프로젝트 하나를 시작하는 데 **저장소 만들기 → 웹 등록 → 토큰 발급 → 클라이언트 설정** 네 단계를 사람이 손으로 밟는다. 실제로 오늘 세 프로젝트(`BBS`·`BBT`·`INS`)를 만들며 매번 반복했다. 토큰 발급은 닭과 달걀이라 첫 1회 웹 방문이 남지만, **그 뒤로는 "프로젝트 하나 만들어줘" 한마디로 끝나야 한다.**

**정한 것 넷.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 언제 만드나 | **`create_repo=true`일 때만** | 기본값을 참으로 두면 주소 오타가 조용히 새 저장소를 만든다. 지금은 그럴 때 `push-failed`가 나서 오타를 알 수 있다 |
| 공개 여부 | **항상 공개** | v1은 공개 저장소만 지원한다 — 폴링 `fetch`가 토큰 없이 돈다([[SYNC-MS-009#git.fetch]]). 비공개로 만들면 등록은 되고 **폴링이 죽는다.** 선택지를 아예 안 둬서 그 함정을 없앤다 |
| 만든 뒤 실패하면 | **저장소는 남기고 알린다** | DB·작업 사본은 지금처럼 되돌리되 GitHub 저장소는 안 지운다. 앱이 남의 저장소를 지우는 권한을 쓰는 것이 위험하고, 그 사이 사람이 넣은 것까지 사라진다. 사용자가 지우거나 `import_existing`으로 다시 등록하면 된다 |
| 첫 토큰 발급 | **이 카드 밖** | MCP를 쓰려면 토큰이 있어야 하고 토큰은 웹에서 발급한다. 닭과 달걀이라 첫 1회 웹 방문은 남는다 |

#### G 붙이는 법을 앱 안에

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-16]] 6·6.1·6.2·6.3 · [[SYNC-UI-001#UI-16]] · [[SYNC-INFRA-001]] 5장 「MCP 인증이 다른 이유」 |
| 구현 함수 | 없음 — 화면만. 백엔드 변경 없음 |
| 화면 | UI-16에 절 하나 — 「에이전트를 붙이는 법」 표(6) + `claude mcp add` 명령 상자(6.2, 주소 채움) + 그 다음(6.3) + 앱 밖 화면 그림 셋(6.4~6.6) |
| 테스트 | `check_ui.py` UI-16 요소 17/17 · 명령 상자의 주소가 지금 화면의 origin과 같다 · 그림 셋이 200으로 서빙된다 |
| 선행 | F |
| 완료 | 2026-09-14 · 브랜치 `card/G-howto-connect` · 커밋 `26e501f`(spec) `4e193d8`(code) · PR #62 · `check_ui.py` UI-16 **14/14**, 전체 15/15 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 백엔드 무변경(213) · **실물 확인**(터널, 1875px): 절 4행 · 명령에 `https://…trycloudflare.com/mcp` 채워짐 · 토큰 자리표시 · 다이얼로그 660px · **걸린 것 하나**: import를 화면 docstring 앞에 두었더니 `check_ui`가 UI-16을 "컴포넌트 없음"으로 빠뜨리면서 전체가 14/14로 통과해 버렸다 — 안 본 화면이 통과로 세어진 것(STD-004 4장). docstring 뒤로 옮겨 15/15 · **추가(PR #63, 커밋 `e3bbfdf` spec · `b0773bc` code)**: 앱 밖 화면 그림 셋(6.4~6.6) — 발급 순간은 실제 캡처(원문 가림, 토큰 폐기), 터미널 둘은 실제 출력을 렌더한 것. 셋 67KB. `check_ui` UI-16 17/17 · `/howto/*.png` 셋 200 |

**왜 카드인가.** 새 절이 화면에 생긴다. 요소 번호가 넷 늘고 `check_ui`의 집합이 바뀐다. 버그가 아니라 기능이다(DEV-15).

**왜 지금인가.** 붙이는 절차를 설명서로 앱 밖(claude.ai 아티팩트)에 만들었더니, 다른 컴퓨터·다른 프로젝트에서 붙이려던 사람이 그걸 못 보고 "syncdoc 명령이 없다"에서 멈췄다. 가장 자주 걸리는 한 줄 — **MCP 서버는 세션 시작 때 읽히니 새로 켜야 한다** — 이 앱 안에 있어야 한다. 앱 화면 캡처는 넣지 않는다 — 한 클릭 거리고 바뀌면 낡는다. **앱 밖 화면 셋**(토큰이 한 번만 보이는 순간·터미널의 add·list)은 넣는다 — 앱 안에서 볼 수 없는 것이라서. 처음엔 셋 다 뺐다가 사용자가 캡처를 어디 뒀냐고 물어 상의해서 정했다.

**정한 것 둘.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 주소를 어디서 얻나 | **지금 화면의 origin** | UI-13 클라이언트 설정(8.1)이 이미 그렇게 한다. 사람이 옮겨 적으면 터널 주소를 틀린다 |
| 토큰도 채우나 | **안 채운다** | 원문은 발급 화면에서 한 번만 보이고 서버도 다시 못 준다(해시만 있다). 자리표시 `syncdoc_pat_…` |
| 캡처는 | **앱 밖 화면 3장만** | 앱 화면은 한 클릭 거리고 바뀌면 낡는다. 터미널·발급 순간은 앱 안에서 못 본다. 약 100KB, `frontend/public/howto/` |

#### H 프로젝트를 싱크독에서 해제한다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UC-001#UC-H17]] · [[SYNC-UI-002#UI-14]] 7·4.3 · [[SYNC-API-001#DELETE/api/projects/{code}]] |
| 구현 함수 | 없음 — 화면만. `DELETE /api/projects/{code}`와 [[SYNC-MS-001#ProjectService.delete_project]]는 카드 A부터 있었다 |
| 화면 | UI-14 표의 행마다 셋째 버튼 「해제」(7, 위험색 외곽선) + 확인 다이얼로그(4)에 해제 안내(4.3) |
| 테스트 | `check_ui.py` UI-14 요소 17/17 · 취소하면 아무 일 없음 · 해제 후 UI-2에 행이 없고 GitHub 저장소는 그대로 |
| 선행 | G |
| 완료 | 2026-09-14 · 브랜치 `card/H-project-delete` · 커밋 `d86959d`(spec) `a87e385`(code) · PR #64 · `check_ui.py` UI-14 **17/17**, 전체 15/15 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 백엔드 무변경 · **실물 확인**(터널): 네 행 모두 `재구축 · 복원 · 해제` · INS 해제 → 머리 「INS 싱크독에서 해제」 · 4.3에 그 행의 백업 유무 그대로(「백업이 없습니다」) · 취소로 닫힘. 실제 해제는 안 눌렀다 — 남은 넷이 다 실제 프로젝트고 DELETE는 카드 A 테스트가 덮는다 · **걸린 것**: 유스케이스를 `UC-H15`로 잡았다가 `item.duplicate`(내 할 일 조회가 H15). 통째 치환으로 기존 참조까지 건드려 다섯 파일을 되돌리고 `UC-H17`로 다시 넣었다 — 기존 참조 변경 0건 |

**왜 카드인가.** 새 동작이 화면에 생긴다. 유스케이스 하나(UC-H17)와 요소 둘이 늘고 `check_ui`의 집합이 바뀐다. 버그가 아니라 기능이다(DEV-15).

**왜 지금인가.** 시험으로 만든 프로젝트 넷(BBS·BBT·CF·TALK)을 치우려는데 화면이 없었다. API는 카드 A부터 있었는데 누를 데가 없어 브라우저 콘솔에서 `fetch(…, {method:'DELETE'})`로 지웠다. 사람이 하는 일에 API만 있는 것은 구멍이다.

**정한 것 셋** — 자리는 셋을 그려 놓고 상의해 골랐다(상세 아래 위험 구역 · 관리 표 · 목록 행 호버).

| 질문 | 결정 | 이유 |
|---|---|---|
| 어디에 두나 | **UI-14 관리 표의 셋째 버튼** | 표에 이미 프로젝트별 재구축·복원이 있다. 셋 다 「이 저장소를 싱크독이 어떻게 들고 있나」를 만지는 일이라 한곳이 맞고, 새 화면이 없어 가장 싸다. 「위험한 동작이 있습니다」 머리글 아래라 뜻도 맞는다 |
| GitHub 저장소는 | **손대지 않는다** | 명세 원본은 저장소다(INFRA C2). 앱이 남의 저장소를 지우는 권한을 쓰지 않는다 — 카드 F의 「만든 뒤 실패해도 저장소는 남긴다」와 같은 선 |
| 끝나면 | **UI-2로** | 설정은 어느 화면 위에서든 뜨므로 지운 프로젝트의 상세 위에서 눌렀을 수 있다 |

#### I 프로젝트를 「[코드] 이름」으로 적는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002]] 1.6 프로젝트 표기 · 여덟 자리(UI-2·UI-4·UI-5·UI-7·UI-8·UI-9·UI-14) |
| 구현 함수 | 없음 — 화면만. 공통 조각 `ProjName`(`components/ui.tsx`) 하나를 여덟 자리가 쓴다(DEV-17 「두 화면 이상이 같은 요소를 쓸 때만 components/」) |
| 화면 | 코드를 `[SYNC]`처럼 대괄호 친 고정폭·굵게 + 이름. UI-14 표에는 이름이 없던 것을 붙인다 |
| 테스트 | `check_ui.py` 15/15 그대로(요소 번호는 안 바뀐다) · 여덟 자리 전부 `[코드] 이름` — 한 곳만 다르면 어휘가 아니라 실수다 |
| 선행 | H |
| 완료 | 2026-09-14 · 브랜치 `card/I-code-name` · 커밋 `3af52a0`(spec) `6286968`(code) · PR #65 · `check_ui.py` 15/15 · `check_code.py` 132/132 · `validate.py` 위반 0·경고 0 · 백엔드 213 · ruff · `tsc`·`build` 통과 · **실물 확인**(터널, 새로 불러서): 여덟 자리 전부 — UI-2 `[SYNC] 싱크독` · UI-4 `[INS] 보험청구심사 어시스턴트` · UI-5 문서 바·킥커 · UI-7 · UI-8 · UI-9 `← [INS] …` · UI-14 네 행 · **걸린 것**: 관리 표 데이터(RepoStatus)에 이름이 없었다 — DTO·pydantic·프런트 타입·API-001·MS-001에 `name`을 더했다. 처음엔 배포 전 번들이 탭에 남아 옛 화면을 읽었다 — 새로 불러서 다시 봤다 |

**왜 카드인가.** 여덟 화면의 표기가 한꺼번에 바뀌고 공통 조각이 하나 생긴다. 버그가 아니라 어휘 결정이다(DEV-15).

**왜 지금인가.** 목록에서 `INS 보험청구심사 어시스턴트`를 보고 어디까지가 코드인지 한 번 읽어야 알았다. 문서 ID는 `INS-UC-001`처럼 코드가 접두로 딱 갈리는데 프로젝트 이름만 안 갈렸다. 사용자가 제안했고, 네 자리 전후를 그려 보고 정했다.

**정한 것 둘.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 대괄호를 어디까지 | **코드에만, 고정폭으로** | 이름까지 감싸면 뱃지가 된다. 코드가 문서 ID의 접두라는 것만 보이면 된다 |
| 코드만 있는 자리 | **대괄호 안 친다** | 재구축 결과의 `SYNC · 방금`처럼 이름이 없으면 가를 게 없다 |

#### J 11단계 표에 문서 구성을 붙인다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002#UI-16]] 3.5·3.4 · [[SYNC-STD-001]] 2장(서브타입) · [[SYNC-STD-003]] 결정(여섯이 실질) |
| 구현 함수 | 없음 — 화면만 |
| 화면 | UI-16 11단계 표의 행마다 둘째 줄(3.5): 문서가 몇 개고 왜 그 수인지, 선택인지. 주의(3.4)에 실질/선택 한 문장 |
| 테스트 | `check_ui.py` UI-16 요소 18/18 · 열한 행 전부 둘째 줄이 있다 |
| 선행 | I |
| 완료 | 2026-09-14 · 브랜치 `card/J-howto-stages` · 커밋 `84d1a0f`(spec) `b098346`(code) · PR #66 · `check_ui.py` UI-16 **18/18**, 전체 15/15 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 백엔드 무변경 · **실물 확인**(터널, 새로 불러서): 열한 행 전부 둘째 줄, DOM 「문서 셋…」 · UI 「문서 둘…」 · API 「문서 둘…」 · MS 「문서 여러 개…」 · 주의에 실질/선택 문장 · **덤으로 고친 것**: STD-001 2.7 머리 "(문서 셋)" → "(문서 둘)" — 서브타입이 둘인데 머리만 셋이었다 · **추가(PR #67, `01fbcdf` spec · `1a15ae8` code)**: 둘째 줄을 한 문단으로 썼더니 세 줄로 접혀 "가시성이 없다"는 말을 들었다. 수는 라벨(`문서 3`), 문서는 줄마다 하나, 선택은 태그로 세우고 글자를 13px muted로 올렸다 |

**왜 카드인가.** 요소가 하나 늘고 표의 내용이 바뀐다. 기능이다(DEV-15).

**왜 지금인가.** 목록 화면에서 `SYNC-DOM-001·002·003`을 보고 "도메인은 왜 셋이냐, 화면·API는 왜 둘이냐"는 물음이 나왔다. 표는 "도메인·클래스·데이터"라고만 하고 이유를 안 말했다. 근거(STD-001 2장 서브타입, STD-003 실질/선택 결정)는 다 있는데 사람이 보는 자리에 없었다.

**정한 것 둘.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 어디에 적나 | **행 안 둘째 줄** | 열을 하나 더 두면 660px에서 표가 깨진다. 둘째 줄은 흐린 색·작은 글자라 첫 줄의 이름을 가리지 않는다 |
| 어디까지 적나 | **수와 이유, 선택 여부** | 서브타입의 필수 절까지 적으면 STD-001을 베끼는 것이 된다. 이유 한 줄이면 "왜 셋"이 풀린다 |

#### K 그림 전체보기

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-UI-002]] 1.7 · [[SYNC-UI-002#UI-5]] 7.5·7.6 · [[SYNC-UI-002#UI-9]] 4 · [[SYNC-UI-001]] 3.3 겹침 순서 |
| 구현 함수 | 없음 — 화면만. 공통 조각 `DiagramFull`(`components/`) 하나를 UI-5·UI-9가 쓴다(DEV-17) |
| 화면 | 유저용 본문 안 그림마다 「전체보기」 버튼(7.5) → 화면 전체 층(7.6): 이름 · －100%＋ · 닫기, 원본 SVG 복제 |
| 테스트 | `check_ui.py` UI-5 요소 36/36 · SEQ-001 흐름 그림에서 전체보기 → 층이 뜨고 svg가 있다 · Esc로 닫힌다 · 본문 쪽 그림은 그대로 |
| 선행 | J |
| 완료 | 2026-09-15 · 브랜치 `card/K-diagram-full` · 커밋 `ce7121f`(spec) `12cc743`(code) · PR #68 · `check_ui.py` UI-5 **36/36** · UI-9 10/10 · 전체 15/15 · `check_tokens` 0 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 백엔드 무변경 · **실물 확인**(터널, SYNC-SEQ-001): 그림마다 버튼, 첫 버튼 → 층에 원본보다 큰 svg, ＋로 125%, Esc로 닫힘, 본문 svg 그대로 · **걸린 것**: 7.6을 요소 표에만 적고 배치 HTML에 안 넣어 `check_ui`가 「코드에만 7.6」 — 배치에 층 블록을 넣었다 · 카드 I가 빠뜨린 UI-9 킥커도 여기서 「[코드] 이름」으로 · **실물에서 두 번 더 고침**(`9872388` spec · `7b62faf`·`e41297d` code): SEQ-1이 3263px라 100%로 열리며 가로 스크롤부터 만나 **열릴 때 폭에 맞춤(57%)**, 이름이 앞선 형제 「생명선 표」로 잡혀 **문서 순서로 앞선 마지막 헤딩 + 절의 h2**(「SEQ-1 … · 흐름」)로 |

**왜 카드인가.** 요소 둘과 공통 조각이 생긴다. 기능이다(DEV-15).

**왜 지금인가.** SEQ-001 흐름 그림이 본문 폭 안에서 스물몇 줄 시퀀스라 글자가 안 보였다. 본문을 열까지 넓혔는데도(#61) 그림은 그 안에서 또 작다. UI-8 그래프에는 전체보기가 있는데 본문 그림에는 없었다.

**정한 것 셋.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 어느 그림에 | **유저용 본문 안 전부** — mermaid·UC 패키지·SEQ | 종류를 가리면 "왜 이건 안 되나"가 생긴다. svg가 있는 상자면 다 붙인다 |
| 원본을 옮기나 복제하나 | **복제** | 옮기면 닫을 때 제자리에 돌려놔야 하고 mermaid가 붙인 id가 겹친다. 복제는 본문을 안 건드린다 |
| SEQ의 자기 확대 바는 | **그대로** | 그건 본문 안에서 조금 키우는 것. 전체보기는 화면을 통째로 쓰는 것이라 다른 일이다 |

#### L 내 할 일을 프로젝트로 가른다

| 항목 | 내용 |
|---|---|
| 근거 | `SYNC-UI-002#UI-10` 10·10.1·11·11.1 · `SYNC-UC-001#UC-H15` |
| 구현 함수 | 없음 — 화면만. `/api/todo`는 그대로고 코드는 문서 ID 접두에서, 이름은 셸이 든 프로젝트 목록에서 얻는다 |
| 화면 | UI-10에 프로젝트 칩 줄(10)과 프로젝트 묶음(11). 프로젝트가 둘 이상일 때만 |
| 테스트 | `check_ui.py` UI-10 요소 21/21 · 프로젝트 넷 → 칩 다섯(전체 포함)·묶음 넷, 가장 오래된 일이 있는 묶음이 위 · 칩을 눌러도 부제 건수 그대로 · 프로젝트 하나면 지금과 같은 화면 |
| 선행 | K |
| 완료 | 2026-09-15 · 브랜치 `card/L-todo-by-project` · 커밋 `ae362f4`(spec) `c1954ed`(code) · PR #69 · `check_ui.py` UI-10 **21/21**, 전체 15/15 · `check_tokens` 0 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · 백엔드 무변경 · **실물 확인**(터널): 지금 계정들엔 할 일이 한 프로젝트에만 있어 `/api/todo`를 표본 응답(SYNC 9일·TBL 6일·INS 3일/1일/반나절)으로 바꿔 그렸다 — 칩 `전체 5 · [SYNC] 1 · [TBL] 1 · [INS] 3`, 묶음 순서 SYNC→TBL→INS(가장 오래된 일 순, 담당 미지정도 순서에 든다), `[INS]` 칩 → INS 묶음만 남고 부제는 `5건` 그대로 · 실제 계정(한 프로젝트)에서는 칩·머리 없이 예전 화면 · **걸린 것**: `ItemRef.doc_id`가 null일 수 있어(미존재 참조) `raw_target` 접두로 대신 |

**왜 카드인가.** 요소 넷이 늘고 화면 구조가 바뀐다. 기능이다(DEV-15).

**왜 지금인가.** 프로젝트가 넷(SYNC·INS·TBL·JSD)이 되자 내 할 일이 한 줄에 섞였다. 카드의 `SYNC-PRD-001#R1`에 코드가 있어도 훑어서는 안 갈린다. 사용자가 "프로젝트별로 구분이 안 된다"고 했고, 칩 필터와 프로젝트 묶음 둘 중 하나를 물었더니 **둘 다** 골랐다.

**정한 것 셋.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 묶음 순서 | **가장 오래된 일이 있는 프로젝트가 위** | 이 화면의 원칙이 경과일순이다. 프로젝트로 갈라도 그 원칙이 묶음 사이에 살아야 한다 |
| 프로젝트 하나일 때 | **칩도 머리도 안 그린다** | 2~3명 프로젝트 하나짜리가 이 도구의 기본 사용자다. 그 화면이 바뀌면 안 된다 |
| 칩이 건수를 바꾸나 | **안 바꾼다** | 거른 건 화면이지 할 일이 아니다. 배지와 부제는 늘 전체 |

---

#### M DOM 셋의 순서와 문서 하나의 작업 단위

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 1.8·2.6·3장 · [[SYNC-PRD-001#R6]] · [[SYNC-UC-001#UC-A6]] 3·3a·8 · [[SYNC-API-002#create_document]] · [[SYNC-API-002#update_document]] · [[SYNC-SEQ-001#SEQ-19]] 3a · [[SYNC-RFQ-001]] 2장 |
| 구현 함수 | [[SYNC-MS-002#SpecService.precondition]] · [[SYNC-MS-002#SpecService.validate]] 1(`frontmatter.title.subtype`) · [[SYNC-MS-007#pipeline.save_pipeline]] 3a·15(`next_step`) · [[SYNC-MS-009#git.init_specs]] README · `mcp/tools` 도구 설명(API-002 전사) |
| 화면 | UI-16 3.4·3.5 — DOM 행 줄마다 언제 쓰는지, 주의에 예외 하나 |
| 테스트 | `precondition` 여섯 갈래(API 없이 클래스 → 거부 · API 초안 하나면 통과 · 클래스 없이 ERD → 거부 · 클래스 초안이면 통과 · 도메인 모델은 늘 통과 · DOM 아니면 늘 통과) · `validate` DOM 제목에 키워드 없음 → `frontmatter.title.subtype` · e2e: API 없이 클래스 명세 → `precondition-unmet {requires, have}`, API 만든 뒤 통과, 결과에 `next_step` · README에 순서·작업 단위 문장 · 기존 명세 전부 여전히 위반 0 · `check_ui.py` UI-16 |
| 선행 | L |
| 완료 | 2026-09-15 · 브랜치 `card/M-dom-order` · 커밋 `9506137`(spec) `dfaf411`(code) · PR #71 · pytest **215 passed** · `check_code` 133/133 · `check_dom` 경고 0 · `check_ui` 15/15(UI-16 18/18) · `check_tokens` 0 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · **실물 확인**(터널·MCP 토큰): `tools/list`의 `create_document` 설명에 `precondition-unmet`·`next_step` 있음 · API 문서가 없는 VA에 「클래스 명세」 → `precondition-unmet {requires: "API 문서(REST 또는 MCP) — …", have: [VA-DOM-001·002·003]}`, 문서 수 8 그대로(부작용 없음) · 제목 「데이터」 → `frontmatter.title.subtype` · UI-16 DOM 행에 「여기서 · 8 API 뒤에 돌아와서 · 클래스 명세 뒤에」, 3.4에 예외 한 줄 · 머지 뒤 폴링이 명세 13개를 받아 10개를 `검토중`으로 내렸고 전파 미결정 9건은 「안 붙임」, 13개 재승인 |

**왜 카드인가.** 저장을 막는 조건이 하나 늘고(`precondition-unmet`), 위반 규칙이 하나 늘고, 응답 필드가 하나 는다. 기능이다(DEV-15).

**왜 지금인가.** 싱크독으로 다른 프로젝트(VA)를 쓰던 중 에이전트가 DOM 단계에서 **도메인 모델·클래스 명세·ERD 셋을 한 대화에 한꺼번에** 만들었다. 사용자는 싱크독을 만들 때 "도메인 모델을 쓰고 화면·API로 갔다가 돌아와서 클래스 명세와 ERD를 썼다"고 기억했고, 데이터가 맞다 — `SYNC-DOM-002`의 `upstream`이 `API-001`·`API-002`다. 그런데 RFQ 2장·STD-001 2.6·저장소 README는 셋을 한 칸에 「문서 셋」으로만 적어 에이전트가 예측으로 셋을 채우는 게 당연했다. 어디에도 "문서 하나 쓰고 멈춰라"가 없었다.

**정한 것 넷.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 물리적으로 단계를 나누나 | **안 나눈다.** 타입·ID 그대로, 규약 + 서버 검사 | 나누면 다섯 프로젝트 DOM 문서 12개의 ID가 바뀌고 들어오는 참조 60건이 끊긴다. 규약과 `precondition-unmet`으로도 "예측으로 셋"은 막힌다 |
| 선행조건을 무엇으로 판정하나 | **존재.** 상태는 안 본다 | PRD R6 "상태는 게이트가 아니다"를 지킨다. 막는 건 순서지 승인이 아니다 |
| ERD의 선행 | **클래스 명세가 있어야** (싱크독 방식) | 사용자 결정. JSD·TBL은 클래스 명세 없이 ERD를 먼저 썼는데, 그건 이미 있는 문서라 안 건드린다 — 앞으로는 클래스 명세가 먼저다 |
| 단계 사이 멈춤을 서버가 막나 | **안 막는다.** 규약(1.8) + 응답 `next_step` | "초안이 있으면 새 문서 거부"는 R6과 정면 충돌이고 직접 push는 못 막는다. 대신 응답이 매번 말한다 |

**제목 키워드 검사는 DOM만.** UI·API도 서브타입을 제목으로 가르지만 기존 문서에 키워드 없는 제목(`JSD-API-002 에이전트 도구`)이 있어 지금 넣으면 재구축이 위반을 만든다. 따로 정한다.

---

#### N 이력 없는 문서를 지운다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#N3]] 예외 · [[SYNC-UC-001#UC-A7]] · [[SYNC-UC-001#UC-H18]] · [[SYNC-API-001#DELETE/api/docs/{docId}]] · [[SYNC-API-002#delete_document]] · [[SYNC-SEQ-001#SEQ-22]] · [[SYNC-STD-001]] 1.1 · [[SYNC-DOM-003]] 설계 규칙 |
| 구현 함수 | [[SYNC-MS-007#pipeline.trash_document]](카드 R이 `delete_document`를 대체) · [[SYNC-MS-007#pipeline.process_commit]] 4(행 없는 D 건너뜀) · [[SYNC-MS-002#SpecService.delete_document]] · [[SYNC-MS-002#SpecService.status_change_count]] · [[SYNC-MS-003#ReferenceService.inbound_of_document]] · `SYNC-MS-004#TrackingService.history_of_document` · `SYNC-MS-005#CommentService.count` · [[SYNC-MS-009#git.commit_push]] `delete` |
| 화면 | UI-5 12 문서 삭제(초안만) · 13 확인 다이얼로그(13.1~13.4) |
| 테스트 | 문지기 넷 각각 한 번씩 걸림(`document-has-history`에 값) · confirm 없이 → needs-confirm에 `version_count` · confirm → 원격 파일 사라짐 + 커밋 메시지 + 행 다섯 종류 0 · 다른 문서 참조·항목 그대로 · 지운 번호 재발급 · 폴링이 삭제 커밋 D를 건너뛰고 `last_processed_commit` 전진 · 웹 DELETE 204/409 · MCP 도구 두 번 호출 · `check_ui.py` UI-5 |
| 선행 | M |
| 완료 | 2026-09-15 · 브랜치 `card/N-delete-document` · 커밋 `bd80906`·`26a7aae`(spec) `21de246`(code) · PR #73 · pytest **219 passed** · `check_code` 139/139 · `check_dom` 경고 0 · `check_ui` 15/15(UI-5 42/42) · `check_tokens` 0 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · **실물 확인**(터널·MCP 토큰·HoyoungParkme 세션): `tools/list`에 `delete_document` · MCP `delete_document(VA-DOM-003)` → `document-has-history {status: draft, inbound_refs: 13건(VA-DOM-001·VA-DOM-002·VA-DOM-002#AnalysisJob…), comments 0, flags 0, decisions 0, status_changes 0}`, 문서 수 3 그대로 · UI-5 `VA-DOM-003`에 「문서 삭제」(12) → 확인(13.1 「ERD·DD — 영상 분석 에이전트 · 버전 1개 · … 되돌릴 수 없습니다」) → 삭제(13.3) → 409 → 13.2에 걸리는 것 13건이 링크로, 13.3 비활성 · 머지 뒤 폴링이 명세 17개를 받아 검토중으로 내렸고 전파 미결정 7건은 「안 붙임」, 15개 재승인 · **걸린 것**: `Version` DTO에 id가 없어 `history_of_document`가 버전 ID를 서브쿼리로 센다(`26a7aae`) · 삭제 커밋의 `D`를 폴링이 `mark_deleted`로 보내 not-found가 나던 것을 「행 없는 D는 건너뜀」으로 |

**왜 카드인가.** PRD N3의 규칙에 예외가 생기고, 엔드포인트·MCP 도구·에러 둘·함수 일곱이 는다. 기능이다(DEV-15).

**왜 지금인가.** 카드 M의 원인이 된 VA 프로젝트에서 사용자가 에이전트에게 "DOM-002·003을 날려줘"라고 했더니, 에이전트가 싱크독에는 문서를 지우는 길이 없다고 답했다. 맞는 답이었다 — PRD N3·DOM-003이 "문서는 삭제하지 않는다"라고 못 박았고, 파일을 지워 push하면 `file.deleted` 규약 오류로 영원히 남는다. 그 결정은 "쓰다가 폐기된 문서"를 위한 것이지 "예측으로 잘못 만든 초안"을 생각한 것이 아니었다.

**정한 것 넷.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 무엇을 지울 수 있나 | **이력 없는 초안만** — 초안 · 들어오는 참조 0 · 댓글 0 · 플래그 0(해결된 것 포함) · 전파 결정 0 · 상태 변경 0 | N3의 뜻("이력은 남긴다")을 정확히 지키면서 쓰레기만 거른다. FK를 물고 있는 표가 곧 이력이다 |
| 누가 지우나 | **웹 + MCP 둘 다.** MCP는 항목 삭제처럼 두 번 호출(needs-confirm → confirm) | 사용자 흐름이 "에이전트에게 말한다"라 웹 버튼만 있으면 오늘처럼 막힌다. 사용자 결정 |
| 지운 번호 | **다시 쓰인다** | 되살아날 참조가 없다. 번호를 영구 예약하려면 삭제된 문서 표가 필요한데, 그러면 "행째 지운다"가 아니다 |
| 폴링이 삭제 커밋을 어떻게 보나 | **행 없는 D는 건너뛴다** | 앱이 지운 커밋에는 해시를 적어 둘 행이 없다. `mark_deleted`로 가면 not-found로 그 커밋이 영영 처리 실패가 되고 저장소가 멈춘다 |

---

#### O 저장이 끊어진 참조를 푼다

| 항목 | 내용 |
|---|---|
| 근거 | `SYNC-UC-001#UC-H12` 3 · [[SYNC-SEQ-001#SEQ-1]] 10b · #70 |
| 구현 함수 | `SYNC-MS-004#TrackingService.release_broken` · [[SYNC-MS-007#pipeline.save_pipeline]] 10b |
| 화면 | 없음 — 저장이 푼다. UI-10 끊어진 참조 묶음에서 그 행이 사라진다 |
| 테스트 | Q1 삭제 → R1 broken_ref → R1의 참조를 지워 저장 → `resolved_with_edit=True`, 확인자 = 저장시킨 사람 · 참조를 둔 채 저장 → 남음 · 원인 이름은 삭제 항목 포함(`describe_items`) |
| 선행 | N |
| 완료 | 2026-09-16 · 브랜치 `card/O-release-broken` · 커밋 `8dd6d7c`(spec) `code(O)`(code) · PR #77 · pytest **220 passed** · `check_code` 140/140 · `check_dom` 0 · `check_ui` 15/15 · `validate.py` 0·0 · **실물 확인**(2026-09-16, 카드 R이 만든 진짜 끊어짐으로): 카드 R이 `MS-007#pipeline.delete_document` 항목을 없애자 그것을 가리키던 `MS-009#git.commit_push`·`CODE-001#N`에 `끊어진 참조`가 붙었고(#120·#121), 두 참조를 `trash_document`로 고쳐 push(#85)하니 폴링이 받은 저장에서 **둘 다 저절로 풀렸다** — `resolved_with_edit=true`, 확인자는 저장시킨 사람. 사람이 누른 버튼은 없다. 이슈 #70 닫힘 |

**왜 카드인가.** 파이프라인 단계가 하나 늘고 함수가 하나 는다. 기능이다(DEV-15). 이슈 #70에서 왔지만 "버그 수정"이 아니라 **빠진 단계를 넣는 것**이다.

**왜 지금인가.** 싱크독 미결 정리 때 `SYNC-CODE-001#B2`·`#B4`의 끊어진 참조 플래그 둘이 참조는 이미 `MS-007#pipeline.*`로 고쳐졌는데도 남아 있었다. UC-H12 3은 "시스템이 참조를 다시 추출하고 플래그를 해제한다"인데 SEQ-1·MS-004·MS-007·코드 어디에도 해제 단계가 없었고, 화면에도 끊어진 참조를 닫는 버튼이 없어 API로만 닫을 수 있었다.

**정한 것 둘.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 「더 이상 가리키지 않는다」의 판정 | 저장 후 그 항목의 참조 중 `to_item == 원인` 또는 (`is_missing`이고 `raw_target == 원인 이름`)이 없으면 | 원인 항목은 `is_deleted`라 재추출 때 미존재로 잡힐 수 있다. 둘 다 봐야 "여전히 가리킨다"를 놓치지 않는다 |
| 어느 입구에서 푸나 | 전부 — mcp·github·web_revert | 고친 사람이 누구든 참조가 없어졌으면 풀린 것이다. 확인자는 저장시킨 사람 |

---

#### P UI·API 제목에도 서브타입 키워드

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 2.7·2.8·3장 `frontmatter.title.subtype` · [[SYNC-API-002#create_document]] |
| 구현 함수 | [[SYNC-MS-002#SpecService.validate]] 1 |
| 화면 | 없음 |
| 테스트 | UI 제목 「목록」 → 위반 · 「화면 설계」·「와이어프레임」·둘 다 → 통과 · API 「에이전트 도구」 → 위반 · 「REST」·「MCP」 → 통과 · 기존 명세 전부 여전히 위반 0 |
| 선행 | M |
| 완료 | 2026-09-16 · 브랜치 `card/P-title-keyword` · 커밋 `0ba1a28`(spec) `code(P)`(code) · PR #78 · pytest **220 passed** · `validate.py` 0·0(싱크독 문서는 전부 키워드 있음) · `JSD-API-002 에이전트 도구`는 사용자가 고치기로 — 그 전 재구축이면 그 문서에 규약 오류 하나 |

**왜 카드인가.** 위반 규칙의 범위가 넓어진다 — 기존 문서가 걸릴 수 있는 변경이다(DEV-15).

**왜 지금인가.** 카드 M에서 DOM만 넣고 UI·API는 `JSD-API-002 에이전트 도구`가 걸려 미뤘다. 사용자가 "필수로 하고 JSD 제목은 내가 고친다"로 결정했다. 고치기 전까지 JSD를 재구축하면 그 문서에 규약 오류 하나가 뜬다 — 그게 맞는 상태다.

**정한 것 하나.** UI는 둘 다 들어가도 된다(`JSD-UI-001 화면 설계·와이어프레임`처럼 한 문서에 합친 프로젝트가 있다). `patterns_for`는 표 순서상 뒤 것(와이어프레임)을 고르는데, 그 문서는 형식 절만 필수라 검사가 느슨해지는 쪽이다 — 합친 문서를 두 번 검사하는 규칙은 두지 않는다.

---

#### Q Named Tunnel — 고정 주소

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 5장 공개 경로 · 9장 미결(도메인) · [[SYNC-INFRA-001#C7]] |
| 구현 함수 | 없음 — `scripts/tunnel.sh`(`TUNNEL_TOKEN` 있으면 `cloudflared tunnel run --token`, 없으면 Quick) · `.env.example` `TUNNEL_TOKEN` · `config.py` 주석 · README |
| 화면 | 없음 |
| 테스트 | 손으로 — 토큰 넣고 `scripts/tunnel.sh` → 고정 주소로 `/health` · 재부팅 뒤 같은 주소 · `TUNNEL_TOKEN` 비우면 Quick으로 뜨고 `PUBLIC_BASE_URL`이 새 주소로 바뀜 |
| 선행 | C |
| 완료 | 2026-09-16 · 브랜치 `card/Q-named-tunnel` · 커밋 `12b39a5`(spec) `chore(Q)`(script) · PR #79 · #81(플래그 순서 — `--no-autoupdate`는 `run` 앞) · **실물**: 무료 도메인 `syncdoc.dpdns.org`(DigitalPlat FreeDomain, 만료 2027-09-16, 120일 전부터 무료 갱신) → Cloudflare 존(Free, NS owen·serena) → Zero Trust 터널 `syncdoc`(Healthy, 커넥터 `hoyoung` linux_amd64) → Published application route `syncdoc.dpdns.org → http://localhost:8000` → `.env` `TUNNEL_TOKEN`·`PUBLIC_BASE_URL` → `scripts/tunnel.sh` 「named tunnel → https://syncdoc.dpdns.org」 → `/health` ok · OAuth 콜백 고정 주소로 갱신, 고정 주소로 GitHub 로그인 통과 · MCP 등록(WSL·Windows) 고정 주소, `tools/list` 9개 · **걸린 것**: 경로를 만들기 전에 이름을 조회한 WSL DNS 중계기(10.255.255.254)가 「없음」을 캐시해 이 노트북에서만 한동안 못 찾음 — `/etc/hosts`로 우회. 순서는 「경로 저장 → 조회」 · 셋업 기록(캡처 9장): claude.ai/artifact/BetNPr14t6npa2H3vANcnX |

**왜 카드인가.** 인프라 문서의 결정이 바뀐다(INFRA 9장 미결 하나를 뒤집는다). 코드는 스크립트뿐이라 작지만 기록해야 한다.

**왜 지금인가.** 재부팅 두 번에 두 번 다 터널 주소가 바뀌어 OAuth 콜백을 고치고 WSL·Windows의 MCP 등록을 고치고 에이전트 세션을 재시작했다. 사용자가 도메인이 있다고 했다.

**정한 것 둘.**

| 질문 | 결정 | 이유 |
|---|---|---|
| Quick Tunnel을 없애나 | **남긴다.** `TUNNEL_TOKEN`이 비면 Quick | 도메인 없는 사람이 같은 스크립트로 시작할 수 있어야 한다 |
| webhook을 켜나 | **선택.** 폴링은 그대로 | 폴링 5분이면 충분했고, webhook은 저장소마다 사람이 걸어야 한다. 켜고 싶은 사람은 켠다 |

---

#### R 휴지통 — 지우기는 되돌릴 수 있게

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#N3]] · [[SYNC-UC-001#UC-A7]] · [[SYNC-UC-001#UC-A8]] · [[SYNC-UC-001#UC-H18]] · [[SYNC-API-001#DELETE/api/docs/{docId}]] · [[SYNC-API-001#POST/api/docs/{docId}/restore]] · [[SYNC-API-001#POST/api/docs/{docId}/purge]] · [[SYNC-API-001#GET/api/projects/{code}/trash]] · [[SYNC-API-002#delete_document]] · [[SYNC-API-002#restore_document]] · [[SYNC-SEQ-001#SEQ-22]] · [[SYNC-SEQ-001#SEQ-23]] · [[SYNC-DOM-003]] `documents.trashed_at` |
| 구현 함수 | [[SYNC-MS-007#pipeline.trash_document]] · [[SYNC-MS-007#pipeline.restore_document]] · [[SYNC-MS-007#pipeline.purge_document]] · [[SYNC-MS-007#pipeline.save_pipeline]] 2(`document-trashed`) · [[SYNC-MS-007#pipeline.process_commit]] 4 · [[SYNC-MS-002#SpecService.trash]] · [[SYNC-MS-002#SpecService.trash_commit]] · [[SYNC-MS-002#SpecService.list_trashed]] · [[SYNC-MS-002#SpecService.delete_document]] · [[SYNC-MS-002#SpecService.save]] 7 · [[SYNC-MS-002#SpecService.validate]] 3 · `SYNC-MS-004#TrackingService.release_broken_causes` · `SYNC-MS-004#TrackingService.open_flags_of_document` · [[SYNC-MS-008#queries.trash_list]] · 마이그레이션 `0010` |
| 화면 | UI-5 12·13(휴지통에 넣기·끊어질 것) · 4b 휴지통 배너 + 되살리기 · UI-4 8 휴지통 묶음(8.1~8.4) |
| 테스트 | 남이 가리키는 문서도 넣힘 + 하위 broken_ref · 두 번 넣기 `document-trashed` · 휴지통 문서 저장·상태 변경 막힘 · 목록·단계 칸에서 빠짐 · 되살리기 → 직전 본문·버전 +1·항목 복구·broken_ref `with_edit=false` 해제·목록 복귀 · 폴링이 휴지통 커밋 D 건너뜀 · 완전 삭제: 가리키는 곳 있으면 `document-has-history`, 없으면 행 0·남의 플래그 원인 칸 null·번호 재발급 · 웹 DELETE/restore/purge/trash 목록 · MCP 두 도구 · `check_ui.py` UI-4·UI-5 |
| 선행 | N · O |
| 완료 | 2026-09-16 · 브랜치 `card/R-trash` · 커밋 `1c49b5b`·`c78346d`·`696ce52`(spec) `code(R)` · PR #83 · pytest **220 passed** · `check_ui` 15/15(UI-4 **28/28** · UI-5 **44/44**) · `check_code` 148/148 · `check_dom` 0 · `check_tokens` 0 · `validate.py` 위반 0·경고 0 · `tsc`·`build` 통과 · **실물 확인**(터널·HoyoungParkme, VA-DOM-002로 한 바퀴): confirm 없이 → `document-deletion-needs-confirm`(제목 「클래스 명세 — 영상 분석 에이전트」·버전 4·끊어질 참조 0·댓글 0) → `confirm=true` → 200 `TrashResult{broken_refs: 0}`, 저장소 HEAD `spec(VA-DOM-002): 휴지통`(`2ea946f`)이고 `06-DOM`에서 파일 사라짐 · DB: `trashed_at`·`trashed_by=HoyoungParkme`, 항목 15개 전부 `삭제됨`, **버전 4개 보존**, 규약 오류 아님 · 목록·단계 칸에서 빠지고 `/trash`에만 뜸 · 상태 변경·재삽입 둘 다 409 `document-trashed` · UI-4 휴지통 묶음 「1개」와 행 `VA-DOM-002 v4 · 방금 넣음 · 에이전트(Hoyoung Park)` + 되살리기·완전 삭제 · 되살리기 → 201 **v5**, 저장소에 파일 복귀(`db1d5b8` `spec(VA-DOM-002): 되살림 — 휴지통에서`), 항목 15개 살아나고 휴지통 비고 목록 복귀, 재요청은 409 `document-not-trashed` · **폴링 검증**(실물): 휴지통·되살림 커밋이 저장소에 쌓인 뒤에도 VA-DOM-002의 버전은 5개 그대로이고 `behind_by` 0 — `process_commit`이 휴지통의 `D`를 건너뛰고 앱이 민 되살림 커밋을 아는 해시로 걸렀다 · **테스트로만 본 것**: 끊어진 참조 해제(`release_broken_causes`)와 완전 삭제 문지기 — VA-DOM-002는 하위가 이미 걷혀 있어 실물에서 0건이었다 |

**왜 카드인가.** PRD N3의 삭제 규칙이 바뀌고(하드 삭제 → 휴지통), 엔드포인트 셋·MCP 도구 하나·컬럼 둘·함수 아홉이 는다. 카드 N을 덮어쓴다(DEV-15).

**왜 지금인가.** 카드 N의 「이력 없는 초안만 지운다」가 실물에서 바로 막혔다 — VA-DOM-002는 하위를 걷어내는 저장 자체가 전파 결정을 남겨 영영 못 지웠다. 사용자가 "물어보고 지우되 휴지통으로 되돌릴 수 있게"를 냈고, 그것이 N3의 원래 뜻(문서를 잃지 않는다)에 더 가까웠다. 되살리기의 반은 이미 있었다 — GitHub에서 파일을 지웠다 되살리는 경로(UC-G1 3d, MS-002 복구 결정).

**정한 것 다섯.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 휴지통이 무엇인가 | `documents.trashed_at` + 파일 삭제 커밋. 행·버전·항목(삭제됨)·댓글·플래그 전부 남음 | UC-G1 3d의 상태에 표시 하나 더한 것. 새 표가 아니다 |
| 넣을 때 막나 | **안 막는다.** 끊어질 참조·댓글 수를 보여주고 확인만 받는다 | 되돌릴 수 있으니 문지기가 필요 없다. 끊어진 참조 플래그가 통보다 |
| 되살리기의 본문 | 휴지통 커밋의 **부모**에서 `git.read` — 새 버전으로 저장 | 되돌리기와 같은 원칙: 이력을 안 지운다. `status_changes.commit_hash`가 열쇠 |
| 되살리면 끊어진 참조는 | 원인이 이 문서 항목인 broken_ref를 `with_edit=false`로 푼다 | 가리키던 쪽은 안 고쳤다. 카드 O의 `release_broken`(대상 쪽)과 짝 |
| 완전 삭제의 문지기 | 들어오는 참조 · 댓글 · **미해결** 플래그. 나머지(해결된 플래그·결정·상태 변경)는 함께 지움, 남의 플래그는 원인 칸만 null | 카드 N의 「이력 전부」는 휴지통 자체가 이력(상태 변경·플래그)을 만들어 자기 모순이었다 |

---

#### S 코드 구조를 명세에 못 박는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 1.9·2.6 · [[SYNC-STD-004#DEV-1]] · [[SYNC-DOM-002]] 1장 · [[SYNC-API-002#get_template]] |
| 구현 함수 | 없음 — 명세와 스킬뿐. `get_template`이 이미 STD-001 1장을 통째로 내려준다 |
| 화면 | 없음 |
| 테스트 | `validate.py` 위반 0·경고 0 · **실물**: MCP `get_template(VA, "DOM")`의 `common_rules`에 1.9가 실려 오는지 — VA 저장소엔 STD 파일이 없어 싱크독 것으로 폴백하는 경로가 그대로 증명된다 |
| 선행 | R |
| 완료 | 2026-09-16 · 브랜치 `card/S-code-structure` · 커밋 `fec9dd8`(spec) · PR #87 · `validate.py` 위반 0·경고 0 · `check_dom` 0 · `check_code` 148/148 · `check_ui` 15/15 · `check_tokens` 0 · pytest **220 passed** · **실물 확인**: 앱을 다시 빌드한 뒤 MCP `get_template(VA, "DOM")` → `common_rules` 6842자에 **1.9 코드 구조·기본형 트리·「벗어나려면 클래스 명세에 이유」가 모두 실려 나갔다.** VA 저장소엔 STD 파일이 없으므로 싱크독 STD-001로 폴백하는 경로가 그대로 증명됐다 · **걸린 것 둘** — (1) 그 폴백은 SYNC 저장소 작업 사본이 아니라 **앱 이미지에 구워진 `docs/specs/`** 를 읽는다([[SYNC-API-002#get_template]]). 폴링이 명세를 받아도 규약은 안 바뀌고 **앱을 다시 빌드해야** 에이전트에게 내려간다 (2) `get_template`은 `doc_type`만 받고 `title`을 모르므로 DOM·UI·API의 `required_sections`가 `[]`로 온다 — 서브타입별 필수 절(2.6~2.8)이 에이전트에게 닿지 않는다. 카드 S 범위 밖이라 적어만 둔다 |

**왜 카드인가.** 코드는 안 바뀌지만 규약이 바뀌고, 그 규약이 모든 프로젝트 에이전트에게 전달된다. 기록이 남아야 한다(DEV-15).

**왜 지금인가.** 같은 싱크독으로 만든 프로젝트인데 폴더 구조가 제각각이었다 — INS는 4계층(`domains`·`infrastructure`·`shared`·`interfaces`), VA는 도메인 5파일 + 조건부 어댑터, 싱크독은 `core`·`web`·`mcp`·`infra`. 사용자가 「왜 매번 다른가, 어떤 게 표준인가」를 물었고, 조사해 보니 구조를 정하는 곳이 셋(노트북의 스킬 · STD-004 DEV-1 · 각 클래스 명세 1장)으로 흩어져 **서로 모르고, 그중 다른 프로젝트 에이전트에게 닿는 것이 하나도 없었다.** INS는 「의도는 4계층이다」라고만 적고 왜 그런지는 안 적었다.

**정한 것 넷.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 어디에 못을 박나 | **STD-001 1장** | `get_template`이 1장만 잘라 보내고, 저장소에 STD가 없는 프로젝트는 싱크독 것으로 폴백한다 — 지금 싱크독 말고는 전부 그렇다. 유일한 통로다 |
| 얼마나 강하게 | **기본형 + 벗어나면 이유** | 프로젝트마다 제약이 다르다. 금지하면 INS가 통째로 위반이 되고, 권장만 하면 지금과 같다. 「왜」를 남기게 하는 것이 값이다 |
| 무엇을 「다름」으로 보나 | **폴더의 역할.** 이름은 아니다 | `infra`와 `infrastructure`를 갈라 봐야 얻는 것이 없다 |
| 싱크독 자신은 | **예외로 두고 이유를 적는다** | 입구 둘(C3)이 한 파이프라인(C4)을 타야 해 라우터가 도메인 밖이다. 파일 63개를 옮겨 얻는 것이 일관성뿐이다 |

**스킬은 저장소 밖이다.** `~/.claude/skills/fastapi-domain-architecture`는 이 노트북의 Claude만 읽는다. 1.9와 문장을 맞추고 맨 위에 「싱크독 명세가 있으면 그 클래스 명세 1장이 우선」을 넣었지만 커밋에는 들어오지 않는다 — 팀원의 에이전트에게 닿는 것은 STD-001뿐이다.

---

#### T 저장소 구조 — 프런트와 설정 파일까지

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 1.9·2.6 · [[SYNC-STD-004#DEV-17]] · [[SYNC-DOM-002]] 1장 |
| 구현 함수 | 없음 — 명세뿐 |
| 화면 | 없음 |
| 테스트 | `validate.py` 위반 0·경고 0 · **실물**: MCP `get_template`의 `common_rules`에 저장소 루트·프런트 기본형·설정 파일 표가 실려 오는지 |
| 선행 | S |
| 완료 | 2026-09-17 · 브랜치 `card/T-repo-structure` · 커밋 `57ec0d8`(spec) · 머지 후 main `acf0f80` · PR #89 · `validate.py` 위반 0·경고 0 · `check_dom` 0 · `check_code` 148/148 · `check_ui` 15/15 · `check_tokens` 0 · pytest **220 passed** · **실물 확인**: 앱을 다시 빌드한 뒤 이미지에 구워진 `/srv/docs/specs/STD/SYNC-STD-001.md`에서 `_section`이 자르는 범위(27~243행) **16153자**에 1.9 코드 구조 · 저장소 루트 기본형 · 프런트엔드 기본형 · 설정 파일 표 · 입구 수 판단 표 · `pages → api → 서버`가 **전부 실렸다** · **걸린 것 하나** — 같은 1장을 셸 `awk`로 자르니 3358자만 나와 새 절이 하나도 없는 것처럼 보였다. 74행 `## 2. 요구사항`이 문서 안 **예시 코드블록**인데 마스킹을 안 해 거기서 멈춘 것이다. 진짜 `_section`은 `masked_lines`로 그것을 건너뛰고 244행까지 간다. **검사기가 아니라 확인 방법이 틀린 경우**로, [[SYNC-STD-004#DEV-17]]의 「검사기가 0건이라고 말할 때 그게 안 봤다일 수 있다」와 같은 종류다 — 수가 예상과 다르면 통과든 실패든 먼저 의심한다 |

**왜 카드인가.** 카드 S와 같다 — 코드는 안 바뀌지만 규약이 바뀌고, 그 규약이 모든 프로젝트 에이전트에게 전달된다(DEV-15).

**왜 지금인가.** 카드 S의 1.9는 `app/` **안**만 정했다. 저장소 루트에 무엇이 있는지, 프런트를 어디에 두는지, 설정 파일을 어디에 두는지가 비어 있었다. 실제로 코드가 있는 두 프로젝트가 이미 갈렸다 — 둘 다 `frontend/`를 따로 두지만 INS는 루트에 `Dockerfile` 둘과 compose 다섯을 놓았고 싱크독은 각각 하나씩이다. 규약이 없으니 갈린 것이 맞는지 틀린지 판단할 근거가 없다. 사용자가 「대부분 프론트도 따로 두는데 그 구조도 쓰고, 도커 같은 설정 파일도 명시해 달라」고 했다.

**정한 것 다섯.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 서버와 화면을 한 폴더에 둘 수 있나 | **따로 둔다** | 언어도 빌드도 다르다. 섞으면 의존성 파일이 서로를 덮는다. 하나뿐이어도 루트에 쏟지 않는다 — 다른 하나가 생길 때 전부 옮겨야 한다 |
| 라우터를 밖으로 낼 기준 | **입구의 수** | 하나면 도메인 안, 둘 이상이 같은 쓰기 경로를 타면 밖. 카드 S는 싱크독을 「예외」라고만 했지 판단 기준을 안 줬다 |
| crud도 모을 수 있나 | **아니다. 도메인 안에 남는다** | 모으면 어느 테이블이 어느 도메인 것인지 파일 위치로 알 수 없다. 싱크독도 `repository.py`를 묶음 안에 뒀다 |
| 설정 파일 자리 | **자기가 설정하는 것 옆** | 저장소 전체는 루트, 한쪽만 설정하는 것은 그 폴더. 같은 종류가 여럿이면 접미사로 용도를 붙인다 |
| `.env` | **커밋하지 않는다. `.env.example`만** | 토큰·비밀번호가 저장소에 들어가는 경로가 여기다 |

**프런트 규약은 DEV-17 위에 얹는다.** DEV-17이 이미 「화면 하나 = 컴포넌트 하나」와 `data-el` 대조를 정해 놨다. 1.9가 더하는 것은 **폴더 자리**와 `pages → api → 서버` 호출 방향뿐이다 — 화면이 직접 요청을 짜면 주소와 응답 형태가 화면마다 흩어진다.

---

#### V 한 사람의 도구 — 협업 기능을 걷어낸다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-RFQ-001#Q6]] · [[SYNC-PRD-001#R4]] · [[SYNC-PRD-001#R6]] · [[SYNC-UC-001#UC-H8]] · [[SYNC-INFRA-001]] 6장 · [[SYNC-DOM-003]] · [[SYNC-STD-004#DEV-7]] |
| 구현 함수 | 신설 [[SYNC-MS-003#ReferenceService.mark_missing]] · 축소 [[SYNC-MS-007#pipeline.save_pipeline]] · [[SYNC-MS-007#pipeline.change_status]] · [[SYNC-MS-007#pipeline.purge_document]] · [[SYNC-MS-007#pipeline.rebuild]] · [[SYNC-MS-002#SpecService.validate]] · [[SYNC-MS-002#SpecService.save]] · [[SYNC-MS-008#queries.project_summary]] · [[SYNC-MS-008#queries.project_detail]] · [[SYNC-MS-008#queries.project_items]] · [[SYNC-MS-008#queries.graph_view]] · 삭제 MS-004 전부 · MS-005 댓글 전부 · MS-007 `export_tracking`·`import_tracking`·`backup_loop` · MS-008 `flag_summaries`·`todo`·`decision_view`·`flag_view`·`upstream_checklist` · MS-009 `git.last_commit_at` |
| DB | Alembic `0011_drop_flags_decisions_comments` — 테이블 셋 삭제. `downgrade`는 0001·0007·0008의 정의를 복원하되 데이터는 안 돌아온다(`v1-collab` 태그의 `import_tracking`으로) |
| API | 엔드포인트 10개 삭제(플래그 2·전파 2·댓글 3·내 할 일·백업 복원·상위 대조) · `POST …/status`는 `{to}`만 · 에러 5개 삭제 |
| 화면 | UI-10·11·12 삭제 · UI-5 요소 3(토글)·5·7.4·8.2·8.8·11~11.4 · UI-4 요약 셋 · UI-2 2색 · UI-8 범위 둘 · UI-14 백업 칸 |
| 테스트 | 협업 테스트 삭제(`tests/core/tracking`·`tests/core/collab`·`test_tracking.py`·`test_e2e_b3.py` 등) · 상태 테스트는 둘로 · `mark_missing`이 `to_item_id`·`to_document_id`를 **둘 다** 비운다 · 항목 삭제 저장 → `is_missing` 참조 → 상대 문서 저장 시 풀림 · 완료 문서를 MCP로 고치면 초안 · 규약 오류 문서는 완료로 못 올림 · 마이그레이션 up→down→up 왕복 · `check_dom` 10·10·10 · `check_ui` 화면 12 · **사람 확인**: 아래 열 가지 |
| 선행 | T |
| 완료 | 2026-09-21 · 브랜치 `card/V-solo` · 커밋 `9019be1`~`a3eba3f` (spec 25 + code 10) · 테스트 190(삭제 27·수정 20·신설 5) · `validate` 0/0 · `check_code` 142 중 일치 103, 미완 39(MS-004 26·MS-005 11은 휴지통 예정, `ask_item`·`llm.ask`는 U) · `check_ui` 12화면 중 11 일치(UI-5의 8.4~8.7은 U) · `check_dom` 10·10·10 · `check_tokens` 91/0 · 0011 up→down→up 왕복 · 사람 확인 열 가지는 배포 뒤 브라우저에서(아래 기록) · 되먹임: 상태 라벨 「완료」, `SaveResult.warnings`에 `ref.broken: n`, STD-002 `data-src` 규약 삭제, RFQ 7장 Q6 신설 |

**왜 카드인가.** 걷어내기가 테이블·파이프라인·화면·검사기에 한꺼번에 걸려 있어 자르면 중간 상태가 뜨지 않는다 — `core/tracking`을 지우는 순간 `queries`·`types`·`env.py`가 같이 깨진다. 그리고 걷어내는 일은 이슈(DEV-15 `fix`)가 아니다. 틀린 게 아니라 **전제가 바뀌었다.**

**왜 지금인가.** 써 보니 한 사람이 프로젝트 하나를 혼자 다 쓴다([[SYNC-RFQ-001]] 7장). 승인·전파·플래그·댓글은 두세 명이 서로 확인하라고 만든 장치라 혼자면 일만 늘린다 — 자기가 쓴 것을 자기가 승인하고, 자기 변경의 전파를 자기가 결정한다. 실측으로도 여덟 프로젝트에 교차 작성이 한 건도 없다. RFQ 6장이 처음부터 「실사용 2~3명이라 얼마나 필요한지」를 미정으로 남겨 뒀고, 이것이 그 답이다.

**정한 것 다섯.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 상태를 없애나 | **초안·완료 둘로 줄인다** | 없애면 목록 히트맵·그래프 범위·순서대로 읽기·MCP `get_document`의 「확정인가」 신호가 전부 축을 잃는다. `review`만 지우면 frontmatter 변경은 세 건 |
| 끊어진 참조는 | **`references.is_missing`으로 되돌린다** | 플래그는 「누가 확인했나」를 얹은 것이었다. 혼자면 확인할 사람이 없다. 참조 추출이 이미 갖고 있던 `is_missing`으로 돌아가면 4a 배너·참조 패널·`resolve_missing`이 그대로 일한다 |
| `status_changes`는 | **남긴다** | 휴지통 되살리기가 `reason='휴지통'` 행의 커밋 해시를 열쇠로 쓰고, 이력이 상태 줄을 보여준다. 협업 표가 아니다 |
| 백업은 | **없앤다** | 백업 대상이 플래그·전파·댓글이었다. 남는 데이터는 전부 저장소에서 재구축된다 |
| 옛 데이터는 | **`v1-collab` 태그와 `backup/tracking.json`으로 남긴다** | 마지막 export를 돌리고 태그를 찍었다. 되돌릴 일이 생기면 그 태그의 코드가 읽는다. 저장소의 파일은 파이프라인 감지 밖이라 두어도 아무 일이 없다 |

**상태의 닭과 달걀.** 이 카드가 승인 게이트를 없애는데 명세를 고치는 동안은 옛 게이트가 살아 있다. 고친 문서는 전부 frontmatter를 같은 커밋에서 `draft`로 내렸다 — GitHub 경로 자동 강등은 frontmatter가 `approved`일 때만 `review` 커밋을 밀므로(MS-002 save 6) 작성자가 스스로 내리면 `review`가 생기지 않는다. 코드가 들어간 뒤 새 토글로 한 번에 완료로 올린다.

**사람이 브라우저에서 볼 열 가지.**

1. UI-5에서 토글 하나로 초안⇄완료가 되고 다이얼로그가 없는가
2. 규약 오류나 미완성이 있는 문서는 완료로 눌러도 막히고 이유가 보이는가
3. 완료 문서를 MCP로 고치면 초안으로 내려가고 이력에 그 줄이 남는가
4. 오른쪽 패널이 참조 하나뿐인가 (질문 탭은 U가 더한다)
5. 항목을 지운 저장 뒤 UI-4 끊어진 참조 수가 늘고, 상대 문서를 다시 저장하면 주는가
6. UI-4 요약이 셋이고 문서 행에 플래그·댓글 열이 없는가
7. UI-8 범위가 둘이고 ▲가 없는가
8. UI-2 히트맵이 두 색과 미작성뿐인가
9. UI-14에 백업 칸과 복원 버튼이 없는가
10. 휴지통 → 되살리기 → 완전 삭제가 전과 같은가

---

#### W 프로젝트는 등록한 사람의 것

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-RFQ-001#Q6]] · [[SYNC-PRD-001#R12]] · [[SYNC-UC-001#UC-H14]] · [[SYNC-INFRA-001]] 5장 · [[SYNC-DOM-003]] `projects` · #91 · #75 |
| 구현 함수 | 신설 [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-MS-001#ProjectService.list_owned]] · 변경 [[SYNC-MS-001#ProjectService.init_project]] · [[SYNC-MS-001#ProjectService.repo_status]] · [[SYNC-MS-001#ProjectService.delete_project]] · [[SYNC-MS-001#ProjectService.rebuild_index]] · [[SYNC-MS-007#pipeline.save_pipeline]](사람 경로는 `get_owned`) · [[SYNC-MS-007#pipeline.change_status]] · [[SYNC-MS-007#pipeline.trash_document]] · [[SYNC-MS-007#pipeline.restore_document]] · [[SYNC-MS-007#pipeline.purge_document]] · [[SYNC-MS-007#pipeline.revert]] · MS-008 사람용 조회 전부에 `user` |
| DB | Alembic `0012_add_projects_owner` — `projects.owner_user_id` nullable 추가 → 등록자로 UPDATE → not null → FK·인덱스. downgrade는 역순 |
| API | 규칙 한 줄 「소유하지 않은 프로젝트는 없는 것과 같다」. 엔드포인트·에러 표 변경 없음. OAuth scope `public_repo` |
| 화면 | UI-2 「내 프로젝트만」 + 빈 상태 · UI-14 규칙 · UI-1·UI-3 한 줄 |
| 테스트 | 웹·MCP 각각 「남의 프로젝트는 목록에 없음 · 주소로 not-found · 저장도 not-found」 · 폴링·웹훅은 소유 무관 · 백필 뒤 `owner_user_id is null` 0건 · 마이그레이션 up→down→up · 픽스처의 등록자 = 요청자 · **사람 확인**: 아래 다섯 |
| 선행 | V |
| 완료 | 2026-09-21 · 브랜치 `card/W-owner` · 커밋 `79a10bb`~`8ad75f9` (spec 15 + code 7) · 테스트 197(신설 7·수정 12) · `validate` 0/0 · `check_code` 107 중 105(미완 2는 U) · `check_ui` 12 중 11(UI-5 8.4~8.7은 U) · `check_dom` 10·10·10 · 0012 왕복+백필 · 사람 확인은 배포 뒤(아래 기록) · 되먹임: `delete_all_of`에 남아 있던 협업 표 delete(V 잔재) 제거, `user`는 마지막 필수 인자(선택 인자 앞) |

**왜 카드인가.** 게이트 함수 둘과 그것을 지나는 자리 20여 곳이 한 덩어리다. 반만 걸면 「목록엔 없는데 주소로는 열린다」가 되어 안 한 것보다 나쁘다.

**왜 지금인가.** 프로젝트 8개 중 하나가 다른 계정으로 등록됐고, 두 계정에 서로의 프로젝트가 전부 보이고 있다. v1이 「저장소 접근 권한이 곧 접근 권한」이라 적어 놓고 그 검사를 한 번도 안 했다(#75). 협업 장치를 걷어낸 지금(V) 남은 다인 전제가 이것 하나다.

**정한 것 넷.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 소유를 어디에 두나 | **`projects.owner_user_id`** 신설 | `repositories.registered_by_user_id`는 push 토큰의 주인이다. 소유권이 옮겨가는 일과 토큰 주인이 바뀌는 일은 다른 사건인데 한 칸에 묶이면 갈라낼 수 없다. 접근 단위도 저장소가 아니라 프로젝트(`code`)다 |
| 남의 것을 열면 | **없는 것과 같다 — 기존 `not-found`** | 403을 두면 남의 프로젝트가 있다는 사실이 샌다. 새 에러 타입도 안 는다 |
| 게이트 모양 | **`get_owned(code, user)`·`list_owned(user)` 신설, `get`·`list_projects`는 배치용으로 남긴다** | `get(code, user \| None)`이나 ContextVar는 「빠뜨린 자리 = 조용히 전체 열람」이다. 두 이름이면 `grep`으로 남은 자리를 세고 `check_code`가 시그니처를 대조한다 |
| 공유·초대 | **안 만든다** | 교차 작성 0건. 필요해지면 `project_members` 표 하나와 게이트 조건 한 줄 — 첫 변경이 자리를 다 만들어 두므로 두 번째가 싸다 |

**사람이 브라우저에서 볼 다섯.** 두 계정이 필요하다.

1. A로 들어오면 목록에 A가 등록한 것만 뜨는가
2. B가 A의 `/p/{code}`를 직접 치면 없다고 나오는가 (본문이 잠깐이라도 비치지 않는가)
3. B의 MCP 토큰으로 A 프로젝트에 `get_document`·`create_document`를 부르면 not-found인가
4. UI-14 표에 자기 것만 뜨고, 폴링은 두 프로젝트 다 도는가(동기화 칸)
5. 프로젝트가 하나도 없는 계정이 빈 상태를 보는가

---

#### X 화면 문서는 하나 또는 둘

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-RFQ-001#Q6]] · [[SYNC-STD-001]] 2.7 · [[SYNC-STD-002]] V-UI · [[SYNC-STD-004#DEV-17]] · #94 |
| 구현 | `tools/validate.py` UI 두 서브타입의 필수 절을 `미결사항` 하나로 · `tools/check_ui.py` 화면 헤딩 단계 무관 + 제목 폴백 + 요소 표 `#`↔`data-el` 대조 · `tools/wf_build.py`·`frontend/src/view/wireframe.ts`·`index.ts` 렌더러 하나(`vUi`) — 화면별 html 유무로 갈리고 비화면 절도 렌더 · `_templates/UI.md` 제목 하나·화면 헤딩이 소제목보다 상위 · [[SYNC-API-002#get_template]] 읽는 순서 뒤집기(이미지 먼저) |
| 화면 | 새 화면·요소 없음. UI-5 유저용 탭이 UI 문서를 그리는 방식만 바뀐다 |
| 테스트 | `check_ui` 싱크독 12화면 중 11(UI-5 8.4~8.7은 U) · 다른 프로젝트 화면 문서 8개를 새 `validate`·`check_ui`·`view_build --all`로 돌려 **손대지 않고** 통과 · INS-UI-002가 비지 않고 · TBL-UI-001의 html 9개가 보이고 · JSD·VA·SYNC의 비화면 절이 살아나고 · 우측 셋 비면 좌측 전폭 · `get_template`이 저장소 사본이 낡아도 이미지 것을 준다 · **사람 확인**: 아래 다섯 |
| 선행 | V |
| 완료 | 2026-09-21 · 브랜치 `card/X-ui-doc` · 커밋 `7a4e821`~ (spec 7 + code 4) · 테스트 197 · `validate` 0/0 · `check_ui` 12 중 11(UI-5 8.4~8.7은 U) + 새 대조(요소 표↔data-el) `!` 0 · `check_code` 105/107 · `check_view_css` 같음 · `view_build --all` 오류 0 · 다른 프로젝트 문서 손 안 대고: INS-UI-002 화면 4(전엔 0) · TBL-UI-001 화면 7·배치 7(전엔 배치 0) · JSD 화면 5 + 비화면 절 7 · SYNC-UI-002 화면 12 + 절 3 · SYNC-UI-001 설계 표 12행 · 사람 확인 다섯은 배포 뒤(아래 기록) · 되먹임: `check_ui`가 UI-002의 빠진 요소 표 행(1.1·1.2)을 잡아 채웠고, UI-002에 `미결사항` 절이 생겼다 · **놓친 것**: 앱의 `SpecService.validate`에도 같은 `SUBTYPES` 표가 있는데 `tools/validate.py`만 고쳤다 — 디자인 스킬 산출물 시험(CCR-UI-001)이 잡아 #105로 고침 |

**왜 카드인가.** 규약(STD-001)·뷰 규약(STD-002)·검사기·정적 뷰 생성기·React 렌더러·템플릿이 같은 한 문장을 각자 코드로 갖고 있다. 하나만 고치면 「검사는 통과하는데 뷰는 빈다」가 된다 — 바로 지금 상태다.

**왜 지금인가.** 사용자가 「클로드가 준 와이어프레임을 그대로 올리고 싶은데 이상한 구조만 올라간다」고 했다. 조사하니 다른 프로젝트 화면 문서 8개는 고칠 것이 없었다. 깨진 것은 전부 우리 쪽이다 — 파서가 `## UI-N` 2단계만 읽고, `### 배치` 문자열에 묶여 있고, 비화면 절을 버린다. 템플릿은 `#### UI-1` 아래 `### 배치`를 두어 항목 블록을 스스로 끊는다(#94).

**정한 것 넷.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 문서를 하나로 강제하나 | **하나 또는 둘** | 규약은 이미 「둘 다 들어가도 된다」고 허용하고 있었다. 부족한 건 합쳤을 때의 규칙이었다 |
| 필수는 무엇인가 | **절은 `미결사항` 하나, 항목 블록은 html 하나** | 사용자 결정. 하위 문서는 화면 ID로 참조하고 검사기는 `data-el` 집합만 본다 — html만 있으면 체인이 이어진다 |
| 헤딩 단계 | **무관** | 승인된 문서들도 `##`·`###`·`####`가 섞여 있고 `md.ts itemBlocks`는 이미 1~6을 읽는다. 검사기와 정적 뷰만 2단계에 묶여 있었다 |
| 싱크독 자신은 | **둘로 둔다** | 합치면 참조 112줄과 React docstring 16건이 바뀌는데 얻는 게 없다. 두 도구(`check_ui`·`check_tokens`)가 각각 문서 하나를 본다 |

**사람이 브라우저에서 볼 다섯.**

1. INS-UI-002가 비어 있지 않고 화면 4개가 배치와 함께 뜨는가
2. TBL-UI-001에서 화면마다 html 배치가 보이고 요소 표가 없으면 좌측 전폭인가
3. JSD-UI-001의 0장·대응표·공통 틀·흐름·미결이 화면 탭과 함께 보이는가
4. 싱크독 UI-001(설계만)·UI-002(와이어프레임)가 전과 같이 보이는가
5. 새 프로젝트의 `get_template("UI")`가 새 템플릿을 주는가

---

#### U 읽다가 항목에 대해 묻는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R11]] · [[SYNC-UC-001#UC-H19]] · [[SYNC-SEQ-001#SEQ-24]] · [[SYNC-INFRA-001]] 5.3 |
| 구현 함수 | `SYNC-MS-009#llm.ask`(Y에서 `llm.step`으로 대체) · [[SYNC-MS-008#queries.ask_item]] · 엔드포인트 `POST /api/docs/{docId}/items/{itemId}/ask` ([[SYNC-API-001]] 3.4) |
| 화면 | [[SYNC-UI-002]] UI-5 요소 8.4~8.7 — 질문 탭 · 맥락 줄 · 입력 · 대화 |
| 테스트 | 구현 함수의 테스트 관점 전부 · **DB에 아무것도 안 쓴다**(호출 전후 행 수가 같다) · 맥락에 문서 전문이 안 들어간다 · 키가 비면 네트워크를 타기 전에 막힌다 · 외부 429가 `llm-unavailable`로 접힌다 · `check_ui` UI-5 전부 · **사람 확인**: 아래 아홉 가지 |
| 선행 | V · X |
| 완료 | 2026-09-21 · 브랜치 `card/U-ask-panel` · 커밋 `3fa72d0`~ (spec 6 + code 4; 명세 본체는 #95) · 테스트 207(신설 10) · `validate` 0/0 · `check_code` 107/107 · `check_ui` 12/12 · `check_tokens` 91/0 · 사람 확인 아홉 중 9번(키 없으면 탭이 없고 나머지 멀쩡)은 배포 뒤 확인, 1~8은 키를 넣은 뒤 사용자가 본다 · 되먹임: 「어느 회사의 API인가」(OpenAI 호환, `LLM_API_URL`)와 「키 유무 신호」(`GET /api/me`의 `llm_enabled`) 둘이 명세에 없어 사용자와 정해 API-001·INFRA·MS-009·UI-002에 적었다 |

**왜 카드인가.** 함수 둘과 엔드포인트 하나와 화면 요소 넷이 한 호출 그래프로 닫힌다(DEV-12). 백엔드와 화면으로 자르면 뒷 카드가 앞 카드 함수를 전부 쓰는 직선이 되고, 화면 없는 카드는 DEV-14의 일곱째 조건(사람이 눌러 본다)을 못 채운 채 닫힌다.

**왜 지금인가.** 명세를 읽다 막히면 화면을 떠나야 했다. 에이전트로 옮겨가 프로젝트와 문서를 다시 지정하는 동안 읽던 맥락이 버려진다. 처음에는 「코드가 어떻게 구현됐나」를 묻는 챗봇을 검토했으나, 그 일은 각자의 에이전트가 이미 하고 있었다. 목적을 **읽는 중 질의**로 좁히자 설계가 크게 싸졌다 — 보고 있는 항목이 곧 맥락이라 검색이 필요 없고, 새 화면도 표도 필요 없다.

**정한 것 여섯.**

| 질문 | 결정 | 이유 |
|---|---|---|
| 비목표를 어떻게 하나 | **지우지 않고 쓰기와 판정 둘로 나눈다** | 원래 줄의 괄호 안 예시가 각각 그 둘이다. 근거(R9 쓰기 경로·R6 승인 주체)를 못 박으면 비목표가 약해지지 않고 또렷해진다. 지우면 「플랫폼이 명세를 써도 되는가」가 다시 열린다 |
| 어디에 두나 | **UI-5 패널의 탭 하나** | 별도 화면이면 무엇에 대해 묻는지를 사람이 다시 지정해야 한다. 문서 뷰에서는 그 지정이 공짜다 |
| 대화를 저장하나 | **안 한다.** 클라이언트가 들고 요청마다 통째로 보낸다 | 표가 늘면 백업·재구축·완전삭제가 전부 그것을 알아야 한다. 게다가 **저장해도 DB 유실에는 대비 못 한다** — 저장소가 공개라 자유 텍스트를 백업에 못 싣는다. 남는 것이 껍데기뿐이다 |
| 키는 누구 것인가 | **서버에 하나** | 사람마다 키면 `users`에 컬럼이 늘고 5.1 재암호화가 하나 더 생긴다. 그 유틸이 한쪽만 돌면 **모델 키만 못 푸는 채로 옛 키가 지워진다** |
| 어느 회사의 API인가 | **OpenAI 호환 Chat Completions** (`LLM_API_URL`) | 명세가 「httpx로 한 번」까지만 정했다. 회사를 고정하면 키가 그 회사에 묶이고, 호환 규격이면 주소 하나로 로컬 모델까지 간다. 코드 시작 전에 사용자가 골랐다(2026-09-21) |
| 비용을 어떻게 막나 | **한도가 아니라 상한과 스위치** | 맥락은 항목 본문까지, 대화는 `LLM_MAX_TURNS`턴까지. 회수 경로는 키를 비우는 것이다. 디스크 한도를 「한도보다 회수 경로가 먼저다」로 닫은 것과 같은 판단이고, 429를 만들지 않으므로 에러 표가 안 는다 |

**답을 남기는 길은 없다.** 처음에는 댓글로 옮기는 길을 뒀으나 V가 댓글을 걷어냈다. 남는 경계는 둘 — 답은 저장되지 않고, 명세를 바꾸지 않는다. 남길 값이 있으면 사람이 읽고 자기 에이전트에게 말한다. 그 경로가 R9 그대로라 「모델이 명세에 쓴다」가 되지 않는다.

**사람이 브라우저에서 볼 아홉 가지.** 검사기가 못 잡는 몫이다(DEV-17이 그 한계를 적어 뒀다).

1. 처음 열면 패널이 여전히 참조 탭이고 「항목을 선택하세요」인가
2. 7.1이 참조 탭으로 가는 기존 전환이 안 바뀌었나
3. `?panel=ask`로 직접 열리고 `#item-X`와 함께 오면 항목까지 잡히나
4. 원본 탭으로 바꿔도 패널이 그대로 있고 3단이 안 흔들리나
5. 답이 길어져도 패널 안에서만 스크롤하나
6. 휴지통 문서에서 질문 탭이 없는가
7. MINISPEC이 빈 프로젝트에서 「아직 안 쓰였다」고 답하나
8. 새로고침하면 대화가 사라지나
9. 키를 비우고 띄우면 탭이 안 보이고 나머지가 멀쩡한가

---

#### Y 질문 탭이 관계도를 따라 읽는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-PRD-001#R11]] · [[SYNC-UC-001#UC-H19]] · [[SYNC-SEQ-001#SEQ-24]] · [[SYNC-INFRA-001]] 5.3 · 사용자 결정 2026-09-21~22 |
| 구현 함수 | [[SYNC-MS-009#llm.step]](`llm.ask` 대체) · [[SYNC-MS-008#queries.ask_tool]](신설) · [[SYNC-MS-008#queries.ask_item]](ReAct 루프로 재작성) · 엔드포인트 `POST /api/docs/{docId}/ask`([[SYNC-API-001]] 3.4, SSE — `…/items/{itemId}/ask` 대체) |
| 화면 | [[SYNC-UI-002]] UI-5 요소 8.5(문서 전체)·8.6(항상 활성)·8.7(본 것 = 읽은 순서)·**8.9 진행 줄** 신설. 대화는 프로젝트 단위로 `Shell`이 든다 |
| 테스트 | `llm.step`(tools·tool_choice 실림·tool_calls 파싱·비JSON→unavailable·usage 0) · `ask_tool` 다섯(키 집합·다른 프로젝트 ID→「없음」 텍스트·남의 프로젝트→not-found·끊어진 참조 「아직 없음」·빈 단계 유지) · `ask_item` 가짜 대본(이벤트 순서 `start·note·read·…·answer` · `context_item_ids` 순서·중복 접힘 · 9번째에서 `tool_choice="none"` 마무리 · 120초 · 마무리도 답 없음→unavailable · 시작 맥락에 본문 없음 · `item_id=None` · 없는 item_id→not-found가 start 전 · **DB 행 수 불변** · usage 로그 한 줄) · 라우터(404·503은 상태 코드, 루프 중 unavailable은 `error` 이벤트) · `check_ui` 12/12 · **사람 확인**: 아래 열둘 |
| 선행 | U |
| 완료 | 2026-09-22 · 브랜치 `card/Y-ask-react` · 커밋 `eef87b6`~ (spec 11 + code 5) · 테스트 215(신설 18) · `validate` 0/0 · `check_code` 108/108 · `check_ui` 12/12 · `check_tokens` 91/0 · `check_dom` 10·10·10 · 사람 확인 열둘은 배포 뒤(아래 기록) · 되먹임: 카드 U 명세의 맥락 상한은 내가 채운 값이었다 — 이번엔 plan 모드에서 열셋을 물어 정했다 · `alembic/env.py`의 `fileConfig`가 앱 로거를 끄고 있어 usage 로그 테스트가 못 보던 것을 `disable_existing_loggers=False`로 |

**왜 카드인가.** 어댑터(한 번 호출→도구 파싱)·루프·도구 실행·SSE·화면이 한 호출 그래프다. 어느 하나만 바꾸면 「모델은 도구를 부르는데 아무도 실행하지 않는다」거나 「진행이 오는데 화면이 못 받는다」가 된다.

**왜 지금인가.** 카드 U를 쓸 때 맥락 상한(항목 본문 + 이웃 이름)을 사용자에게 묻지 않고 내가 채웠다. 배포 뒤 「근거 Q4가 뭐라고 했어?」에 「모른다」가 나왔다 — 관계도가 있는데 이름만 싣고 있었다. 이번엔 설계값을 하나하나 물어 정했다(아래 표).

**사용자가 정한 것 열셋.**

| 질문 | 결정 |
|---|---|
| 맥락을 어떻게 넓히나 | 모델이 읽기 도구를 스스로 부른다(ReAct) |
| 도구 | `get_item` · `get_references` · `item_chain` · `list_documents` · `get_document`. 쓰기 없음. 같은 프로젝트 안, 소유 검사 |
| 첫 호출에 싣는 것 | 문서 제목·상태·버전 + 모든 항목 ID·이름. 본문은 안 실음 |
| 항목 선택 | 없어도 묻는다 — 문서 단위 시작 |
| 도구 호출 상한 | 8번(코드 상수), 넘으면 읽은 것으로 마무리 답 |
| 시간 상한 | 전체 120초(호출 사이 검사, 최악 180초) |
| 글자 상한 | 없음 |
| 문서·끊어진 참조 | 문서는 제목·상태만, 끊어진 건 「아직 없음」 |
| 진행 표시 | 실시간 — 읽기 전 한 줄(`reason`)과 읽은 대상이 차례로 |
| 본 것 | 실제로 읽은 대상, 순서 |
| 비용 관측 | usage 서버 로그 한 줄. DB 없음 |
| 엔드포인트 | 문서 단위 하나 `POST /api/docs/{docId}/ask` |
| 대화 유지 | 프로젝트 단위. 문서·항목을 옮겨도 남고 프로젝트가 바뀌면 새 대화 |

**설계 단계에서 정한 것.** 모든 도구에 `reason` 필수(진행 줄을 결정적으로) · 도구 결과는 JSON(MCP와 같은 모양) · `list_documents`는 「본 것」에 안 실음 · 진행 줄 번호 8.9(8.8은 은퇴) · 「새 창」은 프로젝트별 대화 state로.

**사람이 브라우저에서 볼 열둘.**

1. 항목 없이 열어도 8.5가 「문서 전체」이고 8.6이 활성인가
2. 항목을 고르면 8.5가 바뀌고 대화는 남는가
3. 진행 줄이 도구마다 실시간으로 뜨는가 — 터널 뒤에서도 한 번에 몰려 오지 않는가
4. 「본 것」이 읽은 순서와 같고 링크가 되는가
5. 아홉 번 이상 읽게 하는 질문에서 「읽은 것으로 답」이 오는가
6. 키를 빼고 띄우면 스트림 전에 503이고 탭이 없는가
7. 모델 주소를 틀리게 두면 `error` 이벤트가 패널에 「답을 못 받았습니다」로 뜨는가
8. 휴지통 문서에 탭이 없는가
9. `?panel=ask`·`#item-X` 진입이 그대로인가
10. 다른 프로젝트로 가면 새 대화인가
11. 서버 로그에 usage 한 줄이 남고 DB 행 수가 그대로인가
12. 실제 질문 셋 — 「이 챗봇은 어떻게 만들었어」·「근거 Q4가 뭐라고 했어」·「이게 어느 코드 카드까지 이어져」에 관계도를 따라 답하는가

---

#### Z 화면 문서는 디자인 산출물 그대로

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-RFQ-001#Q6]] 2 · [[SYNC-STD-001]] 2.7 · [[SYNC-STD-002]] V-UI · [[SYNC-PRD-001#R5]] · #118 · 사용자 결정 2026-09-22 |
| 구현 | `frontend/src/view/frame.ts`(srcdoc 조립·`mountFrames`) · `wireframe.ts`(클래스 사전·강제 테두리 삭제, iframe) · `md.ts` 화면 밖 html 블록도 iframe · `tools/wf_build.py`·`view_build.py` 같은 srcdoc · `tools/check_view_css.py`에 `FRAME_CSS`·`SANDBOX` 쌍 · [[SYNC-MS-001#ProjectService.asset_path]] + `GET /api/projects/{code}/files/{path}` · `infra/git.py` 새 저장소 README 두 줄 · `HowTo.tsx` |
| 화면 | 새 요소 없음. UI-5 유저용 탭에서 배치가 iframe으로 그려진다. UI-002에 `공통 틀` 절 신설(렌더러 사전을 문서로) · UI-16 문구 둘 |
| 테스트 | `asset_path`(소유자·남·`..`·심볼릭 링크·확장자·없음) · 라우터(200·Content-Type·Cache-Control·svg CSP·401·404) · `safe_layout` 정규식 자체 검사 · `check_view_css` 셋 다 같음 · `view_build --all` 오류 0 · 다른 프로젝트 화면 문서 8개 + HB + CCR이 손 안 대고 열림 · `check_ui` 12/12 · **사람 확인**: 아래 열하나 |
| 선행 | X |
| 완료 | 2026-09-22 · 브랜치 `card/Z-wf-iframe` · 커밋 `bccf473`~ (spec 12 + code 3) · 테스트 217(신설 2) · `validate` 0/0 · `check_code` 109/109 · `check_ui` 12/12 · `check_tokens` 91/0 · `check_dom` 10·10·10 · `check_view_css` 셋 다 같음 · `wf_build --selftest` 통과 · `view_build --all` 오류 0(UI-002 iframe 12) · 사람 확인(배포 뒤 2026-09-22, 브라우저): (1) SYNC 12화면 iframe 안 computed style에 앱 CSS 없음·공통 틀로 지금 모습 유지 ✓ (2) 요소 표↔배치 양방향 강조 ✓(iframe→표는 #122 고친 뒤) · `#item-UI-2` 진입 ✓ (3) 탭 바꿔도 높이 0 아님 ✓ (4) 1280 고정폭 → scale 0.12(폭 155)·「원래 크기」↔「맞춤」 토글 ✓ (5) `.md`·없는 파일·남의 프로젝트(KB)·`..` 전부 404 ✓(실제 이미지는 첨부를 둔 프로젝트가 아직 없어 테스트로만) (6) Google Fonts는 첨부와 같은 이유로 미확인 (7) UI-9 순서대로 읽기에서 HB UI-1 341px, 탭 전환 UI-2 156px ✓ (8) 다른 타입 html 블록(wfbox) ✓ (9) 정적 뷰 `view_build --all`로만(파일로 열어 이미지 상대 경로는 미확인) (10) 배치 안 `<a href="#unclassified">` 클릭에 iframe·부모 URL 그대로 ✓ (11) HB UI-1 topbar 글씨 검정(#118) ✓ · 발견: SPA index.html에 Cache-Control이 없어 배포 뒤 옛 번들을 연다 → #124 · 되먹임: UI-002 공통 틀에 옮긴 CSS가 사전 134줄 + 앱에서 우연히 맞던 105개 클래스 218규칙 — 12화면을 다시 그리면(AA) 줄인다 · `.wfbox`의 점선·회색도 같이 뺐다(배지만 규칙) |

**왜 카드인가.** 격리(iframe)·배지·공통 틀·첨부·안내가 한 덩어리다. 격리만 하면 싱크독 12화면이 벗겨지고, 안내만 고치면 디자인 산출물이 사이트 CSS에 먹힌다.

**왜 지금인가.** HB 온보딩 시험의 화면이 회색 상자로 보였다. 사용자: 「디자인 스킬로 더 이쁘게 만들 텐데 반드시 저 구조로 올려야 하나?」 — 필수는 html 블록 하나뿐인데, 렌더러가 `data-el` 요소마다 점선 테두리·흰 배경을 강제하고, 사이트 CSS가 스며들고(#118), 템플릿이 회색 상자를 가르치고 있었다.

**사용자가 정한 것 열.**

| 질문 | 결정 |
|---|---|
| 격리 | iframe(srcdoc). 정적 뷰도 같게 |
| 만드는 법 | 도구 중립 — 에이전트의 디자인 도구로 만든 자기 완결 html을 그대로 |
| 이미지 | 앱 엔드포인트 `GET /api/projects/{code}/files/{path}` |
| 폰트 | 외부 `<link>` 허용 |
| 배지 | 배지만 붙이고 모양은 안 건드린다 |
| 공통 스타일 | 공통 틀 절의 첫 html 블록을 모든 화면 앞에 |
| 폭 | 넓으면 축소, 누르면 원래 크기 |
| 싱크독 12화면 | CSS 전부 공통 틀로 옮겨 지금 모습 유지(Z) + 디자인 도구로 다시 그린다(AA) |
| 시험 | HB 화면 문서를 새 에이전트가 새 안내만 보고 다시 쓴다(AA) |
| 커밋 표시 | 클로드 표시 금지 — 싱크독 저장소 포함, 이 카드부터 |

**설계 단계에서 정한 것.** `sandbox="allow-same-origin"`(스크립트 없음) · `data-el`→`data-wf` 치환 폐지 · 제거 태그에 `iframe·object·embed·meta http-equiv·form` 추가 · 첨부 확장자 열 개, svg에 CSP sandbox · 공통 틀 절은 이름으로 찾고 `<style>/<link>`는 head · 화면 밖 html 블록도 같은 iframe.

**사람이 브라우저에서 볼 열하나.**

1. 싱크독 12화면이 격리 뒤에도 지금 모습인가 (iframe 안 computed style에 앱 CSS 없음)
2. 요소 표 ↔ 배치 양방향 강조, `#item-UI-N` 진입
3. 탭을 바꿔도 높이가 0으로 남지 않는가
4. 1280 고정폭이 축소되고 「원래 크기」 토글이 되는가
5. `../assets/x.png`가 뜨고 남의 프로젝트 파일은 404인가
6. Google Fonts `<link>`가 iframe 안에서 적용되는가
7. UI-9 순서대로 읽기에서 높이가 잡히는가
8. 다른 타입 문서의 html 블록이 전처럼 보이는가
9. 정적 뷰 파일로 열어 같은가
10. 배치 안 `<a href="#x">`를 눌러도 iframe이 이동하지 않는가
11. HB UI-1의 `topbar`가 더는 흰 글씨가 아닌가

---

#### AA 싱크독 화면을 디자인 도구로 다시 그린다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 2.7 「만드는 법」 · [[#Z]] · 사용자 결정 2026-09-22 |
| 구현 | 코드 없음. 새 에이전트(내 맥락 없음)가 새 안내만 보고 (a) HB 화면 문서, (b) `SYNC-UI-002` 12화면을 디자인 도구로 다시 쓴다 — **`data-el` 번호·요소 표·규칙·시나리오는 그대로**. 되먹임은 이슈로, 공통 틀의 「우연히 맞던 101개」 정리 |
| 테스트 | `check_ui` 12/12 · `validate` 0/0 · `view_build --all` · 사람이 12화면을 본다 |
| 선행 | Z |
| 완료 | 2026-09-22 · 새 에이전트 둘(내 맥락 없음) · (a) HB `HoyoungParkme/hb#1` — 클로드 디자인 캔버스로 4화면, `data-el` 집합 그대로, `validate` 0/0 · (b) SYNC `#131`(브랜치 `card/AA-sync-redesign`, 커밋 `9fab38b`) — 그 세션엔 캔버스가 없어 `frontend-design` 스킬로 12화면을 직접 씀, `check_ui` 12/12 · `validate` 0/0 · `view_build` 오류 0 · 공통 틀의 옛 사전 300여 줄 삭제 → UI-001 3.1 토큰을 CSS 변수로 한 체계 · 사람 확인: HB UI-1·SYNC UI-5를 정적 뷰와 배포본에서 봄 — 폰트·배지·축소 다 됨, 실제 목업 수준 · **되먹임 이슈 열**: #126 view_build 외부 저장소 · #127 STD-001 2.7 빈 곳(자기 완결↔공통 틀·요소 표 부분집합·대화상자) · #128 캔버스 인라인 스타일·도구 이름 · #129 새 저장소 STD 사본 갱신 · #130 토글이 배치 가림 · #132 FRAME_CSS 제약(tr·svg·순서) · #133 check_tokens 제목 열쇠 · #134 배치 열 폭(늘 60% 축소) · #135 정적 뷰 해시 · 검토: #131이 UI-16 그림 셋을 자리표시로 바꿈(절대경로면 앱에선 뜬다) |

**왜 카드인가.** 문서만 바뀌지만 12화면·HB·안내 되먹임이 한 시험이다. 시험이 안내를 고치면 Z의 규약이 바뀐다.

---

#### AB 새 저장소는 규약 링크만

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 1.1 · [[SYNC-UC-001#UC-A1]] 4 · [[SYNC-UC-001#UC-S6]] 1 · [[SYNC-MS-009#git.sync_readme]] · #113 · #129 · 사용자 결정 2026-09-22 |
| 구현 | `init_specs`가 템플릿 12개를 복사하지 않는다 — 빈 단계 디렉터리 13 + README, **14파일**. README 첫 문단이 `SPECS_URL`로 싱크독 저장소의 규약·템플릿을 가리킨다. `git.sync_readme` 신설, `ProjectService.rebuild_index`가 인덱스보다 **먼저** 부른다. `RebuildResult.readme_updated` |
| 테스트 | `init_specs` 14파일·링크·`_templates` 없음 · `sync_readme` 셋(낡음·같음·없음) · `rebuild_index`가 README 먼저, 두 번째는 커밋 없음 · 남의 프로젝트 not-found |
| 선행 | — |
| 완료 | 2026-09-22 · 브랜치 `card/AB-readme-links` · spec 11 + code 2 · 테스트 220(신설 4, 고침 5) · `validate` 0/0 · `check_code` 110/110 · `check_ui` 12/12 · `check_dom` 10·10·10 · `check_tokens` 91/0 · `check_view_css` 셋 다 같음 · 사람 확인은 배포 뒤(HB에서 재구축 한 번) · 되먹임: `sync_readme`는 `fetch` 뒤에 비교해야 한다 — `commit_push`가 토큰 URL로 밀어 `origin/main` 추적 참조가 안 갱신된다(MS-009에 반영) · 발견 #137(상태 토글이 아직 처리 안 된 커밋을 되돌린다 — 카드 AA 완료란이 실제로 날아갔다) |

**왜 카드인가.** 사본을 복사하는 구조 자체가 틀렸다. 실측으로 저장소 8/8이 낡은 README를 들고 있었고 그중 넷은 두 세대 전이라 작업 단위 규약(1.8)과 DOM 셋 순서(2.6)가 아예 없었다 — MS-009가 「여기 없으면 규약이 없는 것과 같다」고 못 박은 두 줄이다. 템플릿은 `get_template`이 이미 내장본으로 우회하고 있었으므로(#94) 저장소 사본은 아무도 안 읽는 낡은 짐이었다.

**왜 재구축 버튼인가.** 이미 만들어진 여덟 저장소는 앞으로의 규칙으로는 안 고쳐진다. 사람이 프로젝트마다 한 번 누르면 README가 새 판이 된다 — 앱이 사용자 저장소에 쓰는 유일한 일이라 버튼 뒤에 둔다. 옛 `_templates/`는 지우지 않는다(사용자 파일을 지우는 일은 더 위험하다).

---

#### AC 배치는 위, 요소 표는 아래

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-002]] V-UI · [[SYNC-UI-002#UI-5]] · #134 · #130 · #135 · #132 · 사용자 결정 2026-09-22 |
| 구현 | 화면 섹션을 좌우(`.split`)에서 **세로**(`.wfstack`)로 — 배치가 본문 전폭(1280이 넓은 창에서 1:1), 요소 표·규칙·시나리오는 아래. 배치 위 도구 줄(자연폭·배율 · 맞춤/원래 크기 · 전체보기)로 #130. 「전체보기」는 그림 전체보기(7.6)와 같은 층에 같은 srcdoc을 scale. FRAME_CSS를 문서 `<style>` **앞**으로(#132) · 정적 뷰 `#item-UI-N` 해시(#135) · `check_view_css` 넷째 쌍 `wireframeCss`↔`WF_SCREEN_CSS` |
| 테스트 | `check_ui` 12/12(UI-5에 7.7~7.10) · `check_view_css` 넷 · `wf_build --selftest` · `view_build --all` · 사람이 넓은 창·좁은 창·전체보기·정적 뷰를 본다 |
| 선행 | Z · AA |
| 완료 | 2026-09-22 · 브랜치 `card/AC-wf-stack` · spec 5 + code 1 · `validate` 0/0 · `check_code` 110/110 · `check_ui` 12/12(UI-5 요소 45) · `check_dom` 10·10·10 · `check_tokens` 91/0 · **`check_view_css` 네 쌍 다 같음** · `wf_build --selftest` · `view_build --all` 오류 0 · 테스트 220 · 사람 확인(배포 뒤 브라우저): 정적 뷰 UI-5가 `#item-UI-5`로 바로 열리고 1406폭 1:1 · 앱 UI-5도 1361폭 1:1(창 1600) · 「전체보기」가 7.6 층에 같은 srcdoc을 100%로 띄우고 Esc로 닫힘 · 표 행↔배치 양방향 강조 · 창 1100에서 43% 축소와 「원래 크기」↔「맞춤」(가로 스크롤) · HB UI-1이 82%로 본문을 채우고 폰트·배지 그대로 · `[data-el]` 42개 전부 `position:relative` 유지(FRAME_CSS를 앞으로 옮겨도 배지가 산다) · 되먹임: 창이 1930px보다 좁으면 여전히 축소된다(목차 186 + 패널 250 + 여백) — 1:1로 보는 길은 「전체보기」다 |

**왜 카드인가.** 카드 AA가 12화면을 제대로 그려 놨는데 뷰가 늘 57%로 줄여 보여 준다. 원인이 세 겹(`--doc-w` 1440 → `.split` 53:47 → `.left` 패딩)이라 한 줄로 안 고쳐지고, 같은 파일을 만지는 #130·#132·#135가 함께 붙는다.

---

#### AD 저장소에 쓰기 전에 먼저 읽는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-004#DEV-19]] · [[SYNC-UC-001#UC-H8]] 1d · [[SYNC-MS-007#pipeline.read_pending]] · [[SYNC-DOM-001#StatusChange]] · #137 · 사용자 결정 2026-09-22 |
| 구현 | `pipeline.read_pending(code, user)` 신설 — `fetch` 후 밀렸으면 `process_commit`. 저장소에 쓰는 다섯 경로(상태 토글·되돌리기·되살리기·휴지통·MCP 저장)가 **세션·락을 열기 전에** 부른다. `change_status`는 커밋할 본문도 `origin/main`에서 읽어 `status:` 줄만 교체. `_set_status` 하나로 모음 |
| 테스트 | 저장소를 앞세운 뒤 각 동작 → 그 커밋 내용이 살아 있다 · 상태 커밋 `--numstat`이 `1 1` · `read_pending` 멱등 · `github` 경로에선 안 불린다 |
| 선행 | — |
| 완료 | 2026-09-22 · 브랜치 `card/AD-read-before-write` · spec 9 + code 1 · 테스트 **223**(신설 3) · `validate` 0/0 · `check_code` 111/111 · `check_ui` 12/12 · `check_dom` 10·10·10 · `check_tokens` 91/0 · `check_view_css` 네 쌍 · 사람 확인(배포 뒤 2026-09-22): **이 줄이 그 확인이다** — PR을 머지하고 파이프라인이 읽기 전에 곧바로 SYNC-CODE-001을 완료로 올렸다. 옛 구현이면 이 문장이 사라졌을 자리다 · **되먹임 둘**: ① 쓰기 경로 다섯이 쓰기 락 밖에서 `fetch`하니 동시 저장 둘이 같은 작업 사본을 동시에 건드려 git이 죽었다 — **읽기 락**(`_read_lock`, 쓰기 락과 다른 것)을 따로 두고 락 안에서 `last_processed_commit`을 다시 읽는다 ② `last_processed_commit`이 비어 있으면 읽지 않는다 — 그 값이 비는 것은 등록 중뿐이고 초기화·재구축이 자기가 읽는다 |

**왜 카드인가.** 한 줄 고침이 아니다. 저장소에 쓰는 모든 경로의 순서가 바뀌고(읽기가 앞선다), 명세가 붙들고 있던 전제 둘(MS-007 4단계의 `current_body`, SEQ-5 Note 「본문이 안 바뀐다」)이 함께 바뀐다. 데이터가 실제로 사라진 사고라 회귀 장치도 같이 둔다.

**왜 아무도 못 봤나.** 세 가지가 겹쳤다. ① 명세가 DB 캐시를 쓰기 출처로 삼도록 적혀 있었다 ② `git.commit_push`의 `reset --hard`가 「원격이 앞서면 push가 거부된다」는 안전망(UC-S7 2a)을 없앴다 ③ 테스트가 커밋 **제목**만 봤다. 셋 중 하나만 없었어도 잡혔다.

---

#### AE 화면 문서 안내를 코드가 하는 일에 맞춘다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 2.7 · [[SYNC-STD-004#DEV-17]] · [[SYNC-STD-002]] V-UI · #127 · #128 · #132 · 사용자 결정 2026-09-22 |
| 구현 | 2.7에 기계적 제약 일곱 행(요소 표 부분집합 · `data-el` 붙이는 곳 · 블록 하나 · 상태 여럿 · 대화상자 · 디자인 토큰 장 · 제목) · 「만드는 법」에 도구 없을 때·캔버스 스타일 위치 · **뷰가 배지를 얹는다**(`.wfbadge`, svg·치환 요소·표 행) · `check_ui`가 **배치 html로 문서를 고르고 화면 0이면 실패** · 첫 블록만 · 중복 파일·배지 없는 태그 알림 · 좌우 옛말 셋 |
| 테스트 | `check_ui` 12/12 유지하며 알림 4 · 제목에 두 낱말을 다 넣어도 12화면을 찾는다 · 화면 0이면 exit 1 |
| 선행 | Z · AA · AC |
| 완료 | 2026-09-22 · 브랜치 `card/AE-ui-guidance` · spec 8 + code 1 · `check_ui` 화면 12/12 **알림 4**(배지 안 붙는 태그 10곳: UI-3 입력 넷 · UI-5 질문 입력 · UI-8 svg 셋 · UI-13 입력 둘) · `check_view_css` 네 쌍(프레임 CSS 391→666바이트) · 테스트 223 · `validate` 0/0 · `check_code` 111/111 · `check_dom` · `check_tokens` 91/0 · 일부러 깨뜨려 확인: 제목에 두 낱말을 다 넣어도 12화면을 찾고, 화면 절이 없으면 **exit 1** · 사람 확인(배포 뒤): UI-8 svg 화살표 3.2·3.3·3.4에 번호가 **보인다**(전에는 안 보였다), 표 행을 누르면 얹은 배지도 같이 강조된다, 정적 뷰도 같다 · **남긴 것**: 알림 4가 가리키는 10곳은 감싸는 요소로 옮기는 편이 낫지만 배치를 또 건드리는 일이라 다음에 |

**왜 카드인가.** 새 에이전트 둘의 되먹임이 한 곳을 가리켰다 — 2.7이 **무엇을 그릴지**는 말하면서 **통과하려면 지켜야 할 기계적 제약**은 코드에만 두었다. 문장만 고치면 다음 사람이 또 같은 데서 막힌다. 그래서 안내와 검사기를 같이 고친다.

**가장 나빴던 것.** 2.7이 권한 대로 제목에 두 낱말을 다 넣고 문서를 둘로 나누면, 검사기가 엉뚱한 파일을 골라 화면을 하나도 못 찾은 채 **「화면 0, 불일치 0」 exit 0**을 냈다. STD-004가 이름 붙인 실패(「0건이 안 봤다는 뜻일 수 있다」)가 규약 자신의 권고로 재현되고 있었다.

---

#### AF push가 몇 초 만에 반영되고, 화면이 언제 확인한 값인지 말한다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-INFRA-001]] 7장 · [[SYNC-UC-001#UC-G2]] · [[SYNC-MS-001#ProjectService.ensure_hook]] · [[SYNC-MS-009#github.create_hook]] · #115 · 사용자 결정 2026-09-22 |
| 구현 | `github.create_hook` 신설 — 등록할 때 앱이 push 통지를 걸고(실패해도 등록은 마친다), 이미 있는 저장소는 관리 화면 버튼으로. 받는 쪽은 `push`·`refs/heads/main`만, 비밀번호가 비면 전부 거부. `ProjectService.ensure_hook`·`sync_now`(본체는 `read_pending` 재사용) · `read_pending`이 밀린 게 없어도 `fetched_at`을 적는다 · 화면에 **확인 시각**·**통지 상태**·**지금 가져오기**·**통지 걸기** · OAuth 범위에 `admin:repo_hook` |
| 테스트 | `create_hook` 멱등·권한 없으면 예외 · `verify_signature`가 빈 비밀번호에 항상 False · `ping`·작업 브랜치·삭제 push 무시 · `ensure_hook` 넷 · `sync_now` · `read_pending`이 밀린 게 없어도 `fetched_at` 갱신 |
| 선행 | AD |
| 완료 | 2026-09-22 · 브랜치 `card/AF-webhook` · spec 10 + code 1 + `fix(#145)` · 테스트 **230**(신설 7) · 리비전 `0013` · `validate` 0/0 · `check_code` 114/114 · `check_ui` 12/12 · `check_dom` 10·10·10 · `check_tokens` 91/0 · `check_view_css` 네 쌍 · 사람 확인(배포 뒤): **저장소 아홉 전부에 통지를 걸었다**(`gh api … /hooks`로 확인 — `https://syncdoc.dpdns.org/hooks/github` events=push) · 두 번째로 눌러도 훅이 안 늘고 `created=false` · 「지금 가져오기」가 0을 돌려주며 확인 시각을 갱신 · **기존 토큰이 옛 범위(`repo`)를 들고 있어 다시 로그인하지 않고도 걸렸다** — 새 범위는 앞으로 받을 토큰을 위한 것 · 되먹임 **#145**: `ensure_hook`이 `flush`만 하고 라우터가 커밋하지 않아 GitHub에는 훅이 생기는데 `hook_id`가 안 남았다. 같은 세션만 보던 테스트가 못 잡아 **다른 요청에서도 보이는지**를 고정했다 |

**왜 카드인가.** 명세가 **주 경로**라고 적어 둔 통지를 코드가 한 번도 등록하지 않았다. 실측으로 두 저장소 다 훅이 비어 있었고(`gh api … /hooks` → `[]`), 실제 경로는 5분 폴링 하나였다. INFRA 7장은 이유를 「Quick Tunnel 주소가 바뀌어 못 건다」로 적었는데 고정 주소는 카드 Q에서 이미 생겼다 — 전제가 사라진 채 숙제만 남아 있었다.

**두 문제를 함께 푼다.** 통지는 **반영이 늦은 것**을 고치고, 확인 시각 표시는 **「최신」이 거짓일 수 있는 것**을 고친다. 통지를 걸어도 유실되면 「최신」은 여전히 거짓이 되므로 둘은 서로를 대신하지 못한다. 「최신」의 낡음은 사고가 아니라 테스트 셋이 단언하던 계약이었다 — 계약째 바꿨다.

**권한이 는다.** 통지를 걸려면 `admin:repo_hook`이 필요해 OAuth 범위를 넓혔다. 이미 로그인한 토큰은 옛 범위라 **한 번 다시 로그인해야** 통지 걸기가 동작한다.

---

#### AG 템플릿은 서브타입마다, 에이전트는 서브타입을 말하고 받는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-001]] 1.1·2.6·2.8 · [[SYNC-API-002#get_template]] · [[SYNC-STD-004#DEV-17]] · #114 · 사용자 결정 2026-09-23 |
| 구현 | DOM·API 템플릿을 서브타입별로 — `DOM-도메인.md`·`DOM-클래스.md`·`DOM-ERD.md`·`API-REST.md`·`API-MCP.md`. `DOM.md`·`API.md`는 고르는 안내. `get_template`이 `subtype`을 받아 그 서브타입의 항목 패턴·필수 절·항목 블록·뼈대를 준다(안 주면 필수 절이 비고 `subtypes`가 온다). `tools/check_templates.py` 신설 · `validate.py`의 서브타입 판정을 서버처럼 첫 매치로 · 검사기가 찾은 둘(SEQ 항목 예시 없음 · UI 예시 제목 없음)도 고침 |
| 테스트 | `get_template` 서브타입별 넷 · 서브타입 없이 · 틀린 서브타입 · **템플릿 열다섯을 문서 ID만 채워 서버 validate에 넣으면 위반 0·경고 0** |
| 선행 | — |
| 완료 | 2026-09-23 · 브랜치 `card/AG-subtype-templates` · spec 6 + 템플릿 9 + code 1 · 테스트 **233**(신설 3) · `validate` 0/0 · **`check_templates` 16/16**(신설) · `check_code` 114/114 · `check_ui` 12/12 · `check_dom` 10·10·10 · `check_tokens` 91/0 · `check_view_css` 네 쌍 · 사람 확인(배포 뒤): 실제 MCP 연결로 `get_template(HB, DOM, subtype="클래스")`가 필수 절 다섯·항목 패턴·항목 블록·클래스 뼈대를 준다. 서브타입 없이 부르면 필수 절이 비고 `subtypes`에 셋이 온다 · **되먹임**: 새 검사기가 돌자마자 DOM·API 밖의 결손 둘을 더 찾았다 — SEQ 템플릿에 항목 예시가 없었고 UI 템플릿 제목이 비어 있었다. 함께 고쳤다 · MCP 클라이언트는 도구 목록을 연결할 때 받아 두므로, 이미 붙어 있던 세션은 다시 붙어야 새 설명(`subtype`)이 보인다 — 인자는 그 전에도 통한다 |

**왜 카드인가.** 템플릿은 타입마다 한 파일인데 필수 절은 서브타입마다 다르다. DOM 템플릿은 도메인 모델 골격 하나라, 그대로 쓴 클래스 명세는 네 절, ERD는 세 절이 **반드시** 비었다. HB에서 세 문서가 전부 같은 골격으로 시작해 두 개를 다시 올렸다(커밋 제목이 「필수 절 이름 맞춤」). 같은 병이 API 템플릿에도 있었다 — 괄호로 겸업시킨 절 제목(`엔드포인트 (또는 도구)`)을 검사기가 못 읽는다.

**왜 아무도 못 봤나.** 물어볼 길이 없었다 — `get_template`에 서브타입 자리가 없어 DOM의 필수 절이 늘 빈 배열로 왔다. 그리고 모든 검사기가 `_templates/`를 건너뛰어 템플릿이 규약을 못 지키는 것을 잡을 장치가 없었다.

---

#### AH 목표·제약도 본문까지 — 뷰는 원본 문장을 버리지 않는다

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-STD-002]] V-PRD·V-INFRA · [[SYNC-STD-001]] 2.2·2.5·4장 · [[SYNC-MS-002#SpecService.validate]] · #120 · 사용자 결정 2026-09-23 |
| 구현 | `view_build.py`·`md.ts`·`views.ts`에 `split_items`/`splitItems` — 절 본문을 원본 순서대로 항목과 항목 밖 문장으로 가른다(`item_blocks`는 그것을 거른 것). 목표·제약을 R·N과 같은 **카드**로(카드 하나를 셋이 같이 — 머리 ID·제목·`하위 N`, 몸 본문 전부, 바닥 「이 목표/제약을 근거로 삼은 문서」). 요구사항 절 머리·소절 머리 문장을 그대로, 빈 소제목을 없앤다. 제약 꼬리 하드코딩(「이 설계의 두 축」)을 지우고 SYNC-INFRA-001의 그 문단을 절 머리로 옮긴다. `SpecService.validate` 7 `constraint.source`(원형 `tools/validate.py`·화면 문구도) · `view_build.py --selftest` 신설 |
| 테스트 | `constraint.source` — 출처 있음·없음·`출처: RFQ`(링크 아님)·문단 끝 `근거:`만·코드블록 안 `출처:`만 · SYNC 명세 전부 위반 0·경고 0 유지 · `view_build --selftest`(G·C 본문 · 절 머리·소절 머리 · 빈 소제목 없음 · 앵커) · `check_templates` · 사람이 배포 뒤 HB·SYNC·QBOT의 PRD·INFRA를 브라우저에서 |
| 선행 | — |
| 완료 | 2026-09-23 · 브랜치 `card/AH-item-bodies` · spec 8 + code 2 · 테스트 **239**(신설 1) · `validate` 0/0 · `check_code` 114/114 · `check_ui` 12/12 · `check_dom` 10·10·10 · `check_tokens` 91/0 · `check_view_css` 네 쌍 · `check_templates` 16/16 · **`view_build --selftest`**(신설 — 옛 동작을 흉내 내면 4건씩 실패) · 앱 포트를 일회성으로 묶어 돌려 SYNC PRD·INFRA와 시험 문서 둘에서 정적 뷰와 **같은 HTML**(앱 전용 `data-item`·`data-ref` 빼고) · 사람 확인(배포 뒤 2026-09-23, 브라우저): HB PRD G1·G2와 HB INFRA C1~C5가 카드로 본문까지 보인다 · SYNC PRD 목표 카드 7장, 「11개 기능 전부 v1 범위다」, 빈 소제목 0 · SYNC INFRA 절 머리에 「C7이 이 설계의 축이다」 · QBOT 목표 머리 문단과 C9 한도 표 · 카드를 누르면 참조 패널, `#item-C1`로 진입 · `get_template`이 새 항목 블록 문장과 템플릿을 준다 · 새 경고는 로컬로 돌려 보니 BBS 제약 넷·QBOT C14에만 걸린다(VA·HB·SYNC 통과) — 그 저장소들은 손대지 않았다 · **되먹임 둘**: ① 절 구분선 `---`가 마지막 항목 블록에 들어가 마지막 카드 바닥에 빈 가로줄이 생긴다(SYNC C9. 요구사항 마지막 카드는 전부터) ② 카드의 `하위 N`과 참조 패널(UI-5 8.1)의 하위 참조가 다른 기준으로 센다 — 패널은 항목 밖에서 건 참조(HB-SCN-001 대응표 → G1)를 빼고, 문서 전체를 가리킨 참조(`[[QBOT-INFRA-001]]`)는 모든 항목 아래에 보인다. 표였을 때도 같았고 카드와 패널이 나란히 보이며 드러났다 · 남긴 것: #152 · #153 |

**왜 카드인가.** 코드는 규약(STD-002 V-PRD·V-INFRA)대로 버리고 있었다 — 고칠 것은 규약이라 DEV-15의 `fix`가 아니다. 규약은 「G: 한 줄」·「제약 한 줄 + 출처」라 표가 맞았는데, STD-001 5장 예시와 `get_template`은 제목 아래에 본문을 두었다. 에이전트는 예시를 따라 근거 문장을 쓰고, 뷰는 규약을 따라 그것을 버렸다. 규약·예시·뷰가 서로 다른 말을 하고 있어서 셋을 같이 고친다.

**왜 아무도 못 봤나.** SYNC 자기 문서는 G가 제목뿐이고 C가 출처 한 줄이라 표로 잃는 것이 없었다. 처음 쓰는 사람(HB 온보딩 시험)이 예시대로 본문을 쓰자 드러났다. 꼬리 문단 하드코딩은 카드 V가 원본 문장을 바꾼 날부터 SYNC에서도 틀렸지만, 정적 뷰와 앱이 **똑같이** 틀려 대조로도 못 잡았다(#153).

---

#### AI 앱 밖이 실패한 오류는 424 — 앞단이 덮지 않게

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-API-001]] 2장 · [[SYNC-STD-004#DEV-5]] · [[SYNC-INFRA-001]] 5장 · #76 · 사용자 결정 2026-09-23 |
| 구현 | `PushFailed`·`RepoCreateFailed`·`LlmUnavailable`의 status 502 → **424**. `tests/core/test_errors.py` 신설 — 에러 클래스 전부를 훑어 502·504가 있으면 실패. 웹 클라이언트(`client.ts`)는 problem+json이 아닌 오류 본문을 `urn:syncdoc:http`로 접고 「HTTP {status} — 서버 앞단(Cloudflare)이 보낸 오류 페이지입니다. 서버가 꺼져 있거나 터널이 끊겼을 수 있습니다.」를 보인다(`call`·`stream` 둘 다) |
| 테스트 | 가드 둘(502·504 없음 · 셋이 424) · 라우터에서 `PushFailed`가 나면 424 + problem+json(`type`·`reason`) · 임시 터널(Quick Tunnel) 실험으로 Cloudflare가 502·504만 덮고 424는 통과시키는지 · `client.ts`를 묶어 가짜 fetch로 한 줄 문구 확인 |
| 선행 | — |
| 완료 | — |

**왜 카드인가.** 명세(API-001 2장)가 502라고 적었고 코드는 그대로 따랐다 — 바꾸는 것은 명세다(카드 AH와 같은 기준). 502는 뜻으로는 맞는 코드였다(앱 밖이 실패했다). 그런데 Cloudflare가 원본의 502·504를 자기 페이지로 바꾸는 것은 문서에 적힌 기본 동작이고 무료 플랜에는 끄는 설정이 없다. 앞단을 바꿀 수 없으니 코드를 고른다.

---

## 2. 통합 테스트 시나리오

시나리오 S1~S7을 그대로 E2E 테스트로. 각 슬라이스의 `테스트` 행에 나눠 들어가 있다. 전부 통과하면 PRD 성공지표 측정을 시작한다.

| 시나리오 | 슬라이스 | 검증하는 것 |
|---|---|---|
| [[SYNC-SCN-001#S1]] | B1 | MCP로 문서가 쌓이고 커밋·참조가 생긴다 |
| [[SYNC-SCN-001#S2]] | B2 · V | 웹에서 읽고 완료로 올린다 |
| [[SYNC-SCN-001#S3]] | B1·B4 | 코딩 중 에이전트가 항목·참조를 조회한다 |
| [[SYNC-SCN-001#S4]] | B3 · V | 상위 항목이 사라지면 하위 참조가 끊어진 것으로 보인다 |
| [[SYNC-SCN-001#S5]] | B2 | 다른 툴을 쓰는 사람이 토큰 발급 후 MCP로 붙는다 |
| [[SYNC-SCN-001#S6]] | B2·B4 | 그래프·순서 읽기·원본 탭 |
| [[SYNC-SCN-001#S7]] | B4 | 플랫폼 없이 push한 것이 반영된다 |

---

## 3. CODE 단계 전 결정

MINISPEC이 낸 미결 셋. 카드에 들어가기 전에 정해야 한다.

- [x] **삭제된 파일 push** → 문서는 남기고 `draft` + 규약 오류 `file.deleted`, 항목 전부 `is_deleted`, 하위에 끊어진 참조. `SpecService.mark_deleted` 신설 (B4)
- [x] **같은 문서 안 참조 전파** → 전파한다. 같은 문서 항목도 대상 (B3) — V에서 전파 자체가 사라짐
- [x] **원인 항목이 여럿일 때** → 원인마다 플래그 따로. 확인도 따로 (B3) — V에서 플래그 자체가 사라짐

- [x] **원격 기본 브랜치** → `main` 고정 (B1)
- [x] **React 라이브러리** → react-markdown+remark-gfm · mermaid · react-flow+dagre · diff 직접 (B2·B4). 인프라 3장에 기록

결정 전부 끝. A 카드부터 시작할 수 있다.

## 4. 커밋·PR 목록

슬라이스 카드의 `완료` 행에 기록한다. PR 하나 = 슬라이스 하나(DEV-15).

작업은 `feat/a-foundation` 한 줄에서 하고, 카드가 끝날 때 그 자리에서 `card/{슬라이스}` 브랜치를 떼어 PR을 만든다.

| 슬라이스 | 브랜치 | 커밋 | PR | 날짜 |
|---|---|---|---|---|
| A | `card/A` | `9d99b93`~`ad06e7a` | #1 | 2026-09-08 |
| B1 | `card/B1` | `0697ad2`~`9070b2b` | #2 | 2026-09-09 |
| B2 | `card/B2` | `6edc202`~`95fd483` | #3 | 2026-09-09 |
| B3 | `card/B3` | `021cded`~`193dcf6` | #4 | 2026-09-09 |
| B4 | `card/B4` | `a592237`~`52b966c` | #5 | 2026-09-09 |
| C | `card/C` | `6389635`~`00d12c3` | #21 | 2026-09-10 |
| D6 | `card/D6` | `3f0ab95`~`88d14a8` | #22 | 2026-09-10 |
| D1 | `card/D1` | `4ad5870`~`0f8c7c6` | #23 | 2026-09-10 |
| D2 | `card/D2` | `a0d1259`~`f5520f2` | #24 | 2026-09-10 |
| D3 | `card/D3` | `1320d99`~`1fea959` | #25 | 2026-09-10 |
| D4 | `card/D4` | `15749ef`~`06fe01d` | #26 | 2026-09-10 |
| D5 | `card/D5` | `39cea75`~`62d8f0f` | #27 | 2026-09-10 |
| (핸드오프 대조) | `design/handoff` | `28a78e7`~`74d945a` | #28 | 2026-09-10 |
| E | `card/E-backup` | `c8f2749`~`e715423` | — | 2026-09-11 |
| F | `card/F-repo-create` | `a11f698`~ | — | 2026-09-14 |
| U | `card/U-ask-panel` | `3fa72d0`~ | #95 · #104 | 2026-09-21 |
| Y | `card/Y-ask-react` | `eef87b6`~ | #109 | 2026-09-22 |
| Z | `card/Z-wf-iframe` | `bccf473`~ | #121 | 2026-09-22 |
| AA | `card/AA-sync-redesign` · hb#1 | `9fab38b` | #131 | 2026-09-22 |
| AB | `card/AB-readme-links` | `6a0fd97`~ | — | 2026-09-22 |
| AC | `card/AC-wf-stack` | `f2a6f4d`~ | — | 2026-09-22 |
| AD | `card/AD-read-before-write` | `9ea83ca`~ | — | 2026-09-22 |
| AE | `card/AE-ui-guidance` | `8331a96`~ | #142 | 2026-09-22 |
| AF | `card/AF-webhook` | `1770920`~ | #144 · #146 | 2026-09-22 |
| AG | `card/AG-subtype-templates` | `8850433` | #148 | 2026-09-23 |
| (#124) | `fix/124-cache-headers` | — | #124 | 2026-09-23 |
| AH | `card/AH-item-bodies` | `f0ae4f5` | #154 | 2026-09-23 |
| AI | `card/AI-424` | — | — | 2026-09-23 |
| V | `card/V-solo` | `9019be1`~`a3eba3f` | #98 | 2026-09-21 |
| W | `card/W-owner` | `79a10bb`~`8ad75f9` | #102 | 2026-09-21 |
| X | `card/X-ui-doc` | `7a4e821`~ | #103 | 2026-09-21 |

**핸드오프 대조는 카드가 아니다.** D1~D5 여러 장에 걸쳐 있어 슬라이스로 나누지 않았고, 무엇을 고쳤는지는 각 카드의 `완료` 행에 적었다. PR 하나 = 슬라이스 하나 규칙의 유일한 예외다.

`card/C`는 카드 C와 그 전후의 명세 개정(미결 닫기·디자인 핸드오프 반영·카드 D1~D6 신설)을 함께 담는다. 명세 개정은 카드가 아니라서 따로 뗄 자리가 없었다.

## 5. 미결사항

- [x] B1에서 `detect_impact` 스텁 — B3에서 해제할 때 B1 카드를 미완으로 되돌리나 — 결정: 되돌리지 않는다. 앞 카드는 스텁 행에 어느 카드가 푸는지 적고 그대로 두며, 해제한 카드가 완료란에 해제 사실을 적는다. B1·B3·B4가 이미 그렇게 기록돼 있다 ([[SYNC-STD-004#DEV-12]])
