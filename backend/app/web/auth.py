"""GitHub OAuth·세션. SYNC-DOM-002 1장 web/auth.py · SYNC-SEQ-001#SEQ-8 · SYNC-INFRA-001 5장.

세션 = 서명 쿠키 `syncdoc_session`(SYNC-API-001 4장 securitySchemes). 세션 테이블은 없다(ERD 13개).
세션에는 github_login만 둔다 — 사용자 조회는 AccountService.user_by_login(MS-006).
"""

from __future__ import annotations

from urllib.parse import urlencode, urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import Unauthorized
from app.db import get_session

SESSION_COOKIE = "syncdoc_session"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


CALLBACK_PATH = "/auth/github/callback"


def callback_url(request: Request) -> str:
    """이 요청으로 들어온 주소의 콜백 URL (인프라 5장 PUBLIC_BASE_URL).

    터널 뒤에서는 프록시가 https를 http로 보이게 하므로 요청만으로는 스킴을 못 믿는다.
    요청 Host가 PUBLIC_BASE_URL의 host와 같으면 그 값을, 아니면 요청에서 만든다.
    """
    public = settings.PUBLIC_BASE_URL.strip().rstrip("/")
    if public and urlsplit(public).netloc == request.url.netloc:
        return f"{public}{CALLBACK_PATH}"
    return f"{request.url.scheme}://{request.url.netloc}{CALLBACK_PATH}"


def authorize_url(state: str, redirect_uri: str) -> str:
    """GitHub 동의 화면 주소. scope=repo(인프라 5장 — 저장소 범위만) · redirect_uri(SEQ-8)."""
    q = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "scope": "repo",
            "state": state,
            "redirect_uri": redirect_uri,
        }
    )
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
