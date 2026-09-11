"""routers/account — /auth/* · /api/me*. SYNC-API-001 3.1·3.7 · SEQ-8·C1. AccountService만."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import Unauthorized
from app.db import get_session
from app.web import auth
from app.web.schemas.account import AccessToken, AddEmail, CommitEmail, IssuedToken, IssueToken
from app.web.schemas.common import User as UserSchema

router = APIRouter(tags=["auth"])


@router.get("/auth/github", status_code=302)
async def github_start(
    request: Request, next_path: str = Query("/", alias="next", pattern=r"^/([^/].*)?$")
) -> RedirectResponse:
    """SYNC-API-001#GET/auth/github — state 생성 · 세션에 next·state 저장 · 302 GitHub 동의 화면."""
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next_path
    return RedirectResponse(auth.authorize_url(state, auth.callback_url(request)), status_code=302)


@router.get("/auth/github/callback", status_code=302)
async def github_callback(
    request: Request, code: str, state: str, session: Session = Depends(get_session)
) -> RedirectResponse:
    """SYNC-API-001#GET/auth/github/callback — state 대조 · login_github · 세션 · 302 next."""
    if not state or state != request.session.get("oauth_state"):
        raise Unauthorized("state 불일치")
    next_path = request.session.get("oauth_next") or "/"
    user = await AccountService(session).login_github(code, state, auth.callback_url(request))
    session.commit()  # 트랜잭션은 호출자(DEV-10)
    auth.login(request, user)
    return RedirectResponse(next_path, status_code=302)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request) -> Response:
    """SYNC-API-001#POST/auth/logout — 세션 종료."""
    auth.logout(request)
    return Response(status_code=204)


@router.get("/api/me", response_model=UserSchema)
async def me(user: User = Depends(auth.current_user)) -> UserSchema:
    """SYNC-API-001#GET/api/me"""
    return UserSchema.model_validate(user)


@router.get("/api/me/emails", response_model=list[CommitEmail])
async def list_emails(
    user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> list[CommitEmail]:
    """SYNC-API-001#GET/api/me/emails — UI-13 2.3"""
    return [CommitEmail.model_validate(e) for e in AccountService(session).commit_emails(user)]


@router.post("/api/me/emails", response_model=CommitEmail, status_code=201)
async def add_email(
    req: AddEmail,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> CommitEmail:
    """SYNC-API-001#POST/api/me/emails — 이미 내 것이면 그 행. 남의 것이면 409"""
    row = AccountService(session).add_commit_email(user, req.email)
    session.commit()
    return CommitEmail.model_validate(row)


@router.delete("/api/me/emails/{email_id}", status_code=204)
async def remove_email(
    email_id: int,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> Response:
    """SYNC-API-001#DELETE/api/me/emails/{id} — 남의 것이면 404"""
    AccountService(session).remove_commit_email(user, email_id)
    session.commit()
    return Response(status_code=204)


@router.get("/api/me/tokens", response_model=list[AccessToken])
async def list_tokens(
    user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> list[AccessToken]:
    """SYNC-API-001#GET/api/me/tokens — 폐기된 것 포함, 원문·해시 없음"""
    return [AccessToken.model_validate(t) for t in AccountService(session).list_tokens(user)]


@router.post("/api/me/tokens", response_model=IssuedToken, status_code=201)
async def issue_token(
    req: IssueToken,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> IssuedToken:
    """SYNC-API-001#POST/api/me/tokens — 원문은 이 응답에서만"""
    issued = AccountService(session).issue_token(user, req.label)
    session.commit()
    return IssuedToken(**AccessToken.model_validate(issued.token).model_dump(), token=issued.raw)


@router.delete("/api/me/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: int,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> Response:
    """SYNC-API-001#DELETE/api/me/tokens/{id}"""
    AccountService(session).revoke_token(user, token_id)
    session.commit()
    return Response(status_code=204)
