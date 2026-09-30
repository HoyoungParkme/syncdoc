# 싱크독 폐쇄망판 — 설치 안내

인터넷이 없는 PC에서 혼자 쓰는 판이다. 로그인이 없고, 명세와 코드는 이 PC의 싱크독 서버 안 git 저장소에 쌓인다. GitHub에 닿지 않는다.

필요한 것: Docker(Compose 포함). 그 밖에 설치할 것은 없다 — git도 이미지 안에 있다.

## 0. 묶음 확인

```
sha256sum -c SHA256SUMS
```

모두 `OK`여야 한다. 아니면 옮기다 깨진 것이다 — 다시 받는다.

## 1. 설치

```
docker load -i images.tar.gz
cp .env.example .env
```

`.env`를 연다.

- `SECRET_KEY` — 길고 무작위한 문자열. `openssl rand -base64 48`의 결과를 넣는다
- `POSTGRES_PASSWORD` — DB 비밀번호. 처음 켜기 전에 정한다
- `LOCAL_NAME` — 이력에 보일 내 이름(비면 `LOCAL_LOGIN`)

```
docker compose up -d
```

브라우저로 <http://127.0.0.1:8000>을 연다. 프로젝트 목록이 바로 뜬다 — 로그인 화면이 없다. 스키마는 앱이 켜질 때 스스로 올린다.

## 2. 에이전트 붙이기 (MCP)

1. 화면 오른쪽 위 `설정` → MCP 토큰 `+ 발급` → 이름을 적고 발급 → 원문을 복사한다(한 번만 보인다)
2. 에이전트에 넣는다. Claude Code라면:

```
claude mcp add --transport http --scope user syncdoc \
  http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer {토큰}"
```

3. 에이전트를 **새로 켠다** — 켜져 있던 세션에는 안 보인다
4. 「싱크독으로 프로젝트 하나 만들어 줘」라고 말한다. 이 판은 저장 방식이 서버 하나라 묻지 않고 서버 저장소를 만든다

상단 바 `사용 방법`에 같은 순서가 그림과 함께 있다.

## 3. 코드 대조 — git push

프로젝트 화면 머리의 **push 방법**을 복사해 코드 저장소에서 돌린다.

```
git remote add syncdoc http://127.0.0.1:8000/git/{코드}.git
git push syncdoc main
```

아이디를 물으면 아무거나, **비밀번호 칸에 1에서 받은 MCP 토큰**을 넣는다. `main`만 처리하고, 되감기(force push)는 거절한다. push가 끝나면 코드 그래프가 만들어지고 문서 뷰의 코드 탭이 켜진다.

git이 없는 PC라면 에이전트가 MCP `upload_code`로 올린다 — 한 번에 5MB·파일 500개까지, 글자 파일만.

## 4. 질문 탭 (선택)

사내에 OpenAI 호환 모델 서버가 있으면 `.env`의 셋을 채우고 `docker compose up -d`로 다시 켠다.

```
LLM_API_URL=http://{사내 주소}/v1/chat/completions
LLM_MODEL={모델 이름}
LLM_API_KEY={키}
```

키가 필요 없는 서버면 `LLM_API_KEY`에 아무 값이나 넣는다 — 비어 있으면 탭이 꺼진다.

## 5. 업데이트

새 묶음을 받아 0처럼 확인한 뒤:

```
docker load -i images.tar.gz
```

지금 쓰는 폴더의 `.env`에서 `SYNCDOC_VERSION`만 새 판으로 바꾸고 새 `docker-compose.yml`을 그 폴더에 덮어쓴 뒤:

```
docker compose up -d
```

데이터(볼륨 `syncdoc-closed_pgdata`·`_repos`·`_origins`)는 그대로다. 새 스키마는 켜질 때 올라간다.

## 6. 백업

**서버 저장소가 명세와 코드의 원본이다.** DB와 함께 백업한다.

```
docker compose exec -T db pg_dump -U syncdoc syncdoc > syncdoc-$(date +%F).sql
docker compose exec -T app tar czf - -C /var/syncdoc/origins . > origins-$(date +%F).tgz
```

`repos`는 작업 사본이라 백업하지 않아도 된다 — 없으면 다시 만든다.

새 PC에 되살리기: 1의 `docker load`와 `.env`까지 하고(**`docker compose up -d`는 아직 하지 않는다** — 앱이 빈 스키마를 먼저 만든다) DB만 켠 뒤 넣는다.

```
docker compose up -d --wait db
docker compose exec -T db psql -U syncdoc -d syncdoc < syncdoc-{날짜}.sql
docker compose run --rm --no-deps -T app tar xzf - -C /var/syncdoc/origins < origins-{날짜}.tgz
docker compose up -d
```

발급한 토큰은 DB에 있어 그대로 쓰인다.

## 7. 같은 망의 다른 PC에서 열 때 (주의)

**로그인이 없으니 그 망의 누구나 쓰게 된다.** 그래도 열려면:

1. `docker-compose.yml`의 포트를 `"8000:8000"`으로 바꾼다
2. `.env`의 `PUBLIC_BASE_URL`을 다른 PC가 부르는 주소로 바꾼다(예: `http://10.0.0.5:8000`) — 이 서버는 허용한 주소로 들어온 요청만 받는다
3. `docker compose up -d`

## 8. 막힐 때

| 증상 | 할 일 |
|---|---|
| 화면이 403 `forbidden-origin` | 허용하지 않은 주소로 열었다. `127.0.0.1`로 열거나 7의 2 |
| 앱이 곧바로 멈춘다 | `docker compose logs app` — `LOCAL_LOGIN … 다른 사용자`면 다른 아이디로 바꾼다 |
| push가 401 | 비밀번호 칸에 토큰을 넣었는지, 폐기한 토큰이 아닌지 |
| push가 404 | 프로젝트 코드가 맞는지(`/git/{코드}.git`, 대문자) |
