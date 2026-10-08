---
doc_id: SYNC-MS-016
type: MS
title: MINISPEC — AccountService (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-006, SYNC-SEQ-001, SYNC-API-001]
---

# MINISPEC — AccountService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/account/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.5. 파이썬 판 [[SYNC-MS-006]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

서비스는 연결을 빌려 받는다 — `AccountService<'c> { pub db: &'c mut PgConnection }`. 트랜잭션은 부르는 쪽(켜기·웹 입구)이 쥔다([[SYNC-STD-004#DEV-10]]). 돌려주는 행은 `UserRow`다([[SYNC-STD-004#DEV-2]]).

**카드 L1 몫은 로컬 사용자 둘이고(2026-10-07), 카드 L3가 토큰 넷을 더했다(2026-10-08).** 커밋 작성자(L11)는 그 카드가 이 문서에 더한다.

**토큰은 파이썬 판과 같은 꼴이다** — 원문 `syncdoc_pat_` + 32바이트를 base64url(채움 없음)로 쓴 43자, DB에는 원문의 sha256 16진 64자만. 두 판은 같은 표를 쓰므로 한 판이 발급한 토큰을 다른 판이 그대로 받는다(데이터 자리를 옮겨 와도). 돌려주는 토큰 행은 `AccessTokenRow`, 발급 결과는 `IssuedToken { token, raw }`다([[SYNC-DOM-004]] 4.5).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#AccountService.ensure_local_user]] | 로컬 사용자를 둔다 |
| [[#AccountService.local_user]] | 로컬 사용자 |
| [[#AccountService.list_tokens]] | 내 토큰 |
| [[#AccountService.issue_token]] | 토큰 발급 |
| [[#AccountService.revoke_token]] | 토큰 폐기 |
| [[#AccountService.authenticate_token]] | MCP 인증 |

---

## 2. 함수

#### AccountService.ensure_local_user 로컬 사용자를 둔다

**시그니처**
```rust
pub async fn ensure_local_user(&mut self, login: &str, display_name: &str) -> Result<UserRow, Problem>
```

근거: [[SYNC-MS-006#AccountService.ensure_local_user]] · [[SYNC-PRD-001#R15]]

**입력** 설정의 아이디와 표시 이름 — 켤 때 [[SYNC-MS-012#runtime.run]]이 부른다

**처리** [[SYNC-MS-006#AccountService.ensure_local_user]]와 같다
1. `u = users where kind='local'`(id 순 첫 행)
2. `other = users where github_login=login` · if `other`가 있고 `u`가 아니다 → `! Internal`(「LOCAL_LOGIN {login}은 이미 다른 사용자다 — 다른 아이디로」) — 켤 때라 서버가 뜨지 않고 이 문장이 로그에 남는다
3. if `u` → `github_login`·`display_name`을 입력대로 고친다 · `→ 고친 행`
4. `users insert (github_login=login, github_user_id=NULL, kind='local', display_name=display_name, github_token_encrypted=NULL)` · `→ 새 행`

**다른 점** 파이썬은 2에서 `RuntimeError`를 던진다 — Rust는 MINISPEC 함수가 `Problem`을 돌려주므로([[SYNC-STD-004#DEV-5]]) `Problem::Internal`의 로그 문장이다

**테스트 관점** 처음 → `kind=local` 행 하나 · 두 번 불러도 행 하나 · 이름을 바꿔 부르면 같은 행의 이름이 바뀐다 · 같은 아이디의 GitHub 사용자·자리표시가 있으면 `Problem`이고 그 행은 그대로 · 로컬 사용자의 아이디를 남의 아이디로 바꾸려 하면 `Problem`

---

#### AccountService.local_user 로컬 사용자

**시그니처**
```rust
pub async fn local_user(&mut self, login: &str, display_name: &str) -> Result<UserRow, Problem>
```

근거: [[SYNC-MS-006#AccountService.local_user]] · [[SYNC-SEQ-001#SEQ-C3]]

**처리** `u = users where kind='local'` · if `u` → `→ u` · else → `→ ensure_local_user(login, display_name)` — 켤 때 만들었으니 보통은 있다. DB를 바꿔 끼운 경우의 안전망

**다른 점** 전역 설정이 없어 아이디·이름을 받는다 — 부르는 쪽(웹 입구의 현재 사용자)이 설정에서 넘긴다

**호출하는 것** [[#AccountService.ensure_local_user]]

**테스트 관점** 있으면 그 행(이름을 고치지 않는다) · 없으면 받은 아이디·이름으로 만든다

---

#### AccountService.list_tokens 내 토큰

**시그니처**
```rust
pub async fn list_tokens(&mut self, user: &UserRow) -> Result<Vec<AccessTokenRow>, Problem>
```

근거: [[SYNC-MS-006#AccountService.list_tokens]] · [[SYNC-API-001#GET/api/me/tokens]]

**처리** `access_tokens where user_id=user.id order by issued_at desc` — 폐기된 것도. 행에 `token_hash`가 있지만 응답 형태(`AccessToken`)가 싣지 않는다

**다른 점** 같은 `issued_at`이면 순서가 정해지지 않는 것도 파이썬과 같다(둘 다 `order by issued_at desc`뿐)

**테스트 관점** 내 것만 · 새것이 앞 · 폐기한 것도 나온다

---

#### AccountService.issue_token 토큰 발급

**시그니처**
```rust
pub async fn issue_token(&mut self, user: &UserRow, label: &str) -> Result<IssuedToken, Problem>
```

근거: [[SYNC-MS-006#AccountService.issue_token]] · [[SYNC-API-001#POST/api/me/tokens]] · [[SYNC-INFRA-001]] 5장

**입력** `label` — 웹 입구가 50자 이하를 이미 보았다(빈 문자열도 받는다 — 파이썬 판과 같다)

**처리** [[SYNC-MS-006#AccountService.issue_token]]와 같다
1. `raw = "syncdoc_pat_" + base64url(OS 난수 32바이트)` — 파이썬 `secrets.token_urlsafe(32)`와 같은 길이·글자
2. `access_tokens insert (user_id, token_hash=sha256_hex(raw), label, issued_at=저장 시각([[SYNC-STD-004#DEV-18]]), expires_at=NULL, last_used_at=NULL)`
3. `→ IssuedToken { token: 새 행, raw }` — `raw`는 이 반환에만 있다. 로그에 남기지 않는다

**테스트 관점** DB에 `raw`가 없고 해시만 · 원문이 `syncdoc_pat_` + 43자 · `authenticate_token(raw)` → 같은 사용자 · 발급 직후 `last_used_at`·`revoked_at`·`expires_at`이 비었다

---

#### AccountService.revoke_token 토큰 폐기

**시그니처**
```rust
pub async fn revoke_token(&mut self, user: &UserRow, token_id: i64) -> Result<(), Problem>
```

근거: [[SYNC-MS-006#AccountService.revoke_token]] · [[SYNC-API-001#DELETE/api/me/tokens/{id}]]

**처리** `access_tokens where id=token_id and user_id=user.id` · if 없음 → `! NotFound("access_token", token_id)`(남의 토큰도 같은 답) · `update revoked_at=저장 시각`. 행은 남긴다

**다른 점** 파이썬의 `int`는 크기가 없다 — `i64` 밖의 id는 웹 입구가 이 함수를 부르지 않고 같은 `not-found`를 낸다(그런 행은 없다). 이미 폐기한 토큰을 다시 폐기하면 `revoked_at`이 새 시각으로 바뀐다 — 파이썬 판과 같다

**테스트 관점** 폐기 뒤 행이 남고 `revoked_at`이 찬다 · 남의 토큰 → `not-found`이고 그 행은 그대로 · 없는 id → `not-found`

---

#### AccountService.authenticate_token MCP 인증

**시그니처**
```rust
pub async fn authenticate_token(&mut self, raw: &str) -> Result<Option<UserRow>, Problem>
```

근거: [[SYNC-MS-006#AccountService.authenticate_token]] · [[SYNC-SEQ-001#SEQ-C2]]

**처리** [[SYNC-MS-006#AccountService.authenticate_token]]와 같다
1. `t = access_tokens where token_hash=sha256_hex(raw)`
2. if `t`가 없거나 폐기됐거나 만료됐다(`expires_at < now`) → `→ None`
3. `u = users where id=t.user_id` · if 없음 → `→ None`
4. `access_tokens update last_used_at=저장 시각` — 통과한 요청만. 부르는 쪽(MCP 입구)이 응답 전에 곧바로 커밋한다
5. `→ u`

**다른 점** 싱크독_로컬에는 허용 목록(`ALLOWED_LOGINS`)이 없다 — 파이썬 폐쇄망판에서도 로컬 사용자는 목록과 상관없이 통과한다([[SYNC-MS-006#AccountService.authenticate_token]] 테스트 관점). 그래서 3a의 목록 확인이 없다

**호출되는 것** MCP 입구의 Bearer 인증(`server/mcp/auth`)

**테스트 관점** 폐기 뒤 → None · 오타 → None · 어느 경우든 무엇이 틀렸는지 알리지 않는다 · 통과하면 `last_used_at`이 찬다 · 실패하면 아무것도 안 바꾼다 · 부르는 쪽 — 통과한 요청 뒤 `last_used_at`이 커밋돼 있다

---

## 3. 미결사항

없음.
