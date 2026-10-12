---
doc_id: SYNC-MS-023
type: MS
title: MINISPEC — 이 PC — 백업·되살리기·데이터 자리·자동 시작 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-INFRA-001, SYNC-API-001, SYNC-UI-002, SYNC-MS-012, SYNC-STD-004]
---

# MINISPEC — 이 PC (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

싱크독_로컬 설치형만 가진 일 — `crates/app`의 `local`·`backup`·`datadir`·`autostart`(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.12. 파이썬 판에는 짝이 없다 — Docker 묶음은 환경 변수와 `scripts/backup.sh`(카드 BR, [[SYNC-INFRA-001]] 6.1)가 맡는다. 그래서 이 문서는 「다른 점」이 아니라 처리 전부를 적는다.

**카드 L16 몫이다(2026-10-11)** — [[SYNC-INFRA-001]] 9.3(데이터 자리 옮기기)·9.5(자동 시작)·9.6(백업·되살리기)과 설정 「이 PC」·「백업」 카드([[SYNC-UI-002#UI-13]] 10·11), 경로 [[SYNC-API-001]] 3.11.

**`Local`** — 처리기가 부르는 쪽(server crate의 `LocalOps` 짝, [[SYNC-DOM-004]] 4.12). 켤 때마다 [[SYNC-MS-012#runtime.run]]이 만들어 서버 상태에 넣는다 — 데이터 자리 · 설정 파일 · PostgreSQL(바이너리 자리·포트·이번 암호) · git · `--data-dir`로 켰나 · 다시 켜기 통로(`Op`를 runtime으로) · 프로세스 내내 사는 `Shared`(마지막 백업·마지막 다시 켜기·백업 한 줄 잠금).

**다시 켜기** — 설정 저장·되살리기·옮기기는 검사를 마친 뒤 `Op`(`Settings`·`Restore`·`Move`)를 runtime에 보내고 `Ok`다(처리기는 202). runtime이 진행 중 요청을 끝낸 뒤 서버를 내리고 그 일을 하고 다시 켠다 — 프로그램은 그대로다([[SYNC-MS-012#runtime.run]]).

**백업 꼴** — [[SYNC-INFRA-001]] 6.1(카드 BR)과 같다. tar 하나에 `db.dump`(`pg_dump -Fc`)와 `origins.tar`(항목 `origins/…`). 암호가 있으면 OpenPGP 대칭 암호 — SEIPDv1·AES256·iterated+salted S2K(`gpg --symmetric --cipher-algo AES256`과 서로 풀린다). 이름 `syncdoc-{YYYYMMDD}-{HHMMSS}.tar.gpg`(암호 없으면 `.tar`) — 이 PC의 지역 시각. 남기는 수는 14(`KEEP`).

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `pg:` 함께 담은 PostgreSQL 도구, `git:` 자식 git, `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#Local.info]] | 「이 PC」·「백업」 카드가 그리는 것 |
| [[#Local.save_settings]] | 설정 값만 바꾸고 다시 켜기를 건다 |
| [[#Local.set_autostart]] | 자동 시작 켜고 끄기 |
| [[#Local.backup_now]] | 지금 백업 — 한 번에 하나 |
| [[#Local.restore]] | 백업을 풀어 보고 되살리기를 건다 |
| [[#Local.move_to]] | 옮길 자리를 보고 옮기기를 건다 |
| [[#backup.make]] | 백업 하나를 만든다 — 켠 채로 |
| [[#backup.list]] | 폴더의 백업 파일 — 새것부터 |
| [[#backup.open]] | 백업을 풀어 본다 — 암호·꼴·덤프 |
| [[#backup.restore]] | 되살린다 — 지금 것을 옆에 두고 |
| [[#backup.daily]] | 하루 한 번 — 매시 확인 |
| [[#datadir.check]] | 옮길 자리를 본다 |
| [[#datadir.copy]] | 데이터를 복사하고 확인한다 |
| [[#autostart.enabled]] | 자동 시작이 걸려 있나 |
| [[#autostart.set]] | 자동 시작을 걸거나 푼다 |

---

## 2. 함수

#### Local.info 「이 PC」·「백업」 카드가 그리는 것

**시그니처**
```rust
async fn info(&self) -> Result<LocalInfo, Problem>
```

근거: [[SYNC-API-001#GET/api/local]] · [[SYNC-UI-002#UI-13]] 10·11

**처리**
1. `settings = settings.load(data_dir)`([[SYNC-MS-012#settings.load]]) — 켠 뒤 고친 파일도 그대로 보인다
2. `files = backup.list(settings.backup_dir)` — 폴더가 비었거나 없으면 빈 목록
3. `→ LocalInfo { login, name: LOCAL_NAME 그대로, llm_api_url, llm_api_key_set: 키가 비어 있지 않다, llm_model, public_base_url, autostart: autostart.enabled(), data_dir: 절대 경로, backup: { dir, encrypted: 암호가 비어 있지 않다, keep: 14, files, last: Shared의 마지막 백업 }, last_op: Shared의 마지막 다시 켜기 }`

**예외** 설정 파일을 못 읽음 → `! Internal` · 자동 시작을 못 읽음 → `! Internal`

**호출하는 것** [[SYNC-MS-012#settings.load]] · [[#backup.list]] · [[#autostart.enabled]]

**테스트 관점** 키·암호 원문이 답에 없다(있나만) · 백업 폴더의 파일이 새것부터 · 폴더가 없으면 빈 목록

---

#### Local.save_settings 설정 값만 바꾸고 다시 켜기를 건다

**시그니처**
```rust
async fn save_settings(&self, change: SettingsChange) -> Result<(), Problem>
```

근거: [[SYNC-API-001#PUT/api/local/settings]] · [[SYNC-INFRA-001]] 9.3

**입력** `SettingsChange { name, llm_api_url, llm_api_key, llm_model, backup_dir, backup_password }` — 모두 `Option<String>`, 없으면 그대로(검사는 처리기 — 길이·`http(s)://`·절대 경로)

**처리** `settings.save(data_dir, change)`([[SYNC-MS-012#settings.save]]) — 값만 바꾸고 주석·다른 키는 그대로 · 다시 켜기 `Op::Settings`를 보낸다 · `→ Ok`

**예외** 파일 쓰기 실패 → `! Internal`

**호출하는 것** [[SYNC-MS-012#settings.save]]

**테스트 관점** 준 칸만 바뀌고 주석이 남는다 · 다시 켜기 통로에 `Settings`

---

#### Local.set_autostart 자동 시작 켜고 끄기

**시그니처**
```rust
async fn set_autostart(&self, on: bool) -> Result<(), Problem>
```

근거: [[SYNC-API-001#PUT/api/local/autostart]] · [[SYNC-INFRA-001]] 9.5

**처리** `autostart.set(on)` · 다시 켜지 않는다

**호출하는 것** [[#autostart.set]]

---

#### Local.backup_now 지금 백업 — 한 번에 하나

**시그니처**
```rust
async fn backup_now(&self) -> Result<BackupFile, Problem>
```

근거: [[SYNC-API-001#POST/api/local/backups]] · [[SYNC-INFRA-001]] 9.6 · 트레이 「지금 백업」 · [[#backup.daily]]

**처리**
1. `settings = settings.load(data_dir)` · if `backup_dir`가 비었다 → `! BackupUnconfigured`
2. Shared의 백업 잠금을 쥔다 — 「지금 백업」·트레이·하루 한 번이 겹쳐도 한 줄로
3. `backup.make(Job { dir, password, PostgreSQL, git, origins, 작업 자리: data/tmp })`
4. 결과(시각·파일 이름 또는 오류 문장)를 Shared의 마지막 백업에 적고 로그에 남긴다 · `→ BackupFile` 또는 그 `Problem`

**예외** 1 · 3의 `Problem`

**호출하는 것** [[SYNC-MS-012#settings.load]] · [[#backup.make]]

**테스트 관점** 폴더가 없으면 `backup-unconfigured` · 둘을 함께 불러도 파일이 둘(이름이 초로 갈린다)이고 섞이지 않는다 · 실패도 마지막 백업에 남는다

---

#### Local.restore 백업을 풀어 보고 되살리기를 건다

**시그니처**
```rust
async fn restore(&self, name: &str, password: Option<&str>) -> Result<(), Problem>
```

근거: [[SYNC-API-001#POST/api/local/restore]] · [[SYNC-INFRA-001]] 9.6

**처리**
1. `settings = settings.load(data_dir)` · if `backup_dir`가 비었다 → `! BackupUnconfigured`
2. if `name`이 `/`·`\`·`..`을 품거나 `backup.list(backup_dir)`에 없다 → `! NotFound { resource: "backup", id: name }`
3. `opened = backup.open(backup_dir/name, password 또는 설정의 암호, PostgreSQL 바이너리, data/restore/incoming)` — 틀리면 `backup-invalid`, 아무것도 안 바뀐다
4. 다시 켜기 `Op::Restore(opened)`를 보낸다 · `→ Ok`

**호출하는 것** [[SYNC-MS-012#settings.load]] · [[#backup.list]] · [[#backup.open]]

**테스트 관점** 없는 이름·경로 조각 → `not-found` · 틀린 암호 → `backup-invalid`, 통로에 아무것도 없다

---

#### Local.move_to 옮길 자리를 보고 옮기기를 건다

**시그니처**
```rust
async fn move_to(&self, dir: &str) -> Result<(), Problem>
```

근거: [[SYNC-API-001#POST/api/local/move]] · [[SYNC-INFRA-001]] 9.3

**처리** `target = datadir.check(data_dir, dir)` · 다시 켜기 `Op::Move(target)`를 보낸다 · `→ Ok`

**호출하는 것** [[#datadir.check]]

---

#### backup.make 백업 하나를 만든다 — 켠 채로

**시그니처**
```rust
pub async fn make(job: &Job) -> Result<BackupFile, Problem>
```

근거: [[SYNC-INFRA-001]] 6.1·9.6

**입력** `Job { dir, password, bin, port, pg_password, git, origins, work }` — 백업 폴더 · 암호(비면 암호 없이) · PostgreSQL 바이너리 자리·포트·이번 암호 · git · 서버 저장소 자리 · 작업 자리

**처리**
1. `work` 아래 새 임시 폴더 — 끝나면(실패해도) 지운다
2. `pg: pg_dump -h 127.0.0.1 -p {port} -U syncdoc -d syncdoc -Fc -f {tmp}/db.dump`(암호는 환경 변수 `PGPASSWORD`) — **덤프가 먼저다**: 원본이 DB보다 앞서면 되살린 뒤 켤 때의 따라잡기가 메운다 · 실패 → `! BackupFailed("DB 덤프 실패 — {stderr}")`
3. 서버 저장소 사진 — `origins/*.git`과 `origins/_archive/*.git`마다 `git.mirror(원본, {tmp}/origins/{같은 상대 경로})`([[SYNC-MS-019#Git.mirror]]) — 쓰기를 멈추지 않아도 저장소마다 참조와 객체가 맞는다 · `.git`이 아닌 것은 담지 않는다
4. `{tmp}/origins.tar` — 3의 `origins/`를 항목 `origins/…`로 · 보통 파일과 폴더만
5. `name = syncdoc-{지역 시각 %Y%m%d-%H%M%S}.tar` + 암호가 있으면 `.gpg` · if 폴더에 같은 이름이 있다 → 1초 기다려 다시 이름
6. 바깥 tar(`db.dump`·`origins.tar` 차례)를 만들어 암호가 있으면 OpenPGP 대칭 암호(SEIPDv1·AES256)로 감싸 `{dir}/{name}.part`에 쓰고 `{name}`으로 바꾼다 — 반쯤 쓴 파일이 백업 이름으로 남지 않는다
7. 남기기 — `backup.list(dir)`의 15번째부터 지운다(이름 순 = 시각 순. Docker 묶음의 것도 같은 이름이라 함께 센다)
8. `→ BackupFile { name, size, encrypted }`

**예외** 2·3·4·6의 실패 → `! BackupFailed(reason)` · 폴더를 못 만듦 → `! BackupFailed("폴더에 쓰지 못했다 — {e}")`

**호출하는 것** [[SYNC-MS-019#Git.mirror]] · [[#backup.list]]

**테스트 관점** (진짜 PostgreSQL·git) 풀면 `db.dump`·`origins.tar` 차례 · `pg_restore --list`가 표를 읽는다 · `origins.tar`에 저장소·보관본, 참조 해시가 원본과 같고 원격이 없다 · 암호면 `.gpg` — gpg가 있으면 `gpg -d`로 풀린다 · 15개째에 가장 오래된 것이 지워진다 · `.part`가 남지 않는다

---

#### backup.list 폴더의 백업 파일 — 새것부터

**시그니처**
```rust
pub fn list(dir: &Path) -> Result<Vec<BackupFile>, Problem>
```

**처리** 폴더가 없으면 빈 목록 · 이름이 `syncdoc-`로 시작하고 `.tar` 또는 `.tar.gpg`로 끝나는 보통 파일 · 이름 거꾸로(새것부터) · `→ [BackupFile { name, size, encrypted: .gpg로 끝난다 }]`

**예외** 폴더를 못 읽음 → `! Internal`

**테스트 관점** `.part`·다른 이름은 빠진다 · 새것부터

---

#### backup.open 백업을 풀어 본다 — 암호·꼴·덤프

**시그니처**
```rust
pub async fn open(file: &Path, password: &str, bin: &Path, work: &Path) -> Result<Opened, Problem>
```

근거: [[SYNC-INFRA-001]] 9.6 — 되살리기는 먼저 풀어 보고 틀리면 아무것도 바꾸지 않는다

**처리**
1. `work`를 비우고 만든다
2. if 이름이 `.gpg`로 끝난다 → if `password`가 비었다 → `! BackupInvalid("암호가 필요하다")` · OpenPGP로 푼다 — 암호가 틀리면 `! BackupInvalid("암호가 틀리다")`, 꼴이 아니면 `! BackupInvalid("깨졌다 — {e}")` · 아니면 그대로
3. tar를 푼다 — `db.dump`와 `origins.tar` 둘 다 보통 파일로 있어야 한다, 아니면 `! BackupInvalid("싱크독 백업이 아니다 — db.dump·origins.tar가 없다")`
4. `pg: pg_restore --list {work}/db.dump` · 실패 → `! BackupInvalid("DB 덤프를 읽지 못한다 — {stderr}")`
5. `origins.tar`의 항목이 모두 `origins/` 아래 보통 파일·폴더인지 본다(절대 경로·`..` 없음) · 아니면 `! BackupInvalid("서버 저장소 묶음이 맞지 않다")`
6. `→ Opened { name, dump: work/db.dump, origins: work/origins.tar }`

**테스트 관점** 맞는 암호 → 풀린다 · 틀린 암호 → `backup-invalid`(암호가 틀리다) · `.gpg`인데 암호 없음 → 암호가 필요하다 · tar 아닌 것 → 싱크독 백업이 아니다 · gpg가 만든 것(gpg가 있으면) · Docker 묶음 꼴(`scripts/backup.sh`와 같은 차례로 만든 것)

---

#### backup.restore 되살린다 — 지금 것을 옆에 두고

**시그니처**
```rust
pub async fn restore(opened: &Opened, pg: &PgServer, data_dir: &Path) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.6 · 서버가 내려간 뒤 runtime이 부른다([[SYNC-MS-012#runtime.run]]) — 연결 풀은 닫혀 있고 PostgreSQL은 떠 있다

**처리**
1. 옆에 두기 — `data/restore/previous/`를 비우고 `pg: pg_dump -Fc`로 지금 DB를 `previous/db.dump`에 · `data/origins`를 `previous/origins`로 옮긴다
2. `opened.origins`(origins.tar)를 데이터 자리에 푼다 — 보통 파일·폴더만 · 없으면 빈 `origins/`
3. DB — 연결 하나로 `DROP SCHEMA public CASCADE; CREATE SCHEMA public` · `pg: pg_restore --no-owner --no-privileges --single-transaction --exit-on-error -d syncdoc {dump}` — 덤프에 없는 표(프로그램이 더 새 판)도 남지 않는다
4. `migrate.apply` — 옛 판 덤프면 이전 SQL을 올린다. 프로그램보다 새 판이면 `Problem`([[SYNC-MS-012#migrate.apply]])
5. `data/repos`를 지운다 — 켤 때 [[SYNC-MS-013#ProjectService.rehome]]이 서버 저장소 자리를 맞추고 다시 만든다
6. 성공 → `data/restore/`를 지운다 · `→ Ok`
7. 2~5가 실패 → 되돌린다: 지금 `origins`를 지우고 `previous/origins`를 제자리로 · 3과 같은 방법으로 `previous/db.dump`를 되살린다 · `data/repos`를 지운다 · `→` 처음 실패의 `Problem`(되돌리기도 실패하면 로그에 둘 다)

**예외** 1의 실패(옆에 두기 전) → 아무것도 안 바뀐 채 그 `Problem` · 7

**호출하는 것** [[SYNC-MS-012#migrate.apply]]

**테스트 관점** (진짜 PostgreSQL) 백업 → 문서 하나 더 → 되살리기 → 그 문서가 없다, 서버 저장소 참조가 백업 때 · 다른 데이터 자리(경로가 다른 저장소 행)의 백업 → 켤 때 자리가 맞춰진다 · 덤프의 이전 판이 프로그램보다 새 것이면 되돌아가 처음 그대로 · 옆에 둔 것이 성공 뒤 남지 않는다

---

#### backup.daily 하루 한 번 — 매시 확인

**시그니처**
```rust
pub async fn daily(local: Arc<Local>)
```

근거: [[SYNC-INFRA-001]] 9.6 · 6.1(카드 BR — 매시 불러 오늘 것이 있으면 건너뛴다)

**처리** 켜고 1분 뒤부터 한 시간마다 — 오늘(지역 날짜) 정리를 아직 안 했으면 `origins/*.git`(보관본은 빼고)마다 그 코드의 쓰기 락([[SYNC-MS-017#pipeline.write_lock]])을 쥐고 `git.gc(원본)`(실패는 로그만) · 한 날짜는 메모리에(켤 때마다 첫 확인에서 한 번 — 쌓인 것이 없으면 git이 아무것도 안 한다, 카드 L19) · 그다음 `settings.load` · if `backup_dir`가 있고 `backup.list`에 오늘(지역 날짜) `syncdoc-{YYYYMMDD}-`로 시작하는 것이 없다 → `local.backup_now()`(실패는 로그와 마지막 백업에만) · 끝없이 돈다 — runtime이 다시 켜거나 끌 때 멈춘다

**호출하는 것** [[SYNC-MS-017#pipeline.write_lock]] · [[SYNC-MS-019#Git.gc]] · [[SYNC-MS-012#settings.load]] · [[#backup.list]] · [[#Local.backup_now]]

**테스트 관점** 오늘 것이 있으면 만들지 않는다 · 폴더가 없으면 백업은 안 하고 정리는 한다 · 같은 날 두 번째 확인은 정리하지 않는다

---

#### datadir.check 옮길 자리를 본다

**시그니처**
```rust
pub fn check(current: &Path, target: &str) -> Result<PathBuf, Problem>
```

근거: [[SYNC-INFRA-001]] 9.3

**처리**
1. `target`의 앞뒤 공백을 뗀다 · if 절대 경로가 아니다 → `! DataDirInvalid("절대 경로가 아니다")`
2. 두 경로를 정규화(있는 데까지 실제 경로) · if 같거나 한쪽이 다른 쪽 안이다 → `! DataDirInvalid("지금 데이터 자리와 겹친다")`
3. if 있는데 폴더가 아니다 · 비어 있지 않은 폴더다 → `! DataDirInvalid("비어 있지 않은 폴더다")`
4. 폴더를 만들고 시험 파일을 써 보고 지운다 · 실패 → `! DataDirInvalid("쓸 수 없다 — {e}")`
5. `→` 정규화한 자리

**테스트 관점** 상대 경로 · 지금 자리 안 · 지금 자리를 품는 곳 · 파일이 든 폴더 → 각 문장 · 없는 폴더 → 만들어지고 통과

---

#### datadir.copy 데이터를 복사하고 확인한다

**시그니처**
```rust
pub fn copy(from: &Path, to: &Path) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.3 — PostgreSQL이 멈춘 뒤 runtime이 부른다

**처리**
1. `pgdata/`·`origins/`(폴더째) · `settings.toml`·`gitconfig`(파일)를 `to`로 복사한다 — 있는 것만. `repos/`·`logs/`·잠금·`instance.json`·`tmp/`는 복사하지 않는다(작업 사본은 켤 때 다시 만든다)
2. 확인 — 두 쪽의 상대 경로·크기 목록이 같아야 한다 · 아니면 `to`에 복사한 것을 지우고 `! DataDirInvalid("복사가 맞지 않다 — {첫 다른 경로}")`
3. 실패하면 `to`에 복사한 것을 지운다(옛 자리는 그대로)

**테스트 관점** 복사 뒤 목록·크기가 같다 · `repos/`·`logs/`는 없다 · 옛 자리는 그대로

---

#### autostart.enabled 자동 시작이 걸려 있나

**시그니처**
```rust
pub fn enabled() -> Result<bool, Problem>
```

근거: [[SYNC-INFRA-001]] 9.5

**처리** 윈도 — `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`에 값 `SyncDoc Local`이 있나(설치 화면의 체크가 쓰는 것과 같은 이름) · 리눅스 — `{XDG_CONFIG_HOME 또는 ~/.config}/autostart/syncdoc-local.desktop`이 있나

**테스트 관점** (리눅스, 임시 `XDG_CONFIG_HOME`) 없음 → 거짓 · `set(true)` 뒤 참

---

#### autostart.set 자동 시작을 걸거나 푼다

**시그니처**
```rust
pub fn set(on: bool) -> Result<(), Problem>
```

근거: [[SYNC-INFRA-001]] 9.5 · 사용자 결정 2026-10-08(자동 시작은 트레이로만, 브라우저를 열지 않는다)

**처리** 실행 파일 = 리눅스 AppImage면 `$APPIMAGE`, 아니면 지금 실행 파일 · 윈도 — `on`이면 값 `SyncDoc Local` = `"{실행 파일}" --autostart`, 아니면 값을 지운다(없어도 된다) · 리눅스 — `on`이면 `.desktop`(`Type=Application` · `Name=싱크독_로컬` · `Exec="{실행 파일}" --autostart` · `X-GNOME-Autostart-enabled=true`)을 쓰고, 아니면 지운다

**예외** 레지스트리·파일 실패 → `! Internal`

**테스트 관점** (리눅스) 켜면 파일과 `Exec`, 끄면 없다 · 두 번 꺼도 된다

---

## 3. 미결사항

없음.
