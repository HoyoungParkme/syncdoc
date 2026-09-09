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
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn syncdoc.main:app --host 0.0.0.0 --port 8000"]
