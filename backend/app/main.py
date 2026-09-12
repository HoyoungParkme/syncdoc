"""앱 조립. SYNC-DOM-002 1장 — web·mcp 라우터 마운트. SYNC-INFRA-001 4.1 경로 구분.

에러는 SYNC-STD-004#DEV-5 — Problem 예외 하나 = problem+json 타입 하나(SYNC-API-001 2장).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from mcp.server.transport_security import TransportSecuritySettings

from app import scheduler
from app.config import settings
from app.core.errors import Internal, Problem
from app.mcp.auth import BearerAuth
from app.mcp.tools import server as mcp_server
from app.web import auth
from app.web.auth import SessionMiddleware
from app.web.routers import (
    account,
    admin,
    comments,
    decisions,
    documents,
    flags,
    hooks,
    projects,
    references,
    todo,
)

log = logging.getLogger(__name__)


class MCPMount:
    """streamable HTTP 앱은 lifespan마다 새로 만든다 — 세션 매니저는 한 번만 run() 된다."""

    def __init__(self) -> None:
        self.inner = None

    def build(self):
        # DNS rebinding 보호는 끈다 — 터널 뒤 고정 도메인이라 Host가 127.0.0.1이 아니다.
        # 접근 통제는 Bearer(SEQ-C2)
        self.inner = mcp_server.streamable_http_app(
            streamable_http_path="/mcp",
            stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )

    async def __call__(self, scope, receive, send) -> None:
        if self.inner is None:
            self.build()
        await self.inner(scope, receive, send)


mcp_mount = MCPMount()


@asynccontextmanager
async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
    mcp_mount.build()
    # SPA 대체 라우트(/{path})는 맨 뒤여야 한다 — 기동 시점에 뒤로 보낸다
    routes = app_.router.routes
    spa_routes = [r for r in routes if getattr(r, "name", "") == "spa"]
    for r in spa_routes:
        routes.remove(r)
        routes.append(r)
    async with mcp_server.session_manager.run():
        tasks: list[asyncio.Task] = []
        if settings.POLL_INTERVAL_SECONDS > 0:  # INFRA 7장 — 기동 시 따라잡기(1a) + 폴링(1b)
            tasks.append(asyncio.create_task(scheduler.catch_up()))
            tasks.append(asyncio.create_task(scheduler.poll_loop(settings.POLL_INTERVAL_SECONDS)))
        # 폴링과 별도 if — 하나를 끄고 다른 하나를 볼 수 있어야 한다.
        # 기동 시 한 번은 없다 (INFRA 6.1)
        if settings.BACKUP_INTERVAL_SECONDS > 0:
            tasks.append(
                asyncio.create_task(scheduler.backup_loop(settings.BACKUP_INTERVAL_SECONDS))
            )
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()


app = FastAPI(title="SyncDoc", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,  # 토큰 암호화 키와 나눈다 (INFRA 5.1)
    session_cookie=auth.SESSION_COOKIE,
    same_site="lax",
)
app.include_router(account.router)
for r in (
    projects.router,
    documents.router,
    references.router,
    comments.router,
    todo.router,
    flags.router,
    decisions.router,
    admin.router,
    hooks.router,
):
    app.include_router(r)


@app.exception_handler(Problem)
async def problem_handler(_: Request, exc: Problem) -> JSONResponse:
    return JSONResponse(
        exc.to_dict(), status_code=exc.status, media_type="application/problem+json"
    )


# SYNC-API-001 2장 — 표에 없는 예외도 problem+json으로 나간다.
# 클라이언트가 problem+json을 전제로 파싱하므로 평문 500이 나가면 오류를 읽지도 못한다.
@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled %s %s", request.method, request.url.path, exc_info=exc)
    problem = Internal()
    return JSONResponse(
        problem.to_dict(), status_code=problem.status, media_type="application/problem+json"
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# /mcp — SYNC-INFRA-001 4.1 경로 · SEQ-C2 Bearer 인증. 정확 경로 Route라 다른 라우트와 순서 무관
app.add_route("/mcp", BearerAuth(mcp_mount), methods=["GET", "POST", "DELETE"])


# `/` 및 정적 — React 빌드 결과(SYNC-INFRA-001 4.1).
# frontend/ → `npm run build` → backend/app/web/static. 없으면 API만
STATIC = Path(__file__).resolve().parent / "web" / "static"


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str) -> FileResponse:
    """정적 파일이면 그것, 아니면 index.html(SPA). /api·/auth·/mcp는 위 라우트가 먼저."""
    if not STATIC.exists():
        raise Problem("React 빌드 결과가 없다 — frontend/에서 npm run build")
    target = STATIC / path
    if path and target.is_file() and target.resolve().is_relative_to(STATIC):
        return FileResponse(target)
    return FileResponse(STATIC / "index.html")
