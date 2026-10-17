---
doc_id: SYNC-MS-027
type: MS
title: MINISPEC — trace — 실행 기록 받기·기록 도구·요청 보내기 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-025, SYNC-INFRA-001, SYNC-API-001]
---

# MINISPEC — trace (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/trace`(`TraceService`)와 기록 도구 `crates/app/src/trace`(하위 명령 `trace`·`trace-web`, 카드 L29)의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.14. 파이썬 판 [[SYNC-MS-025]]과 **같은 이름·같은 처리·같은 응답**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 같은지는 계약 시험(카드 L28)이 응답 바이트로 본다.

서비스는 다른 서비스처럼 연결을 빌려 받는다(`TraceService { db: &mut PgConnection }`) — 트랜잭션은 입구가 쥔다([[SYNC-STD-004#DEV-10]]). 시각은 `time::OffsetDateTime`, 기록은 `serde_json::Value`(받은 JSON 그대로 — JSONB에 넣고 읽은 차례 그대로 돌려준다).

**상수** — [[SYNC-MS-025]]와 같다(`KEEP = 300` · `MAX_EVENTS = 20000` · `MAX_BYTES = 4 * 1024 * 1024`).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#TraceService.save]] | 기록 하나를 받는다 — 꼴·상한, 같은 기록은 하나, 300개 |
| [[#TraceService.list_recent]] | 최근 기록 머리 |
| [[#TraceService.get]] | 기록 하나 |
| [[#TraceService.delete]] | 하나 또는 전부 지우기 |
| [[#TraceService.coverage]] | 기록에 나온 함수와 닿은 장비 |
| [[#TraceService.delete_by_project]] | 프로젝트 해제와 함께 |
| [[#trace.run]] | 기록 도구 — 준비·띄우기·지켜보며 올리기·정리 |
| [[#trace.detect]] | 띄울 명령의 언어 |
| [[#trace.unpack]] | 담아 둔 기록기를 푼다 |
| [[#trace.fetch_spans]] | 서버에서 함수 범위를 받는다 |
| [[#trace.span_table]] | 범위를 기록기의 꼴로 |
| [[#trace.env_for]] | 띄울 프로그램의 환경 변수 |
| [[#trace.normalize]] | 기록을 TraceRecord 꼴로 맞춘다 |
| [[#trace.send]] | 기록 하나를 올린다 |
| [[#trace.watch]] | 기록 폴더를 훑어 올린다 |
| [[#trace.copy_rust]] | Rust 작업 공간을 계측한 사본으로 |
| [[#trace.proxy]] | 화면 기록 — Node 프록시 |
| [[#local.request]] | 이 PC의 개발 서버로 요청 하나를 대신 보낸다 |

---

## 2. 함수

#### TraceService.save 기록 하나를 받는다

**시그니처**
```rust
pub async fn save(&mut self, project_id: i32, user_id: i32, record: &Value) -> Result<(TraceBrief, bool), Problem>
```

근거: [[SYNC-MS-025#TraceService.save]]

**처리** [[SYNC-MS-025#TraceService.save]] 1~5 그대로 — 꼴(차례·부모·`startedAt`) → 같은 `trace_key`면 그 머리와 거짓 → 넣고 같은 트랜잭션에서 최근 300개만. `startedAt`은 파이썬 `datetime.fromisoformat`과 같은 꼴만 받는다(정규식이 같으니 같은 글이 통과한다), 시간대가 없으면 UTC. `error`는 300자(글자 수)에서 자른다

**테스트 관점** [[SYNC-MS-025#TraceService.save]]의 것

---

#### TraceService.list_recent 최근 기록 머리

**시그니처**
```rust
pub async fn list_recent(&mut self, project_id: i32, limit: i64) -> Result<Vec<TraceBrief>, Problem>
```

**처리** [[SYNC-MS-025#TraceService.list_recent]] 그대로 — `record`를 읽지 않는다

**테스트 관점** [[SYNC-MS-025#TraceService.list_recent]]의 것

---

#### TraceService.get 기록 하나

**시그니처**
```rust
pub async fn get(&mut self, project_id: i32, trace_id: i64) -> Result<TraceView, Problem>
```

**처리** [[SYNC-MS-025#TraceService.get]] 그대로 — 없거나 다른 프로젝트면 `not-found {resource: "trace", id}`

**테스트 관점** [[SYNC-MS-025#TraceService.get]]의 것

---

#### TraceService.delete 하나 또는 전부 지우기

**시그니처**
```rust
pub async fn delete(&mut self, project_id: i32, trace_id: Option<i64>) -> Result<i64, Problem>
```

**처리** [[SYNC-MS-025#TraceService.delete]] 그대로

**호출하는 것** [[#TraceService.get]]

**테스트 관점** [[SYNC-MS-025#TraceService.delete]]의 것

---

#### TraceService.coverage 기록에 나온 함수와 닿은 장비

**시그니처**
```rust
pub async fn coverage(&mut self, project_id: i32) -> Result<TraceCoverage, Problem>
```

**처리** [[SYNC-MS-025#TraceService.coverage]] 그대로 — 열쇠와 장비는 파이썬 `sorted`처럼 코드 포인트 차례(UTF-8 바이트 차례와 같다)

**테스트 관점** [[SYNC-MS-025#TraceService.coverage]]의 것

---

#### TraceService.delete_by_project 프로젝트 해제와 함께

**시그니처**
```rust
pub async fn delete_by_project(&mut self, project_id: i32) -> Result<(), Problem>
```

**처리** `DB: DELETE FROM traces WHERE project_id=?`

**테스트 관점** 그 프로젝트 것만 지운다

---

#### trace.run 기록 도구 — 준비·띄우기·지켜보며 올리기·정리

**시그니처**
```rust
pub async fn run(args: TraceArgs) -> ExitCode
```

근거: [[SYNC-INFRA-001]] 9.9 · [[SYNC-SEQ-001#SEQ-36]] · [[SYNC-UC-001#UC-H25]]

**처리**
1. 언어 — [[#trace.detect]]. 모르면 한 줄 알리고 끝 코드 2
2. 준비 — 토큰(`SYNCDOC_TOKEN`, 없으면 터미널에서 화면에 안 찍고 묻는다) · [[#trace.fetch_spans]] · 그래프가 없으면(커밋 null) 「코드를 먼저 push하세요」 끝 코드 2 · 저장소 뿌리(`git rev-parse --show-toplevel`, 아니면 `--cwd`)의 HEAD가 그래프 커밋과 다르면 한 줄 알림
3. 임시 폴더에 [[#trace.unpack]] · [[#trace.span_table]]을 범위 파일로 · [[#trace.env_for]]
4. Rust면 [[#trace.copy_rust]] — 사본에서 띄우고 `CARGO_TARGET_DIR`도 캐시 자리
5. 띄운다(표준 입출력은 그대로) · 0.4초마다 [[#trace.watch]] · Ctrl+C는 프로그램이 받는다 — 도구는 끝나기를 기다린다
6. 끝나면 남은 기록을 [[#trace.watch]]로 올리고 임시 폴더를 지운다 · 끝 코드는 프로그램의 것

**호출하는 것** [[#trace.detect]] · [[#trace.fetch_spans]] · [[#trace.unpack]] · [[#trace.span_table]] · [[#trace.env_for]] · [[#trace.copy_rust]] · [[#trace.watch]]

**테스트 관점** E2E(스크래치 FastAPI·순수 Node http·std Rust `--job`) — 기록이 올라오고 사건의 함수가 그래프 열쇠 · 비밀 이름의 값이 `***` · 작업 사본이 그대로

---

#### trace.detect 띄울 명령의 언어

**시그니처**
```rust
pub fn detect(command: &[String]) -> Option<Lang>
```

**처리** 명령의 낱말(공백·`;`·`&`·`|`로 나누고 경로·`.exe`를 뗀 이름) 중 — `cargo` → Rust · `python`·`python3(.x)`·`py`·`uv`·`uvicorn`·`gunicorn`·`flask`·`celery`·`manage.py`·`hypercorn`·`fastapi`·`poetry`·`pipenv` → Python · `node`·`npm`·`npx`·`pnpm`·`yarn`·`tsx`·`ts-node`·`next`·`nodemon`·`bun` → Node. 앞의 것이 이긴다. 없으면 없음

**테스트 관점** `uv run uvicorn …` · 경로 붙은 `python3` · `npm run dev` · `cargo run` · 모르는 것 → 없음

---

#### trace.unpack 담아 둔 기록기를 푼다

**시그니처**
```rust
pub fn unpack(dir: &Path) -> std::io::Result<Kit>
```

**처리** 실행 파일에 담긴 `crates/app/tracers/`(python·node·rust)를 `dir`에, Node 기록기가 쓰는 TypeScript 파서(화면 빌드와 같은 판 — `frontend/node_modules/typescript`의 `package.json`·`lib/typescript.js`)를 `dir/node/node_modules/typescript`에

**테스트 관점** 풀면 `sitecustomize.py`·`node-tracer.mjs`·TypeScript·Rust 도우미가 있다

---

#### trace.fetch_spans 서버에서 함수 범위를 받는다

**시그니처**
```rust
pub async fn fetch_spans(client: &reqwest::Client, to: &str, project: &str, token: &str) -> Result<Value, String>
```

**처리** `GET {to}/api/projects/{project}/trace-spans`(Bearer) — 200이면 본문 · 401 「토큰이 틀렸거나 폐기됐다」 · 404 「프로젝트가 없거나 내 것이 아니다」 · 닿지 못하면 그 문장

**테스트 관점** E2E에서 받는다

---

#### trace.span_table 범위를 기록기의 꼴로

**시그니처**
```rust
pub fn span_table(spans: &Value, root: &Path) -> SpanTable
```

**처리** `{files: {절대 경로: [[시작 줄, 끝 줄, 열쇠]…]}, routes: [라우트 있는 열쇠], names: {열쇠: 이름}, hosts: {호스트:포트: db|redis|s3|http}, byName: {상대 경로: {이름·클래스.이름: 열쇠}}}` — 장비 종류는 `db`→db · `cache`→redis · `storage`→s3 · 나머지 http, `backend`·`browser`는 뺀다. 이름 표는 먼저 본 것이 이긴다

**테스트 관점** 라우트·장비·화면 이름 표(메서드는 `클래스.이름`도)

---

#### trace.env_for 띄울 프로그램의 환경 변수

**시그니처**
```rust
pub fn env_for(lang: Lang, kit: &Kit, spans: &Path, out: &Path, root: &Path, job: bool) -> Vec<(String, String)>
```

**처리** `SYNCDOC_TRACE_OUT`·`SYNCDOC_TRACE_SPANS`·`SYNCDOC_TRACE_ROOT`(+ `--job`이면 `SYNCDOC_TRACE_JOB=1`) · Python·Node면 둘 다 — `PYTHONPATH` 앞에 기록기 폴더, `NODE_OPTIONS` 앞에 `--import=file://…/node-tracer.mjs`(명령이 다른 언어를 부를 수 있다)

**테스트 관점** E2E

---

#### trace.normalize 기록을 TraceRecord 꼴로 맞춘다

**시그니처**
```rust
pub fn normalize(record: &mut Value, commit: Option<&str>)
```

**처리** 기록기마다 조금씩 다른 꼴을 [[SYNC-API-001]] 4장 `TraceRecord`에 — `version` 1 · `kind` 기본 `back` · `method` 10자(비면 작업 `JOB`, 아니면 `GET`) · `path` 500자 · `id` 64자 · `ms` 0 이상 정수(반올림) · `status` 정수나 null · 글자가 아닌 `error`·`query`·`page`는 null · `commit` = 작업 사본 HEAD · 사건 2만 개 · 본문 4MB를 넘으면 사건을 반씩 덜고 `truncated`

**테스트 관점** 긴 id·빈 method·소수 ms·작업

---

#### trace.send 기록 하나를 올린다

**시그니처**
```rust
pub async fn send(client: &reqwest::Client, to: &str, project: &str, token: &str, record: &Value) -> Result<u16, String>
```

**처리** `POST {to}/api/projects/{project}/traces`(Bearer) — 성공이면 상태 · 401·404·413·422는 다시 보내도 같아 바로 실패 · 그 밖(닿지 못함·5xx)은 1·2·4초 뒤 세 번 더(같은 기록은 서버에 하나라 안전하다)

**테스트 관점** E2E

---

#### trace.watch 기록 폴더를 훑어 올린다

**시그니처**
```rust
pub async fn watch(client: &reqwest::Client, out: &Path, to: &str, project: &str, token: &str, commit: Option<&str>) -> usize
```

**처리** `out`의 `*.json`(점으로 시작하는 쓰는 중 파일 빼고)을 이름 차례로 — 읽고 지우고 [[#trace.normalize]] · [[#trace.send]] · 한 줄 알림(올림 / 올리지 못해 버림) · 올린 수

**호출하는 것** [[#trace.normalize]] · [[#trace.send]]

**테스트 관점** E2E

---

#### trace.copy_rust Rust 작업 공간을 계측한 사본으로

**시그니처**
```rust
pub fn copy_rust(cwd: &Path, files: &[(PathBuf, Vec<Span>)], copy: &Path, helper: &Path) -> Result<Prepared, String>
```

근거: view_arc `native/rust.mts`

**처리** 작업 공간 뿌리(`cwd`에서 위로 — `[workspace]`가 있는 곳, 없으면 가장 가까운 패키지)를 `copy`로(바뀐 것만, `target`·`.git`·`node_modules` 빼고) · 범위 파일마다 함수 몸통 첫머리에 `enter(열쇠, &[(매개변수, 값 표현)…])`를 같은 줄에 끼운다(주석·문자열을 가린 글로 `fn` 이름·매개변수·몸통 `{`를 찾는다 — 몸통 없는 선언·`const fn`은 건너뛴다) · 패키지마다 크레이트 뿌리 끝줄에 도우미 모듈(`#[path]`, lib은 `pub`, bin은 lib의 것을 `use`) · 사본에서 돌 자리와 계측한 파일 수 · 계측할 것이 없으면 「그래프에서 찾지 못했다」

**다른 점** 사본과 빌드 폴더는 캐시 자리(`syncdoc-local/trace/{뿌리 해시}-copy`·`-target`)에 두고 다시 쓴다 — 매번 처음부터 빌드하지 않게. 원본은 고치지 않는다

**테스트 관점** 가리기(문자열·주석·원시 문자열·수명) · 매개변수 이름(패턴·self) · 줄 수 그대로 · 몸통 없는 트레이트 선언 · E2E(std Rust `--job`)

---

#### trace.proxy 화면 기록 — Node 프록시

**시그니처**
```rust
pub async fn proxy(args: WebArgs) -> ExitCode
```

**처리** `node`가 없으면 끝 코드 2 · 준비는 [[#trace.run]] 2·3과 같다 · 풀어 둔 `web-proxy.mjs`를 띄운다(`SYNCDOC_TRACE_TARGET`·`SYNCDOC_TRACE_PORT`) — HTML에 브라우저 기록기를 넣고, 화면 모듈의 함수를 이름 표(`byName`)로 열쇠를 찾아 감싸고, 브라우저가 보낸 기록을 기록 폴더에 `kind: front`로 쓴다 · 0.4초마다 [[#trace.watch]] · 프록시가 끝나면 남은 것을 올리고 지운다

**호출하는 것** [[#trace.fetch_spans]] · [[#trace.unpack]] · [[#trace.span_table]] · [[#trace.watch]]

**테스트 관점** E2E — Vite 앱을 프록시로 열어 버튼 → 화면 기록 하나(`@fetch` 포함)

---

#### local.request 이 PC의 개발 서버로 요청 하나를 대신 보낸다

**시그니처**
```rust
pub async fn request(method: &str, url: &str, body: Option<&str>) -> Result<LocalReply, Problem>
```

근거: [[SYNC-UC-001#UC-H26]] · [[SYNC-SEQ-001#SEQ-37]] · [[SYNC-API-001#POST/api/local/request]] · [[SYNC-INFRA-001#C14]] · 사용자 결정 2026-10-12(로컬 판만)

**처리**
1. 주소 — `http`·`https`이고 호스트가 `localhost`·`127.0.0.1`·`::1`이 아니면(읽지 못해도) `! request-refused {url}`
2. 보낸다 — 리다이렉트를 따르지 않고 10초. `GET`이 아니고 본문이 있으면 `Content-Type: application/json`
3. 닿지 못하거나 시간이 지나면 `! request-failed {reason}`
4. `→ LocalReply { status, headers(이름 소문자, 같은 이름은 `, `로 잇는다), body(UTF-8 — 못 읽는 바이트는 대체 문자), truncated(1MB에서 잘렸나), ms }`

**테스트 관점** localhost 아님 → refused · 닿지 못함 → failed · 1MB 자르기 · 리다이렉트를 따르지 않는다 · 머리 이름이 소문자

---

## 3. 미결사항

없음.
