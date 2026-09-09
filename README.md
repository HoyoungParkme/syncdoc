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

```
cp .env.example .env      # SECRET_KEY·GITHUB_CLIENT_ID·GITHUB_CLIENT_SECRET 채우기
docker compose up -d --build
```

`http://localhost:8000` — GitHub 로그인 뒤 프로젝트를 등록한다.
노트북 밖에서 쓰려면 `scripts/tunnel.sh` (Cloudflare Quick Tunnel).

이 저장소는 싱크독으로 싱크독을 만드는 첫 프로젝트다.
