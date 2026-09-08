"""앱 조립. SYNC-DOM-002 1장 — web·mcp 라우터 마운트. SYNC-INFRA-001 4.1 경로 구분.

에러는 SYNC-STD-004#DEV-5 — Problem 예외 하나 = problem+json 타입 하나(SYNC-API-001 2장).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.sessions import SessionMiddleware

from syncdoc.config import settings
from syncdoc.core.errors import Problem
from syncdoc.mcp.auth import BearerAuth
from syncdoc.mcp.tools import server as mcp_server
from syncdoc.web import auth
from syncdoc.web.routers import account


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
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    mcp_mount.build()
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="SyncDoc", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie=auth.SESSION_COOKIE,
    same_site="lax",
)
app.include_router(account.router)


@app.exception_handler(Problem)
async def problem_handler(_: Request, exc: Problem) -> JSONResponse:
    return JSONResponse(
        exc.to_dict(), status_code=exc.status, media_type="application/problem+json"
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# /mcp — SYNC-INFRA-001 4.1 경로 · SEQ-C2 Bearer 인증. 정확 경로 Route라 다른 라우트와 순서 무관
app.add_route("/mcp", BearerAuth(mcp_mount), methods=["GET", "POST", "DELETE"])
