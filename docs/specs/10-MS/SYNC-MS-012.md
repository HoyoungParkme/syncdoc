---
doc_id: SYNC-MS-012
type: MS
title: MINISPEC — runtime — 켜기·끄기·설정·PostgreSQL·한 번만 실행 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-INFRA-001, SYNC-PRD-001, SYNC-SEQ-001, SYNC-STD-004, SYNC-MS-017]
---

# MINISPEC — runtime (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

싱크독_로컬(Rust)의 켜기·끄기 — `crates/app`의 `runtime`·`tray`·`privilege`·`paths`·`settings`·`logs`·`instance`·`pg`와 `crates/core/src/migrate.rs`(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.1. 파이썬 판에서는 `main.py`(lifespan)·`config.py`·`db.py`와 Dockerfile의 `alembic upgrade head`가 하던 일이다 — 설치형 프로그램 하나라 PostgreSQL을 띄우고 끄는 일까지 여기서 한다([[SYNC-INFRA-001]] 9.1).

형식은 [[SYNC-STD-001]] 2.10 — 시그니처는 Rust(코드와 글자 그대로, [[SYNC-STD-004#DEV-4]]), 분기는 `if 조건 → 결과`. **표기** — `→` 반환·결과, `!` 예외(`Problem`), `·` 같은 단계 안 구분.

**켜는 중 실패는 HTTP가 아니다.** 이 문서의 함수도 `Result<_, Problem>`을 돌려주지만([[SYNC-STD-004#DEV-5]]) 켜는 중에 난 것은 `Problem::Internal`의 로그 문장이 사람이 읽는 말이다 — `main`이 그 문장을 표준 오류와 로그에 남기고 끝 코드 1로 끝난다.

**카드 L1 몫이고(2026-10-07) 카드 L4가 트레이와 첫 켜기의 브라우저, 윈도 관리자 권한 내려놓기를, 카드 L6이 git 자리와 서버 저장소 자리를, 카드 L11이 밀린 커밋 따라잡기와 주기 확인을 더했다(2026-10-11).** 카드 L16이 다시 켜기 고리(설정 저장·되살리기·데이터 자리 옮기기 — 처리는 [[SYNC-MS-023]])와 같은 망 열기, 「지금 백업」, 설정 값 쓰기, 옮긴 자리를 가리키는 파일, 로그 대상 바꾸기를 더했다(2026-10-11).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#runtime.run]] | 켠다 — 끌 때까지 |
| [[#runtime.bind]] | 127.0.0.1의 포트에 묶는다 (8010, 못 쓰면 다음) |
| [[#runtime.shutdown]] | 서빙을 내린다 — 새 요청 끊기 → 기다림 → 연결 풀 닫기 |
| [[#tray.run]] | 트레이 — 열기·지금 백업·끝내기, 끝날 때까지 |
| [[#privilege.drop_admin]] | 윈도 관리자 권한을 내려놓고 다시 켠다 |
| [[#paths.data_dir]] | 데이터 자리 — 옮겼으면 가리키는 곳 |
| [[#paths.set_data_dir]] | 옮긴 자리를 가리키는 파일을 쓴다 |
| [[#paths.pg_dir]] | PostgreSQL 바이너리 자리 |
| [[#paths.git]] | git 실행 파일 |
| [[#settings.load]] | `settings.toml`을 읽는다 (없으면 만든다) |
| [[#settings.save]] | `settings.toml`의 값만 바꾼다 |
| [[#logs.init]] | 로그를 연다 — 날마다 한 파일, 최근 14개 |
| [[#logs.retarget]] | 로그를 옮긴 자리로 |
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

근거: [[SYNC-INFRA-001]] 9.1·9.3·9.4·9.5·9.6 · [[SYNC-PRD-001#R15]]

**입력** `Args` — `--data-dir`(없으면 [[#paths.data_dir]]) · `--port`(기본 8010, 0이면 OS가 고른 포트 — 시험용) · `--no-tray`(트레이 없이 — 개발·시험) · `--no-browser`(브라우저를 열지 않는다 — 시험용) · `--autostart`(로그인 때 자동 시작이 붙인다 — 트레이로만, 브라우저를 열지 않는다. 사용자 결정 2026-10-08). `tray` — [[#tray.run]]이 넘긴 짝: 켜진 주소를 보낼 곳 · 「끝내기」를 받을 곳 · 「지금 백업」을 받을 곳. `--no-tray`면 없다

**처리** 고리가 둘이다 — 바깥은 데이터 자리(잠금·로그 대상·PostgreSQL), 안은 켜기(설정·연결 풀·서빙). 다시 켜기(카드 L16)는 프로그램과 트레이를 그대로 두고 고리를 다시 돈다
1. `data = args.data_dir` 또는 `paths.data_dir()` · `data`와 그 안 `logs/`·`origins/`·`repos/`를 만든다 · `gitconfig`를 고정 내용으로 쓴다(켤 때마다 — `gc.auto=0` · `maintenance.auto=false` · `receive.autogc=false`) — git이 사용자 전역 설정 대신 읽는다. 자동 정리를 끄고 하루 한 번 [[SYNC-MS-019#Git.gc]]가 대신한다([[SYNC-MS-019]] 0장, 카드 L6·L19)
2. `lock = instance.acquire(data)` · if `None`(이미 켜져 있다) → `url = instance.open_running(data, !no_browser)` · 표준 출력에 `url` · `→ Ok`
3. `guard = logs.init(data)` — 이 뒤로 로그가 파일과 표준 오류에 남는다 · 프로세스 내내 사는 `Shared`(마지막 백업·마지막 다시 켜기·백업 잠금, [[SYNC-MS-023]] 0장)
4. **바깥 고리(데이터 자리)** — `pg = pg.start(paths.pg_dir(), data)`
5. **안 고리(켜기)**
   1. `settings = settings.load(data)`
   2. 연결 풀(최대 10, 쉬는 연결을 닫지 않는다 — `idle_timeout`·`max_lifetime` 없음. 윈도는 연결마다 postgres 프로세스를 띄워 다시 맺는 값이 크다, 카드 L19)을 연다 · 연결 하나로 `migrate.apply` · 트랜잭션을 열어 `AccountService { db }.ensure_local_user(settings.local_login, settings.local_name)` 후 커밋 — 실패하면 `pg.stop` 뒤 그 `Problem`
   3. 묶는 곳 — `settings.public_base_url`이 있으면 모든 주소(`0.0.0.0`), 없으면 `127.0.0.1`(같은 망 열기, INFRA 9.4) · 처음이면 `listener = runtime.bind(곳, port, port + 9)`(0이면 `bind(곳, 0, 0)`), 다시 켜는 것이면 지난 포트를 먼저 · 받은 포트가 `port`가 아니면 「{port}을 못 써 {실제}에 열었다 — 에이전트의 MCP 주소도 바뀐다」를 로그와 표준 출력에
   4. `instance.publish(data, 실제 포트)` · 공개 주소 = `settings.public_base_url`(끝 `/`를 뗀 것) 또는 `http://127.0.0.1:{실제 포트}` · 서버 저장소 자리 `ServerRepos { git: Git::new(paths.git(), data/gitconfig), origins: data/origins, repos: data/repos, specs_url: {공개 주소}/specs }`(카드 L6·L19)
   5. 작업 사본 맞추기 — `ProjectService { db, repos }.rehome()`([[SYNC-MS-013#ProjectService.rehome]]) · 다시 만든 코드는 로그에(카드 L16 — 옮긴 자리·되살린 백업) · 서버를 조립한다 — 가드의 공개 netloc(공개 주소의 `이름[:포트]`) · 이 PC `Local`([[SYNC-MS-023]] — 데이터 자리·PostgreSQL·git·`Shared`·다시 켜기 통로)
   6. 따라잡기 — [[SYNC-MS-017#pipeline.catch_up]]을 따로 한 번 띄우고(기다리지 않는다 — 꺼져 있던 동안 쌓인 커밋) [[SYNC-MS-017#pipeline.poll_loop]]`(300초)`와 [[SYNC-MS-023#backup.daily]]를 띄운다(INFRA 9.1 켜기·9.6)
   7. 처음 켜질 때만 — 「싱크독_로컬 — http://127.0.0.1:{실제 포트}/」를 로그와 표준 출력에 · `tray`가 있으면 주소를 보낸다 · if `--autostart`도 `--no-browser`도 아니다 → 기본 브라우저로 연다(못 열면 로그만, 사용자 결정 2026-10-08)
   8. 기다린다 — 끄기 신호(Ctrl+C·SIGTERM)·트레이 「끝내기」 → 끈다 · 트레이 「지금 백업」 → `Local.backup_now`를 따로 띄우고 계속 기다린다(`tokio::select!` 안이라 코드 그래프의 「호출하는 것」에는 없다) · 다시 켜기 통로의 `Op` → 그것
   9. `runtime.shutdown(serving)` — 서빙을 내린다
   10. 끈다 → `pg.stop(pg)` · `instance.json`을 지우고 잠금을 놓는다(`pg.stop`이 실패해도) · `→ Ok` 또는 `pg.stop`의 `Problem`
   11. `Op::Settings` → 마지막 다시 켜기를 「설정을 저장하고 다시 켰다」로 · 안 고리 처음으로
   12. `Op::Restore(opened)` → `backup.restore(opened, pg, data)`([[SYNC-MS-023#backup.restore]]) · 마지막 다시 켜기를 성공 「{이름}로 되살렸다」 또는 실패 「되살리지 못해 되돌렸다 — {이유}」로 · 안 고리 처음으로
   13. `Op::Move(target)` → `pg.stop(pg)` · `datadir.copy(data, target)`([[SYNC-MS-023#datadir.copy]]) · 성공 → `--data-dir`로 켠 것이 아니면 `paths.set_data_dir(target)` · 새 자리에 `logs/`·`origins/`·`repos/`를 만들고 `instance.acquire(target)`(못 잡으면 실패) · 옛 `instance.json`을 지우고 옛 잠금을 놓는다 · `guard = logs.retarget(target)` · `data = target` · 마지막 다시 켜기를 「{자리}로 옮겼다」로 — 실패 → 「옮기지 못했다 — {이유}」(옛 자리 그대로) · 바깥 고리 처음으로

**출력** `Ok(())` — `main`이 끝 코드 0

**예외** 1~5의 `Problem`은 그대로 — `main`이 끝 코드 1. 다시 켠 뒤 5에서 실패해도 그렇다(설정 저장은 처리기가 먼저 검사한다)

**호출하는 것** [[#paths.data_dir]] · [[#instance.acquire]] · [[#instance.open_running]] · [[#logs.init]] · [[#settings.load]] · [[#paths.pg_dir]] · [[#paths.git]] · [[SYNC-MS-019#Git.new]] · [[#pg.start]] · [[#migrate.apply]] · [[SYNC-MS-016#AccountService.ensure_local_user]] · [[SYNC-MS-013#ProjectService.rehome]] · [[#runtime.bind]] · [[#instance.publish]] · [[SYNC-MS-017#pipeline.catch_up]] · [[SYNC-MS-017#pipeline.poll_loop]] · [[SYNC-MS-023#backup.daily]] · [[#runtime.shutdown]] · [[#pg.stop]] · [[SYNC-MS-023#backup.restore]] · [[SYNC-MS-023#datadir.copy]] · [[#paths.set_data_dir]] · [[#logs.retarget]]

**테스트 관점** 실행 파일 시험(임시 데이터 자리) — 꺼진 동안 서버 저장소에 민 명세 커밋이 켜면 문서가 된다 · 켜면 `/health`·`/api/me`가 뜨고 `instance.json`이 생긴다 · 트레이의 끝내기 신호로도 끝난다(끄는 순서는 같다) · `--autostart`·`--no-browser`면 브라우저를 열지 않는다 · 두 번째 실행은 주소를 찍고 끝 코드 0 · SIGINT로 10초 안에 끝나고 `postmaster.pid`·`instance.json`이 없다 · 다시 켜면 같은 데이터 · `LOCAL_LOGIN`이 남의 아이디면 끝 코드 1과 그 문장, PostgreSQL은 멈춰 있다 · 켜기 시간을 찍어 둔다(첫 실행·다시 켜기 — 판정은 L17) · 설정 저장 → 같은 포트로 다시 뜨고 바뀐 이름이 `/api/me`에 · 백업 → 문서 더함 → 되살리기 → 그 문서가 없다 · 옮기기 → 새 자리에서 같은 문서, 옛 자리는 그대로, `instance.json`은 새 자리에 · `PUBLIC_BASE_URL`이면 그 이름의 Host가 통과한다
---

#### runtime.bind 포트에 묶는다 (8010, 못 쓰면 다음)

**시그니처**
```rust
pub async fn bind(host: IpAddr, first: u16, last: u16) -> Result<TcpListener, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 — 8010을 못 쓰면 8011~8019 가운데 하나(윈도 예약 포트 범위) · 9.4 — 같은 망 열기면 모든 주소

**처리** `first..=last`를 차례로 `{host}:{포트}`에 묶어 본다 — 처음 된 것 · `0`이면 OS가 고른 포트. `host`는 [[#runtime.run]]이 고른다 — 보통 `127.0.0.1`, `PUBLIC_BASE_URL`이 있으면 `0.0.0.0`

**출력** 묶인 `TcpListener`(tokio)

**예외** 다 못 묶으면 `! Internal`(「{host}의 {first}~{last}를 다 못 쓴다 — 쓰는 프로그램을 끄거나 --port로」)

**테스트 관점** 앞 포트를 잡아 두면 다음 포트 · 범위를 다 잡아 두면 `Problem` · 0이면 아무 포트 · 준 주소에 묶인다
---

#### runtime.shutdown 서빙을 내린다

**시그니처**
```rust
pub async fn shutdown(serving: Serving)
```

근거: [[SYNC-INFRA-001]] 9.1 끄기 · 9.6 다시 켜기(카드 L16)

**입력** `Serving` — 서버 작업·끄기 신호·따로 띄운 작업(따라잡기·주기 확인·하루 한 번 백업)·연결 풀·git 어댑터

**처리**
1. 서버에 끄기 신호 — 새 연결을 받지 않는다
2. 따로 띄운 작업을 멈춘다(파이썬 판 `lifespan`이 끌 때 취소하는 것과 같다)
3. 진행 중 요청과 쓰기 락([[SYNC-MS-017#pipeline.wait_idle]])을 합쳐 최대 10초 기다린다 · 넘으면 끊는다 — INFRA 9.1의 「쓰기 락이 풀리기를 기다린다」. 요청이 끊겨도 저장은 따로 돌므로([[SYNC-MS-017#pipeline.save_pipeline]]) git과 DB 사이에 있는 저장까지(카드 L7)
4. 연결 풀을 닫는다
5. git 읽기 프로세스를 모두 끈다([[SYNC-MS-019#Git.close_all]], 카드 L19) — 되살리기·옮기기가 서버 저장소 폴더를 바꾸거나 옮기기 전에(윈도는 열린 팩 파일이 있으면 못 한다)

PostgreSQL·`instance.json`·잠금은 [[#runtime.run]]이 쥔다 — 끌 때는 그 뒤 `pg.stop`, 다시 켤 때는 그대로(옮기기면 `pg.stop`)

**호출하는 것** [[SYNC-MS-017#pipeline.wait_idle]] · [[SYNC-MS-019#Git.close_all]]

**테스트 관점** 느린 요청이 있어도 10초 안에 끝난다 · 읽기 프로세스를 끄는 것은 [[SYNC-MS-019#Git.close_all]] 시험이 본다(띄운 것이 모두 끝나고 폴더를 옮길 수 있다) · 끝난 뒤 그 포트를 다시 묶을 수 있다
---

#### tray.run 트레이 — 열기·끝내기

**시그니처**
```rust
pub fn run(rt: &Runtime, args: Args) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1·9.2·9.6 · [[SYNC-PRD-001#R15]] · 사용자 결정 2026-10-08(메뉴는 열기·끝내기 — 「지금 백업」은 L16이 더했다)

**입력** `rt` — `main`이 만든 tokio 실행기 · `args` — `--no-tray`가 아닐 때 `main`이 넘긴다

**처리**
1. `TrayLink`(주소를 받을 곳·「끝내기」를 보낼 곳·「지금 백업」을 보낼 곳)를 만들고 `rt`에서 [[#runtime.run]]을 띄운다
2. 주소를 기다린다 — 오기 전에 `runtime.run`이 끝나면(켜기 실패·두 번째 실행) 그 결과를 그대로 돌려준다
3. 아이콘(실행 파일에 담은 32×32)과 메뉴 「열기」·「지금 백업」·「끝내기」로 트레이를 만든다. 툴팁 「싱크독_로컬 — {주소}」. 못 만들면(트레이를 받는 데스크톱이 없다) 로그만 남기고 트레이 없이 간다
4. 메뉴를 받는다 — 「열기」·아이콘 두 번 누르기 → 기본 브라우저로 주소 · 「지금 백업」 → `runtime.run`에 보낸다(결과는 로그와 설정 「백업」의 마지막 백업) · 「끝내기」 → `runtime.run`에 끝내기를 보낸다
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

#### paths.data_dir 데이터 자리 — 옮겼으면 가리키는 곳

**시그니처**
```rust
pub fn data_dir() -> Result<PathBuf, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 · [[SYNC-PRD-001#R15]]

**처리** 기본 자리 = 사용자의 로컬 데이터 폴더(윈도 `%LOCALAPPDATA%`, 리눅스 `$XDG_DATA_HOME` 또는 `~/.local/share`) 아래 윈도 `SyncDoc Local` · 리눅스 `syncdoc-local` · 그 옆 가리키는 파일 `{기본 자리}.location`(윈도 `SyncDoc Local.location`)이 있고 앞뒤 공백을 뗀 내용이 비어 있지 않으면 그 자리(카드 L16 — 옮긴 자리) · 만들지는 않는다 — [[#runtime.run]] 1이 만든다

**예외** 사용자 폴더를 모르면 `! Internal`

**테스트 관점** 로컬 데이터 폴더 아래 · 끝 이름이 판마다 맞다(리눅스 `syncdoc-local`) · 가리키는 파일이 있으면 그 자리, 비었으면 기본
---

#### paths.set_data_dir 옮긴 자리를 가리키는 파일을 쓴다

**시그니처**
```rust
pub fn set_data_dir(dir: &Path) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 — 자리를 가리키는 파일은 옛 폴더 밖이라 옛 폴더를 지워도 남는다(카드 L16)

**처리** `{기본 자리}.location`에 `dir`(절대 경로)을 쓴다 — 옆 임시 파일에 쓰고 이름을 바꾼다. 위 폴더가 없으면 만든다

**예외** 쓰기 실패 → `! Internal`

**테스트 관점** 쓴 뒤 [[#paths.data_dir]]이 그 자리

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

#### paths.git git 실행 파일

**시그니처**
```rust
pub fn git() -> Result<PathBuf, Problem>
```

근거: [[SYNC-INFRA-001]] 9.1·9.2 — 윈도는 함께 담은 MinGit, 리눅스는 시스템 git(카드 L6)

**처리** 환경 변수 `SYNCDOC_LOCAL_GIT`가 있으면 그것 · 윈도는 실행 파일 옆 `mingit/ucrt64/bin/git.exe` — MinGit의 진짜 git. 런처 `cmd/git.exe`는 그것을 한 번 더 띄워 git마다 프로세스가 둘이다(카드 L19 — 같은 PC에서 63ms → 45ms) · 그 밖은 `git`(PATH에서 찾는다 — .deb가 의존한다) · 자리를 준 것(환경 변수·윈도)인데 파일이 없으면 `Problem`

**예외** `! Internal`(「git을 못 찾았다 — {자리}」)

**테스트 관점** 환경 변수가 가리키는 파일 → 그 자리 · 없는 파일 → 그 경로가 든 `Problem` · 리눅스 기본 → `git`

---

#### settings.load 설정 파일을 읽는다

**시그니처**
```rust
pub fn load(data_dir: &Path) -> Result<Settings, Problem>
```

근거: [[SYNC-INFRA-001]] 5.2(이름)·9.3 · 사용자 결정 2026-10-07 — 파이썬 판 환경 변수와 같은 이름을 평평하게, 첫 실행 때 기본 파일

**입력** 데이터 자리

**처리**
1. `settings.toml`이 없으면 기본 파일을 쓴다 — 키 여덟과 기본값, 키마다 설명 주석. 유닉스에서는 사용자만 읽는다(600)
2. TOML로 읽는다. 키는 `LOCAL_LOGIN`(기본 `local`) · `LOCAL_NAME`(기본 빈 값) · `LLM_API_URL`(기본 빈 값 — 싱크독_로컬은 기본 주소가 없다, INFRA 5.3) · `LLM_API_KEY`(빈 값) · `LLM_MODEL`(`gpt-4o`) · `PUBLIC_BASE_URL`(빈 값 — 같은 망 열기, INFRA 9.4) · `BACKUP_DIR`(빈 값 — 백업 안 함) · `BACKUP_PASSWORD`(빈 값 — 암호 없이) · 모르는 키는 로그에 경고만. 파일에 없는 키(옛 판이 만든 파일)는 기본값이다
3. `local_name` = `LOCAL_NAME`의 앞뒤 공백을 뗀 것, 비면 `LOCAL_LOGIN` · `llm_enabled` = `LLM_API_KEY`와 `LLM_API_URL`(앞뒤 공백 뗌)이 다 비어 있지 않다
4. if `LOCAL_LOGIN`이 비었거나 50자를 넘는다 · `local_name`이 100자를 넘는다 → `Problem` — DB 칸 길이다. 넣다가 깨지기 전에 켤 때 멈춘다 · if `PUBLIC_BASE_URL`(앞뒤 공백 뗌)이 비지 않았는데 `http://`·`https://` 뒤에 호스트가 없다 · `BACKUP_DIR`(앞뒤 공백 뗌)이 비지 않았는데 절대 경로가 아니다 → `Problem`

**출력** `Settings { local_login, local_name, local_name_raw, llm_api_url, llm_api_key, llm_model, llm_enabled, public_base_url, backup_dir, backup_password }` — `local_name_raw`는 파일의 `LOCAL_NAME` 그대로(설정 화면이 보인다)

**예외** 못 읽는 TOML → `! Internal`(파일과 줄) · 4 → `! Internal`

**테스트 관점** 처음 → 파일이 생기고 기본값 · 다시 읽어도 같은 값 · 빈 `LOCAL_NAME` → 아이디 · 키만 있고 주소가 없다 → `llm_enabled` 거짓 · 둘 다 있다 → 참 · 깨진 TOML → `Problem` · 빈 아이디·긴 아이디 → `Problem` · 모르는 키가 있어도 나머지 값은 그대로 · 옛 판의 다섯 키 파일 → 새 키는 기본값 · 상대 경로 `BACKUP_DIR`·호스트 없는 `PUBLIC_BASE_URL` → `Problem`

---

#### settings.save `settings.toml`의 값만 바꾼다

**시그니처**
```rust
pub fn save(data_dir: &Path, change: &SettingsChange) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 · [[SYNC-API-001#PUT/api/local/settings]] · 카드 L16

**입력** `SettingsChange` — `name`·`llm_api_url`·`llm_api_key`·`llm_model`·`backup_dir`·`backup_password`, 모두 `Option<String>`(없으면 그대로). 검사는 처리기가 먼저 한다

**처리** 파일을 TOML 문서로 읽어(주석·차례 그대로) 준 값만 `LOCAL_NAME`·`LLM_API_URL`·`LLM_API_KEY`·`LLM_MODEL`·`BACKUP_DIR`·`BACKUP_PASSWORD` 글자로 바꾼다 — 없던 키는 끝에 더한다 · 옆 임시 파일에 쓰고 이름을 바꾼다(유닉스 600) · 파일이 없으면 기본 파일부터

**예외** 못 읽는 TOML·쓰기 실패 → `! Internal`

**테스트 관점** 준 키만 바뀌고 주석·다른 키·차례가 그대로 · 없던 키는 끝에 · `settings.load`가 바뀐 값을 읽는다

---

#### logs.init 로그를 연다

**시그니처**
```rust
pub fn init(data_dir: &Path) -> Result<WorkerGuard, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 · 사용자 결정 2026-10-07 — 날마다 한 파일, 최근 14개

**처리** `logs/syncdoc-local.{날짜}.log`에 날마다 새 파일로 · 표준 오류에도 · `logs/`의 `syncdoc-local.*.log`와 `postgresql-*.log`를 각각 최근 14개만 남긴다 · 같은 프로세스에서 이미 열었으면 다시 걸지 않는다 · 파일 쪽 쓰기는 바꿀 수 있는 대상을 거친다 — [[#logs.retarget]]이 옮긴 자리로 돌린다(카드 L16)

**출력** 쓰기 작업의 지킴이(`WorkerGuard`) — 놓이면 남은 줄을 마저 쓴다

**테스트 관점** 20개를 깔아 두고 열면 종류마다 14개 · 쓴 줄이 오늘 파일에

---

#### logs.retarget 로그를 옮긴 자리로

**시그니처**
```rust
pub fn retarget(data_dir: &Path) -> Result<WorkerGuard, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 — 데이터 자리를 옮기면 로그도 새 자리 `logs/`에(카드 L16)

**처리** 새 자리 `logs/`를 만들고 [[#logs.init]]과 같은 파일·보관 규칙으로 연다 · 파일 쪽 쓰기 대상을 바꾼다 — 이 뒤의 줄은 새 파일로 · 표준 오류는 그대로

**출력** 새 쓰기 작업의 지킴이 — 옛 지킴이를 놓으면 옛 파일의 남은 줄을 마저 쓴다

**테스트 관점** 바꾼 뒤 쓴 줄이 새 자리 파일에, 옛 파일에는 없다

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
3. if `pgdata/`가 없다(처음) → `initdb -D pgdata.init -U syncdoc -A scram-sha-256 --pwfile=… -E UTF8 --locale=C --no-sync` — 암호 파일은 사용자만 읽고 바로 지운다 · 표식 `pgdata.sync`(빈 파일)를 두고 `pgdata.init`을 `pgdata`로 이름 바꿈 — 반쯤 만든 것을 다음 실행이 완성본으로 읽지 않게 · 디스크에 내리기(`fsync`)는 7 뒤로 미룬다(카드 L19 — 윈도에서 initdb 6.5초가 3.3초). 역할 이름은 Docker 판과 같은 `syncdoc`이다 — 한 판의 덤프가 다른 판에 그대로 들어간다
4. if `pgdata/postmaster.pid`가 있고 `pg_ctl status`가 돌고 있다 → `pg_ctl stop -m fast` — 지난번 비정상 종료로 남은 서버
5. `postgres --single -D pgdata postgres`의 표준 입력으로 `ALTER ROLE syncdoc PASSWORD pw` · `ALTER SYSTEM SET` `listen_addresses='127.0.0.1'` · `timezone='UTC'` · `log_timezone='UTC'` · `logging_collector=on` · `log_directory='../logs'` · `log_filename='postgresql-%Y-%m-%d.log'` · 유닉스는 `unix_socket_directories=''` — 켤 때마다 암호가 바뀐다. 암호는 디스크·명령줄·로그에 남지 않는다
6. `127.0.0.1:0`에 잠깐 묶어 빈 포트를 얻고 `pg_ctl start -D pgdata -w -t 60 -l logs/postgresql-boot.log -o "-p {포트}"` — 따로 프로세스 묶음으로 띄운다. `pg_ctl`의 표준 출력·오류는 `logs/pg_ctl.log`로 받는다 — 윈도의 `pg_ctl`은 핸들을 물려주며 서버를 띄워, 파이프로 받으면 서버가 끝날 때까지 기다린다. 터미널의 Ctrl+C가 PostgreSQL에 바로 닿지 않게 하고, 멈추는 순서는 [[#runtime.shutdown]]이 쥔다 · 실패하면 다른 포트로 두 번 더
3a. if 표식 `pgdata.sync`가 있다(지난번 디스크에 내리기를 마치지 못했다) → `initdb --sync-only -D pgdata`를 끝내고 표식을 지운다 — 서버를 띄우기 전에
7. `syncdoc` 역할로 `postgres` DB에 붙어 `syncdoc` DB가 없으면 만든다
8. 이번에 3을 했으면 따로 띄운 작업에서 `initdb --sync-only -D pgdata` · 끝나면 표식을 지운다(실패는 로그만 — 표식이 남아 다음 켜기의 3a가 다시 한다) · 기다리지 않는다 · 앱이 끝나면 함께 끝낸다(윈도는 끝난 앱의 자식이 남아 설치 폴더를 쥔다 — 표식이 남아 다음 켜기가 다시 한다)

도구(`initdb`·`postgres --single`·`pg_ctl`)는 윈도에서 창 없이(`CREATE_NO_WINDOW`) 띄운다 — git과 같다([[SYNC-MS-019]] 0장). 앱은 창 없는 실행 파일이라 콘솔 프로그램을 그냥 띄우면 새 콘솔 창이 열리고, 6의 서버가 그 창을 물려받아 창을 닫으면 PostgreSQL이 끝난다(#392)

**출력** `PgServer { options, port, pgdata, bin, password }` — `options`는 127.0.0.1·포트·`syncdoc`·`pw`·DB `syncdoc`, `password`는 `pw`(백업의 `pg_dump`·`pg_restore`가 환경 변수로 쓴다, 카드 L16). 놓이면(패닉 등) `pg_ctl stop`을 한 번 시도한다

**예외** 1 · `initdb`·`postgres --single`·`pg_ctl` 실패(로그 경로와 함께) · 7 → `! Internal`

**테스트 관점** (진짜 바이너리, 임시 데이터 자리) 처음 → 역할 `syncdoc` · `SHOW listen_addresses`가 127.0.0.1 · `SHOW fsync`가 on · 표식이 생겼다가 뒤에서 지워진다 · 표식을 남겨 두고 켜면 서버가 뜨기 전에 지워진다 · 인코딩 UTF8·정렬 C · DB `syncdoc`이 있다 · 두 번째 → 데이터가 그대로 · 새 암호만 되고 옛 암호는 안 된다 · 앞 서버를 멈추지 않고 버려도 다음 `start`가 된다 · 암호 파일이 남지 않는다

---

#### pg.stop PostgreSQL을 멈춘다

**시그니처**
```rust
pub async fn stop(server: PgServer) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.1 끄기

**처리** `pg_ctl stop -D pgdata -m fast -w -t 30` — 윈도는 창 없이([[#pg.start]]와 같다) · 이미 멈춰 있으면(`postmaster.pid` 없음) 성공

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
