# SYNC-INFRA-001 8장 — app 이미지: React 빌드(1단계) + FastAPI(2단계). CMD가 마이그레이션 뒤 서버를 띄운다.
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY syncdoc ./syncdoc
COPY alembic ./alembic
COPY alembic.ini ./
COPY docs/specs/_templates ./docs/specs/_templates
# React 빌드 결과 — vite outDir이 ../syncdoc/web/static 이므로 1단계에서 /syncdoc/web/static 에 생긴다
COPY --from=web /syncdoc/web/static ./syncdoc/web/static
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn syncdoc.main:app --host 0.0.0.0 --port 8000"]
