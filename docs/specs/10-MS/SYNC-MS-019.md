---
doc_id: SYNC-MS-019
type: MS
title: MINISPEC — git 어댑터 (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-009, SYNC-INFRA-001, SYNC-STD-004]
---

# MINISPEC — git 어댑터 (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/infra/git.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.8. 파이썬 판 [[SYNC-MS-009]]의 `git.*`와 **같은 명령·같은 옵션·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 서비스가 아니다 — git CLI를 자식 프로세스로 부르는 얇은 층이다([[SYNC-INFRA-001]] 9.1·9.2 — 순수 Rust git은 아직 push를 받지 못한다).

**카드 L6 몫은 서버 저장 프로젝트를 만들고 지우는 데 드는 일곱이다(2026-10-08).** 카드 L7이 받기·밀린 커밋 수 둘을 더했다(저장 파이프라인의 「밀린 커밋 읽기」·처리 지점 앞당기기). 이력·되돌리기(L9·L11)와 git 입구의 upload-pack·receive-pack(L10)은 그 카드가 더한다.

**`Git { exe, global_config }`** — git 실행 파일과 빈 전역 설정 파일. 켤 때 [[SYNC-MS-012#runtime.run]]이 만들어 서버 상태에 둔다. 실행 파일은 [[SYNC-MS-012#paths.git]] — 윈도는 설치 폴더의 MinGit(`mingit/cmd/git.exe`), 리눅스는 시스템 git.

**사용자 git 설정을 막는다**(사용자 결정 2026-10-08 — Rust만 격리). 파이썬 판은 Docker 안에서 돌아 시스템·전역 설정이 없다. Rust 판은 사용자 PC에서 돌아 `~/.gitconfig`의 서명·훅·autocrlf·자격 도우미와 언어가 끼어든다. 그래서 모든 git을 이렇게 부른다 — 파이썬 판이 받는 깨끗한 환경을 똑같이 만든다
- 환경: `GIT_CONFIG_NOSYSTEM=1` · `GIT_CONFIG_GLOBAL={global_config}`(빈 파일 — `~/.gitconfig`·XDG 설정 대신) · `GIT_TERMINAL_PROMPT=0` · `LC_ALL=C` · `LANGUAGE=C`
- 앞 인자: `-c core.quotepath=false`(파이썬 판과 같다, #349) `-c core.autocrlf=false` `-c commit.gpgsign=false` `-c credential.helper=` `-c safe.directory=*`(앱이 만든 저장소만 연다 — 윈도 관리자 계정에서 권한을 내린 토큰이 만든 폴더도)
- 윈도는 창 없이(`CREATE_NO_WINDOW`) · 부른 쪽이 끊기면 자식도 끝난다(`kill_on_drop`) · 시간 제한은 없다(파이썬 판과 같다)
- 표준 출력은 UTF-8 그대로(아니면 `! Internal`), 표준 오류는 깨진 바이트를 바꿔 읽는다

**실패** — 끝 코드가 0이 아니면 `Problem::Git { cmd, stderr }`(파이썬 `GitError` — `internal`로 나간다). `cmd`는 앞 인자를 뺀 `git …`(파이썬 판 메시지와 같다). push 실패는 `! PushFailed { reason }`.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `git:` 부르는 명령, `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#Git.init_bare]] | 서버 저장소 만들기 |
| [[#Git.clone]] | 작업 사본 받기 |
| [[#Git.exists]] | 커밋된 경로가 있나 |
| [[#Git.list]] | 명세 파일 목록 |
| [[#Git.read]] | 커밋된 파일 읽기 |
| [[#Git.commit_push]] | 쓰고 커밋하고 민다 |
| [[#Git.init_specs]] | 새 프로젝트의 골격 파일 |
| [[#Git.fetch]] | 서버 저장소에서 받아 온다 |
| [[#Git.rev_list_count]] | 밀린 커밋 수 |

---

## 2. 함수

#### Git.init_bare 서버 저장소 만들기

**시그니처**
```rust
pub async fn init_bare(&self, path: &Path) -> Result<(), Problem>
```

근거: [[SYNC-MS-009#git.init_bare]] · [[SYNC-INFRA-001]] 6장·9.1

**처리** [[SYNC-MS-009#git.init_bare]]와 같다 — 위 폴더를 만들고 `git: init -q --bare --initial-branch=main {path}` · 그 자리에서 `git: config receive.denyNonFastForwards true` · `receive.denyDeletes true` · `receive.fsckObjects true`. 훅은 두지 않는다

**테스트 관점** HEAD가 `refs/heads/main` · 받기 규칙 셋이 `true` · 되감는 push를 받지 않는다

---

#### Git.clone 작업 사본 받기

**시그니처**
```rust
pub async fn clone(&self, remote: &str, workdir: &Path) -> Result<(), Problem>
```

근거: [[SYNC-MS-009#git.clone]]

**처리** `git: clone {remote} {workdir}`(전체 이력) · `git: remote set-url origin {remote}`(작업 사본에서)

**다른 점** 토큰을 받지 않는다 — 싱크독_로컬은 서버 저장뿐이다([[SYNC-PRD-001#R15]])

**테스트 관점** 빈 저장소도 받는다 · 없는 자리 → `Problem::Git`

---

#### Git.exists 커밋된 경로가 있나

**시그니처**
```rust
pub async fn exists(&self, workdir: &Path, path: &str) -> Result<bool, Problem>
```

근거: [[SYNC-MS-009#git.exists]] · #349

**처리** [[SYNC-MS-009#git.exists]]와 같다 — `git: rev-parse --verify --quiet HEAD^{commit}` · if 끝 코드 1 → `false`(커밋이 없다) · if 다른 실패 → `Problem::Git` · `git: ls-tree HEAD -- {path}` 출력이 비지 않았나

**테스트 관점** 빈 저장소 → `false` · 커밋된 경로 → `true` · 작업 사본에만 있는 것 → `false` · 저장소가 아닌 자리 → `Problem::Git`

---

#### Git.list 명세 파일 목록

**시그니처**
```rust
pub async fn list(&self, workdir: &Path, glob: &str, git_ref: &str) -> Result<Vec<String>, Problem>
```

근거: [[SYNC-MS-009#git.list]]

**처리** `git: ls-tree -r --name-only {git_ref} -- docs/specs` · 줄마다 파이썬 `PurePosixPath(p).match(glob)`(뒤에서부터 조각마다 `*`·`?` 맞추기)이고 조각에 `_templates`·`assets`가 없는 것 · 차례 그대로. 맨 저장소(보관본)에도 부른다

**테스트 관점** `docs/specs/*/*.md`에 번호 붙은 폴더가 걸린다 · 더 깊은 경로·`_templates/`·`assets/`는 빠진다 · 한글 이름 문서도 센다

---

#### Git.read 커밋된 파일 읽기

**시그니처**
```rust
pub async fn read(&self, workdir: &Path, path: &str, git_ref: &str) -> Result<String, Problem>
```

근거: [[SYNC-MS-009#git.read]]

**처리** `git: show {git_ref}:{path}` → 출력 그대로 · 없는 파일 → `Problem::Git` · 작업 사본 자리가 없으면 `Problem::Internal`(파이썬 `OSError` — 부르는 쪽이 둘 다 내장 사본으로 떨어진다)

**테스트 관점** 커밋된 내용 그대로(줄바꿈 바꾸지 않음) · 없는 경로 → `Problem::Git`

---

#### Git.commit_push 쓰고 커밋하고 민다

**시그니처**
```rust
pub async fn commit_push(&self, workdir: &Path, message: &str, user: &UserRow, files: &IndexMap<String, String>, delete: &[String]) -> Result<String, Problem>
```

근거: [[SYNC-MS-009#git.commit_push]] · [[SYNC-INFRA-001]] 4.3

**처리** [[SYNC-MS-009#git.commit_push]]와 같은 차례
1. `origin = git: remote get-url origin` · if `https://`로 시작 → `! PushFailed("미등록")`(GitHub 토큰이 없다 — 파이썬 판의 토큰 없는 사람과 같은 답)
2. `git: fetch origin` · `git: rev-parse --verify --quiet origin/main` · if 있다 → `git: reset --hard origin/main`
3. 경로 가드 — 쓸 것·지울 것마다 빈 경로·`.git` 조각·작업 사본 밖(심볼릭 링크를 풀어서)이면 `! PushFailed("작업 사본 밖 경로: {p}")`, 아무것도 쓰기 전에
4. 파일을 UTF-8 그대로 쓴다(위 폴더를 만들고, 줄바꿈을 바꾸지 않는다) · 실패 → 되돌리고(`reset --hard origin/main` 또는 `update-ref -d HEAD`) `git: clean -fdq` · `! PushFailed("쓰기 실패: {경로} {사유}")`
5. `git: add -- {files…}`(넣은 차례) · `git: rm -q --ignore-unmatch -- {delete…}` · if `git: diff --cached --quiet`가 0 → 커밋 없이 `→ git: rev-parse HEAD`
6. `git: -c user.name={표시 이름} -c user.email={login}@syncdoc.local commit -q -m {message}` — 로컬 사용자(`kind=local`). 아니면 `@users.noreply.github.com`(파이썬 판과 같은 규칙)
7. 세 번까지 다시(`PUSH_RETRIES` 3, [[SYNC-INFRA-001]] 5.2): `git: push --porcelain {origin} HEAD:main` · 성공 → 끝 · `--porcelain`에 `!` 줄이 없는 실패 → 되돌리고 `! PushFailed(stderr 또는 stdout)` · 마지막에도 거부 → 되돌리고 같은 것 · 거부 → `git: fetch origin` · `git: -c user.name=… -c user.email=… rebase origin/main` · 충돌 → `git: rebase --abort` · `git: reset --hard origin/main` · `! PushFailed("conflict")` · 사이에 기다리지 않는다
8. `→ git: rev-parse HEAD`

**다른 점** 쓰는 사람은 `UserRow`(파이썬 `Author.user`) · 지울 것이 없으면 빈 조각 · 재시도 수는 상수(설정 파일에 없다)

**테스트 관점** 커밋 하나가 원격에 · 반환 해시 = 원격 main · 로컬 사용자 이메일 `{login}@syncdoc.local` · 같은 내용 → 커밋 없음 · 빈 원격 → 첫 커밋 · 원격이 앞섬 → rebase 뒤 성공 · 같은 줄 충돌 → `conflict`, 작업 사본 원상 · `.git/`·`..`·바깥 링크 → `PushFailed`, 아무것도 안 씀 · 사용자 `~/.gitconfig`의 서명·훅·autocrlf가 있어도 같은 커밋

---

#### Git.init_specs 새 프로젝트의 골격 파일

**시그니처**
```rust
pub fn init_specs(specs_url: &str) -> IndexMap<String, String>
```

근거: [[SYNC-MS-009#git.init_specs]]

**처리** [[SYNC-MS-009#git.init_specs]]와 같다 — `docs/specs/{01-RFQ…11-CODE, STD}/.gitkeep` 12 · `docs/specs/assets/.gitkeep` · `docs/specs/README.md`(파이썬 `_readme()`와 글자 하나 다르지 않다 — 규약 링크의 뿌리가 `specs_url`) — 14개, 이 차례

**다른 점** 규약 주소를 인자로 받는다 — 전역 설정이 없다. 싱크독_로컬은 `http://127.0.0.1:{실제 포트}/specs`(파이썬 폐쇄망판의 `{PUBLIC_BASE_URL}/specs`와 같은 규칙)

**테스트 관점** 14개 · 템플릿·규약 사본이 없다 · README가 파이썬 판과 바이트로 같다(같은 주소면)

---

#### Git.fetch 서버 저장소에서 받아 온다

**시그니처**
```rust
pub async fn fetch(&self, workdir: &Path) -> Result<String, Problem>
```

근거: [[SYNC-MS-009#git.fetch]]

**처리** `git: remote get-url origin` · `git: fetch origin` · `→ git: rev-parse origin/main` — 작업 사본은 건드리지 않는다

**다른 점** 사람을 받지 않는다 — 토큰 갈래(`https://` 원격)가 없다. 싱크독_로컬은 서버 저장뿐이다([[SYNC-PRD-001#R15]]). 원격 주소를 읽는 첫 명령은 파이썬 판처럼 부른다(없는 원격이면 거기서 `Problem::Git`)

**테스트 관점** 밖에서 원격에 민 커밋 → 그 해시, 작업 사본 HEAD는 그대로 · 빈 원격(커밋 없음) → `Problem::Git`

---

#### Git.rev_list_count 밀린 커밋 수

**시그니처**
```rust
pub async fn rev_list_count(&self, workdir: &Path, range: &str) -> Result<i64, Problem>
```

근거: [[SYNC-MS-009#git.rev_list_count]]

**처리** `git: rev-list --count {range}` → 정수(앞뒤 공백을 걷고) · 정수가 아니면 `Problem::Internal`

**테스트 관점** `a..b`에 커밋 하나 → 1 · 같은 것 → 0 · 없는 해시 → `Problem::Git`

---

## 3. 미결사항

없음. 이력·되돌리기·git 입구는 그 카드가 더한다 — [[SYNC-CODE-002]].
