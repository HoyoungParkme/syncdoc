"""환경 변수·비밀키. SYNC-DOM-002 1장 · SYNC-CODE-001#A.

설정값 목록은 SYNC-INFRA-001 5.2. 비밀키 교체는 5.1 — 세션 서명 키와 토큰 암호화 키를 나눈다.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://syncdoc:syncdoc@localhost:5432/syncdoc"
    SECRET_KEY: str = "change-me"  # GitHub 토큰 암호화 (INFRA 5.1)
    SECRET_KEY_OLD: str = ""  # 교체 중일 때만. 복호화에만 쓴다 (INFRA 5.1)
    SESSION_SECRET: str = ""  # 세션 쿠키 서명. 비면 SECRET_KEY를 쓴다 (INFRA 5.1)
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    WEBHOOK_SECRET: str = ""
    REPOS_DIR: Path = Path("/var/syncdoc/repos")
    PUBLIC_BASE_URL: str = ""  # Quick Tunnel 주소 (INFRA 5장). 비면 로컬만
    POLL_INTERVAL_SECONDS: int = 300  # INFRA 7장 보조 경로. 0이면 폴링·기동 따라잡기 끔(테스트)
    DIFF_CONTEXT_LINES: int = 3  # diff에서 앞뒤로 함께 보여줄 줄 수 (INFRA 5.2)
    PUSH_RETRIES: int = 3  # push 거부 시 rebase 후 재시도 횟수 (INFRA 5.2)

    @property
    def session_secret(self) -> str:
        """세션 서명 키. 안 주면 SECRET_KEY로 떨어진다 — 기존 배포가 안 깨지게."""
        return self.SESSION_SECRET or self.SECRET_KEY


settings = Settings()
