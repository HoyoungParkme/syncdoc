---
doc_id: SYNC-MS-006
type: MS
title: MINISPEC — AccountService
status: draft
upstream: [SYNC-DOM-002, SYNC-SEQ-001, SYNC-API-001, SYNC-API-002, SYNC-STD-001]
---

# MINISPEC — AccountService

## 0. 이 문서가 다루는 것

`core/account/service.py`의 함수 13개. 클래스 명세 [[SYNC-DOM-002]] 4.6의 시그니처를 함수 내부까지 내린 것. **MS 문서 하나 = 클래스 명세 4장 절 하나 = 코드 파일 하나** — 이 파일을 짤 때 이 문서를 본다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입(`Author` `ItemBlock` `ValidateResult` …)은 [[SYNC-DOM-002]] 2.8.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `git:` 저장소 접근, `·` 같은 단계 안 구분.

`users`·`access_tokens`·`commit_emails`만. 비밀키는 `config.SECRET_KEY`(DB 밖).

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
| [[#AccountService.user_for_commit]] | 커밋 작성자 → User |
| [[#AccountService.commit_emails]] | 내 커밋 이메일 |
| [[#AccountService.add_commit_email]] | 커밋 이메일 등록 |
| [[#AccountService.remove_commit_email]] | 커밋 이메일 삭제 |

---

## 2. 함수

#### AccountService.login_github OAuth 콜백

**시그니처** `async def login_github(code: str, state: str, redirect_uri: str) -> User` — `github.*`가 async라 async([[SYNC-STD-004#DEV-16]])

근거: [[SYNC-SEQ-001#SEQ-8]] · [[SYNC-INFRA-001]] 5장 · [[SYNC-API-001#GET/auth/github/callback]]

**입력** GitHub가 돌려준 `code`, 우리가 보낸 `state`(라우터가 세션과 대조한 뒤 넘김), `redirect_uri`(라우터가 `auth.callback_url(request)`로 만든 것 — authorize 때와 같은 값)

**처리**
1. `token = github.exchange_code(code, redirect_uri)` · if 실패 → `! unauthorized`
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
2. `DB: access_tokens insert (user_id, token_hash=sha256(raw), label, issued_at=now, expires_at=None, last_used_at=None)`
3. `→ IssuedToken(token=행, raw)`. **`raw`는 이 반환에만 있다.** 로그에 남기지 않는다

`expires_at=None`은 **정책이다.** v1은 만료를 두지 않는다(인프라 9장). 컬럼과 검증 분기는 남겨
두므로 정책이 바뀌면 이 함수만 고치면 된다.

만료가 없으니 안 쓰는 토큰을 찾을 단서가 필요하다 — 그게 `last_used_at`이다.

**테스트 관점** 발급 후 DB에 `raw` 없음 · `authenticate_token(raw)` → 같은 User · 발급 직후 `last_used_at is None`

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
4. `DB: access_tokens update last_used_at=now` — 통과한 요청만. UI-13이 이 값을 보여준다
5. `→ DB: users where id=t.user_id`

**테스트 관점** 폐기 후 → None · 오타 raw → None. 어느 경우든 **어느 쪽이 틀렸는지 알려주지 않는다** · 성공한 인증 뒤 `last_used_at`이 갱신됨 · 실패한 인증은 아무것도 안 건드림

---

#### AccountService.github_token_for push용 토큰 복호화

**시그니처** `github_token_for(user: User) -> str`

**처리** if `user.github_token_encrypted is None` → `! unauthorized {reason: 미등록 사용자. 로그인 필요}` · else → `decrypt(…)`. 자리표시 User는 push할 수 없다 — 그 사람 이름으로 커밋이 필요한 경로(웹 되돌리기·상태 변경)는 로그인한 뒤에야 가능

**복호화 실패도 `unauthorized`다.** 비밀키를 바꾸면 기존에 저장된 토큰이 전부 풀리지 않는다.
이때 나는 `InvalidToken`을 잡아 `! unauthorized {reason: 토큰을 풀 수 없다. 다시 로그인해야 한다}`로
바꾼다. 안 잡으면 `Problem`이 아니라서 평문 500이 나가고, `git.commit_push`의 `except Unauthorized`도
못 잡는다.

**복호화는 옛 키도 시도한다.** `SECRET_KEY`(새 키)와 `SECRET_KEY_OLD`(있으면)를 함께 써서
복호화하고 암호화는 늘 새 키로 한다. 교체 절차는 인프라 5장.

**테스트 관점** 미등록 → unauthorized · 키를 바꾼 뒤 옛 토큰 → unauthorized(500 아님) · 옛 키를 함께 주면 풀림

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

**`login`이 GitHub 아이디가 아닐 수 있다.** 커밋 이메일이 noreply가 아니면 `git._login_of`가 `%an`(사람 이름)을 대신 준다. 공백이 든 문자열이 `github_login`에 앉는다 — 그래도 만든다. 판정을 여기서 하면 push를 건너뛰게 되고 원본·DB가 어긋난다([[SYNC-DOM-002]] 5장 결정 3)

---

#### AccountService.user_for_commit 커밋 작성자 → User

**시그니처** `user_for_commit(email: str, login: str) -> User`

근거: [[SYNC-DOM-002]] 5장 결정 3 · [[SYNC-UC-001#UC-G1]]

**입력** `email` git 커밋의 `%ae` 원본 · `login` `git._login_of`가 준 값([[SYNC-MS-009#git.changed_files]])

**처리**
1. if `email` → `u = DB: commit_emails where email=email.strip().lower() join users` · if `u` → `→ u`
2. `u = user_by_login(login)` · if `u` → `→ u`
3. `→ create_placeholder(login)`

**순서가 규칙이다.** 이메일이 먼저인 이유는 git 커밋이 남기는 신원 중 계정으로 이어지는 것이 이메일뿐이기 때문이다. `login`은 noreply 메일일 때만 진짜 아이디이고, 아니면 `%an` 대체값이다.

**자리표시를 만드는 곳은 여기 하나다.** `process_commit`과 `rebuild`가 각자 만들면 판정이 두 경로에서 어긋난다 — 실제로 어긋나 있었다(#34).

**호출하는 것** `pipeline.process_commit` 4단계 · `pipeline.rebuild` 5단계

**테스트 관점** 등록된 이메일 → 그 사용자(login이 달라도) · 미등록 이메일 + noreply login → login으로 찾은 사용자 · 둘 다 없음 → 자리표시 · 대소문자가 달라도 같은 이메일로 찾는다 · `email`이 빈 문자열이면 2번부터

---

#### AccountService.commit_emails 내 커밋 이메일

**시그니처** `commit_emails(user: User) -> list[CommitEmail]`

**처리** `DB: commit_emails where user_id=user.id order by added_at` → 목록

**호출하는 것** `GET /api/me/emails`(UI-13 2.3)

---

#### AccountService.add_commit_email 커밋 이메일 등록

**시그니처** `add_commit_email(user: User, email: str) -> CommitEmail`

**처리**
1. `e = email.strip().lower()` — git 이메일은 대소문자가 흔들린다
2. `row = DB: commit_emails where email=e`
3. if `row and row.user_id == user.id` → `→ row` — 멱등. 두 번 눌러도 오류가 아니다
4. if `row` → `! email-taken {email: e}` — 이메일 하나는 사람 하나다
5. `DB: commit_emails insert (user_id=user.id, email=e)` → `→ row`

**등록만으로는 이미 쌓인 것이 안 옮겨진다.** 버전·플래그는 인덱스를 다시 만들 때 작성자를 다시 찾는다. 재구축을 한 번 돌려야 한다(UI-13 규칙)

**예외** `email-taken` 409

**테스트 관점** 남이 가진 이메일 → email-taken · 내가 이미 가진 이메일 → 같은 행(새로 안 만든다) · `Foo@Bar.COM` 등록 뒤 `foo@bar.com`으로 찾힘

---

#### AccountService.remove_commit_email 커밋 이메일 삭제

**시그니처** `remove_commit_email(user: User, email_id: int) -> None`

**처리** `row = DB: commit_emails where id=email_id` · if `row is None or row.user_id != user.id` → `! not-found` · else `DB: delete row`

**남의 것인지 아닌지를 구분해 알려주지 않는다** — 둘 다 `not-found`다. 있는지 없는지가 새어 나가면 안 된다

**테스트 관점** 남의 이메일 삭제 → not-found · 없는 id → not-found · 삭제 뒤 재구축하면 그 이메일 커밋이 자리표시로 돌아간다

---

## 3. 미결사항

- [x] **GitHub OAuth 토큰 갱신이 없다.** OAuth 앱의 "Expire user access tokens"를 켜면 8시간 뒤 만료되고 `refresh_token`으로 갱신해야 하는데 `login_github`·`github_token_for`에 갱신 경로가 없다. 만료 뒤 push가 `push-failed`로 죽는다. **지금은 앱 설정에서 만료를 꺼서 피한다** — 인프라 5장에 적었다. v2에 갱신 넣기 — 결정: v1은 앱 설정에서 만료를 꺼서 피한다(인프라 5장). 갱신은 v2
