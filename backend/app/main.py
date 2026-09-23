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
from fastapi.responses import FileResponse, JSONResponse, Response
from mcp.server.transport_security import TransportSecuritySettings

from app import scheduler
from app.config import settings
from app.core.errors import Internal, Problem
from app.mcp.auth import BearerAuth
from app.mcp.tools import server as mcp_server
from app.web import auth
from app.web.auth import SessionMiddleware
from app.web.routers import account, admin, documents, hooks, projects, references

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


# 캐시 규칙 — 서버가 말하지 않으면 Cloudflare 기본값(4시간)과 브라우저 추측이 채워 배포 뒤에도
# 옛 화면이 떴다 (SYNC-INFRA-001 4.1, #124)
_BUNDLE = "public, max-age=31536000, immutable"  # 이름에 해시 — 내용이 바뀌면 이름이 바뀐다
_PLAIN = "public, max-age=3600"  # 이름이 안 바뀌는 파일(아이콘·사용 방법 그림)
_SHELL = "no-cache"  # 화면 틀 — 매번 새 판인지 묻는다. 같으면 304
_ASSETS = "assets/"  # Vite 기본 assetsDir. 빌드 설정을 바꾸면 여기도 바꾼다


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str) -> Response:
    """정적 파일이면 그것, 아니면 index.html(SPA). /api·/auth·/mcp는 위 라우트가 먼저."""
    if not STATIC.exists():
        raise Problem("React 빌드 결과가 없다 — frontend/에서 npm run build")
    target = STATIC / path
    found = bool(path) and target.is_file() and target.resolve().is_relative_to(STATIC)
    if path.startswith(_ASSETS):
        if found:
            return FileResponse(target, headers={"Cache-Control": _BUNDLE})
        # 번들 폴더에 없는 파일을 화면 틀로 떨어뜨리지 않는다 — 떨어뜨리면 배포 전에 열린 탭이
        # 옛 조각 대신 HTML을 스크립트로 읽다 깨지고, 그 HTML이 에지에 4시간 남았다
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    # 화면 틀은 주소로 직접 불러도(`/index.html`) 화면 틀이다 —
    # 한 시간 두면 배포가 한 시간 늦게 보인다
    if found and target.name != "index.html":
        return FileResponse(target, headers={"Cache-Control": _PLAIN})
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": _SHELL})
