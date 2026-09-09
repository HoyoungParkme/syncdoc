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
