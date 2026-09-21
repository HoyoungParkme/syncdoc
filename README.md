# 싱크독 (SyncDoc)

바이브코딩 시대에 개발자가 PM 없이 11단계 명세 체인을 쓰고, 에이전트가 그 명세를 따르게 하는 플랫폼.

- 명세: `docs/specs/` — 27개. 디렉터리 번호가 읽는 순서다. 시작은 `docs/specs/STD/SYNC-STD-003.md`(체인 지도)
- 사람용 뷰: `python tools/view_build.py --all` → `docs/views/index.html`
- 에이전트: `AGENTS.md`
- 구현: `docs/specs/11-CODE/SYNC-CODE-001.md` 카드 A부터

## 구조

```
backend/    파이썬 (FastAPI + MCP). app/ 이 임포트 패키지
frontend/   React (Vite+TS). 빌드 결과를 백엔드가 서빙한다
docs/specs/ 명세 원본 — 이 저장소의 진실
tools/      명세·코드·화면 검사기
```

## 띄우기

**처음 한 번**

```
cp .env.example .env      # SECRET_KEY·GITHUB_CLIENT_ID·GITHUB_CLIENT_SECRET 채우기
```

**켤 때마다 — 재부팅한 뒤에도 이것 하나면 된다**

```
scripts/tunnel.sh
```

앱·DB를 띄우고 `/health`가 200이 될 때까지 기다린 뒤 터널을 붙인다.
`.env`에 `TUNNEL_TOKEN`·`PUBLIC_BASE_URL`이 있으면 Cloudflare **Named Tunnel**(고정 주소)이라 사람이 할 일이 없다.
없으면 **Quick Tunnel**이고 주소가 매번 바뀌므로 스크립트가 시키는 대로 OAuth 콜백을 고친다.

터널만 끄려면 `scripts/tunnel.sh --stop`. 앱만 띄우려면 `docker compose up -d --build`.

### 재부팅하면 왜 매번 해야 하나

자동으로 뜨는 것이 하나도 없다.

| 무엇 | 왜 안 뜨나 |
|---|---|
| 컨테이너 | 재시작 정책이 `no`다. 도커가 알아서 띄우지 않는다 |
| 터널 | WSL 안에서 도는 프로세스다. 윈도우 서비스로 등록돼 있지 않다 |
| 도커 자체 | 윈도우에서 Docker Desktop이 먼저 떠 있어야 한다 |

**데이터는 남는다.** 문서·DB·작업 사본이 전부 도커 볼륨(`pgdata`·`repos`)에 있고 명세 원본은 GitHub에 있다.

**확인**

```
docker compose ps                                  # app·db 가 Up
curl -s localhost:8000/health                      # {"status":"ok"}
curl -s $(grep ^PUBLIC_BASE_URL= .env | cut -d= -f2)/health   # 공개 주소도 같은 응답
```

`docker compose ps`가 비어 있으면 Docker Desktop이 아직 안 뜬 것이다.
공개 주소만 502면 터널은 붙었는데 앱이 안 뜬 것이니 `docker compose logs app`을 본다.

이 저장소는 싱크독으로 싱크독을 만드는 첫 프로젝트다.
