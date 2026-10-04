"""GitHub OAuth·세션. SYNC-DOM-002 1장 web/auth.py · SYNC-SEQ-001#SEQ-8 · SYNC-INFRA-001 5장.

세션 = 서명 쿠키 `syncdoc_session`(SYNC-API-001 4장 securitySchemes). 세션 테이블은 없다(ERD 13개).
세션에는 github_login만 둔다 — 사용자 조회는 AccountService.user_by_login(MS-006).

폐쇄망판(PRD R15)은 세션이 없다 — 모든 웹 요청이 로컬 사용자이고, 대신 어디서 부르는지를 본다
(`ClosedEditionGuard`, SEQ-C3).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import TimestampSigner
from itsdangerous.exc import SignatureExpired
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.middleware.sessions import SessionMiddleware as _StarletteSessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import ForbiddenOrigin, NotFound, Problem, Unauthorized
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
    """GitHub 동의 화면 주소.

    scope=repo + admin:repo_hook (인프라 5장·7장) · redirect_uri(SEQ-8).
    """
    q = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            # repo는 비공개 저장소를 만들고 읽기 위한 것이다 (INFRA 5장, #310). admin:repo_hook은
            # push 통지를 걸기 위한 것(INFRA 7장, 카드 AF). 범위를 넓히기 전에 받은 토큰은 다음
            # 로그인까지 옛 범위로 남는다
            "scope": "repo admin:repo_hook",
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
    """라우터 의존성. 세션 없거나 사용자 없으면 401 unauthorized(API-001 1장).

    폐쇄망판은 세션 없이 로컬 사용자다(SEQ-C3). 켜질 때 만들었으니 보통은 읽기만 하고,
    없어서 방금 만들었으면 남도록 커밋한다.
    """
    if settings.closed:
        user = AccountService(session).local_user()
        session.commit()
        return user
    login_ = request.session.get("login")
    user = AccountService(session).user_by_login(login_) if login_ else None
    if user is None:
        raise Unauthorized("세션 없음")
    if not settings.login_allowed(user.github_login):
        request.session.clear()  # 허용 목록에서 뺀 사람의 세션은 비운다 (카드 BP)
        raise Unauthorized("허용되지 않은 계정")
    return user


# ───────────────────────── 폐쇄망판 가드 (SEQ-C3) ─────────────────────────

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_TOKEN_PATHS = ("/mcp", "/git/")  # 토큰이 사람을 정한다 — Origin을 보지 않는다 (SEQ-C2·29)
_GITHUB_PATHS = ("/auth/github", "/hooks/github")  # 폐쇄망판에는 없다 (API-001 1장)


def _hostname(netloc: str) -> str:
    """Host 헤더·주소의 netloc → 이름만(포트 없이, 소문자). `[::1]:8000` → `::1`."""
    try:
        return (urlsplit(f"//{netloc.strip()}").hostname or "").lower()
    except ValueError:  # 대괄호가 짝이 안 맞는 따위 — 허용 목록에 없는 것과 같다
        return ""


def _public_netloc() -> str:
    return urlsplit(settings.PUBLIC_BASE_URL.strip()).netloc.lower()


def allowed_host(host: str) -> bool:
    """허용 목록 — 127.0.0.1·localhost·[::1]과 PUBLIC_BASE_URL의 host (INFRA 5장)."""
    name = _hostname(host)
    return bool(name) and (name in _LOCAL_HOSTS or name == _hostname(_public_netloc()))


def same_origin(origin: str, host: str) -> bool:
    """Origin이 이 서버인가 — 요청 Host와 같은 곳이거나 PUBLIC_BASE_URL."""
    netloc = urlsplit(origin.strip()).netloc.lower()
    return bool(netloc) and netloc in {host.strip().lower(), _public_netloc()}


class ClosedEditionGuard:
    """폐쇄망판 웹 요청 가드 — SYNC-SEQ-001#SEQ-C3 (카드 BC).

    로그인이 없으니 누가가 아니라 어디서 부르는지를 본다. Host가 허용 목록 밖이면(DNS rebinding)
    403, 쓰기 요청의 Origin이 다른 곳이면(CSRF — 본문 없는 POST는 미리 묻는 요청도 없다) 403,
    GitHub 로그인·통지 경로는 404, 로그인 화면(UI-1)은 목록(UI-2)으로 보낸다(UI-001 2장).
    인터넷판에서는 그대로 지나간다. 순수 ASGI라 스트리밍 응답과 응답 뒤 작업(git push 처리)을
    건드리지 않는다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.closed:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        host, path = headers.get("host", ""), scope.get("path", "")
        refusal: Problem | None = None
        if not allowed_host(host):
            refusal = ForbiddenOrigin(host=host)
        elif (
            scope.get("method", "GET") in _UNSAFE
            and (origin := headers.get("origin")) is not None
            and not path.startswith(_TOKEN_PATHS)
            and not same_origin(origin, host)
        ):
            refusal = ForbiddenOrigin(origin=origin)
        elif path.startswith(_GITHUB_PATHS):
            refusal = NotFound("path", path)
        elif path == "/login":
            await RedirectResponse("/", status_code=302)(scope, receive, send)
            return
        if refusal is None:
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            refusal.to_dict(), status_code=refusal.status, media_type="application/problem+json"
        )
        await response(scope, receive, send)
