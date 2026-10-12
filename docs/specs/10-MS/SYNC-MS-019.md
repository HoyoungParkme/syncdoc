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

**카드 L6 몫은 서버 저장 프로젝트를 만들고 지우는 데 드는 일곱이다(2026-10-08).** 카드 L7이 받기·밀린 커밋 수 둘을 더했다(저장 파이프라인의 「밀린 커밋 읽기」·처리 지점 앞당기기). 카드 L10이 git 입구의 둘(광고·rpc)을 더했다(2026-10-11) — 파이썬 판의 `git http-backend`를 쓰지 않고 `upload-pack`·`receive-pack --stateless-rpc`를 직접 부르되, http-backend가 내는 머리·문장을 그대로 낸다(INFRA 9.1). 카드 L11이 밀린 커밋 처리·재구축의 넷(바뀐 파일·파일 이력·작업 사본 돌리기·README 맞추기)을 더했다(2026-10-11). 카드 L12가 코드 그래프의 둘(바뀐 경로 전부·커밋 풀기)을 더했다(2026-10-11). 카드 L15가 번들 가져오기의 하나(통째로 복제)를, 카드 L16이 백업의 하나(거울 복제)를 더했다(2026-10-11). **카드 L19가 작업 사본을 git에서 뺐다(2026-10-12)** — 아래 「프로세스를 적게」.

**`Git { exe, global_config, readers }`** — git 실행 파일 · 전역 설정 파일 · 저장소마다 오래 사는 읽기 프로세스(아래). 켤 때 [[SYNC-MS-012#runtime.run]]이 [[#Git.new]]로 만들어 서버 상태에 둔다. 실행 파일은 [[SYNC-MS-012#paths.git]] — 윈도는 설치 폴더의 MinGit(`mingit/ucrt64/bin/git.exe` — 런처 `cmd/git.exe`를 거르지 않는다), 리눅스는 시스템 git.

**프로세스를 적게**(카드 L19, 사용자 결정 2026-10-11·12) — 윈도는 git 프로세스 하나가 50~70ms다(Defender가 켜진 PC, 2026-10 같은 PC에서 잼). 파이썬 판처럼 작업 사본에서 받고(fetch)·쓰고·커밋하고·밀면(push) 저장 한 번에 git이 스물 남짓 떠 0.3초([[SYNC-PRD-001#R15]])를 못 넘는다. 그래서 Rust 판은 **같은 결과를 다른 차례로** 만든다
- **작업 사본은 git이 아니다** — `repos/{code}`는 서버 저장소 `main`의 `docs/specs/`를 풀어 둔 폴더다([[#Git.materialize]]). 첨부 파일 읽기([[SYNC-MS-013#ProjectService.asset_path]])만 쓴다. git은 늘 서버 저장소(`origins/{code}.git`)에서 돈다 — 받기·되돌리기·밀기가 없다
- **커밋은 `git fast-import` 하나**([[#Git.commit]]) — 서버 저장소의 `main` 위에 바로 커밋하고 `main`을 앞으로만 옮긴다. 커밋 객체는 `git commit`이 만든 것과 바이트로 같다(본인 줄·시각·메시지 정리)
- **읽기는 저장소마다 오래 사는 `git cat-file --batch` 하나**(`readers`) — 처음 쓸 때 띄우고 다음 읽기부터 파이프로 묻는다. 없다는 답이면 그때만 원래 명령을 띄워 같은 오류 문장을 낸다 · 저장소 이름을 바꾸거나 지우기 전·gc 전·끌 때 끈다([[#Git.close]] — 윈도는 열린 팩 파일이 있으면 바꾸지도 지우지도 못한다)
- **자동 maintenance를 끈다** — 전역 설정 파일에 `gc.auto=0` · `maintenance.auto=false` · `receive.autogc=false`([[SYNC-MS-012#runtime.run]] 1). git이 스스로 띄우던 gc·maintenance가 없어지고, 하루 한 번 [[#Git.gc]]가 대신한다([[SYNC-MS-023#backup.daily]])
- 저장 도중 밖에서 같은 파일을 밀었으면 파이썬 판은 rebase로 합치고 Rust 판은 `conflict`로 돌려준다(계약 밖 — [[SYNC-CODE-002]] 2장)

**사용자 git 설정을 막는다**(사용자 결정 2026-10-08 — Rust만 격리). 파이썬 판은 Docker 안에서 돌아 시스템·전역 설정이 없다. Rust 판은 사용자 PC에서 돌아 `~/.gitconfig`의 서명·훅·autocrlf·자격 도우미와 언어가 끼어든다. 그래서 모든 git을 이렇게 부른다 — 파이썬 판이 받는 깨끗한 환경을 똑같이 만든다
- 환경: `GIT_CONFIG_NOSYSTEM=1` · `GIT_CONFIG_GLOBAL={global_config}`(앱이 쓰는 고정 내용 — `~/.gitconfig`·XDG 설정 대신. git이 띄우는 자식 git도 읽는다) · `GIT_TERMINAL_PROMPT=0` · `LC_ALL=C` · `LANGUAGE=C`
- 앞 인자: `-c core.quotepath=false`(파이썬 판과 같다, #349) `-c core.autocrlf=false` `-c commit.gpgsign=false` `-c credential.helper=` `-c safe.directory=*`(앱이 만든 저장소만 연다 — 윈도 관리자 계정에서 권한을 내린 토큰이 만든 폴더도)
- 윈도는 창 없이(`CREATE_NO_WINDOW`) · 부른 쪽이 끊기면 자식도 끝난다(`kill_on_drop`) · 시간 제한은 없다(파이썬 판과 같다)
- 표준 출력은 UTF-8 그대로(아니면 `! Internal`), 표준 오류는 깨진 바이트를 바꿔 읽는다

**실패** — 끝 코드가 0이 아니면 `Problem::Git { cmd, stderr }`(파이썬 `GitError` — `internal`로 나간다). `cmd`는 앞 인자를 뺀 `git …`(파이썬 판 메시지와 같다). push 실패는 `! PushFailed { reason }`.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `git:` 부르는 명령, `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#Git.new]] | 어댑터 만들기 |
| [[#Git.init_bare]] | 서버 저장소 만들기 |
| [[#Git.exists]] | 커밋된 경로가 있나 |
| [[#Git.list]] | 명세 파일 목록 |
| [[#Git.read]] | 커밋된 파일 읽기 |
| [[#Git.commit]] | 서버 저장소에 바로 커밋한다 |
| [[#Git.init_specs]] | 새 프로젝트의 골격 파일 |
| [[#Git.head]] | 서버 저장소의 main 끝 |
| [[#Git.rev_list_count]] | 밀린 커밋 수 |
| [[#Git.advertise_refs]] | git 입구 — 참조 광고 |
| [[#Git.service_rpc]] | git 입구 — 읽기·쓰기 |
| [[#Git.changed_files]] | 범위의 바뀐 명세 파일 |
| [[#Git.log]] | 파일 이력 |
| [[#Git.sync_readme]] | 저장소 README를 지금 판으로 |
| [[#Git.changed_paths]] | 범위에서 바뀐 경로 전부 |
| [[#Git.archive]] | 커밋의 파일을 폴더에 푼다 |
| [[#Git.materialize]] | 작업 사본 폴더를 커밋의 `docs/specs/`로 |
| [[#Git.clone_bare]] | 번들을 서버 저장소로 통째로 |
| [[#Git.mirror]] | 서버 저장소의 거울 — 백업 사진 |
| [[#Git.close]] | 저장소의 읽기 프로세스를 끈다 |
| [[#Git.close_all]] | 읽기 프로세스를 모두 끈다 |
| [[#Git.gc]] | 하루 한 번 정리 |

---

## 2. 함수

#### Git.new 어댑터 만들기

**시그니처**
```rust
pub fn new(exe: PathBuf, global_config: PathBuf) -> Git
```

근거: 0장 「프로세스를 적게」 · 카드 L19

**처리** 실행 파일·전역 설정 파일을 담고 읽기 프로세스 지도는 비운다 · 복제하면 지도를 함께 쓴다(서버 상태·파이프라인·백업이 같은 프로세스를 본다)

**테스트 관점** 복제본이 띄운 읽기 프로세스를 원본의 [[#Git.close_all]]이 끈다

---

#### Git.init_bare 서버 저장소 만들기

**시그니처**
```rust
pub async fn init_bare(&self, path: &Path) -> Result<(), Problem>
```

근거: [[SYNC-MS-009#git.init_bare]] · [[SYNC-INFRA-001]] 6장·9.1

**처리** [[SYNC-MS-009#git.init_bare]]와 같다 — 위 폴더를 만들고 `git: init -q --bare --initial-branch=main {path}` · 그 자리에서 `git: config receive.denyNonFastForwards true` · `receive.denyDeletes true` · `receive.fsckObjects true`. 훅은 두지 않는다

**테스트 관점** HEAD가 `refs/heads/main` · 받기 규칙 셋이 `true` · 되감는 push를 받지 않는다

---

#### Git.exists 커밋된 경로가 있나

**시그니처**
```rust
pub async fn exists(&self, origin: &Path, path: &str) -> Result<bool, Problem>
```

근거: [[SYNC-MS-009#git.exists]] · #349

**처리** [[SYNC-MS-009#git.exists]]와 같은 판정 — `HEAD:{path}`가 읽기 프로세스에 있나(커밋이 없으면 없다)

**다른 점** 서버 저장소의 `HEAD`(= `main`)에서 본다 · 프로세스를 띄우지 않는다(0장)

**테스트 관점** 빈 저장소 → `false` · 커밋된 경로 → `true` · 저장소가 아닌 자리 → `Problem::Git`

---

#### Git.list 명세 파일 목록

**시그니처**
```rust
pub async fn list(&self, origin: &Path, glob: &str, git_ref: &str) -> Result<Vec<String>, Problem>
```

근거: [[SYNC-MS-009#git.list]]

**처리** `git: ls-tree -r --name-only {git_ref} -- docs/specs` · 줄마다 파이썬 `PurePosixPath(p).match(glob)`(뒤에서부터 조각마다 `*`·`?` 맞추기)이고 조각에 `_templates`·`assets`가 없는 것 · 차례 그대로. 서버 저장소·보관본에서 부른다

**테스트 관점** `docs/specs/*/*.md`에 번호 붙은 폴더가 걸린다 · 더 깊은 경로·`_templates/`·`assets/`는 빠진다 · 한글 이름 문서도 센다

---

#### Git.read 커밋된 파일 읽기

**시그니처**
```rust
pub async fn read(&self, origin: &Path, path: &str, git_ref: &str) -> Result<String, Problem>
```

근거: [[SYNC-MS-009#git.read]]

**처리** `git: show {git_ref}:{path}`와 같은 답 — 읽기 프로세스에 `{git_ref}:{path}`를 묻는다 · 블롭이면 내용 그대로(UTF-8이 아니면 `Problem::Internal`) · 없다·블롭이 아니다 → 그때만 `git: show {git_ref}:{path}`를 띄워 그 결과(없는 파일이면 그 오류 문장의 `Problem::Git`) · 저장소 자리가 없으면 `Problem::Internal`(파이썬 `OSError` — 부르는 쪽이 둘 다 내장 사본으로 떨어진다)

**다른 점** 0장 「프로세스를 적게」 — 읽기 프로세스가 죽었으면 한 번 다시 띄운다

**테스트 관점** 커밋된 내용 그대로(줄바꿈 바꾸지 않음) · 없는 경로 → `Problem::Git`, `git show`와 같은 문장 · **읽기 프로세스를 띄운 뒤 만든 커밋·옮긴 `main`을 읽는다** · 죽인 뒤 다시 읽는다

---

#### Git.commit 서버 저장소에 바로 커밋한다

**시그니처**
```rust
pub async fn commit(&self, origin: &Path, workdir: &Path, message: &str, user: &UserRow, files: &IndexMap<String, String>, delete: &[String]) -> Result<Committed, Problem>
```

근거: [[SYNC-MS-009#git.commit_push]] · 0장 「프로세스를 적게」 · 카드 L19

**처리** [[SYNC-MS-009#git.commit_push]]와 같은 결과 — 서버 저장소 `main` 위에 커밋 하나
1. 경로 가드 — 쓸 것·지울 것마다 빈 경로·`.git` 조각·작업 사본 폴더 밖(심볼릭 링크를 풀어서)이면 `! PushFailed("작업 사본 밖 경로: {p}")`, 아무것도 쓰기 전에(파이썬 판과 같은 문장)
2. 메시지를 `git commit -m`처럼 정리한다(git `strbuf_stripspace` — 줄마다 끝의 공백(` `·`\t`·`\r`·`\n`)을 걷고, 앞뒤 빈 줄을 버리고, 빈 줄 여럿은 하나로, 끝에 줄바꿈 하나) · 비면 `Problem::Git`(파이썬 판의 `git commit`이 「빈 메시지」로 실패하는 것과 같다 — 응답은 `internal`). 4에서 바뀐 것이 있을 때만 본다 — 파이썬 판도 바뀐 것이 없으면 커밋하지 않아 메시지를 보지 않는다
3. `parent = Git.head`(빈 저장소면 없음)
4. 바뀐 것이 없다 — 쓸 파일마다 `parent`의 그 경로가 같은 내용이고 지울 경로마다 `parent`에 없다 → 커밋 없이 `→ Committed { hash: parent, parent }`(파이썬 `diff --cached --quiet`와 같다)
5. 본인 = `{표시 이름} <{login}@syncdoc.local>` — 로컬 사용자(`kind=local`). 아니면 `@users.noreply.github.com`(파이썬 판과 같은 규칙) · git처럼 앞뒤의 군더더기(공백 이하·`,:;<>"\'`)를 걷고 안의 줄바꿈·`<`·`>`를 뺀다 · 시각 = 지금 초, 현지 오프셋(`±HHMM`)
6. `git: -c fastimport.unpackLimit=0 fast-import --quiet --done`에 한 번에 넣는다(팩을 그대로 둔다 — 작은 것을 낱낱의 객체로 풀려고 `unpack-objects`를 하나 더 띄우지 않게. 쌓인 팩은 [[#Git.gc]]가 묶는다) — `commit refs/heads/main` · `mark :1` · `author`·`committer`(5와 같은 줄) · `data`(2의 메시지) · `from {parent}`(있을 때) · 쓸 파일마다 `M {모드} inline {경로}` + `data`(UTF-8 그대로, 줄바꿈 바꾸지 않음) — 모드는 `parent`에 있던 경로면 그 모드(`100644`·`100755`), 아니면 `100644`(파이썬 `git add`가 작업 사본 모드를 지키는 것과 같다) · 지울 것마다 `D {경로}` · `get-mark :1`(새 해시가 표준 출력으로) · `done` · 경로에 `"`·`\`·줄바꿈이 있거나 `"`로 시작하면 C 꼴로 따옴
7. fast-import는 `main`이 `parent`일 때만 옮긴다(앞으로만) — 거부(끝 코드가 0이 아님)이고 지금 `main`이 `parent`가 아니다(사이에 밖에서 밀었다) → 쓸 것·지울 것 가운데 하나라도 `parent`와 지금 `main`에서 내용이 다르면 `! PushFailed("conflict")` · 아니면 지금 `main`을 `parent`로 6을 다시(세 번까지 — `PUSH_RETRIES`, [[SYNC-INFRA-001]] 5.2) · 다른 실패 → `! PushFailed(stderr)`
8. 작업 사본 폴더에 `docs/specs/` 아래의 쓴 것을 쓰고 지운 것을 지운다(폴더가 있을 때 — [[#Git.materialize]]가 만든다)
9. `→ Committed { hash: 새 해시, parent }`

**다른 점** 0장 「프로세스를 적게」 — 받기·되돌리기·밀기가 없고 fast-import 하나다 · 저장 도중 밖에서 같은 파일을 밀었으면 rebase로 합치지 않고 `conflict`(파이썬 판은 합친다 — 계약 밖) · 부모를 돌려준다 — 처리 지점 앞당기기가 `rev-list --count` 없이 「부모 = 처리 지점」으로 같은 판정을 한다([[SYNC-MS-017#pipeline.save_pipeline]] 13a) · 쓰는 사람은 `UserRow` · 재시도 수는 상수

**호출하는 것** [[#Git.head]]

**테스트 관점** **같은 트리·부모·본인·시각이면 `git commit`이 만든 커밋과 해시가 같다**(메시지 꼴 — 끝 공백·앞뒤 빈 줄·빈 줄 여럿·`\r\n`·끝 줄바꿈 없음·한글) · 오프셋이 `git var GIT_COMMITTER_IDENT`와 같다 · 반환 해시 = `main` · 같은 내용 → 커밋 없음 · 빈 저장소 → 첫 커밋(부모 없음) · 지우기 · 실행 비트가 있던 파일을 고쳐도 `100755` · 사이에 밖에서 다른 파일을 밀었다 → 그 위에 커밋 · 같은 파일 → `conflict`, `main`은 밖의 것 · 빈 메시지 → 바뀐 것이 있으면 `Problem::Git`, 없으면 커밋 없이 부모 · `.git/`·`..`·바깥 링크 → `PushFailed`, 아무것도 안 씀 · 폴더에 쓴 것·지운 것이 그대로 · 사용자 `~/.gitconfig`가 있어도 같은 커밋

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

#### Git.head 서버 저장소의 main 끝

**시그니처**
```rust
pub async fn head(&self, origin: &Path) -> Result<Option<String>, Problem>
```

근거: [[SYNC-MS-009#git.fetch]] · 0장 「프로세스를 적게」

**처리** 읽기 프로세스에 `refs/heads/main`을 묻는다 · 커밋이면 `→ Some(해시)` · 없다(빈 저장소) → `None`

**다른 점** 파이썬 `git.fetch`(작업 사본으로 받아 `origin/main`)를 갈음한다 — 작업 사본이 git이 아니다(0장). 받지 않는다

**테스트 관점** 빈 저장소 → `None` · 밖에서 민 커밋 → 그 해시(읽기 프로세스를 띄운 뒤라도)

---

#### Git.rev_list_count 밀린 커밋 수

**시그니처**
```rust
pub async fn rev_list_count(&self, origin: &Path, range: &str) -> Result<i64, Problem>
```

근거: [[SYNC-MS-009#git.rev_list_count]]

**처리** `git: rev-list --count {range}` → 정수(앞뒤 공백을 걷고) · 정수가 아니면 `Problem::Internal`

**테스트 관점** `a..b`에 커밋 하나 → 1 · 같은 것 → 0 · 없는 해시 → `Problem::Git`

---

#### Git.advertise_refs git 입구 — 참조 광고

**시그니처**
```rust
pub async fn advertise_refs(&self, origin: &Path, service: &str, protocol: Option<&str>) -> Result<Vec<u8>, Problem>
```

근거: [[SYNC-MS-009#git.http_backend]] · git `http-backend.c` `get_info_refs` · [[SYNC-INFRA-001]] 9.1

**처리** http-backend의 `info/refs?service=` 그대로 — `service`는 `git-upload-pack`·`git-receive-pack`(부르는 쪽이 거른다) · `protocol`(요청 `Git-Protocol`)을 `:`로 나눈 `version=` 값(`0`·`1`·`2`만 센다) 가운데 가장 큰 것이 2가 아니면 — git `determine_protocol_version_server` — 앞에 pkt-line `# service={service}\n`과 flush(`0000`) · 이어서 `git: {upload-pack|receive-pack} --stateless-rpc --advertise-refs {origin}`의 출력(`GIT_PROTOCOL={protocol}`을 넘겨)

**다른 점** http-backend를 쓰지 않는다(INFRA 9.1 — MinGit에 의존을 줄인다). 머리는 부르는 쪽(입구)이 http-backend와 같이 붙인다 · 광고의 능력 목록·`agent=`는 git 판마다 다르다 — 두 판 바이트 비교 밖

**테스트 관점** 빈 저장소 → 서비스 줄 + 빈 광고 · 커밋 뒤 → `refs/heads/main`이 있다 · v2 요청 → 서비스 줄 없이 v2 광고 · `version=20`·`xversion=2`는 v2가 아니다 · `version=1:version=2`는 v2

---

#### Git.service_rpc git 입구 — 읽기·쓰기

**시그니처**
```rust
pub async fn service_rpc(&self, origin: &Path, service: &str, body: Vec<u8>, protocol: Option<&str>) -> Result<Vec<u8>, Problem>
```

근거: [[SYNC-MS-009#git.http_backend]] · git `http-backend.c` `service_rpc`

**처리** `git: {upload-pack|receive-pack} --stateless-rpc {origin}` — 본문을 표준 입력으로 넣는 일과 출력을 읽는 일을 **동시에**(차례로 하면 파이프가 찬다), 표준 오류도 비운다 · `GIT_PROTOCOL`을 넘긴다 · receive-pack은 받기 규칙(되감기·지우기·깨진 객체 거부 — [[#Git.init_bare]])이 지킨다 — 거절은 git 프로토콜 응답 안에 있다 · `→` 출력 전부

**다른 점** 본문은 부르는 쪽이 다 받아(gzip이면 풀어) 넘긴다 — 파이썬 판이 「본문을 다 넘길 때까지 응답을 시작하지 않는다」를 손으로 지킨 것과 같은 결과 · 출력을 모아 한 번에 돌려준다

**테스트 관점** (임시 자리 · 진짜 git) 진짜 git 클라이언트로 clone·push가 된다 · 되감는 push·지우는 push는 git 거절 문구로 · `main` 아닌 가지는 받는다

---

#### Git.changed_files 범위의 바뀐 명세 파일

**시그니처**
```rust
pub async fn changed_files(&self, origin: &Path, range: &str, prefix: &str) -> Result<Vec<ChangedFile>, Problem>
```

근거: [[SYNC-MS-009#git.changed_files]]

**처리** [[SYNC-MS-009#git.changed_files]]와 같은 명령·같은 갈라 읽기 — `git: log --name-status --format=%H%x00%an%x00%ae%x00%s%n%b%x00 {range} -- {prefix}` · NUL로 갈라 첫 해시 뒤로 넷씩(작성자 이름·메일·「제목\n본문」·「상태 줄들\n다음 해시」) · 커밋은 최신부터 — 경로마다 처음 본 것(가장 최근)만 · 이름 바꾸기(`R…\t옛\t새`)는 새 경로의 `M`으로 접고 옛 경로는 막는다(#31) · `_templates`·`assets` 조각이 있거나 조각이 넷 미만(`docs/specs/README.md`)이면 뺀다 · 경로 순으로 `→ [ChangedFile { path, status(첫 글자), commit_hash, author_login, message, author_email }]`
- `author_login` — 메일이 `@users.noreply.github.com`으로 끝나면 `@` 앞의 마지막 `+` 뒤, 아니면 이름(파이썬 `_login_of`)
- `message` — 제목과 본문을 가르고, 본문을 걷어 비지 않았으면 `{제목}\n\n{본문}`, 아니면 제목(파이썬 `_message`)

**테스트 관점** 커밋 둘에 같은 파일 → 최근 것 하나 · 지운 파일 → `D` · 이름 바꾸기 → 새 경로 `M`, 옛 경로 없음 · README·템플릿·첨부는 빠진다 · 여러 줄 메시지

---

#### Git.log 파일 이력

**시그니처**
```rust
pub async fn log(&self, origin: &Path, path: &str) -> Result<Vec<Commit>, Problem>
```

근거: [[SYNC-MS-009#git.log]]

**처리** [[SYNC-MS-009#git.log]]와 같다(서버 저장소의 `HEAD`에서) — `git: log --follow --diff-filter=d --name-only --format=%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%s%n%b -- {path}` · `%x1e`로 갈라 커밋마다 `%x1f` 넷으로 해시·이름·메일·시각·나머지 · 나머지의 끝 공백을 걷은 마지막 줄이 그 커밋 시점의 경로, 그 앞이 메시지(앞뒤 빈 줄을 걷고 `_message`) · 받아서 뒤집어 오래된 것부터 `→ [Commit { hash, login, date, message, email, path }]`. 지운 커밋은 빠진다(#325)

**테스트 관점** 오래된 것부터 · 이름이 바뀐 경로 — 옛 이름 시절 커밋의 `path`가 옛 경로 · 지웠다 되살린 파일 — 지운 커밋만 빠진다 · 여러 줄 메시지에서 경로를 떼어 낸다 · 없는 경로는 빈 목록

---

#### Git.sync_readme 저장소 README를 지금 판으로

**시그니처**
```rust
pub async fn sync_readme(&self, origin: &Path, workdir: &Path, user: &UserRow, code: &str, specs_url: &str) -> Result<Option<String>, Problem>
```

근거: [[SYNC-MS-009#git.sync_readme]] · [[SYNC-UC-001#UC-S6]] 1a

**처리** 원하는 것 = [[#Git.init_specs]]의 README(규약 주소 `specs_url`) · `have = git.read(서버 저장소, "docs/specs/README.md", "refs/heads/main")`(읽지 못하면 빈 글) · 같으면 `→ None`(커밋이 생기지 않는다) · 다르면 `→ git.commit(서버 저장소, 작업 사본, "chore({code}): README를 싱크독 규약 링크로", user, {README: 원하는 것}, [])`의 해시

**다른 점** 받지 않는다(0장) · 규약 주소를 부르는 쪽이 넘긴다(파이썬은 설정)

**호출하는 것** [[#Git.init_specs]] · [[#Git.read]] · [[#Git.commit]]

**테스트 관점** 앱이 만든 저장소 → `None`, 커밋 없음 · README를 밖에서 고쳐 민 뒤 → 커밋 하나, 다시 부르면 `None` · README가 없는 저장소 → 만든다

---

#### Git.changed_paths 범위에서 바뀐 경로 전부

**시그니처**
```rust
pub async fn changed_paths(&self, origin: &Path, range: &str) -> Result<Vec<String>, Problem>
```

근거: [[SYNC-MS-009#git.changed_paths]]

**처리** `git: diff --name-only {range}` → 공백뿐이 아닌 줄들 — 명세 밖도 거르지 않는다(코드가 바뀌었는지만 본다)

**테스트 관점** 코드·명세를 함께 바꾼 범위 → 둘 다

---

#### Git.archive 커밋의 파일을 폴더에 푼다

**시그니처**
```rust
pub async fn archive(&self, origin: &Path, commit: &str, dest: &Path) -> Result<(), Problem>
```

근거: [[SYNC-MS-009#git.archive]] · [[SYNC-INFRA-001]] 4.3 — 코드 그래프는 작업 사본에서 만들지 않는다

**처리** `dest`를 만든다 · `git: archive --format=tar -o {dest}/.src.tar {commit}` · 그 tar를 `dest`에 푼다 — 보통 파일과 폴더만, 절대 경로·`..` 조각은 버린다 · tar를 지운다(실패해도) — 커밋된 파일만이라 `.gitignore`된 산출물이 섞이지 않는다

**다른 점** 파이썬 `tarfile`의 `filter="data"` 대신 보통 파일·폴더만 푼다 — 심볼릭 링크는 따라가지도 만들지도 않는다(그래프는 파일을 읽기만 한다)

**테스트 관점** 커밋의 내용이 풀린다 · `.gitignore`된 파일은 없다 · 심볼릭 링크는 없다

---

#### Git.materialize 작업 사본 폴더를 커밋의 `docs/specs/`로

**시그니처**
```rust
pub async fn materialize(&self, origin: &Path, commit: &str, workdir: &Path) -> Result<(), Problem>
```

근거: 0장 「프로세스를 적게」 · [[SYNC-MS-013#ProjectService.asset_path]] · 카드 L19

**처리** `workdir`를 지우고 다시 만든다(옛 판의 clone — `.git`이 있는 것도) · `commit`에 `docs/specs`가 있으면 `git: archive --format=tar -o {workdir}/.src.tar {commit} -- docs/specs`를 [[#Git.archive]]와 같은 규칙으로 푼다(보통 파일·폴더만) · tar를 지운다

**다른 점** 파이썬 판의 작업 사본(clone)을 갈음한다 — 첨부 파일 읽기만 이 폴더를 쓴다(0장)

**테스트 관점** 커밋의 `docs/specs/` 파일만 · 옛 clone 폴더 → `.git` 없이 다시 · `docs/specs`가 없는 커밋 → 빈 폴더

---

#### Git.clone_bare 번들을 서버 저장소로 통째로

**시그니처**
```rust
pub async fn clone_bare(&self, source: &str, path: &Path) -> Result<(), Problem>
```

근거: [[SYNC-MS-009#git.clone_bare]] · [[SYNC-UC-001#UC-A1]] 1c · 카드 L15

**처리** [[SYNC-MS-009#git.clone_bare]]와 같은 명령 — 위 폴더를 만들고 `git: clone -q --bare {source} {path}` · 그 자리에서 `git: remote remove origin` · `git: symbolic-ref HEAD refs/heads/main` · [[#Git.init_bare]]와 같은 받기 규칙 셋. 가지·태그가 커밋 해시 그대로 온다

**다른 점** 토큰을 받지 않는다 — 싱크독_로컬은 번들 파일(`source`는 그 경로)에서만 부른다

**테스트 관점** 번들의 가지·태그가 같은 해시로 있다 · 원격이 없다 · HEAD가 `refs/heads/main` · 받기 규칙 셋이 `true` · 번들이 아닌 파일 → `Problem::Git`

---

#### Git.mirror 서버 저장소의 거울 — 백업 사진

**시그니처**
```rust
pub async fn mirror(&self, source: &Path, dest: &Path) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.6 · [[SYNC-MS-023#backup.make]] 3 · 카드 L16

**처리** `head = git: symbolic-ref HEAD`(원본에서, 실패면 `refs/heads/main` — 빈 저장소) · 위 폴더를 만들고 `git: clone --mirror --no-local -q {source} {dest}` — `--no-local`이라 upload-pack을 거친다: 참조를 먼저 읽고 닿는 객체만 보내 켠 채로 떠도 참조와 객체가 맞는다 · 그 자리에서 `remote remove origin` · `symbolic-ref HEAD {head}` · [[#Git.init_bare]]와 같은 받기 규칙 셋

**다른 점** 파이썬 판에 없다 — Docker 묶음의 백업(카드 BR)은 볼륨을 `tar`로 묶는다

**테스트 관점** 가지·태그 해시가 원본과 같다 · 원격이 없다 · HEAD가 원본과 같다 · 받기 규칙 셋 · 빈 저장소도 된다

---

#### Git.close 저장소의 읽기 프로세스를 끈다

**시그니처**
```rust
pub async fn close(&self, origin: &Path)
```

근거: 0장 「프로세스를 적게」 · 카드 L19

**처리** 그 저장소의 읽기 프로세스가 있으면 지도에서 빼고 끝내고 끝나기를 기다린다 · 다음 읽기가 다시 띄운다

**테스트 관점** 끈 뒤 저장소 폴더 이름을 바꿀 수 있다(윈도) · 끈 뒤 읽기 → 다시 띄워 읽는다

---

#### Git.close_all 읽기 프로세스를 모두 끈다

**시그니처**
```rust
pub async fn close_all(&self)
```

근거: 0장 · [[SYNC-MS-012#runtime.shutdown]] · 카드 L19

**처리** 지도의 저장소마다 [[#Git.close]]

**호출하는 것** [[#Git.close]]

**테스트 관점** 띄운 것이 모두 끝난다

---

#### Git.gc 하루 한 번 정리

**시그니처**
```rust
pub async fn gc(&self, origin: &Path) -> Result<(), Problem>
```

근거: 0장 「자동 maintenance를 끈다」 · [[SYNC-MS-023#backup.daily]] · 카드 L19

**처리** [[#Git.close]] · `git: -c gc.auto=6700 -c gc.autoPackLimit=50 -c gc.autoDetach=false gc --auto --quiet`(서버 저장소에서 — 전역 설정의 `gc.auto=0`을 이 한 번만 git 기본 문턱으로 되돌린다. 쌓인 것이 문턱 아래면 아무것도 하지 않는다 · 뒤로 떨어져 돌지 않는다)

**호출하는 것** [[#Git.close]]

**테스트 관점** 저장마다 팩이 하나라 팩이 문턱(50)을 넘은 저장소 → 팩이 줄고 `main`·내용은 그대로 · 낱낱의 객체(6700 넘게 — 밖에서 민 작은 push는 낱낱의 객체로 온다)도 묶인다 · 쌓인 것이 없으면 그대로

---

## 3. 미결사항

없음.
