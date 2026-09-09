---
doc_id: SYNC-MS-009
type: MS
title: MINISPEC — infra — git·github 어댑터
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — infra — git·github 어댑터

## 0. 이 문서가 다루는 것

`infra/git.py · infra/github.py`의 함수 14개. 클래스 명세 [[SYNC-DOM-002]] 4.9의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`infra`는 서비스가 아니다. git 명령과 GitHub API를 감싸는 얇은 층이며, core는 이것을 통해서만 바깥을 만진다. 여기 MINISPEC은 "어떤 git 명령을 어떤 옵션으로"까지 적는다 — 그게 이 층의 전부라서. `git.*`는 전부 `asyncio.create_subprocess_exec`로 CLI를 부른다. 실패는 `GitError(cmd, stderr)`.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#git.clone]] | clone |
| [[#git.fetch]] | fetch |
| [[#git.checkout]] | 작업 사본을 커밋으로 |
| [[#git.commit_push]] | 쓰기·커밋·push·재시도 |
| [[#git.read]] | 커밋의 파일 읽기 |
| [[#git.changed_files]] | 범위의 변경 파일 |
| [[#git.list]] | 파일 목록 |
| [[#git.log]] | 파일 이력 |
| [[#git.rev_list_count]] | 밀린 커밋 수 |
| [[#git.exists]] | 경로 존재 |
| [[#git.init_specs]] | 11단계 디렉터리·템플릿 |
| [[#github.verify_signature]] | webhook 서명 |
| [[#github.exchange_code]] | OAuth code → token |
| [[#github.get_user]] | token → 사용자 정보 |

---

## 2. 함수

#### git.clone clone

**시그니처** `async def clone(remote_url: str, workdir: Path, token: str) -> None`

**처리** `git clone {url with token} {workdir}` — **전체 이력** clone. `--depth`를 쓰지 않는다 — 재구축(`pipeline.rebuild`)이 `git log`로 파일 이력 전체를 읽기 때문. URL은 `https://x-access-token:{token}@github.com/org/repo.git`. 완료 후 `git remote set-url origin {token 없는 url}` — 토큰이 `.git/config`에 남지 않게. push 때마다 토큰을 다시 붙인다

---

#### git.fetch fetch

**시그니처** `async def fetch(workdir: Path) -> str`

**처리** `git fetch origin` → `git rev-parse origin/HEAD` · `→ 해시`. 작업 사본은 건드리지 않는다

---

#### git.checkout 작업 사본을 커밋으로

**시그니처** `async def checkout(workdir: Path, ref: str) -> None`

**처리** `git checkout --force {ref}` · 재구축·되돌리기 준비용. 작업 사본에 미커밋 변경이 있으면 안 되는 구조(모든 쓰기가 즉시 커밋)라 `--force`가 안전

---

#### git.commit_push 쓰기·커밋·push·재시도

**시그니처** `async def commit_push(workdir: Path, message: str, author: Author, path: str | None = None, content: str | None = None, files: dict[str, str] | None = None) -> str`

근거: [[SYNC-SEQ-001#SEQ-1]] 7단계 · [[SYNC-UC-001#UC-S7]] · [[SYNC-INFRA-001]] 4.3

**입력** `path`+`content` 하나 또는 `files` 여럿(초기화용) — 둘 중 하나는 있어야 한다. `author.user` — 커밋 작성자

**처리**
1. `token = AccountService.github_token_for(author.user)` · if 실패 → `! push-failed {reason: 미등록}`
2. `git fetch origin` · `git reset --hard origin/HEAD` — 작업 사본을 원격 최신으로 (락 안이라 안전)
3. 파일 쓰기 (`path` 또는 `files`). 상위 디렉터리 없으면 생성
4. `git add {paths}` · if `git diff --cached --quiet` (변경 없음) → `→ 현재 HEAD` (커밋 안 만듦. 같은 내용 재저장)
5. `git -c user.name={display_name} -c user.email={login}@users.noreply.github.com commit -m {message}`
6. `git push {url with token} HEAD:main` — 기본 브랜치는 `main` 고정(결정). 다른 브랜치 저장소는 v1에서 지원 안 함
   - if 거부(non-fast-forward, UC-S7 2a) → `git fetch` · `git rebase origin/HEAD` · if rebase 충돌 → `git rebase --abort`, `git reset --hard origin/HEAD`, `! push-failed {reason: conflict}` · else → push 재시도 **한 번**
   - if 그래도 실패 → `git reset --hard origin/HEAD`, `! push-failed {reason: stderr}`
7. `→ git rev-parse HEAD`

**출력** 커밋 해시

**테스트 관점** 정상 → 원격에 커밋, 반환 해시 = 원격 HEAD · 같은 내용 → 커밋 안 생김, HEAD 반환 · 원격이 앞서 있음(다른 파일) → rebase 후 성공 · 원격이 같은 파일 수정 → conflict, 작업 사본 원상 · 토큰이 config에 안 남음

---

#### git.read 커밋의 파일 읽기

**시그니처** `async def read(workdir: Path, path: str, ref: str = "HEAD") -> str`

**처리** `git show {ref}:{path}` → 내용. 없으면 `! GitError`

---

#### git.changed_files 범위의 변경 파일

**시그니처** `async def changed_files(workdir: Path, range: str, prefix: str) -> list[ChangedFile]`

근거: [[SYNC-SEQ-001#SEQ-2]] · [[SYNC-MS-007#pipeline.process_commit]]

**처리**
1. `git log --name-status --format="%H%x00%an%x00%ae%x00%s%n%b%x00" {range} -- {prefix}` — 커밋마다 파일 상태
2. 파일별로 **마지막으로 건드린 커밋**을 남긴다 (밀린 커밋 여럿이면 최종 상태 하나)
3. `→ [ChangedFile(path, status=A|M|D, commit_hash, author_login, message)]`. `author_login`: `%ae`가 `@users.noreply.github.com`으로 끝나면 `@` 앞부분에서 `{숫자}+` 접두를 뗀 것 (`12345+hoyoung@users.noreply.github.com` → `hoyoung`). 아니면 `%an`
4. `_templates/`·`assets/` 경로는 제외

**미결** `status=D`(삭제된 파일) — MS-001 미결과 같음

---

#### git.list 파일 목록

**시그니처** `async def list(workdir: Path, glob: str, ref: str = "HEAD") -> list[str]`

**처리** `git ls-tree -r --name-only {ref} -- docs/specs` 후 glob 필터

---

#### git.log 파일 이력

**시그니처** `async def log(workdir: Path, path: str) -> list[Commit]`

**처리** `git log --follow --reverse --format="%H%x00%an%x00%ae%x00%aI%x00%s%n%b%x00" -- {path}` → 오래된 것부터 `[Commit(hash, login, date, message)]`

---

#### git.rev_list_count 밀린 커밋 수

**시그니처** `async def rev_list_count(workdir: Path, range: str) -> int`

**처리** `git rev-list --count {range}` → 정수

---

#### git.exists 경로 존재

**시그니처** `async def exists(workdir: Path, path: str) -> bool`

**처리** `git ls-tree HEAD -- {path}` 결과 유무. 작업 사본이 아니라 **커밋된 것** 기준

---

#### git.init_specs 11단계 디렉터리·템플릿

**시그니처** `async def init_specs(workdir: Path) -> dict[str, str]`

근거: [[SYNC-UC-001#UC-A1]] 4 · [[SYNC-STD-001]] 1.1

**처리** 반환할 `files` dict 구성 — `docs/specs/{TYPE}/.gitkeep` 12개(11단계 + STD), `docs/specs/_templates/{TYPE}.md` 12개(앱에 내장된 `_templates/` 사본), `docs/specs/assets/.gitkeep`, `docs/specs/README.md`(규약 링크). `→ files` — 실제 쓰기·커밋은 `commit_push(files=…)`

---

#### github.verify_signature webhook 서명

**시그니처** `verify_signature(body: bytes, header: str) -> bool`

**처리** `expected = "sha256=" + hmac.new(config.WEBHOOK_SECRET, body, sha256).hexdigest()` · `→ hmac.compare_digest(expected, header)`. 상수 시간 비교

---

#### github.exchange_code OAuth code → token

**시그니처** `async def exchange_code(code: str) -> str`

**처리** `POST https://github.com/login/oauth/access_token {client_id, client_secret, code}` (Accept: json) → `access_token` · if 없음 → `! unauthorized`

---

#### github.get_user token → 사용자 정보

**시그니처** `async def get_user(token: str) -> GithubUser`

**처리** `GET https://api.github.com/user` (Bearer) → `{id, login, name}`. `name`이 null이면 `login`

---

## 3. 미결사항

- [ ] `commit_push` 6단계 rebase 재시도 횟수 — 지금 1회. 락이 있으니 충돌은 외부 push와만
