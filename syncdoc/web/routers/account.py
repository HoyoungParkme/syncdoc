"""routers/account — /auth/*. SYNC-API-001 3.1 · SYNC-SEQ-001#SEQ-8. AccountService만 부른다."""

import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from syncdoc.core.account.service import AccountService
from syncdoc.core.errors import Unauthorized
from syncdoc.db import get_session
from syncdoc.web import auth

router = APIRouter(tags=["auth"])


@router.get("/auth/github", status_code=302)
async def github_start(
    request: Request, next_path: str = Query("/", alias="next", pattern=r"^/([^/].*)?$")
) -> RedirectResponse:
    """SYNC-API-001#GET/auth/github — state 생성 · 세션에 next·state 저장 · 302 GitHub 동의 화면."""
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next_path
    return RedirectResponse(auth.authorize_url(state), status_code=302)


@router.get("/auth/github/callback", status_code=302)
async def github_callback(
    request: Request, code: str, state: str, session: Session = Depends(get_session)
) -> RedirectResponse:
    """SYNC-API-001#GET/auth/github/callback — state 대조 · login_github · 세션 · 302 next."""
    if not state or state != request.session.get("oauth_state"):
        raise Unauthorized("state 불일치")
    next_path = request.session.get("oauth_next") or "/"
    user = await AccountService(session).login_github(code, state)
    session.commit()  # 트랜잭션은 호출자(DEV-10)
    auth.login(request, user)
    return RedirectResponse(next_path, status_code=302)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request) -> Response:
    """SYNC-API-001#POST/auth/logout — 세션 종료."""
    auth.logout(request)
    return Response(status_code=204)
