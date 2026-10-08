---
doc_id: SYNC-MS-013
type: MS
title: MINISPEC — ProjectService (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-001, SYNC-MS-019, SYNC-UC-001, SYNC-API-001, SYNC-API-002]
---

# MINISPEC — ProjectService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/project/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.2. 파이썬 판 [[SYNC-MS-001]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

서비스는 연결과 저장소 자리를 빌려 받는다 — `ProjectService<'c> { pub db: &'c mut PgConnection, pub repos: &'c ServerRepos }`. `ServerRepos { git, origins, repos, specs_url }` — git 어댑터([[SYNC-MS-019]])·서버 저장소 자리 `origins/`·작업 사본 자리 `repos/`·README의 규약 주소. 켤 때 [[SYNC-MS-012#runtime.run]]이 만든다. 트랜잭션은 부르는 쪽이 쥔다([[SYNC-STD-004#DEV-10]]). 돌려주는 행은 `(ProjectRow, RepositoryRow)`다.

**카드 L6 몫은 만들기·지우기(보관)와 조회 셋이다(2026-10-08).** 싱크독_로컬은 **서버 저장뿐**이다([[SYNC-PRD-001#R15]] — 파이썬 폐쇄망판의 `storage_modes == ["server"]`). GitHub 갈래(주소·저장소 만들기·통지)는 없고, `storage=github`는 첫 검사에서 `storage-unavailable`이다. 동기화 상태·지금 가져오기·재구축(L11), 첨부(L8), git 입구 원본(L10)은 그 카드가 더한다.

**보관본 되살리기는 카드 L11이다**(사용자 결정 2026-10-08). 되살린 보관본에 명세가 있으면 파이썬 판은 재구축([[SYNC-MS-007#pipeline.rebuild]])으로 DB에 다시 올린다 — 그 갈래만 `not-implemented(L11)`를 내고 되살린 것을 돌려놓는다. 나머지(보관본 알림 `existing-specs`, 비어 있는 보관본 되살리기)는 파이썬 판과 같다.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `DB:` 테이블 접근, `git:` [[SYNC-MS-019]], `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ProjectService.init_project]] | 프로젝트 만들기 — 서버 저장소와 골격 커밋 |
| [[#ProjectService.delete_project]] | 등록 해제 — 서버 저장소는 보관 |
| [[#ProjectService.get]] | 코드 → 프로젝트 — 시스템 경로 |
| [[#ProjectService.get_owned]] | 코드 → 내 프로젝트 — 사람 경로 |
| [[#ProjectService.list_owned]] | 내가 소유한 목록 |

---

## 2. 함수

#### ProjectService.init_project 프로젝트 만들기 — 서버 저장소와 골격 커밋

**시그니처**
```rust
pub async fn init_project(&mut self, code: &str, name: &str, user: &UserRow, import_existing: bool, storage: Storage) -> Result<(ProjectRow, RepositoryRow), Problem>
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
7. 저장점을 열고 `DB: projects insert (code, name, owner_user_id=user.id)` · `DB: repositories insert (project_id, storage='server', remote_url=origin 절대 경로, workdir_path, registered_by_user_id=user.id)`
8. if `has`이고 `import_existing` → 저장점을 되돌리고 작업 사본을 지우고 되살린 것을 보관 자리로 돌려놓고 `! NotImplemented { card: "L11" }`(재구축)
9. `files = Git::init_specs(repos.specs_url)` · `hash = git.commit_push(workdir, "chore({code}): init syncdoc", user, files, [])` · 실패 → 저장점을 되돌리고 작업 사본을 지우고 원본을 되돌리고 그 `Problem` · `DB: repositories update last_processed_commit=hash`
10. `→ (프로젝트 행, 저장소 행)`

보관 자리 — `origins/_archive/{code}-{UTC %Y%m%d%H%M%S}.git`, 같은 초에 있으면 `-1`·`-2`…를 붙인다. 시각은 [[SYNC-STD-004#DEV-18]]의 저장 시각

**다른 점** GitHub 인자(`remote_url`·`create_repo`·`private`)가 없다 — MCP 도구·REST 본문에는 있지만 서버 저장에서 파이썬 판도 안 쓴다 · 재구축 갈래는 `not-implemented(L11)`

**예외** 1~9의 `Problem` · git·파일 실패는 `Problem::Git`·`Problem::Internal`(파이썬 판도 그대로 올린다)

**호출하는 것** [[SYNC-MS-019#Git.init_bare]] · [[SYNC-MS-019#Git.list]] · [[SYNC-MS-019#Git.clone]] · [[SYNC-MS-019#Git.exists]] · [[SYNC-MS-019#Git.init_specs]] · [[SYNC-MS-019#Git.commit_push]] · [[#ProjectService.get]](돌려줄 행)

**테스트 관점** (시험 DB · 임시 데이터 자리 · 진짜 git) 새 프로젝트 → `origins/{code}.git`(HEAD main, 받기 규칙 셋)과 골격 커밋 하나(14파일, `chore({code}): init syncdoc`), `last_processed_commit`이 원격 main · `github` → `storage-unavailable`, 아무것도 안 생김 · 나쁜 코드 → `project-code-invalid` · 같은 코드 → `project-code-conflict` · 지운 뒤 같은 코드 → `existing-specs`(`doc_count`·`archived_at`), 아무것도 안 바뀜 · 같은 초 보관본 둘 → 번호가 큰 것 · 이름 없이 남은 원본 → 보관으로 옮기고 `existing-specs` · 비어 있는 보관본 + 가져오기 → 되살리고 골격 커밋 · 명세가 있는 보관본 + 가져오기 → `not-implemented(L11)`, 보관본은 제자리 · clone 실패 → 새 원본·작업 사본·행 없음

---

#### ProjectService.delete_project 등록 해제 — 서버 저장소는 보관

**시그니처**
```rust
pub async fn delete_project(&mut self, code: &str, user: &UserRow) -> Result<(), Problem>
```

근거: [[SYNC-MS-001#ProjectService.delete_project]] · [[SYNC-UC-001#UC-H17]]

**처리** [[SYNC-MS-001#ProjectService.delete_project]]와 같다 — 코드마다 잠금을 쥐고
1. `(p, r) = get_owned(code, user)`
2. `DB:` 그 프로젝트의 `conversations`(턴·첨부는 FK로 함께)·`code_graphs` → 참조 셋(나가는 것·들어오는 문서·들어오는 항목) → `status_changes` → `items` → `versions` → `documents` → `repositories` → `projects`를 지운다
3. 작업 사본을 지운다(실패는 넘긴다) · 서버 저장이고 원본이 있으면 보관 자리로 옮긴다 — **지우지 않는다**

**다른 점** 대화·코드 그래프 행을 이 함수가 바로 지운다 — 그 묶음(L12·L14)의 서비스가 아직 없다. 그 카드가 `delete_by_project`를 두면 이 단계가 그것을 부른다

**호출하는 것** [[#ProjectService.get_owned]]

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

## 3. 미결사항

없음. 동기화·재구축·첨부·git 입구는 그 카드가 더한다 — [[SYNC-CODE-002]].
