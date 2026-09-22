---
doc_id: SYNC-MS-001
type: MS
title: MINISPEC — ProjectService
status: approved
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — ProjectService

## 0. 이 문서가 다루는 것

`core/project/service.py`의 함수 9개. 클래스 명세 [[SYNC-DOM-002]] 4.1의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`projects`·`repositories`만. **`documents`를 모른다** — 단계 요약은 `queries`.

**소유가 여기 산다.** `projects.owner_user_id`가 「누구 것인가」이고([[SYNC-PRD-001#R12]]), 사람 경로는 전부 [[#ProjectService.get_owned]]·[[#ProjectService.list_owned]]로 들어온다. `get`·`list_projects`는 사람이 없는 경로(폴링·웹훅) 전용이다 — 사람 경로에서 부르면 남의 프로젝트가 열린다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ProjectService.init_project]] | 프로젝트 초기화 |
| [[#ProjectService.list_projects]] | 목록 — 시스템 경로 |
| [[#ProjectService.list_owned]] | 내가 소유한 목록 — 사람 경로 |
| [[#ProjectService.get]] | 코드 → 프로젝트 — 시스템 경로 |
| [[#ProjectService.get_owned]] | 코드 → 내 프로젝트 — 사람 경로 |
| [[#ProjectService.repo_status]] | 동기화 상태 |
| [[#ProjectService.delete_project]] | 등록 해제·작업 사본 회수 |
| [[#ProjectService.rebuild_index]] | 재구축 위임 |
| [[#ProjectService.asset_path]] | 첨부 파일 경로 — 사람 경로 |

---

## 2. 함수

#### ProjectService.init_project 프로젝트 초기화

**시그니처** `async def init_project(remote_url: str, code: str, name: str, user: User, import_existing: bool = False, create_repo: bool = False) -> Project`

근거: [[SYNC-SEQ-001#SEQ-4]] · [[SYNC-UC-001#UC-A1]] · [[SYNC-API-001#POST/api/projects]] · [[SYNC-API-002#init_project]] · [[SYNC-PRD-001#R12]]

**처리**
0. **코드 단위 락**을 잡는다(`asyncio.Lock`, code별). 같은 코드로 동시에 두 번 들어오면 서로의 작업 사본을 지운다(UC-A1 2c)
1. if `not re.fullmatch(r"[A-Z]{1,4}", code)` → `! project-code-invalid {rule}` (2b)
2. if `DB: projects where code` → `! project-code-conflict {code}` (2a)
2a. if `DB: repositories where remote_url 정규화 일치` → `! repository-already-registered {code: 그 프로젝트}` (UC-A1 2d). 정규화는 소문자 + 끝 `/`·`.git` 제거 — `web/routers/hooks.py`가 webhook 저장소를 찾을 때와 같은 규칙
3. `workdir = config.REPOS_DIR / code` · if 이미 있음 → 지운다 (이전 실패 잔재)
3a. `token = AccountService.github_token_for(user)`
3b. if `create_repo` → `github.create_repo(token, owner, name)` — `owner`·`name`은 `remote_url`에서 뜬다. **이미 있으면 만들지 않고 넘어간다**([[SYNC-MS-009#github.create_repo]]). if 실패 → workdir 삭제, `! repo-create-failed {reason}`
4. `git.clone(remote_url, workdir, token)` · if 실패 → workdir 삭제, `! push-failed {reason: clone}`
5. `has = git.exists(workdir, "docs/specs")` — 커밋이 하나도 없는 빈 저장소는 `false`다([[SYNC-MS-009#git.exists]]). 9단계가 만드는 커밋이 그 저장소의 첫 커밋이 된다 (UC-A1 기본 흐름 3)
6. if `has and not import_existing` → `n = len(git.list(workdir, "docs/specs/*/*.md"))`, workdir 삭제, `! existing-specs {doc_count: n}` (3a)
7. **트랜잭션**: `DB: projects insert (code, name, owner_user_id=user.id)` — **등록하는 사람이 소유자다**([[SYNC-PRD-001#R12]]). 바뀌지 않고 나뉘지 않는다 · `DB: repositories insert (project_id, remote_url, workdir_path, last_processed_commit=None, registered_by_user_id=user.id)` — push 토큰의 주인. 지금은 소유자와 같은 사람이지만 뜻이 다르다(DOM-003 `repositories`)
8. if `has and import_existing` → `pipeline.rebuild(code)` (3a2. 락·트랜잭션은 그쪽) · `last_processed_commit`은 rebuild가 채움
9. else → `files = git.init_specs(workdir)` (11단계 + `STD/` 디렉터리, `_templates/` 12개, `assets/`) · `hash = git.commit_push(workdir, message=f"chore({code}): init syncdoc", author=Author(human, user, None, web), files=files)` · if 실패 → 7단계 롤백, workdir 삭제, `! push-failed` (4a) · `DB: repositories update last_processed_commit=hash`
9a. `ensure_hook(code, user)` — push 통지를 건다([[#ProjectService.ensure_hook]], UC-A1 4). **실패해도 등록을 깨지 않는다**(4a) — 통지는 빠르게 하려는 수단이고, 못 걸어도 주기 확인(UC-G1 1b)이 메운다. 사유는 `repositories.hook_error`에 남아 화면이 말한다
10. `→ Project`. **`ProjectSummary`는 입구(MCP 도구·라우터)가 `queries.project_summary()`로 만든다** — 서비스가 `queries`를 부르면 순환이다(클래스 3.2에 PS→QR 없음). 신규면 11칸 null

**저장소를 만든 뒤 실패하면 저장소는 남는다.** 7~9단계가 실패하면 DB와 작업 사본은 지금처럼 되돌리되 **GitHub 저장소는 지우지 않는다.** 앱이 남의 저장소를 지우는 권한을 쓰는 것이 위험하고, 되돌리는 사이 사람이 넣은 것까지 사라진다. 사용자가 직접 지우거나 `import_existing`으로 다시 등록하면 된다 — 오류 메시지에 그 사실을 적는다

**`create_repo`의 기본값이 거짓인 이유.** 참으로 두면 주소에 오타를 내도 조용히 새 저장소가 생긴다. 지금은 그럴 때 clone이 실패해 `push-failed`가 나므로 오타를 알아챌 수 있다. 에이전트가 이 인자를 붙이려면 사람의 지시가 있어야 한다

**호출하는 것** `AccountService.github_token_for` · [[SYNC-MS-009#github.create_repo]] · `git.clone` `exists` `list` `init_specs` `commit_push` · [[SYNC-MS-007#pipeline.rebuild]]

**테스트 관점** **통지 걸기가 실패해도 프로젝트는 등록된다**(hook_error에 사유) · 빈 저장소 → `docs/specs/` 생김, 커밋 하나, 11칸 null · **`owner_user_id`가 등록한 사람** · `docs/specs/` 있는 저장소 → `existing-specs`, workdir 없음, DB 행 없음 · `import_existing=true` → 재구축 결과 · clone 권한 없음 → `push-failed`, 아무것도 안 남음 · **없는 저장소 + `create_repo=false` → `push-failed`**(지금 동작) · **없는 저장소 + `true` → 공개 저장소가 생기고 골격 커밋까지** · **이미 있는 저장소 + `true` → 만들지 않고 그대로 쓴다** · 만든 뒤 등록이 실패해도 **저장소는 남는다**

---

#### ProjectService.list_projects 목록 — 시스템 경로

**시그니처** `list_projects() -> list[Project]`

**처리** `DB: projects join repositories order by code`. **전부다** — 폴링([[SYNC-MS-007#scheduler.catch_up]])·웹훅이 쓴다. 배치는 사람이 없으니 소유와 무관하게 모든 저장소를 돌아야 한다. **사람 경로에서 부르지 않는다** — 목록 화면은 [[#ProjectService.list_owned]]

---

#### ProjectService.list_owned 내가 소유한 목록 — 사람 경로

**시그니처** `list_owned(user: User) -> list[Project]`

근거: [[SYNC-PRD-001#R12]] · [[SYNC-UC-001#UC-H14]] · [[SYNC-API-001#GET/api/projects]]

**처리** `DB: projects join repositories where owner_user_id = user.id order by code` · `→ list[Project]`. 없으면 빈 목록 — 에러가 아니다(프로젝트를 아직 등록 안 한 계정, UI-2 빈 상태)

**호출되는 것** [[SYNC-MS-008#queries.project_summary]] · [[#ProjectService.repo_status]]

**테스트 관점** 두 사람이 각각 등록 → 각자 자기 것만 · 등록한 적 없는 사람 → 빈 목록 · `list_projects`는 둘 다 준다

---

#### ProjectService.get 코드 → 프로젝트 — 시스템 경로

**시그니처** `get(code: str) -> Project`

**처리** `DB: projects join repositories where code` · if 없음 → `! not-found {resource: project, id: code}`. `Project.repository`로 저장소 접근. **소유를 안 본다** — GitHub 경로([[SYNC-MS-007#pipeline.process_commit]])·폴링·`init_project(import_existing)`처럼 사람이 없는 자리 전용. **사람 경로에서 부르지 않는다** — 새 코드가 이 함수를 사람 경로에서 부르면 남의 프로젝트가 열린다. `grep get(`으로 남은 자리를 셀 수 있게 이름을 하나로 둔다

---

#### ProjectService.get_owned 코드 → 내 프로젝트 — 사람 경로

**시그니처** `get_owned(code: str, user: User) -> Project`

근거: [[SYNC-PRD-001#R12]] · [[SYNC-API-001]] 1장 · [[SYNC-API-002]] 1장

**처리** `project = get(code)` · if `project.owner_user_id != user.id` → `! not-found {resource: project, id: code}` — **없는 것과 같은 답**이다. 남의 프로젝트가 있다는 사실이 새지 않는다. 새 에러 타입은 없다(403을 두지 않는 이유: 「있지만 못 본다」를 알려줄 상대가 없다 — 혼자 쓰는 도구다) · `→ project`

**왜 `get(code, user)`가 아니라 함수를 하나 더 두나.** `user: User | None`으로 만들면 `None`이 「필터 없음」이라는 합법 값이 되어 **빠뜨린 자리가 조용히 전체 열람**이 된다. 함수가 둘이면 호출 자리마다 「시스템 경로인가 사람 경로인가」가 코드에 읽히고, `check_code`가 시그니처를 대조한다

**호출되는 것** [[SYNC-MS-007#pipeline.save_pipeline]](github가 아닌 입구) · [[SYNC-MS-007#pipeline.change_status]] · `trash_document` `restore_document` `purge_document` `revert` · [[SYNC-MS-008]]의 사람용 조회 전부 · [[#ProjectService.delete_project]] · [[#ProjectService.rebuild_index]]

**테스트 관점** 소유자 → `Project` · 다른 사람 → `not-found`이고 확장 필드가 `get`의 없음과 **같다**(`resource: project`) · 없는 코드 → 같은 `not-found`

---

#### ProjectService.repo_status 동기화 상태

**시그니처** `async def repo_status(user: User) -> list[RepoStatus]`

근거: [[SYNC-SEQ-001#SEQ-20]] · UI-14 표 2 · [[SYNC-PRD-001#R12]]

**처리** `projects = list_owned(user)` — **내가 소유한 저장소만.** v1은 전부를 줬고 그것이 관리 화면에서 남의 저장소 주소가 보이던 자리다(#91). **원격을 안 탄다. `git.fetch`를 부르지 않는다.** 저장소마다 `→ RepoStatus(code, name, remote_url, last_processed_commit, synced_at, behind_by, fetched_at, error, hook, hook_error)` — `hook`은 `hook_id`·`hook_error`로 정하는 셋(`ok`/`none`/`error`, 카드 AF) — `name`은 UI-14 표가 「[코드] 이름」으로 적기 위해서다(UI-002 1.6).

`error`는 **폴링이 적어 둔 `repositories.fetch_error`**다([[SYNC-MS-007#scheduler.catch_up]]). v1에는 백업 읽기 실패도 이 칸에 모았는데, 백업이 사라지면서(카드 V) 폴링 오류만 남았다.

`behind_by`·`fetched_at`은 폴링([[SYNC-MS-007#scheduler.catch_up]])이 갱신한다. 예전에는 이 함수가
저장소마다 순차로 fetch를 돌렸는데, 폴링이 5분마다 같은 일을 이미 하고 있어 이중이었고, 원격
하나가 응답하지 않으면 관리 화면 전체가 그 요청에 매달렸다(git 명령에 타임아웃이 없다).

`behind_by`가 `null`이면 아직 한 번도 못 받아본 것이다 — 방금 등록했거나 폴링이 계속 실패하는
경우다. **그 둘을 화면이 구분할 수 있어야 한다** — 계속 실패하는 쪽은 `error`가 채워져 있다(#46).

**호출하는 것** [[#ProjectService.list_owned]]

**테스트 관점** 폴링이 적어 둔 `fetch_error`가 `error`로 나온다 · 이 함수가 `git.fetch`를 부르지 않는다 · 폴링이 적어 둔 값을 그대로 돌려준다 · 등록 직후에는 `behind_by=None` · 작업 사본이 없어도 다른 저장소는 그대로 나온다 · **남의 저장소는 목록에 없다**

---

#### ProjectService.delete_project 등록 해제

**시그니처** `async def delete_project(code: str, user: User) -> None`

근거: [[SYNC-API-001#DELETE/api/projects/{code}]] · 인프라 9장(작업 사본 회수) · [[SYNC-PRD-001#R12]]

**처리** — 코드 단위 락 안에서
1. `project = get_owned(code, user)` · 없거나 남의 것이면 `! not-found`. 해제는 소유자만 한다
2. `DB: 이 프로젝트의 references · items · versions · status_changes · documents · repositories · projects` 순서로 삭제. 외래키를 물고 있으므로 자식부터
3. `shutil.rmtree(workdir, ignore_errors=True)` — 작업 사본 회수
4. `→ None`

**저장소는 건드리지 않는다.** `docs/specs/`는 원격에 그대로 남는다. 다시 등록하면
`import_existing=true`로 문서·항목·참조가 돌아온다.

**돌아오지 않는 것이 있다.** 상태 변경 이력(`status_changes`)은 원본에 없는 정보다(인프라 6장). 그래서 이 함수는 **되돌릴 수 없는 동작**이고, 부르는 쪽이
사람에게 확인을 받아야 한다.

**호출하는 것** [[#ProjectService.get_owned]]

**테스트 관점** 삭제 후 `get` → not-found · 작업 사본 디렉터리가 사라짐 · 같은 저장소를 다시 등록할 수 있음(중복 등록 검사에 안 걸림) · 다른 프로젝트의 문서는 그대로 · **남의 프로젝트 → `not-found`, 아무것도 안 지워짐**

---

#### ProjectService.ensure_hook push 통지를 건다

**시그니처**
```python
async def ensure_hook(code: str, user: User) -> HookStatus
```

근거: [[SYNC-INFRA-001]] 7장 · [[SYNC-UC-001#UC-A1]] 4·4a · [[SYNC-API-001#POST/api/admin/repos/{code}/hook]] · #115

**처리**
1. `get_owned(code, user)` — 남의 것이면 `! not-found {resource: project}`
2. `PUBLIC_BASE_URL`이나 `WEBHOOK_SECRET`이 비면 → `HookStatus("none", "공개 주소나 비밀번호가 없어 걸지 못한다", created=False)`. **걸지 않는다** — 받는 쪽이 빈 비밀번호를 전부 거부하므로 걸어 봐야 안 통한다
3. `hook_id = github.create_hook(token, owner, name, f"{PUBLIC_BASE_URL}/hooks/github", WEBHOOK_SECRET)` · `Unauthorized`면 `repo.hook_error = 사유`, `→ HookStatus("error", 사유, False)`
4. `repo.hook_id = hook_id` · `repo.hook_error = None` · `→ HookStatus("ok", None, created=이번에 만들었나)`

**출력** [[SYNC-API-001]] `HookStatus`

**예외** `not-found`(1). 3의 실패는 **예외로 올리지 않고 상태로 돌려준다** — 사람이 화면에서 사유를 읽고 다시 누르면 된다

**테스트 관점** 주소·비밀번호가 비면 `none`이고 GitHub을 안 부른다 · 권한 없으면 `error`이고 `hook_error`가 남는다 · 성공하면 `ok`·`hook_id` 저장 · **두 번째 호출은 `created=False`** · 남의 프로젝트 → `not-found`

---

#### ProjectService.sync_now 지금 가져오기

**시그니처**
```python
async def sync_now(code: str, user: User) -> SyncResult
```

근거: [[SYNC-UC-001#UC-G2]] · [[SYNC-API-001#POST/api/admin/repos/{code}/sync]] · #115

**처리**
1. `docs = pipeline.read_pending(code, user)` — **그대로 쓴다**([[SYNC-MS-007#pipeline.read_pending]]). 소유 검사·읽기 락·`process_commit`이 그 안에 다 있다. 같은 일을 두 벌 만들지 않는다
2. `→ SyncResult(docs, fetched_at=repo.fetched_at)`

**출력** [[SYNC-API-001]] `SyncResult` — 읽은 문서 수와 방금 확인한 시각

**예외** `not-found`(read_pending 1단계) · `git.fetch` 실패는 그대로 올린다(UC-G2 2b)

**테스트 관점** 밀린 것을 읽고 수를 돌려준다 · 읽을 것이 없으면 0이고 **`fetched_at`이 갱신된다** · 남의 프로젝트 → `not-found`

---

#### ProjectService.rebuild_index 재구축 위임

**시그니처** `async def rebuild_index(code: str, user: User) -> RebuildResult`

**처리**
1. `get_owned(code, user)` — 소유 검사는 여기서 끝난다. `rebuild`는 `get`을 쓴다(`init_project(import_existing)`도 부르므로)
2. `hash = git.sync_readme(repo.workdir, Author(human, user, None, web_status), code)` — README가 낡았으면 새 판으로 커밋·push([[SYNC-MS-009#git.sync_readme]], 카드 AB). **인덱스보다 먼저**: 그 커밋이 3의 `fetch` head에 들어가 밀림이 0으로 끝난다. `PushFailed`는 그대로 올린다 — 저장소에 쓰는 일이 실패했으면 인덱스는 건드리지 않는다(UC-S6 1a)
3. `pipeline.rebuild(code)` — 서비스가 pipeline을 부르는 유일한 곳(클래스 3.2)
4. `→ RebuildResult(…, readme_updated=hash is not None)`

**테스트 관점** 남의 프로젝트 → `not-found`, 재구축 안 돎 · 낡은 README면 커밋이 하나 생기고 `readme_updated=true`, 이어서 재구축하면 밀림 0 · 같은 README면 커밋 없고 `false` · README push 실패면 인덱스가 그대로

---

#### ProjectService.asset_path 첨부 파일 경로

**시그니처** `def asset_path(code: str, path: str, user: User) -> Path`

근거: [[SYNC-PRD-001#R5]] · [[SYNC-API-001#GET/api/projects/{code}/files/{path}]]

**입력** `path` — `docs/specs/` 기준 상대 경로. 라우터가 URL의 나머지를 그대로 넘긴다(`07-UI/../assets/x.png`처럼 문서 폴더 기준으로 쓴 것이 브라우저에서 이미 풀려 `assets/x.png`로 온다)

**처리**
1. `get_owned(code, user)` — 남의 프로젝트는 `! not-found {resource: project, id: code}`([[#ProjectService.get_owned]]과 같은 답)
2. `base = REPOS_DIR / code / "docs" / "specs"`
3. `target = (base / path).resolve()` · if `target`이 `base.resolve()` 안이 아니면(`..`·바깥으로 나가는 심볼릭 링크) → `! not-found {resource: file, id: path}`
4. if 확장자가 `png jpg jpeg gif webp svg css woff woff2 ttf` 밖이면 → `! not-found {resource: file, id: path}` — 문서(`.md`)는 이 길로 안 준다
5. if 파일이 없으면 → `! not-found {resource: file, id: path}`
6. `→ target`

**출력** `Path` — 라우터가 `FileResponse`로 보낸다. 작업 사본은 `git checkout --force`로 `origin/main`과 같다([[SYNC-MS-009#git.checkout]]·[[SYNC-MS-007#pipeline.process_commit]]) — 폴링이 받은 뒤의 파일이다

**왜 [[SYNC-MS-009#git.read]]가 아닌가.** `git.read`는 `str`을 돌려줘 이진 파일(png·woff2)이 깨진다. 작업 사본의 파일을 그대로 준다

**예외** 남의 프로젝트 → `not-found`(project) · 경로 밖·허용 밖 확장자·없는 파일 → `not-found`(file). 새 에러 타입은 없다

**호출하는 것** [[#ProjectService.get_owned]]

**호출되는 것** [[SYNC-API-001#GET/api/projects/{code}/files/{path}]] 라우터

**테스트 관점** 소유자·있는 파일 → `Path`가 `base` 안 · 남의 프로젝트 → `not-found`이고 확장 필드가 `get_owned`의 것과 같다(`resource: project`) · `../../etc/passwd` → `not-found`(file) · `base` 밖을 가리키는 심볼릭 링크 → `not-found` · `01-RFQ/X-RFQ-001.md` → `not-found`(허용 밖 확장자) · 없는 파일 → `not-found`

---

## 3. 미결사항

- [x] `repo_status`의 fetch 캐시 — 결정: DB에서 읽는다. 폴링이 `behind_by`·`fetched_at`을 갱신하고 `repo_status`는 조회만 ([[SYNC-DOM-002]] 7장과 같은 결정)
