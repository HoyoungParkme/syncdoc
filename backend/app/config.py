"""환경 변수·비밀키. SYNC-DOM-002 1장 · SYNC-CODE-001#A.

DB URL · SECRET_KEY · GitHub OAuth · WEBHOOK_SECRET · REPOS_DIR · POLL_INTERVAL_SECONDS.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://syncdoc:syncdoc@localhost:5432/syncdoc"
    SECRET_KEY: str = "change-me"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    WEBHOOK_SECRET: str = ""
    REPOS_DIR: Path = Path("/var/syncdoc/repos")
    PUBLIC_BASE_URL: str = ""  # Quick Tunnel 주소 (INFRA 5장). 비면 로컬만
    POLL_INTERVAL_SECONDS: int = 300  # INFRA 7장 보조 경로. 0이면 폴링·기동 따라잡기 끔(테스트)


settings = Settings()
