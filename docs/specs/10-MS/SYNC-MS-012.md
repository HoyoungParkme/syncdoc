---
doc_id: SYNC-MS-012
type: MS
title: MINISPEC — runtime — 켜기·끄기·설정·PostgreSQL·한 번만 실행 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-INFRA-001, SYNC-PRD-001, SYNC-SEQ-001, SYNC-STD-004]
---

# MINISPEC — runtime (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

싱크독_로컬(Rust)의 켜기·끄기 — `crates/app`의 `runtime`·`tray`·`privilege`·`paths`·`settings`·`logs`·`instance`·`pg`와 `crates/core/src/migrate.rs`(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.1. 파이썬 판에서는 `main.py`(lifespan)·`config.py`·`db.py`와 Dockerfile의 `alembic upgrade head`가 하던 일이다 — 설치형 프로그램 하나라 PostgreSQL을 띄우고 끄는 일까지 여기서 한다([[SYNC-INFRA-001]] 9.1).

형식은 [[SYNC-STD-001]] 2.10 — 시그니처는 Rust(코드와 글자 그대로, [[SYNC-STD-004#DEV-4]]), 분기는 `if 조건 → 결과`. **표기** — `→` 반환·결과, `!` 예외(`Problem`), `·` 같은 단계 안 구분.

**켜는 중 실패는 HTTP가 아니다.** 이 문서의 함수도 `Result<_, Problem>`을 돌려주지만([[SYNC-STD-004#DEV-5]]) 켜는 중에 난 것은 `Problem::Internal`의 로그 문장이 사람이 읽는 말이다 — `main`이 그 문장을 표준 오류와 로그에 남기고 끝 코드 1로 끝난다.

**카드 L1 몫이고(2026-10-07) 카드 L4가 트레이와 첫 켜기의 브라우저, 윈도 관리자 권한 내려놓기를 더했다(2026-10-08).** git 자식 프로세스(L6·L10)·쓰기 락 기다림(L7)·밀린 커밋 따라잡기와 주기 확인(L11)·하루 한 번 백업 확인과 데이터 자리 옮기기(L16)는 그 카드가 [[#runtime.run]]·[[#runtime.shutdown]]에 단계를 더한다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#runtime.run]] | 켠다 — 끌 때까지 |
| [[#runtime.bind]] | 127.0.0.1의 포트에 묶는다 (8010, 못 쓰면 다음) |
| [[#runtime.shutdown]] | 끈다 — 새 요청 끊기 → 기다림 → PostgreSQL 멈춤 |
| [[#tray.run]] | 트레이 — 열기·끝내기, 끝날 때까지 |
| [[#privilege.drop_admin]] | 윈도 관리자 권한을 내려놓고 다시 켠다 |
| [[#paths.data_dir]] | 기본 데이터 자리 |
| [[#paths.pg_dir]] | PostgreSQL 바이너리 자리 |
| [[#settings.load]] | `settings.toml`을 읽는다 (없으면 만든다) |
| [[#logs.init]] | 로그를 연다 — 날마다 한 파일, 최근 14개 |
| [[#instance.acquire]] | 한 번만 실행 — 잠금 |
| [[#instance.publish]] | 켜진 주소를 적는다 |
| [[#instance.open_running]] | 떠 있는 것을 브라우저로 연다 |
| [[#pg.start]] | 함께 담은 PostgreSQL을 띄운다 |
| [[#pg.stop]] | PostgreSQL을 멈춘다 |
| [[#migrate.apply]] | 이전 SQL을 올린다 |

---

## 2. 함수

#### runtime.run 켠다 — 끌 때까지

**시그니처**
```rust
pub async fn run(args: Args, tray: Option<TrayLink>) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1·9.5 · [[SYNC-PRD-001#R15]]

**입력** `Args` — `--data-dir`(없으면 [[#paths.data_dir]]) · `--port`(기본 8010, 0이면 OS가 고른 포트 — 시험용) · `--no-tray`(트레이 없이 — 개발·시험) · `--no-browser`(브라우저를 열지 않는다 — 시험용) · `--autostart`(로그인 때 자동 시작이 붙인다 — 트레이로만, 브라우저를 열지 않는다. 사용자 결정 2026-10-08). `tray` — [[#tray.run]]이 넘긴 짝: 켜진 주소를 보낼 곳과 「끝내기」를 받을 곳. `--no-tray`면 없다

**처리**
1. `data = args.data_dir` 또는 `paths.data_dir()` · `data`와 그 안 `logs/`·`origins/`·`repos/`를 만든다
2. `lock = instance.acquire(data)` · if `None`(이미 켜져 있다) → `url = instance.open_running(data, !no_browser)` · 표준 출력에 `url` · `→ Ok`
3. `guard = logs.init(data)` — 이 뒤로 로그가 파일과 표준 오류에 남는다
4. `settings = settings.load(data)`
5. `pg = pg.start(paths.pg_dir(), data)`
6. 연결 풀(sqlx 기본, 최대 10)을 연다 · 연결 하나로 `migrate.apply` · 트랜잭션을 열어 `AccountService { db }.ensure_local_user(settings.local_login, settings.local_name)` 후 커밋 — 5 뒤에서 실패하면 `pg.stop` 뒤 그 `Problem`
7. `listener = runtime.bind(port, port + 9)`(0이면 `bind(0, 0)`) · 받은 포트가 `port`가 아니면 「{port}을 못 써 {실제}에 열었다 — 에이전트의 MCP 주소도 바뀐다」를 로그와 표준 출력에
8. `instance.publish(data, 실제 포트)` · 서버를 조립한다(공개 주소 `http://127.0.0.1:{실제 포트}` — 같은 망 열기는 L16) · 「싱크독_로컬 — http://127.0.0.1:{실제 포트}/」를 표준 출력에 · `tray`가 있으면 주소를 보낸다 · if `--autostart`도 `--no-browser`도 아니다 → 기본 브라우저로 연다(못 열면 로그만) — 바로 가기로 켠 사람은 화면을 바로 본다(사용자 결정 2026-10-08)
9. 끄기 신호(Ctrl+C·SIGTERM) 또는 트레이의 「끝내기」를 기다린다 → `runtime.shutdown(running)`

**출력** `Ok(())` — `main`이 끝 코드 0

**예외** 1~8의 `Problem`은 그대로 — `main`이 끝 코드 1

**호출하는 것** [[#paths.data_dir]] · [[#instance.acquire]] · [[#instance.open_running]] · [[#logs.init]] · [[#settings.load]] · [[#paths.pg_dir]] · [[#pg.start]] · [[#migrate.apply]] · [[SYNC-MS-016#AccountService.ensure_local_user]] · [[#runtime.bind]] · [[#instance.publish]] · [[#runtime.shutdown]] · [[#pg.stop]]

**테스트 관점** 실행 파일 시험(임시 데이터 자리) — 켜면 `/health`·`/api/me`가 뜨고 `instance.json`이 생긴다 · 트레이의 끝내기 신호로도 끝난다(끄는 순서는 같다) · `--autostart`·`--no-browser`면 브라우저를 열지 않는다 · 두 번째 실행은 주소를 찍고 끝 코드 0 · SIGINT로 10초 안에 끝나고 `postmaster.pid`·`instance.json`이 없다 · 다시 켜면 같은 데이터 · `LOCAL_LOGIN`이 남의 아이디면 끝 코드 1과 그 문장, PostgreSQL은 멈춰 있다 · 켜기 시간을 찍어 둔다(첫 실행·다시 켜기 — 판정은 L17)

---

#### runtime.bind 127.0.0.1의 포트에 묶는다

**시그니처**
```rust
pub async fn bind(first: u16, last: u16) -> Result<TcpListener, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 — 8010을 못 쓰면 8011~8019 가운데 하나(윈도 예약 포트 범위)

**처리** `first..=last`를 차례로 `127.0.0.1:{포트}`에 묶어 본다 — 처음 된 것 · `0`이면 OS가 고른 포트

**출력** 묶인 `TcpListener`(tokio)

**예외** 다 못 묶으면 `! Internal`(「127.0.0.1의 {first}~{last}를 다 못 쓴다 — 쓰는 프로그램을 끄거나 --port로」)

**테스트 관점** 앞 포트를 잡아 두면 다음 포트 · 범위를 다 잡아 두면 `Problem` · 0이면 아무 포트 · 묶는 주소는 127.0.0.1뿐

---

#### runtime.shutdown 끈다

**시그니처**
```rust
pub async fn shutdown(running: Running) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 끄기

**입력** `Running` — 서버 작업·끄기 신호·연결 풀·`PgServer`·데이터 자리·잠금·로그 지킴이

**처리**
1. 서버에 끄기 신호 — 새 연결을 받지 않는다
2. 진행 중 요청을 최대 10초 기다린다 · 넘으면 끊는다 — INFRA 9.1의 「쓰기 락이 풀리기를 기다린다」 자리(락은 L7부터)
3. 연결 풀을 닫는다
4. `pg.stop(pg)`
5. `instance.json`을 지운다 · 잠금을 놓는다 — 4가 실패해도 한다

**출력** `Ok(())`

**예외** 4의 `Problem`은 5 뒤에 그대로

**호출하는 것** [[#pg.stop]]

**테스트 관점** 느린 요청이 있어도 10초 안에 끝난다 · 끝난 뒤 PostgreSQL이 없고 `instance.json`이 없다 · 잠금을 다시 잡을 수 있다 · PostgreSQL이 먼저 멈춰 있어도 `Ok`

---

#### tray.run 트레이 — 열기·끝내기

**시그니처**
```rust
pub fn run(rt: &Runtime, args: Args) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1·9.2 · [[SYNC-PRD-001#R15]] · 사용자 결정 2026-10-08(메뉴는 열기·끝내기 — 「지금 백업」은 L16)

**입력** `rt` — `main`이 만든 tokio 실행기 · `args` — `--no-tray`가 아닐 때 `main`이 넘긴다

**처리**
1. `TrayLink`(주소를 받을 곳·「끝내기」를 보낼 곳)를 만들고 `rt`에서 [[#runtime.run]]을 띄운다
2. 주소를 기다린다 — 오기 전에 `runtime.run`이 끝나면(켜기 실패·두 번째 실행) 그 결과를 그대로 돌려준다
3. 아이콘(실행 파일에 담은 32×32)과 메뉴 「열기」·「끝내기」로 트레이를 만든다. 툴팁 「싱크독_로컬 — {주소}」. 못 만들면(트레이를 받는 데스크톱이 없다) 로그만 남기고 트레이 없이 간다
4. 메뉴를 받는다 — 「열기」·아이콘 두 번 누르기 → 기본 브라우저로 주소 · 「끝내기」 → `runtime.run`에 끝내기를 보낸다
5. 윈도는 이 스레드에서 메시지 루프를 돈다(트레이가 그 스레드에 붙는다) — `runtime.run`이 끝나면 루프를 닫는다. 리눅스(StatusNotifierItem, D-Bus)는 `runtime.run`이 끝나기를 기다린다
6. → `runtime.run`의 결과

**예외** `runtime.run`의 `Problem` 그대로

**호출하는 것** [[#runtime.run]]

**호출되는 것** `main`(트레이가 있을 때)

**테스트 관점** 「끝내기」 신호를 보내면 `runtime.run`이 끄는 순서대로 끝나고 이 함수가 그 결과를 돌려준다 · 켜기가 실패하면 트레이를 만들지 않고 그 `Problem` · 트레이를 못 만들어도 서버는 돈다

---

#### privilege.drop_admin 윈도 관리자 권한을 내려놓는다

**시그니처**
```rust
pub fn drop_admin() -> Option<u32>
```

근거: [[SYNC-INFRA-001]] 9.4 — PostgreSQL은 관리자 권한으로 돌지 않는다(`postgres`가 거부한다). 관리자 권한 그대로 켜지는 때 — UAC를 끈 PC · 「관리자 권한으로 실행」 · GitHub의 윈도 러너

**처리**
1. 윈도가 아니면 → `None`
2. if 환경 변수 `SYNCDOC_RESTRICTED`가 있다(이미 다시 켠 자식) → `None`
3. if 지금 토큰에 Administrators·Power Users 그룹이 켜져 있지 않다 → `None` — UAC가 켜진 보통 계정은 여기서 끝난다
4. 지금 토큰에서 두 그룹을 거부 전용으로 바꾸고 특권을 다 뺀 토큰을 만든다(`CreateRestrictedToken`, `DISABLE_MAX_PRIVILEGE`) — PostgreSQL이 `initdb`·`pg_ctl`에서 하는 것(`restricted_token.c`)과 같다 · 그 토큰의 기본 DACL에 지금 사용자를 더한다 — 관리자 토큰의 기본 DACL은 Administrators·SYSTEM뿐이라, 그 그룹을 거부 전용으로 바꾸면 자기가 만든 파이프·프로세스에도 닿지 못한다(PostgreSQL `AddUserToTokenDacl`)
5. `SYNCDOC_RESTRICTED=1`을 두고 그 토큰으로 같은 명령줄을 다시 켠다 — 표준 입력·출력·오류를 물려준다. 콘솔의 Ctrl+C는 자식이 받아 끄는 순서를 탄다 — 이 프로세스는 무시하고 기다린다
6. 자식이 끝나기를 기다린다 → `Some(자식의 끝 코드)` — `main`이 그 코드로 끝난다

**출력** `None` — 그대로 켠다 · `Some(code)` — 다시 켠 자식이 끝났다

**예외** 없음 — 3~5가 실패하면 표준 오류에 남기고 `None`(그대로 켜면 PostgreSQL이 이유를 말한다) · 자식이 켜진 뒤 6이 실패하면 표준 오류에 남기고 `Some(1)` — 그대로 켜면 둘이 켜진다

**호출되는 것** `main`(맨 처음, tokio를 만들기 전 — 환경 변수를 바꾸므로 스레드가 하나일 때)

**테스트 관점** 윈도가 아니면 `None` · 관리자 계정(GitHub 윈도 러너)에서 설치 파일로 깔아 켜면 `/health`가 뜬다(워크플로) · 이 저장소의 `unsafe`는 이 함수의 Win32 호출뿐이다

---

#### paths.data_dir 기본 데이터 자리

**시그니처**
```rust
pub fn data_dir() -> Result<PathBuf, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 · [[SYNC-PRD-001#R15]]

**처리** 사용자의 로컬 데이터 폴더(윈도 `%LOCALAPPDATA%`, 리눅스 `$XDG_DATA_HOME` 또는 `~/.local/share`) 아래 윈도 `SyncDoc Local` · 리눅스 `syncdoc-local`. 만들지는 않는다 — [[#runtime.run]] 1이 만든다. 옮긴 자리를 가리키는 파일은 L16

**예외** 사용자 폴더를 모르면 `! Internal`

**테스트 관점** 로컬 데이터 폴더 아래 · 끝 이름이 판마다 맞다(리눅스 `syncdoc-local`)

---

#### paths.pg_dir PostgreSQL 바이너리 자리

**시그니처**
```rust
pub fn pg_dir() -> Result<PathBuf, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 — 실행 파일·PostgreSQL은 설치 폴더에

**처리** 환경 변수 `SYNCDOC_LOCAL_PG_DIR`가 있으면 그것(개발 — `cargo xtask pg-fetch`가 받은 `local/target/pg/16.15.0`) · 없으면 실행 파일 옆 `postgresql/` · `bin/postgres`(윈도 `postgres.exe`)가 없으면 `Problem`

**예외** `! Internal`(「PostgreSQL을 못 찾았다 — {자리}/bin/postgres」)

**테스트 관점** 바이너리가 있는 자리면 그 자리 · 없는 자리면 그 경로가 든 `Problem`

---

#### settings.load 설정 파일을 읽는다

**시그니처**
```rust
pub fn load(data_dir: &Path) -> Result<Settings, Problem>
```

근거: [[SYNC-INFRA-001]] 5.2(이름)·9.3 · 사용자 결정 2026-10-07 — 파이썬 판 환경 변수와 같은 이름을 평평하게, 첫 실행 때 기본 파일

**입력** 데이터 자리

**처리**
1. `settings.toml`이 없으면 기본 파일을 쓴다 — 키 다섯과 기본값, 키마다 설명 주석. 유닉스에서는 사용자만 읽는다(600)
2. TOML로 읽는다. 키는 `LOCAL_LOGIN`(기본 `local`) · `LOCAL_NAME`(기본 빈 값) · `LLM_API_URL`(기본 빈 값 — 싱크독_로컬은 기본 주소가 없다, INFRA 5.3) · `LLM_API_KEY`(빈 값) · `LLM_MODEL`(`gpt-4o`) · 모르는 키는 로그에 경고만
3. `local_name` = `LOCAL_NAME`의 앞뒤 공백을 뗀 것, 비면 `LOCAL_LOGIN` · `llm_enabled` = `LLM_API_KEY`와 `LLM_API_URL`(앞뒤 공백 뗌)이 다 비어 있지 않다
4. if `LOCAL_LOGIN`이 비었거나 50자를 넘는다 · `local_name`이 100자를 넘는다 → `Problem` — DB 칸 길이다. 넣다가 깨지기 전에 켤 때 멈춘다

**출력** `Settings { local_login, local_name, llm_api_url, llm_api_key, llm_model, llm_enabled }`

**예외** 못 읽는 TOML → `! Internal`(파일과 줄) · 4 → `! Internal`

**테스트 관점** 처음 → 파일이 생기고 기본값 · 다시 읽어도 같은 값 · 빈 `LOCAL_NAME` → 아이디 · 키만 있고 주소가 없다 → `llm_enabled` 거짓 · 둘 다 있다 → 참 · 깨진 TOML → `Problem` · 빈 아이디·긴 아이디 → `Problem` · 모르는 키가 있어도 나머지 값은 그대로

---

#### logs.init 로그를 연다

**시그니처**
```rust
pub fn init(data_dir: &Path) -> Result<WorkerGuard, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 · 사용자 결정 2026-10-07 — 날마다 한 파일, 최근 14개

**처리** `logs/syncdoc-local.{날짜}.log`에 날마다 새 파일로 · 표준 오류에도 · `logs/`의 `syncdoc-local.*.log`와 `postgresql-*.log`를 각각 최근 14개만 남긴다 · 같은 프로세스에서 이미 열었으면 다시 걸지 않는다

**출력** 쓰기 작업의 지킴이(`WorkerGuard`) — 놓이면 남은 줄을 마저 쓴다

**테스트 관점** 20개를 깔아 두고 열면 종류마다 14개 · 쓴 줄이 오늘 파일에

---

#### instance.acquire 한 번만 실행

**시그니처**
```rust
pub fn acquire(data_dir: &Path) -> Result<Option<File>, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 — 한 번만 실행(잠금 파일)

**처리** `syncdoc-local.lock`을 연다(없으면 만든다) · 배타 잠금을 시도 · if 된다 → 지난번에 남은 `instance.json`을 지우고 `→ Some(파일)` — 놓으면 풀리고, 프로세스가 죽어도 OS가 푼다 · else(이미 잡혀 있다) → `None`

**예외** 파일을 못 열면 `! Internal`

**테스트 관점** 처음 `Some` · 잡고 있는 동안 `None` · 놓은 뒤 다시 `Some` · 남은 `instance.json`을 지운다

---

#### instance.publish 켜진 주소를 적는다

**시그니처**
```rust
pub fn publish(data_dir: &Path, port: u16) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 — 두 번째 실행이 이것을 읽는다

**처리** `instance.json`에 `{"pid":…,"port":…,"url":"http://127.0.0.1:{port}/"}` — 임시 파일에 쓰고 이름을 바꿔 한 번에

**예외** 못 쓰면 `! Internal`

**테스트 관점** 쓴 것을 읽으면 그 포트와 주소

---

#### instance.open_running 떠 있는 것을 연다

**시그니처**
```rust
pub async fn open_running(data_dir: &Path, browser: bool) -> Result<String, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 두 번째 실행 · [[SYNC-PRD-001#R15]]

**처리** `instance.json`의 `url`을 읽는다 — 아직 없으면(앞 실행이 켜는 중이다. 첫 실행은 15초까지) 0.2초마다 다시, 최대 60초 · if `browser` → 기본 브라우저로 연다(못 열면 로그만 — WSL처럼 브라우저가 없는 곳) · `→ url`

**예외** 60초 안에 못 읽으면 `! Internal`(「이미 켜져 있는데 주소를 못 읽었다 — {파일}」)

**테스트 관점** 파일이 있으면 그 주소 · 늦게 생겨도 기다려 읽는다 · `browser=false`면 브라우저를 열지 않는다

---

#### pg.start 함께 담은 PostgreSQL을 띄운다

**시그니처**
```rust
pub async fn start(pg_dir: &Path, data_dir: &Path) -> Result<PgServer, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1·9.2·9.4 · 사용자 결정 2026-10-07 — 앱이 직접 띄운다(시험용 라이브러리는 fsync를 끄고 멈출 때 데이터를 지운다), 연결 수·메모리는 기본값

**입력** 바이너리 자리(`bin/` 아래 `initdb`·`postgres`·`pg_ctl`), 데이터 자리

**처리**
1. `bin/initdb`·`bin/postgres`·`bin/pg_ctl`이 있나 — 없으면 `Problem`
2. `pw` = 무작위 32자(영숫자)
3. if `pgdata/`가 없다(처음) → `initdb -D pgdata.init -U syncdoc -A scram-sha-256 --pwfile=… -E UTF8 --locale=C` — 암호 파일은 사용자만 읽고 바로 지운다 · `pgdata.init`을 `pgdata`로 이름 바꿈 — 반쯤 만든 것을 다음 실행이 완성본으로 읽지 않게. 역할 이름은 Docker 판과 같은 `syncdoc`이다 — 한 판의 덤프가 다른 판에 그대로 들어간다
4. if `pgdata/postmaster.pid`가 있고 `pg_ctl status`가 돌고 있다 → `pg_ctl stop -m fast` — 지난번 비정상 종료로 남은 서버
5. `postgres --single -D pgdata postgres`의 표준 입력으로 `ALTER ROLE syncdoc PASSWORD pw` · `ALTER SYSTEM SET` `listen_addresses='127.0.0.1'` · `timezone='UTC'` · `log_timezone='UTC'` · `logging_collector=on` · `log_directory='../logs'` · `log_filename='postgresql-%Y-%m-%d.log'` · 유닉스는 `unix_socket_directories=''` — 켤 때마다 암호가 바뀐다. 암호는 디스크·명령줄·로그에 남지 않는다
6. `127.0.0.1:0`에 잠깐 묶어 빈 포트를 얻고 `pg_ctl start -D pgdata -w -t 60 -l logs/postgresql-boot.log -o "-p {포트}"` — 따로 프로세스 묶음으로 띄운다. `pg_ctl`의 표준 출력·오류는 `logs/pg_ctl.log`로 받는다 — 윈도의 `pg_ctl`은 핸들을 물려주며 서버를 띄워, 파이프로 받으면 서버가 끝날 때까지 기다린다. 터미널의 Ctrl+C가 PostgreSQL에 바로 닿지 않게 하고, 멈추는 순서는 [[#runtime.shutdown]]이 쥔다 · 실패하면 다른 포트로 두 번 더
7. `syncdoc` 역할로 `postgres` DB에 붙어 `syncdoc` DB가 없으면 만든다

**출력** `PgServer { options, port, pgdata, bin }` — `options`는 127.0.0.1·포트·`syncdoc`·`pw`·DB `syncdoc`. 놓이면(패닉 등) `pg_ctl stop`을 한 번 시도한다

**예외** 1 · `initdb`·`postgres --single`·`pg_ctl` 실패(로그 경로와 함께) · 7 → `! Internal`

**테스트 관점** (진짜 바이너리, 임시 데이터 자리) 처음 → 역할 `syncdoc` · `SHOW listen_addresses`가 127.0.0.1 · `SHOW fsync`가 on · 인코딩 UTF8·정렬 C · DB `syncdoc`이 있다 · 두 번째 → 데이터가 그대로 · 새 암호만 되고 옛 암호는 안 된다 · 앞 서버를 멈추지 않고 버려도 다음 `start`가 된다 · 암호 파일이 남지 않는다

---

#### pg.stop PostgreSQL을 멈춘다

**시그니처**
```rust
pub async fn stop(server: PgServer) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 끄기

**처리** `pg_ctl stop -D pgdata -m fast -w -t 30` · 이미 멈춰 있으면(`postmaster.pid` 없음) 성공

**예외** 멈추지 못하면 `! Internal`(로그 경로와 함께)

**테스트 관점** 멈춘 뒤 `postmaster.pid`가 없고 붙을 수 없다 · 먼저 멈춰 있어도 성공

---

#### migrate.apply 이전 SQL을 올린다

**시그니처**
```rust
pub async fn apply(db: &mut PgConnection) -> Result<Vec<&'static str>, Problem>
```

근거: [[SYNC-STD-004#DEV-7]] · [[SYNC-INFRA-001]] 9.2·9.5 — Alembic이 유일한 원본, 데이터가 더 새 판이면 켜지 않는다

**입력** 연결 하나, 트랜잭션 밖 — 파일마다 제 `BEGIN`·`COMMIT`을 들고 있어 [[SYNC-STD-004#DEV-10]]의 예외다

**처리**
1. 담은 목록 — `local/migrations/NNNN_*.sql`을 빌드 때 실행 파일에 담는다. 리비전은 파일 이름 앞 네 자리(Alembic 리비전 ID와 같다)
2. `alembic_version` 표가 없으면 처음 · 있으면 `version_num` — 행이 하나가 아니면 `Problem`
3. if 리비전이 목록에 없다 → `! Internal`(「DB가 이 프로그램보다 새 판이다(리비전 {v}) — 새 판을 설치한다」) · 아무것도 바꾸지 않는다
4. 그 뒤의 파일을 차례로 그대로 실행한다 — 파일 하나가 한 트랜잭션이다. 실패하면 되돌리고 `Problem`(파일 이름과 오류)

**출력** 올린 리비전들 — 이미 최신이면 빈 목록

**테스트 관점** 빈 DB → `0001`~`0018`을 올리고 `alembic_version`이 `0018`, 표 14개 · 다시 → 빈 목록 · `0010`까지 올린 DB → `0011`~`0018` · 모르는 리비전 → `Problem`이고 DB는 그대로 · 파일마다 `alembic_version`을 앞 리비전에서 제 리비전으로 바꾼다

---

## 3. 미결사항

없음.
