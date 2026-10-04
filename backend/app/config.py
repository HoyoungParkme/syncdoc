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
    # 싱크독이 만드는 GitHub 저장소를 비공개로 (INFRA 5장, #310). 공개는 false로 명시할 때만
    GITHUB_REPO_PRIVATE: bool = True
    WEBHOOK_SECRET: str = ""
    REPOS_DIR: Path = Path("/var/syncdoc/repos")
    # 서버 저장소와 보관 폴더(_archive/). 원본이라 볼륨으로 남기고 백업한다 (INFRA 5.2·6장)
    ORIGINS_DIR: Path = Path("/var/syncdoc/origins")
    # 이 서버에서 켠 저장 방식. 쉼표로 github·server 중 하나 이상 (PRD R14, INFRA 5.2)
    STORAGE_MODES: str = "github,server"
    # 새 저장소 README가 규약·템플릿을 가리키는 주소 (INFRA 5.2, 카드 AB). 저장소를 옮기면 바꾼다
    SPECS_URL: str = "https://github.com/HoyoungParkme/syncdoc/blob/main/docs/specs"
    PUBLIC_BASE_URL: str = ""  # 공개 주소 — Named 고정 호스트 또는 Quick (INFRA 5장). 비면 로컬만
    POLL_INTERVAL_SECONDS: int = 300  # INFRA 7장 보조 경로. 0이면 폴링·기동 따라잡기 끔(테스트)
    DIFF_CONTEXT_LINES: int = 3  # diff에서 앞뒤로 함께 보여줄 줄 수 (INFRA 5.2)
    PUSH_RETRIES: int = 3  # push 거부 시 rebase 후 재시도 횟수 (INFRA 5.2)
    # 읽는 중 질의 (INFRA 5.3). 키가 비면 기능이 꺼진다 — 켜는 쪽이 선택이다
    LLM_API_KEY: str = ""
    LLM_API_URL: str = "https://api.openai.com/v1/chat/completions"  # OpenAI 호환 Chat Completions
    LLM_MODEL: str = "gpt-4o"
    LLM_MAX_TURNS: int = 10  # 한 대화에서 서버가 받는 최대 턴 수
    # 판 — internet 또는 closed (PRD R15, INFRA 8.1). closed면 로그인 없이 로컬 사용자 하나
    EDITION: str = "internet"
    LOCAL_LOGIN: str = "local"  # 폐쇄망판 로컬 사용자의 아이디 — 커밋 작성자 {아이디}@syncdoc.local
    LOCAL_NAME: str = ""  # 폐쇄망판 로컬 사용자의 표시 이름. 비면 LOCAL_LOGIN

    @property
    def closed(self) -> bool:
        """폐쇄망판인가 (PRD R15). 모르는 값은 인터넷판 — 로그인을 끄는 쪽이 명시여야 한다."""
        return self.EDITION.strip().lower() == "closed"

    @property
    def edition(self) -> str:
        return "closed" if self.closed else "internet"

    @property
    def local_name(self) -> str:
        return self.LOCAL_NAME.strip() or self.LOCAL_LOGIN

    @property
    def specs_url(self) -> str:
        """README 규약 링크의 뿌리 (INFRA 5.2·8.1). 폐쇄망판에서 기본값이면 이 서버의 /specs."""
        default = type(self).model_fields["SPECS_URL"].default
        if self.closed and self.SPECS_URL == default:
            return f"{self.PUBLIC_BASE_URL.strip().rstrip('/') or 'http://127.0.0.1:8000'}/specs"
        return self.SPECS_URL

    @property
    def storage_modes(self) -> list[str]:
        """켠 저장 방식 — 적힌 순서대로, 모르는 값과 겹친 값은 뺀다. 비면 github 하나(예전 동작).

        폐쇄망판은 서버 하나다 — GitHub에 닿지 못한다 (PRD R15).
        """
        if self.closed:
            return ["server"]
        out: list[str] = []
        for m in (x.strip().lower() for x in self.STORAGE_MODES.split(",")):
            if m in ("github", "server") and m not in out:
                out.append(m)
        return out or ["github"]

    @property
    def session_secret(self) -> str:
        """세션 서명 키. 안 주면 SECRET_KEY로 떨어진다 — 기존 배포가 안 깨지게."""
        return self.SESSION_SECRET or self.SECRET_KEY


settings = Settings()
