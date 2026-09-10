---
doc_id: SYNC-MS-006
type: MS
title: MINISPEC — AccountService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — AccountService

## 0. 이 문서가 다루는 것

`core/account/service.py`의 함수 8개. 클래스 명세 [[SYNC-DOM-002]] 4.6의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`users`·`access_tokens`만. 비밀키는 `config.SECRET_KEY`(DB 밖).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#AccountService.login_github]] | OAuth 콜백 |
| [[#AccountService.list_tokens]] | 내 토큰 |
| [[#AccountService.issue_token]] | 토큰 발급 |
| [[#AccountService.revoke_token]] | 토큰 폐기 |
| [[#AccountService.authenticate_token]] | MCP 인증 |
| [[#AccountService.github_token_for]] | push용 토큰 복호화 |
| [[#AccountService.user_by_login]] | 로그인 → User |
| [[#AccountService.users_by_ids]] | 여러 사용자 표시 정보 |
| [[#AccountService.create_placeholder]] | 미등록 자리표시 |

---

## 2. 함수

#### AccountService.login_github OAuth 콜백

**시그니처** `async def login_github(code: str, state: str) -> User` — `github.*`가 async라 async([[SYNC-STD-004#DEV-16]])

근거: [[SYNC-SEQ-001#SEQ-8]] · [[SYNC-INFRA-001]] 5장 · [[SYNC-API-001#GET/auth/github/callback]]

**입력** GitHub가 돌려준 `code`, 우리가 보낸 `state`(라우터가 세션과 대조한 뒤 넘김)

**처리**
1. `token = github.exchange_code(code)` · if 실패 → `! unauthorized`
2. `info = github.get_user(token)` → `{id, login, name}`
3. `u = DB: users where github_user_id=info.id`
   - if 있음 → `login`·`display_name` 갱신 (로그인 ID 변경 대응)
   - else → `u = DB: users where github_login=info.login and github_user_id is null` (자리표시) · if 있음 → `github_user_id` 채움 (미등록 push 사람이 로그인) · else → insert
4. `u.github_token_encrypted = encrypt(token, SECRET_KEY)` (Fernet) · `DB: update`
5. `→ u`. 라우터가 세션을 만든다 — 테이블 없이 **서명 쿠키** `syncdoc_session`에 `github_login`만. 요청마다 `user_by_login`으로 User를 얻는다(인프라 5장)

**테스트 관점** 첫 로그인 → 행 생성 · 로그인 ID 바꾼 뒤 → 같은 행, `login` 갱신 · 자리표시가 있던 사람 → 그 행에 `github_user_id`·토큰 채워짐 (별도 행 안 생김)

---

#### AccountService.list_tokens 내 토큰

**시그니처** `list_tokens(user: User) -> list[AccessToken]`

**처리** `DB: access_tokens where user_id order by issued_at desc`. 폐기된 것 포함. `token_hash`는 반환에서 뺀다

---

#### AccountService.issue_token 토큰 발급

**시그니처** `issue_token(user: User, label: str) -> IssuedToken`

근거: [[SYNC-INFRA-001]] 5장 · [[SYNC-API-001#POST/api/me/tokens]] · UI-13 다이얼로그 4

**처리**
1. `raw = "syncdoc_pat_" + secrets.token_urlsafe(32)`
2. `DB: access_tokens insert (user_id, token_hash=sha256(raw), label, issued_at=now, expires_at=None)`
3. `→ IssuedToken(token=행, raw)`. **`raw`는 이 반환에만 있다.** 로그에 남기지 않는다

**테스트 관점** 발급 후 DB에 `raw` 없음 · `authenticate_token(raw)` → 같은 User

---

#### AccountService.revoke_token 토큰 폐기

**시그니처** `revoke_token(user: User, token_id: int) -> None`

**처리** `DB: access_tokens where id and user_id=user.id` · if 없음 → `! not-found` (남의 토큰도 not-found) · `update revoked_at=now`. 행은 남긴다

---

#### AccountService.authenticate_token MCP 인증

**시그니처** `authenticate_token(raw: str) -> User | None`

근거: [[SYNC-SEQ-001#SEQ-C2]]

**처리**
1. `h = sha256(raw)`
2. `t = DB: access_tokens where token_hash=h`
3. if `t is None or t.revoked_at or (t.expires_at and t.expires_at < now)` → `→ None`
4. `→ DB: users where id=t.user_id`

**테스트 관점** 폐기 후 → None · 오타 raw → None. 어느 경우든 **어느 쪽이 틀렸는지 알려주지 않는다**

---

#### AccountService.github_token_for push용 토큰 복호화

**시그니처** `github_token_for(user: User) -> str`

**처리** if `user.github_token_encrypted is None` → `! unauthorized {reason: 미등록 사용자. 로그인 필요}` · else → `decrypt(…, SECRET_KEY)`. 자리표시 User는 push할 수 없다 — 그 사람 이름으로 커밋이 필요한 경로(웹 되돌리기·상태 변경)는 로그인한 뒤에야 가능

---

#### AccountService.user_by_login 로그인 → User

**시그니처** `user_by_login(login: str) -> User | None`

**처리** `DB: users where github_login=login`. 자리표시도 반환

---

#### AccountService.users_by_ids 여러 사용자 표시 정보

**시그니처** `users_by_ids(ids: list[int]) -> dict[int, UserRef]`

**처리** `DB: users where id in ids` → `{id: UserRef(id, github_login, display_name)}`. `queries`가 `AuthorRef`·`assignee_user_id`를 이름으로 바꿀 때. **쿼리 한 번**

---

#### AccountService.create_placeholder 미등록 자리표시

**시그니처** `create_placeholder(login: str) -> User`

근거: [[SYNC-SEQ-001#SEQ-2]] · 결정: 미등록 push는 자리표시 User + `author.unknown`

**처리** `DB: users insert (github_login=login, github_user_id=None, display_name=login, github_token_encrypted=None)` → User. `github_login` unique이므로 동시 호출은 한쪽이 기존 행을 받는다

---

## 3. 미결사항

- [ ] (없음)
