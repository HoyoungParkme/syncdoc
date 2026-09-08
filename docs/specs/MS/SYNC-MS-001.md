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
| [[#ProjectService.rebuild_index]] | 재구축 위임 |

---

## 2. 함수

#### ProjectService.init_project 프로젝트 초기화

**시그니처** `async def init_project(remote_url: str, code: str, name: str, user: User, import_existing: bool = False) -> Project`

근거: [[SYNC-SEQ-001#SEQ-4]] · [[SYNC-UC-001#UC-A1]] · [[SYNC-API-001#POST/api/projects]] · [[SYNC-API-002#init_project]]

**처리**
1. if `not re.fullmatch(r"[A-Z]{1,4}", code)` → `! project-code-invalid {rule}` (2b)
2. if `DB: projects where code` → `! project-code-conflict {code}` (2a)
3. `workdir = config.REPOS_DIR / code` · if 이미 있음 → 지운다 (이전 실패 잔재)
4. `token = AccountService.github_token_for(user)` · `git.clone(remote_url, workdir, token)` · if 실패 → workdir 삭제, `! push-failed {reason: clone}`
5. `has = git.exists(workdir, "docs/specs")`
6. if `has and not import_existing` → `n = len(git.list(workdir, "docs/specs/*/*.md"))`, workdir 삭제, `! existing-specs {doc_count: n}` (3a)
7. **트랜잭션**: `DB: projects insert (code, name)`, `DB: repositories insert (project_id, remote_url, workdir_path, last_processed_commit=None)`
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

**처리** 저장소마다 `git.fetch(workdir)` · `behind = git.rev_list_count(workdir, f"{last_processed_commit}..origin/HEAD")` · if `last_processed_commit is None` → `behind=None`(문서 없음) · `→ RepoStatus(code, remote_url, last_processed_commit, synced_at, behind_by)`. 캐시 여부는 미결

---

#### ProjectService.rebuild_index 재구축 위임

**시그니처** `async def rebuild_index(code: str) -> RebuildResult`

**처리** `get(code)` 확인 후 `pipeline.rebuild(code)`. 서비스가 pipeline을 부르는 유일한 곳(클래스 3.2)

---

## 3. 미결사항

- [ ] `repo_status`의 fetch 캐시
