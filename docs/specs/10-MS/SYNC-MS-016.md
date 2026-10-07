---
doc_id: SYNC-MS-016
type: MS
title: MINISPEC — AccountService (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-006, SYNC-SEQ-001, SYNC-API-001]
---

# MINISPEC — AccountService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/account/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.5. 파이썬 판 [[SYNC-MS-006]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

서비스는 연결을 빌려 받는다 — `AccountService<'c> { pub db: &'c mut PgConnection }`. 트랜잭션은 부르는 쪽(켜기·웹 입구)이 쥔다([[SYNC-STD-004#DEV-10]]). 돌려주는 행은 `UserRow`다([[SYNC-STD-004#DEV-2]]).

**카드 L1 몫은 로컬 사용자 둘이다(2026-10-07).** 토큰(L3)·커밋 작성자(L11)는 그 카드가 이 문서에 더한다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#AccountService.ensure_local_user]] | 로컬 사용자를 둔다 |
| [[#AccountService.local_user]] | 로컬 사용자 |

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

## 3. 미결사항

없음.
