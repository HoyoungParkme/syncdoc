"""routers/account — /auth/*. SYNC-API-001 3.1 · SYNC-SEQ-001#SEQ-8. AccountService만 부른다.

GET /auth/github/callback 은 없다 — AccountService.login_github 보류(MS-006 sync vs MS-009 async).
"""

import secrets

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from syncdoc.web import auth

router = APIRouter(tags=["auth"])


@router.get("/auth/github", status_code=302)
def github_start(
    request: Request, next_path: str = Query("/", alias="next", pattern=r"^/([^/].*)?$")
) -> RedirectResponse:
    """SYNC-API-001#GET/auth/github — state 생성 · 세션에 next·state 저장 · 302 GitHub 동의 화면."""
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next_path
    return RedirectResponse(auth.authorize_url(state), status_code=302)


@router.post("/auth/logout", status_code=204)
def logout(request: Request) -> Response:
    """SYNC-API-001#POST/auth/logout — 세션 종료."""
    auth.logout(request)
    return Response(status_code=204)
