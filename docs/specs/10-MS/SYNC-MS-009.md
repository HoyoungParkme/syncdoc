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

**시그니처** `async def fetch(workdir: Path, token: str | None = None) -> str`

**처리** if `token` → `git fetch {url with token} +refs/heads/*:refs/remotes/origin/*` · else → `git fetch origin` → `git rev-parse origin/HEAD` · `→ 해시`. 작업 사본은 건드리지 않는다.

**public 저장소는 토큰 없이 된다** — v1은 public만 쓴다. `clone`이 `.git/config`에서 토큰을 지우므로 private이면 매번 URL에 붙여야 하고, 그때 호출자가 `AccountService.github_token_for(repo.registered_by_user)`로 얻어 넘긴다. private 지원은 v2(8장 미결)

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
   - **원격에 커밋이 하나도 없으면 `origin/HEAD`가 없다.** 되돌아갈 곳이 없으므로 reset을 건너뛴다. 이 커밋이 그 저장소의 첫 커밋이 된다 (UC-A1 기본 흐름 3, #6)
3. 파일 쓰기 (`path` 또는 `files`). 상위 디렉터리 없으면 생성
4. `git add {paths}` · if `git diff --cached --quiet` (변경 없음) → `→ 현재 HEAD` (커밋 안 만듦. 같은 내용 재저장)
5. `git -c user.name={display_name} -c user.email={login}@users.noreply.github.com commit -m {message}`
6. `git push {url with token} HEAD:main` — 기본 브랜치는 `main` 고정(결정). 다른 브랜치 저장소는 v1에서 지원 안 함
   - if 거부(non-fast-forward, UC-S7 2a) → `git fetch` · `git rebase origin/HEAD` · if rebase 충돌 → `git rebase --abort`, `git reset --hard origin/HEAD`, `! push-failed {reason: conflict}` · else → push 재시도. **`PUSH_RETRIES`회까지**(기본 3)
   - if 다 쓰고도 실패 → `git reset --hard origin/HEAD`, `! push-failed {reason: stderr}`
   - **빈 저장소였으면 되돌릴 원격 커밋이 없다.** reset 대신 `git update-ref -d HEAD`로 방금 만든 로컬 커밋만 푼다
7. `→ git rev-parse HEAD`

**출력** 커밋 해시

**거부 판정을 stderr 문자열로 하지 않는다.** git이 영어로 말한다는 보장이 없다 — 로케일이 다르면
`"rejected"`가 안 나와 거부를 다른 실패로 잘못 보고 재시도조차 안 한다. `git push --porcelain`의
출력이나 종료 코드로 판정한다.

**재시도 사이에 기다리지 않는다.** 저장은 프로젝트 코드 단위 락 안에서 돌므로, 자는 동안 같은
프로젝트의 다른 저장이 전부 막힌다.

**재시도로 건지는 것은 좁다.** 진입할 때 원격 최신에 맞추므로 거부는 `fetch`와 `push` 사이의 짧은
틈에 외부 push가 끼어들 때만 난다. 한 번으로도 대부분 건지고, 셋은 여럿이 같은 저장소를 만질 때의
대비다. **rebase 충돌은 몇 번을 해도 안 풀린다** — 에이전트가 현재 본문을 다시 읽어 합쳐야 한다.

**테스트 관점** 커밋이 하나도 없는 원격 → 이 커밋이 첫 커밋 · 정상 → 원격에 커밋, 반환 해시 = 원격 HEAD · 같은 내용 → 커밋 안 생김, HEAD 반환 · 원격이 앞서 있음(다른 파일) → rebase 후 성공 · 연달아 두 번 앞서도 성공(재시도 2회) · 원격이 같은 파일 수정 → conflict, 작업 사본 원상 · 토큰이 config에 안 남음 · **git 로케일이 영어가 아니어도 거부를 거부로 판정**

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
2a. **rename(`R…`)은 새 경로의 `M`으로 접고 옛 경로는 버린다.** `--name-status`는 rename 감지가 기본이라 `R100\t옛\t새` 줄을 낸다. 파일이 옮겨진 것이지 문서가 둘이 된 게 아니다 — 옛 경로를 남기면 `process_commit`이 `git show {head}:{옛 경로}`를 읽으려다 죽고, 한 파일이 실패하면 `last_processed_commit`이 안 올라가 **따라잡기가 영원히 그 자리에 멈춘다**(#31)
2b. 옛 경로를 버리는 것은 **그 rename보다 앞선 커밋**의 항목에만 적용한다. 커밋 목록은 최신부터 훑으므로, rename 뒤에 옛 경로로 새 파일이 생겼으면 그 항목이 이미 잡혀 있고 그것은 살린다
3. `→ [ChangedFile(path, status=A|M|D, commit_hash, author_login, message, author_email)]`. 상태는 셋뿐이다 — `R`은 2a에서 `M`으로 접혔다. `author_login`: `%ae`가 `@users.noreply.github.com`으로 끝나면 `@` 앞부분에서 `{숫자}+` 접두를 뗀 것 (`12345+hoyoung@users.noreply.github.com` → `hoyoung`). 아니면 `%an`. `author_email`: **`%ae` 원본 그대로**
3a. **`author_login`과 `author_email`을 둘 다 싣는다.** `author_login`은 noreply 메일일 때만 진짜 GitHub 아이디이고, 아니면 `%an`(사람 이름)이라 신원의 근거가 못 된다 — 공백이 든 문자열일 수 있다. 파이프라인은 **이메일로 먼저** 사람을 찾는다([[SYNC-MS-006#AccountService.user_for_commit]]). 여기서 login을 고쳐 이메일만 넘기지는 않는다 — 이메일이 등록 안 됐을 때 login이 2차 단서로 남아야 한다
4. **명세가 아닌 것은 제외한다** — `_templates/`·`assets/` 경로, 그리고 **타입 디렉터리 밖의 파일**(`docs/specs/` 바로 아래). `init_specs`가 만드는 `README.md`가 거기 있다. 제외하지 않으면 싱크독이 만든 파일이 싱크독의 따라잡기를 막는다(#32)
   - `docs/specs/BOGUS/…` 같은 **알 수 없는 타입 디렉터리**는 제외하지 않는다. 사람이 잘못 넣은 것이라 `process_commit`이 실패로 남겨 알려야 한다

**테스트 관점** 범위가 rename 커밋을 **가로지를 때** 옛 경로 항목이 하나도 안 남는다(#31) · rename 커밋 하나만 처리하면 새 경로 `M` 하나 · rename 뒤 옛 경로에 새 파일 → 그 항목은 남는다

**미결** `status=D`(삭제된 파일) — MS-001 미결과 같음

---

#### git.list 파일 목록

**시그니처** `async def list(workdir: Path, glob: str, ref: str = "HEAD") -> list[str]`

**처리** `git ls-tree -r --name-only {ref} -- docs/specs` 후 glob 필터

---

#### git.log 파일 이력

**시그니처** `async def log(workdir: Path, path: str) -> list[Commit]`

**처리** `git log --follow --format="%H%x00%an%x00%ae%x00%aI%x00%s%n%b%x00" -- {path}` → 최신부터 온 것을 **파이썬에서 뒤집어** 오래된 것부터 `[Commit(hash, login, date, message, email)]`. `login`·`email`은 `changed_files` 3·3a와 같은 규칙 — 재구축도 이메일로 먼저 사람을 찾는다

**`--reverse`를 git에 맡기지 않는다.** `--follow`는 revision walker의 특수 처리라 `--reverse`와 조합되지 않는다 — 둘을 같이 주면 커밋이 거의 안 나온다. 실측(`SYNC-DOM-002`): `--follow` 18건 · `--reverse` 7건 · **둘 다 1건**. 이름이 바뀐 경로(`docs/specs/DOM/` → `docs/specs/06-DOM/`)를 건너 이력을 잇는 것이 `--follow`의 목적이므로 그쪽을 남기고 순서는 받아서 뒤집는다(#39)

**테스트 관점** 이름을 안 바꾼 파일 · **이름이 바뀐 경로 — 옛 이름 시절 커밋까지 나온다** · 오래된 것부터 온다 · 없는 경로는 빈 목록

---

#### git.rev_list_count 밀린 커밋 수

**시그니처** `async def rev_list_count(workdir: Path, range: str) -> int`

**처리** `git rev-list --count {range}` → 정수

---

#### git.exists 경로 존재

**시그니처** `async def exists(workdir: Path, path: str) -> bool`

**처리** `git ls-tree HEAD -- {path}` 결과 유무. 작업 사본이 아니라 **커밋된 것** 기준

**커밋이 하나도 없는 저장소는 `false`다.** `HEAD`가 가리키는 것이 없어 git이 실패하는데, 그것을 에러로 올리면 빈 저장소로 프로젝트를 시작하는 길이 막힌다 — 새 프로젝트를 시작하는 가장 흔한 방법이 그것이다. `HEAD` 없음만 `false`로 삼키고 다른 git 오류는 그대로 올린다

---

#### git.init_specs 11단계 디렉터리·템플릿

**시그니처** `async def init_specs(workdir: Path) -> dict[str, str]`

근거: [[SYNC-UC-001#UC-A1]] 4 · [[SYNC-STD-001]] 1.1

**처리** 반환할 `files` dict 구성 — `docs/specs/{NN-TYPE}/.gitkeep` 12개(11단계는 `01-RFQ`…`11-CODE`, 단계 밖 `STD`는 번호 없이 — STD-001 1.1), `docs/specs/_templates/{TYPE}.md` 12개(템플릿 파일명은 타입만. 앱에 내장된 `_templates/` 사본), `docs/specs/assets/.gitkeep`, `docs/specs/README.md`(규약 링크 + 11단계 순서표). `→ files` — 실제 쓰기·커밋은 `commit_push(files=…)`

---

#### github.verify_signature webhook 서명

**시그니처** `verify_signature(body: bytes, header: str) -> bool`

**처리** `expected = "sha256=" + hmac.new(config.WEBHOOK_SECRET, body, sha256).hexdigest()` · `→ hmac.compare_digest(expected, header)`. 상수 시간 비교

---

#### github.exchange_code OAuth code → token

**시그니처** `async def exchange_code(code: str, redirect_uri: str) -> str`

**처리** `POST https://github.com/login/oauth/access_token {client_id, client_secret, code, redirect_uri}` (Accept: json) → `access_token` · if 없음 → `! unauthorized`. `redirect_uri`는 authorize에 보낸 것과 **같은 값**이어야 한다(GitHub가 대조한다)

---

#### github.get_user token → 사용자 정보

**시그니처** `async def get_user(token: str) -> GithubUser`

**처리** `GET https://api.github.com/user` (Bearer) → `{id, login, name}`. `name`이 null이면 `login`

---

## 3. 미결사항

- [x] **private 저장소 지원.** v1은 public 전용 — `fetch`가 토큰 없이 돈다. private이면 폴링·재구축·`repo_status`가 `registered_by_user_id`의 토큰으로 fetch해야 하고, 그 사람이 권한을 잃었을 때 UI-14에 표시하는 흐름이 필요하다. `clone`·`commit_push`는 이미 토큰을 쓴다 — 결정: v1은 public 전용(인프라 5장). private은 v2 — `git.fetch(workdir, token)`과 `registered_by_user_id`가 그 자리
- [x] `commit_push` 6단계 rebase 재시도 횟수 — 지금 1회. 락이 있으니 충돌은 외부 push와만 — 결정: **3회**(`PUSH_RETRIES` 설정, 기본 3). 거부는 `fetch`→`reset` 이후 push 사이의 짧은 틈에 외부 push가 끼어들 때만 나므로 한 번으로도 대부분 건지지만, 여럿이 같은 저장소를 만질 때를 대비한다. 재시도 사이에 기다리지 않는다 — 락을 쥔 채 자면 같은 프로젝트의 다른 저장이 전부 막힌다. **rebase 충돌은 재시도로 안 풀린다** — 되돌리고 `push-failed{reason: conflict}`, 에이전트가 현재 본문을 다시 읽어 합친다
