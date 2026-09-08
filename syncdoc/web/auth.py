"""GitHub OAuth·세션. SYNC-DOM-002 1장 web/auth.py · SYNC-SEQ-001#SEQ-8 · SYNC-INFRA-001 5장.

세션 = 서명 쿠키 `syncdoc_session`(SYNC-API-001 4장 securitySchemes). 세션 테이블은 없다(ERD 12개).
세션에는 github_login만 둔다 — 사용자 조회는 AccountService.user_by_login(MS-006).
"""

from urllib.parse import urlencode

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from syncdoc.config import settings
from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService
from syncdoc.core.errors import Unauthorized
from syncdoc.db import get_session

SESSION_COOKIE = "syncdoc_session"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


def authorize_url(state: str) -> str:
    """GitHub 동의 화면 주소. scope=repo(인프라 5장 — 저장소 범위만)."""
    q = urlencode({"client_id": settings.GITHUB_CLIENT_ID, "scope": "repo", "state": state})
    return f"{AUTHORIZE_URL}?{q}"


def login(request: Request, user: User) -> None:
    """세션 생성(SEQ-8 마지막). OAuth 임시값은 지운다."""
    request.session.clear()
    request.session["login"] = user.github_login


def logout(request: Request) -> None:
    request.session.clear()


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """라우터 의존성. 세션 없거나 사용자 없으면 401 unauthorized(API-001 1장)."""
    login_ = request.session.get("login")
    user = AccountService(session).user_by_login(login_) if login_ else None
    if user is None:
        raise Unauthorized("세션 없음")
    return user
