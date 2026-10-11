---
doc_id: SYNC-MS-013
type: MS
title: MINISPEC — ProjectService (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-001, SYNC-MS-019, SYNC-UC-001, SYNC-API-001, SYNC-API-002]
---

# MINISPEC — ProjectService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/project/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.2. 파이썬 판 [[SYNC-MS-001]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

서비스는 연결과 저장소 자리를 빌려 받는다 — `ProjectService<'c> { pub db: &'c mut PgConnection, pub repos: &'c ServerRepos }`. `ServerRepos { git, origins, repos, specs_url }` — git 어댑터([[SYNC-MS-019]])·서버 저장소 자리 `origins/`·작업 사본 자리 `repos/`·README의 규약 주소. 켤 때 [[SYNC-MS-012#runtime.run]]이 만든다. 트랜잭션은 부르는 쪽이 쥔다([[SYNC-STD-004#DEV-10]]). 돌려주는 행은 `(ProjectRow, RepositoryRow)`다.

**카드 L6 몫은 만들기·지우기(보관)와 조회 셋이다(2026-10-08). 카드 L8이 첨부 파일 경로 하나를, 카드 L10이 git 입구의 원본 경로 하나를, 카드 L11이 전체 목록·동기화 상태·통지·지금 가져오기·재구축 위임과 보관본 되살리기의 재구축 갈래를, 카드 L15가 번들로 가져오기를, 카드 L16이 켤 때 작업 사본 맞추기를 더했다(2026-10-11).** 싱크독_로컬은 **서버 저장뿐**이다([[SYNC-PRD-001#R15]] — 파이썬 폐쇄망판의 `storage_modes == ["server"]`). GitHub 갈래(주소·저장소 만들기·통지)는 없고, `storage=github`는 첫 검사에서 `storage-unavailable`이다. 통지는 늘 `none`이다(파이썬 판의 서버 저장 갈래).

**보관본 되살리기**(사용자 결정 2026-10-08 — 재구축 갈래는 카드 L11) — 되살린 보관본에 명세가 있으면 파이썬 판처럼 재구축([[SYNC-MS-017#pipeline.rebuild]])으로 DB에 다시 올린다. 서비스가 pipeline을 부르는 자리는 이것과 [[#ProjectService.import_bundle]]·[[#ProjectService.sync_now]]·[[#ProjectService.rebuild_index]] 넷뿐이다(파이썬 판 DOM-002 3.2와 같다).

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `DB:` 테이블 접근, `git:` [[SYNC-MS-019]], `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ProjectService.init_project]] | 프로젝트 만들기 — 서버 저장소와 골격 커밋 |
| [[#ProjectService.import_bundle]] | 번들로 가져오기 — 서버 저장 + 재구축 |
| [[#ProjectService.delete_project]] | 등록 해제 — 서버 저장소는 보관 |
| [[#ProjectService.get]] | 코드 → 프로젝트 — 시스템 경로 |
| [[#ProjectService.get_owned]] | 코드 → 내 프로젝트 — 사람 경로 |
| [[#ProjectService.list_owned]] | 내가 소유한 목록 |
| [[#ProjectService.asset_path]] | 첨부 파일 경로 |
| [[#ProjectService.server_origin]] | 서버 저장소 원본 경로 |
| [[#ProjectService.list_projects]] | 목록 — 시스템 경로 |
| [[#ProjectService.repo_status]] | 동기화 상태 |
| [[#ProjectService.ensure_hook]] | push 통지를 건다 — 서버 저장은 없다 |
| [[#ProjectService.sync_now]] | 지금 가져오기 |
| [[#ProjectService.rebuild_index]] | 재구축 위임 |
| [[#ProjectService.rehome]] | 서버 저장소·작업 사본 자리를 이 데이터 자리로 |

---

## 2. 함수

#### ProjectService.init_project 프로젝트 만들기 — 서버 저장소와 골격 커밋

**시그니처**
```rust
pub async fn init_project(&mut self, pool: &PgPool, code: &str, name: &str, user: &UserRow, import_existing: bool, storage: Storage) -> Result<(ProjectRow, RepositoryRow), Problem>
```

근거: [[SYNC-MS-001#ProjectService.init_project]] · [[SYNC-UC-001#UC-A1]] · [[SYNC-SCN-001#S5]] · [[SYNC-SCN-001#S10]]

**처리** [[SYNC-MS-001#ProjectService.init_project]]의 서버 저장 갈래와 같은 차례 — 코드마다 잠금을 쥐고(같은 코드의 만들기·지우기가 서로의 작업 사본을 지우지 않게)
1. if `storage`가 `server`가 아니다 → `! StorageUnavailable { storage, enabled: ["server"] }`
2. if 코드가 `[A-Z]{1,4}` 전체가 아니다 → `! ProjectCodeInvalid { rule: "^[A-Z]{1,4}$" }` · if `DB: projects where code` 있음 → `! ProjectCodeConflict { code }`
3. `workdir = repos/{code}` — 있으면 지운다(지난 실패 잔재)
4. `origin = origins/{code}.git` · if 이미 있다(등록되지 않은 원본) → **지우지 않고** 보관 자리로 옮긴다 · `archives = origins/_archive/{code}-*.git`을 (시각, 번호) 순으로(#349)
   - if 보관본이 있고 `import_existing`이 아니다 → `n = git.list(가장 최근, "docs/specs/*/*.md", "HEAD")`의 수(git 실패면 0) · `! ExistingSpecs { doc_count: n, archived_at: 이름의 시각 }`(파이썬 `isoformat` — `2026-10-08T12:34:56+00:00`, 못 읽으면 이름 그대로)
   - if 보관본이 있고 `import_existing` → 가장 최근 것을 `origin`으로 되살린다 · 아니면 `git.init_bare(origin)`
5. `git.clone(origin, workdir)` · 실패 → 작업 사본을 지우고 원본을 되돌리고(새로 만든 것은 지우고 되살린 것은 보관 자리로) `! PushFailed("clone: {stderr}")`
6. `has = git.exists(workdir, "docs/specs")` · if `has`이고 `import_existing`이 아니다 → `n = git.list(workdir, …)`의 수 · 지우고 되돌리고 `! ExistingSpecs { doc_count: n }`
7. 트랜잭션을 열고(부르는 쪽이 이미 트랜잭션이면 저장점 — REST·MCP 입구는 트랜잭션 없이 연결을 넘긴다) `DB: projects insert (code, name, owner_user_id=user.id)` · `DB: repositories insert (project_id, storage='server', remote_url=origin 절대 경로, workdir_path, registered_by_user_id=user.id)`
8. if `has`이고 `import_existing` → `pipeline.rebuild(그 트랜잭션, pool, repos, code)` — 같은 트랜잭션 안이라 막 넣은 행을 본다 · 실패하면 원본을 되돌리고(되살린 것은 보관 자리로) 그 `Problem` · 골격 커밋 없이 10으로 — 처리 지점은 재구축이 원본 끝으로 적었다 · 커밋 뒤 `pipeline.schedule_code_graph(pool, repos, code, 처리 지점)` — 재구축이 건 것은 아직 커밋되지 않은 프로젝트를 못 볼 수 있다(카드 L12)
9. `files = Git::init_specs(repos.specs_url)` · `hash = git.commit_push(workdir, "chore({code}): init syncdoc", user, files, [])` · 실패 → 트랜잭션을 되돌리고 작업 사본을 지우고 원본을 되돌리고 그 `Problem` · `DB: repositories update last_processed_commit=hash`
10. `→ (프로젝트 행, 저장소 행)`

보관 자리 — `origins/_archive/{code}-{UTC %Y%m%d%H%M%S}.git`, 같은 초에 있으면 `-1`·`-2`…를 붙인다. 시각은 [[SYNC-STD-004#DEV-18]]의 저장 시각

**다른 점** GitHub 인자(`remote_url`·`create_repo`·`private`)가 없다 — MCP 도구·REST 본문에는 있지만 서버 저장에서 파이썬 판도 안 쓴다 · 연결 풀을 받는다 — 8의 그래프 만들기는 따로 띄운 작업이 제 연결로 한다(카드 L12)

**예외** 1~9의 `Problem` · git·파일 실패는 `Problem::Git`·`Problem::Internal`(파이썬 판도 그대로 올린다)

**호출하는 것** [[SYNC-MS-019#Git.init_bare]] · [[SYNC-MS-019#Git.list]] · [[SYNC-MS-019#Git.clone]] · [[SYNC-MS-019#Git.exists]] · [[SYNC-MS-019#Git.init_specs]] · [[SYNC-MS-019#Git.commit_push]] · [[SYNC-MS-017#pipeline.rebuild]] · [[SYNC-MS-017#pipeline.schedule_code_graph]] · [[#ProjectService.get]](돌려줄 행)

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 새 프로젝트 → `origins/{code}.git`(HEAD main, 받기 규칙 셋)과 골격 커밋 하나(14파일, `chore({code}): init syncdoc`), `last_processed_commit`이 원격 main · `github` → `storage-unavailable`, 아무것도 안 생김 · 나쁜 코드 → `project-code-invalid` · 같은 코드 → `project-code-conflict` · 지운 뒤 같은 코드 → `existing-specs`(`doc_count`·`archived_at`), 아무것도 안 바뀜 · 같은 초 보관본 둘 → 번호가 큰 것 · 이름 없이 남은 원본 → 보관으로 옮기고 `existing-specs` · 비어 있는 보관본 + 가져오기 → 되살리고 골격 커밋 · 명세가 있는 보관본 + 가져오기 → 재구축으로 문서·버전이 다시 올라오고 처리 지점이 원본 끝, 골격 커밋 없음 · 재구축이 실패하면 행 없음·보관본은 제자리 · clone 실패 → 새 원본·작업 사본·행 없음

---

#### ProjectService.import_bundle 번들로 가져오기 — 서버 저장 + 재구축

**시그니처**
```rust
pub async fn import_bundle(&mut self, pool: &PgPool, code: &str, name: &str, user: &UserRow, data: &[u8]) -> Result<(ProjectRow, RepositoryRow), Problem>
```

근거: [[SYNC-MS-001#ProjectService.import_bundle]] · [[SYNC-UC-001#UC-A1]] 1c · [[SYNC-PRD-001#R14]] · [[SYNC-INFRA-001]] 9.7 · 카드 L15

**처리** [[SYNC-MS-001#ProjectService.import_bundle]]과 같은 차례 — [[#ProjectService.init_project]]와 같은 코드 잠금
1. if 코드가 `[A-Z]{1,4}` 전체가 아니다 → `! ProjectCodeInvalid { rule: "^[A-Z]{1,4}$" }` · if `DB: projects where code` 있음 → `! ProjectCodeConflict { code }`
2. `workdir = repos/{code}` — 있으면 지운다 · `origin = origins/{code}.git` — 이미 있으면(등록되지 않은 원본) **지우지 않고** 보관 자리로 옮긴다([[#ProjectService.init_project]] 4와 같은 이름). 보관본은 되살리지 않는다
3. 임시 폴더(`syncdoc-bundle-` 머리)에 `data`를 `import.bundle`로 쓰고 `git.clone_bare(그 파일, origin)` · `Problem::Git`이면 `origin`을 지우고 `! BundleInvalid { reason: "번들 파일이 아니거나 깨졌다" }` · 임시 폴더는 지운다
4. `git.rev_list_count(origin, "refs/heads/main")` · `Problem::Git`이면 `origin`을 지우고 `! BundleInvalid { reason: "main 가지가 없다" }`
5. `git.clone(origin, workdir)` · 실패 → 작업 사본·`origin`을 지우고 `! PushFailed("clone: {stderr}")`
6. 트랜잭션(부르는 쪽이 트랜잭션이면 저장점): `DB: projects insert (code, name, owner_user_id=user.id)` · `DB: repositories insert (storage='server', remote_url=origin 절대 경로, workdir_path, registered_by_user_id=user.id)`
7. `pipeline.rebuild(그 트랜잭션, pool, repos, code)` — 명세·버전·상태 이력을 커밋에서 되살리고 처리 지점을 main 끝으로 · 실패 → 트랜잭션을 버리고 작업 사본·`origin`을 지우고 그 `Problem` — 골격 커밋을 만들지 않는다
8. 커밋 · 커밋 뒤 `pipeline.schedule_code_graph(pool, repos, code, 처리 지점)`([[#ProjectService.init_project]] 8과 같은 까닭) · `→ (프로젝트 행, 저장소 행)` — `ProjectSummary`는 입구가 만든다

**다른 점** 서버 저장 켜짐 검사가 없다 — 싱크독_로컬은 서버 저장뿐이다 · 연결 풀을 받는다(7·8의 그래프 만들기)

**예외** 1~7의 `Problem` · 파일 실패는 `Problem::Internal`

**호출하는 것** [[SYNC-MS-019#Git.clone_bare]] · [[SYNC-MS-019#Git.rev_list_count]] · [[SYNC-MS-019#Git.clone]] · [[SYNC-MS-017#pipeline.rebuild]] · [[SYNC-MS-017#pipeline.schedule_code_graph]] · [[#ProjectService.get]](돌려줄 행)

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 명세 두 커밋(초안 → 상태)과 태그가 든 저장소의 번들 → 원본의 main·태그 해시가 같고 원격 없음·HEAD main·받기 규칙, 골격 커밋 없음, 처리 지점이 main 끝, 문서 상태가 `approved` · 번들 아님 → `bundle-invalid`(`번들 파일이 아니거나 깨졌다`), 원본 없음 · main 없는 번들 → `bundle-invalid`(`main 가지가 없다`), 원본·작업 사본·행 없음 · 나쁜 코드 → `project-code-invalid` · 같은 코드 → `project-code-conflict` · 이름 없이 남은 원본 → 보관으로 옮기고 가져온다

---

#### ProjectService.delete_project 등록 해제 — 서버 저장소는 보관

**시그니처**
```rust
pub async fn delete_project(&mut self, code: &str, user: &UserRow) -> Result<(), Problem>
```

근거: [[SYNC-MS-001#ProjectService.delete_project]] · [[SYNC-UC-001#UC-H17]]

**처리** [[SYNC-MS-001#ProjectService.delete_project]]와 같다 — 코드마다 잠금을 쥐고
1. `(p, r) = get_owned(code, user)`
2. [[SYNC-MS-021#ConversationService.delete_by_project]](턴·첨부는 FK로 함께) · [[SYNC-MS-022#CodeGraphService.delete_by_project]] → `DB:` 참조 셋(나가는 것·들어오는 문서·들어오는 항목) → `status_changes` → `items` → `versions` → `documents` → `repositories` → `projects`를 지운다
3. 작업 사본을 지운다(실패는 넘긴다) · 서버 저장이고 원본이 있으면 보관 자리로 옮긴다 — **지우지 않는다**

**호출하는 것** [[#ProjectService.get_owned]] · [[SYNC-MS-021#ConversationService.delete_by_project]] · [[SYNC-MS-022#CodeGraphService.delete_by_project]]

**테스트 관점** 지운 뒤 `get` → `not-found` · 그 프로젝트의 문서·항목·버전·참조·대화·코드 그래프 행이 0 · 작업 사본이 없다 · 원본이 `_archive/{code}-{시각}.git`에, `origins/{code}.git`은 없다 · 다른 프로젝트 행은 그대로 · 남의 프로젝트 → `not-found`, 아무것도 안 지워짐

---

#### ProjectService.get 코드 → 프로젝트 — 시스템 경로

**시그니처**
```rust
pub async fn get(&mut self, code: &str) -> Result<(ProjectRow, RepositoryRow), Problem>
```

근거: [[SYNC-MS-001#ProjectService.get]]

**처리** `DB: projects join repositories where code` · if 없음 → `! NotFound { resource: "project", id: code }`. 소유를 안 본다 — 사람 경로에서 부르지 않는다

**테스트 관점** 있으면 두 행 · 없으면 `not-found`

---

#### ProjectService.get_owned 코드 → 내 프로젝트 — 사람 경로

**시그니처**
```rust
pub async fn get_owned(&mut self, code: &str, user: &UserRow) -> Result<(ProjectRow, RepositoryRow), Problem>
```

근거: [[SYNC-MS-001#ProjectService.get_owned]] · [[SYNC-API-002]] 1장

**처리** `get(code)` · if `owner_user_id != user.id` → `get`의 없음과 **같은** `! NotFound { resource: "project", id: code }`

**호출하는 것** [[#ProjectService.get]]

**테스트 관점** 소유자 → 두 행 · 남의 것·없는 것 → 같은 `not-found`

---

#### ProjectService.list_owned 내가 소유한 목록

**시그니처**
```rust
pub async fn list_owned(&mut self, user: &UserRow) -> Result<Vec<(ProjectRow, RepositoryRow)>, Problem>
```

근거: [[SYNC-MS-001#ProjectService.list_owned]]

**처리** `DB: projects join repositories where owner_user_id = user.id order by code` — 없으면 빈 목록

**테스트 관점** 내 것만 코드 차례 · 없으면 빈 목록

---

#### ProjectService.asset_path 첨부 파일 경로

**시그니처**
```rust
pub async fn asset_path(&mut self, code: &str, path: &str, user: &UserRow) -> Result<PathBuf, Problem>
```

근거: [[SYNC-MS-001#ProjectService.asset_path]] · [[SYNC-API-001#GET/api/projects/{code}/files/{path}]]

**처리** [[SYNC-MS-001#ProjectService.asset_path]]와 같다
1. `get_owned(code, user)`
2. `base = repos/{code}/docs/specs`를 풀어 둔다(심볼릭 링크까지 — 파이썬 `resolve()`)
3. `target = base/path`를 풀어 `base` 안이 아니면 → `! NotFound { resource: "file", id: path }`
4. 확장자(소문자)가 `png jpg jpeg gif webp svg css woff woff2 ttf` 밖이면 → 같은 `not-found`
5. 파일이 아니면 → 같은 `not-found`
6. `→ target`

**다른 점** 파이썬 `resolve()`는 없는 경로도 문자열로 푼다 — Rust는 있는 가장 긴 앞부분을 풀고 나머지를 붙인다(같은 답). 작업 사본 자리는 `repos.repos`

**호출하는 것** [[#ProjectService.get_owned]]

**테스트 관점** (시험 DB · 임시 자리) 있는 그림 → 그 경로 · `../../etc/passwd` → `not-found`(file) · 바깥을 가리키는 심볼릭 링크 → `not-found` · `.md` → `not-found` · 없는 파일 → `not-found` · 남의 프로젝트 → `not-found`(project)


---

#### ProjectService.server_origin 서버 저장소 원본 경로

**시그니처**
```rust
pub async fn server_origin(&mut self, code: &str, user: &UserRow) -> Result<PathBuf, Problem>
```

근거: [[SYNC-MS-001#ProjectService.server_origin]] · [[SYNC-UC-001#UC-H21]] · [[SYNC-API-001#GET/git/{code}.git/info/refs]]

**처리** [[SYNC-MS-001#ProjectService.server_origin]]와 같다 — `get_owned` · 서버 저장이 아니거나 원본(`remote_url`) 폴더가 없으면 `! NotFound { resource: "project", id: code }` — 남의 것과 같은 답 · `→ 원본`

**호출하는 것** [[#ProjectService.get_owned]]

**테스트 관점** (시험 DB · 임시 자리) 소유자 → 원본 · 남의 것·원본 없음 → 같은 `not-found`


---

#### ProjectService.list_projects 목록 — 시스템 경로

**시그니처**
```rust
pub async fn list_projects(&mut self) -> Result<Vec<(ProjectRow, RepositoryRow)>, Problem>
```

근거: [[SYNC-MS-001#ProjectService.list_projects]]

**처리** `DB: projects join repositories order by code` — **전부다.** 따라잡기([[SYNC-MS-017#pipeline.catch_up]])가 쓴다 — 배치는 사람이 없으니 소유와 무관하게 돈다. 사람 경로에서 부르지 않는다(목록 화면은 [[#ProjectService.list_owned]])

**테스트 관점** 남의 것까지 코드 순

---

#### ProjectService.repo_status 동기화 상태

**시그니처**
```rust
pub async fn repo_status(&mut self, user: &UserRow) -> Result<Vec<RepoStatus>, Problem>
```

근거: [[SYNC-MS-001#ProjectService.repo_status]] · [[SYNC-SEQ-001#SEQ-20]]

**처리** [[SYNC-MS-001#ProjectService.repo_status]]와 같다 — [[#ProjectService.list_owned]]마다 `RepoStatus { code, name, storage, remote_url: None, last_processed_commit, synced_at, behind_by, fetched_at, error: fetch_error, hook: "none", hook_error }` · 원격을 타지 않는다(받기는 [[SYNC-MS-017#pipeline.catch_up]]이 한다)

**다른 점** 서버 저장뿐이라 `remote_url`은 늘 없고 `hook`은 늘 `none`이다

**호출하는 것** [[#ProjectService.list_owned]]

**테스트 관점** 내 것만 · 코드 순 · 등록 직후 `behind_by` 없음 · 따라잡기가 적은 `fetch_error`가 `error`로

---

#### ProjectService.ensure_hook push 통지를 건다 — 서버 저장은 없다

**시그니처**
```rust
pub async fn ensure_hook(&mut self, code: &str, user: &UserRow) -> Result<HookStatus, Problem>
```

근거: [[SYNC-MS-001#ProjectService.ensure_hook]] 1a · [[SYNC-API-001#POST/api/admin/repos/{code}/hook]]

**처리** [[#ProjectService.get_owned]] · `→ HookStatus { hook: "none", hook_error: "서버 저장소는 통지가 없다", created: false }`

**다른 점** 서버 저장 갈래만 — 원본이 서버 안이라 밖에서 바뀌지 않는다

**호출하는 것** [[#ProjectService.get_owned]]

**테스트 관점** 내 것 → `none`과 그 문장 · 남의 것 → `not-found`

---

#### ProjectService.sync_now 지금 가져오기

**시그니처**
```rust
pub async fn sync_now(&mut self, pool: &PgPool, code: &str, user: &UserRow) -> Result<SyncResult, Problem>
```

근거: [[SYNC-MS-001#ProjectService.sync_now]] · [[SYNC-UC-001#UC-G2]]

**처리** `docs = pipeline.read_pending(pool, repos, code, user)` — 소유 검사·읽기 락·커밋 처리가 그 안에 있다 · [[#ProjectService.get_owned]]를 다시 읽어 `→ SyncResult { docs, fetched_at }`

**다른 점** 연결 풀을 받는다 — `read_pending`이 저장마다 제 트랜잭션을 연다(파이썬은 세션을 새로 읽는다, `expire_all`)

**호출하는 것** [[SYNC-MS-017#pipeline.read_pending]] · [[#ProjectService.get_owned]]

**테스트 관점** 밖에서 민 명세 커밋 → `docs` 1, 문서가 생기고 `fetched_at`이 적힌다 · 밀린 것 없음 → 0 · 남의 것 → `not-found`

---

#### ProjectService.rebuild_index 재구축 위임

**시그니처**
```rust
pub async fn rebuild_index(&mut self, pool: &PgPool, code: &str, user: &UserRow) -> Result<RebuildResult, Problem>
```

근거: [[SYNC-MS-001#ProjectService.rebuild_index]] · [[SYNC-UC-001#UC-S6]] 1a

**처리** [[#ProjectService.get_owned]] — 소유 검사는 여기서(재구축은 `get`) · README를 인덱스보다 **먼저** 맞춘다 — `hash = git.sync_readme(작업 사본, user, code, repos.specs_url)`(그 커밋이 재구축의 받기 끝에 들어가 밀림 0으로 끝난다, 실패하면 인덱스를 건드리지 않는다) · `result = pipeline.rebuild(이 연결, pool, repos, code)` — 풀은 재구축 10의 그래프 만들기가 쓴다(카드 L12) · `→ result`에 `readme_updated = hash가 있다`

**호출하는 것** [[#ProjectService.get_owned]] · [[SYNC-MS-019#Git.sync_readme]] · [[SYNC-MS-017#pipeline.rebuild]]

**테스트 관점** 앱이 만든 프로젝트 → `readme_updated=false`, 문서 수·버전 수가 저장소와 같다 · README를 밖에서 바꿔 둔 뒤 → `true`, 커밋 하나 · 남의 것 → `not-found`, 아무것도 안 바뀐다

---

#### ProjectService.rehome 서버 저장소·작업 사본 자리를 이 데이터 자리로

**시그니처**
```rust
pub async fn rehome(&mut self) -> Result<Vec<String>, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1(켜기)·9.3(옮기기)·9.6(되살리기) · 카드 L16

**처리** 켤 때마다 [[SYNC-MS-012#runtime.run]]이 부른다
1. `DB: repositories join projects where storage='server'`를 코드 순으로
2. 행마다 `origin = origins/{code}.git` · `workdir = repos/{code}`(절대 경로) · if 행의 `remote_url`·`workdir_path`가 다르다 → `DB: repositories update` — 옮긴 자리, 다른 데이터 자리(Docker 묶음 `/var/syncdoc/…`)의 백업을 되살린 것
3. if `workdir`가 없고 `origin`이 있다 → `git.clone(origin, workdir)` — 되살리기·옮기기는 작업 사본을 복사하지 않는다 · 실패는 로그만(그 프로젝트 하나 때문에 켜기를 멈추지 않는다)
4. `→` 작업 사본을 다시 만든 코드들

**다른 점** 파이썬 판에 없다 — Docker 묶음은 자리가 고정이고 볼륨이 작업 사본을 들고 있다

**예외** DB 실패 → `Problem`

**호출하는 것** [[SYNC-MS-019#Git.clone]]

**테스트 관점** (시험 DB · 임시 자리 · 진짜 git) 다른 자리를 가리키는 행 → 이 자리로 고쳐진다 · 작업 사본을 지우면 다시 만들어지고 원본 끝과 같다 · 원본이 없는 행은 건너뛴다 · 맞는 행은 아무것도 안 바뀐다

---

## 3. 미결사항

없음.
