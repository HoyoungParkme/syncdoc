# SYNC-INFRA-001 8장 — app 이미지: React 빌드(1단계) + FastAPI(2단계). CMD가 마이그레이션 뒤 서버를 띄운다.
# 폴더 구조는 SYNC-DOM-002 1장 — 컨테이너 안도 저장소와 같은 깊이로 둔다(app이 ../../docs/specs의 _templates·STD를 읽는다)
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY docs/specs/_templates /srv/docs/specs/_templates
COPY docs/specs/STD /srv/docs/specs/STD
# vite outDir이 ../backend/app/web/static 이라 1단계에서는 /backend/app/web/static 에 생긴다
COPY --from=web /backend/app/web/static ./app/web/static
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
