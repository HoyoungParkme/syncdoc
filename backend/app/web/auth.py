"""GitHub OAuth·세션. SYNC-DOM-002 1장 web/auth.py · SYNC-SEQ-001#SEQ-8 · SYNC-INFRA-001 5장.

세션 = 서명 쿠키 `syncdoc_session`(SYNC-API-001 4장 securitySchemes). 세션 테이블은 없다(ERD 13개).
세션에는 github_login만 둔다 — 사용자 조회는 AccountService.user_by_login(MS-006).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, Request
from itsdangerous import TimestampSigner
from itsdangerous.exc import SignatureExpired
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware as _StarletteSessionMiddleware

from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import Unauthorized
from app.db import get_session

SESSION_COOKIE = "syncdoc_session"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


CALLBACK_PATH = "/auth/github/callback"


class _ForwardOnlySigner(TimestampSigner):
    """서명 시각이 **미래여도** 거절하지 않는 검사기. 만료(위쪽)는 그대로 본다.

    SYNC-INFRA-001 5장 · SYNC-STD-004#DEV-18 · #17.

    `itsdangerous`는 `age = 지금 - 서명시각`이 음수면 `SignatureExpired`를 던지고,
    Starlette은 그걸 `BadSignature`로 잡아 **조용히 빈 세션**으로 만든다 — 방금
    로그인한 사람이 401을 받는다. 타임스탬프가 정수 초라, 시계가 1초 경계를 한 번
    뒤로 넘으면 그 직전에 발급한 쿠키가 그 자리에서 죽는다. 부하 중 60초에 두 번
    그런 순간이 오는 것을 쟀다.

    미래 시각 쿠키는 세션 서명 키가 있어야 만들 수 있으므로 받아들여도 잃는 게 없다.
    """

    def unsign(  # type: ignore[override]
        self,
        signed_value: str | bytes,
        max_age: int | None = None,
        return_timestamp: bool = False,
    ) -> tuple[bytes, datetime] | bytes:
        # 서명 검증과 타임스탬프 해석은 부모에게 맡기고 만료만 우리가 본다
        value, signed_at = super().unsign(signed_value, None, return_timestamp=True)
        if max_age is not None:
            age = self.get_timestamp() - int(signed_at.timestamp())
            if age > max_age:
                raise SignatureExpired(
                    f"Signature age {age} > {max_age} seconds",
                    payload=value,
                    date_signed=signed_at,
                )
        return (value, signed_at) if return_timestamp else value


class SessionMiddleware(_StarletteSessionMiddleware):
    """Starlette 세션 미들웨어 — 검사기만 바꿔 끼운다 (INFRA 5장, #17)."""

    def __init__(self, app, secret_key, **kw) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app, secret_key=secret_key, **kw)
        self.signer = _ForwardOnlySigner(str(secret_key))


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
