"""routers/git — SYNC-API-001 3.9. 서버 저장소의 git 입구(카드 BB, UC-H21).

git 스마트 HTTP를 이미지 안 git의 http-backend에 흘린다(`git.http_backend`). 인증은 HTTP Basic —
비밀번호 칸에 개인 토큰(MCP와 같은 것), 아이디 칸은 보지 않는다. 토큰이 없거나 틀리면 401과
WWW-Authenticate라 git이 다시 묻는다. 남의 것·GitHub 저장은 없는 것과 같은 404
(`ProjectService.server_origin`). push는 응답을 다 보낸 뒤 밀린 커밋을 곧바로 읽는다 — webhook과
같은 자리다(SEQ-29). 읽기가 실패해도 폴링이 메운다.
"""

from __future__ import annotations

import base64
import binascii
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.config import settings
from app.core import pipeline
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import NotFound, Unauthorized
from app.core.project.service import ProjectService
from app.db import get_session
from app.infra import git

router = APIRouter(prefix="/git", tags=["git"])
log = logging.getLogger(__name__)

# 요청 헤더 → CGI 변수. CONTENT_LENGTH는 요청에 있을 때만 — chunked면 비워야 본문을 끝까지 읽는다
_CGI_HEADERS = (
    ("content-type", "CONTENT_TYPE"),
    ("content-length", "CONTENT_LENGTH"),
    ("content-encoding", "HTTP_CONTENT_ENCODING"),  # gzip이면 그대로 — http-backend가 푼다
    ("git-protocol", "HTTP_GIT_PROTOCOL"),
)
_SERVICES = {"git-upload-pack", "git-receive-pack"}


def _token_user(request: Request, session: Session) -> User | None:
    """Basic의 비밀번호 칸이 개인 토큰이다. 아이디 칸은 보지 않는다 — 토큰이 사람을 정한다."""
    header = request.headers.get("authorization", "")
    if not header[:6].lower() == "basic ":
        return None
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    _, _, token = decoded.partition(":")
    return AccountService(session).authenticate_token(token) if token else None


def _challenge() -> Response:
    """401 + WWW-Authenticate — 없으면 git이 비밀번호를 묻지 않고 실패한다."""
    return JSONResponse(
        Unauthorized("git 입구 — 비밀번호 칸에 개인 토큰").to_dict(),
        status_code=401,
        media_type="application/problem+json",
        headers={"WWW-Authenticate": 'Basic realm="SyncDoc"'},
    )


async def _after_push(code: str, user: User) -> None:
    """push를 받은 뒤 밀린 커밋을 곧바로 읽는다(SEQ-29). 배치다 — 실패는 폴링이 메운다."""
    try:
        await pipeline.read_pending(code, user)
    except Exception:  # noqa: BLE001
        log.exception("git push 처리 실패 code=%s — 폴링이 메운다", code)


async def _serve(
    code: str, rest: str, request: Request, session: Session, after_push: bool = False
) -> Response:
    user = _token_user(request, session)
    if user is None:
        return _challenge()
    origin = ProjectService(session).server_origin(code, user)  # 남의 것·GitHub 저장 → 404
    env = {
        "REQUEST_METHOD": request.method,
        "PATH_INFO": f"/{origin.name}/{rest}",
        "QUERY_STRING": request.url.query,
        "REMOTE_USER": user.github_login,  # 비면 receive-pack이 403
        "REMOTE_ADDR": request.client.host if request.client else "",
    }
    for header, var in _CGI_HEADERS:
        if value := request.headers.get(header):
            env[var] = value
    cgi = await git.http_backend(settings.ORIGINS_DIR, env, request.stream())
    return StreamingResponse(
        cgi.body,
        status_code=cgi.status,
        headers=dict(cgi.headers),
        background=BackgroundTask(_after_push, code, user) if after_push else None,
    )


@router.get("/{code}.git/info/refs")
async def info_refs(
    code: str, request: Request, service: str = "", session: Session = Depends(get_session)
) -> Response:
    """SYNC-API-001#GET/git/{code}.git/info/refs"""
    if service not in _SERVICES:  # 옛 「dumb」 프로토콜은 받지 않는다
        raise NotFound("git-service", service or "-")
    return await _serve(code, "info/refs", request, session)


@router.post("/{code}.git/git-upload-pack")
async def upload_pack(
    code: str, request: Request, session: Session = Depends(get_session)
) -> Response:
    """SYNC-API-001#POST/git/{code}.git/git-upload-pack"""
    return await _serve(code, "git-upload-pack", request, session)


@router.post("/{code}.git/git-receive-pack")
async def receive_pack(
    code: str, request: Request, session: Session = Depends(get_session)
) -> Response:
    """SYNC-API-001#POST/git/{code}.git/git-receive-pack"""
    return await _serve(code, "git-receive-pack", request, session, after_push=True)
