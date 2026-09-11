---
doc_id: SYNC-MS-001
type: MS
title: MINISPEC — ProjectService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — ProjectService

## 0. 이 문서가 다루는 것

`core/project/service.py`의 함수 5개. 클래스 명세 [[SYNC-DOM-002]] 4.1의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`projects`·`repositories`만. **`documents`를 모른다** — 단계 요약은 `queries`.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ProjectService.init_project]] | 프로젝트 초기화 |
| [[#ProjectService.list_projects]] | 목록 |
| [[#ProjectService.get]] | 코드 → 프로젝트 |
| [[#ProjectService.repo_status]] | 동기화 상태 |
| [[#ProjectService.delete_project]] | 등록 해제·작업 사본 회수 |
| [[#ProjectService.rebuild_index]] | 재구축 위임 |

---

## 2. 함수

#### ProjectService.init_project 프로젝트 초기화

**시그니처** `async def init_project(remote_url: str, code: str, name: str, user: User, import_existing: bool = False) -> Project`

근거: [[SYNC-SEQ-001#SEQ-4]] · [[SYNC-UC-001#UC-A1]] · [[SYNC-API-001#POST/api/projects]] · [[SYNC-API-002#init_project]]

**처리**
0. **코드 단위 락**을 잡는다(`asyncio.Lock`, code별). 같은 코드로 동시에 두 번 들어오면 서로의 작업 사본을 지운다(UC-A1 2c)
1. if `not re.fullmatch(r"[A-Z]{1,4}", code)` → `! project-code-invalid {rule}` (2b)
2. if `DB: projects where code` → `! project-code-conflict {code}` (2a)
2a. if `DB: repositories where remote_url 정규화 일치` → `! repository-already-registered {code: 그 프로젝트}` (UC-A1 2d). 정규화는 소문자 + 끝 `/`·`.git` 제거 — `web/routers/hooks.py`가 webhook 저장소를 찾을 때와 같은 규칙
3. `workdir = config.REPOS_DIR / code` · if 이미 있음 → 지운다 (이전 실패 잔재)
4. `token = AccountService.github_token_for(user)` · `git.clone(remote_url, workdir, token)` · if 실패 → workdir 삭제, `! push-failed {reason: clone}`
5. `has = git.exists(workdir, "docs/specs")` — 커밋이 하나도 없는 빈 저장소는 `false`다([[SYNC-MS-009#git.exists]]). 9단계가 만드는 커밋이 그 저장소의 첫 커밋이 된다 (UC-A1 기본 흐름 3)
6. if `has and not import_existing` → `n = len(git.list(workdir, "docs/specs/*/*.md"))`, workdir 삭제, `! existing-specs {doc_count: n}` (3a)
7. **트랜잭션**: `DB: projects insert (code, name)`, `DB: repositories insert (project_id, remote_url, workdir_path, last_processed_commit=None, registered_by_user_id=user.id)` — 누가 등록했는지 기록. private 지원 때 이 사람 토큰으로 fetch한다
8. if `has and import_existing` → `pipeline.rebuild(code)` (3a2. 락·트랜잭션은 그쪽) · `last_processed_commit`은 rebuild가 채움
9. else → `files = git.init_specs(workdir)` (11단계 + `STD/` 디렉터리, `_templates/` 12개, `assets/`) · `hash = git.commit_push(workdir, message=f"chore({code}): init syncdoc", author=Author(human, user, None, web), files=files)` · if 실패 → 7단계 롤백, workdir 삭제, `! push-failed` (4a) · `DB: repositories update last_processed_commit=hash`
10. `→ Project`. **`ProjectSummary`는 입구(MCP 도구·라우터)가 `queries.project_summary()`로 만든다** — 서비스가 `queries`를 부르면 순환이다(클래스 3.2에 PS→QR 없음). 신규면 11칸 null

**호출하는 것** `AccountService.github_token_for` · `git.clone` `exists` `list` `init_specs` `commit_push` · [[SYNC-MS-007#pipeline.rebuild]]

**테스트 관점** 빈 저장소 → `docs/specs/` 생김, 커밋 하나, 11칸 null · `docs/specs/` 있는 저장소 → `existing-specs`, workdir 없음, DB 행 없음 · `import_existing=true` → 재구축 결과 · clone 권한 없음 → `push-failed`, 아무것도 안 남음

---

#### ProjectService.list_projects 목록

**시그니처** `list_projects() -> list[Project]`

**처리** `DB: projects join repositories order by code`

---

#### ProjectService.get 코드 → 프로젝트

**시그니처** `get(code: str) -> Project`

**처리** `DB: projects join repositories where code` · if 없음 → `! not-found {resource: project, id: code}`. `Project.repository`로 저장소 접근

---

#### ProjectService.repo_status 동기화 상태

**시그니처** `async def repo_status() -> list[RepoStatus]`

근거: [[SYNC-SEQ-001#SEQ-20]] · UI-14 표 2

**처리** **원격을 안 탄다. `git.fetch`를 부르지 않는다.** 저장소마다 `→ RepoStatus(code, remote_url, last_processed_commit, synced_at, behind_by, fetched_at, backed_up_at, backup_stale, error=None)`.

`backed_up_at`만은 DB가 아니라 **git에서 읽는다** — `git.last_commit_at(workdir, "backup/tracking.json")`. **DB를 잃어도 남아야 하는 값이라 백업 자신과 같은 곳에 산다**(인프라 6.1). 네트워크를 타지 않는 로컬 조회 하나이므로 이 함수가 피하려던 것(원격 하나가 안 응답해 관리 화면 전체가 매달리는 것)과 다르다. 저장소마다 감싸서 실패하면 `backed_up_at=None` · `error="backup: {사유}"`로 두고 다음 저장소를 계속한다 — 작업 사본이 망가진 프로젝트 하나가 표 전체를 죽이지 않는다.

`backup_stale`은 **서버가 판정한다** — `backed_up_at`이 있고 `BACKUP_INTERVAL_SECONDS`의 두 배가 넘게 지났으면 참. 화면이 계산하지 않는 이유는 **화면이 주기를 모르기 때문**이고, 주기를 응답에 실으면 화면이 검사를 하게 된다. `backed_up_at`이 `None`이면 `backup_stale`도 거짓이다 — 한 번도 안 한 것과 멈춘 것은 다르다.

`behind_by`·`fetched_at`은 폴링([[SYNC-MS-007#scheduler.catch_up]])이 갱신한다. 예전에는 이 함수가
저장소마다 순차로 fetch를 돌렸는데, 폴링이 5분마다 같은 일을 이미 하고 있어 이중이었고, 원격
하나가 응답하지 않으면 관리 화면 전체가 그 요청에 매달렸다(git 명령에 타임아웃이 없다).

`behind_by`가 `null`이면 아직 한 번도 못 받아본 것이다 — 방금 등록했거나 폴링이 계속 실패하는
경우다. 화면은 `fetched_at`으로 "언제 기준인지"를 함께 보여준다.

**테스트 관점** 이 함수가 `git.fetch`를 부르지 않는다 · 폴링이 적어 둔 값을 그대로 돌려준다 · 등록 직후에는 `behind_by=None` · 백업이 없으면 `backed_up_at=None`이고 `backup_stale=false` · 주기의 두 배가 지난 백업은 `backup_stale=true` · 작업 사본이 없어도 다른 저장소는 그대로 나온다

---

#### ProjectService.delete_project 등록 해제

**시그니처** `async def delete_project(code: str) -> None`

근거: [[SYNC-API-001#DELETE/api/projects/{code}]] · 인프라 9장(작업 사본 회수)

**처리** — 코드 단위 락 안에서
1. `project = get(code)` · 없으면 `! not-found`
2. `DB: 이 프로젝트의 flags · propagation_decisions · comments · references · items · versions · status_changes · documents · repositories · projects` 순서로 삭제. 외래키를 물고 있으므로 자식부터
3. `shutil.rmtree(workdir, ignore_errors=True)` — 작업 사본 회수
4. `→ None`

**저장소는 건드리지 않는다.** `docs/specs/`는 원격에 그대로 남는다. 다시 등록하면
`import_existing=true`로 문서·항목·참조가 돌아온다.

**돌아오지 않는 것이 있다.** 플래그·전파결정·댓글은 원본에 없는 정보다(인프라 6장). 백업이
있으면 그것으로만 살릴 수 있다. 그래서 이 함수는 **되돌릴 수 없는 동작**이고, 부르는 쪽이
사람에게 확인을 받아야 한다.

**호출하는 것** [[#ProjectService.get]]

**테스트 관점** 삭제 후 `get` → not-found · 작업 사본 디렉터리가 사라짐 · 같은 저장소를 다시 등록할 수 있음(중복 등록 검사에 안 걸림) · 다른 프로젝트의 문서·플래그는 그대로

---

#### ProjectService.rebuild_index 재구축 위임

**시그니처** `async def rebuild_index(code: str) -> RebuildResult`

**처리** `get(code)` 확인 후 `pipeline.rebuild(code)`. 서비스가 pipeline을 부르는 유일한 곳(클래스 3.2)

---

## 3. 미결사항

- [x] `repo_status`의 fetch 캐시 — 결정: DB에서 읽는다. 폴링이 `behind_by`·`fetched_at`을 갱신하고 `repo_status`는 조회만 ([[SYNC-DOM-002]] 7장과 같은 결정)
