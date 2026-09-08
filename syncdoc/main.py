"""앱 조립. SYNC-DOM-002 1장 — web·mcp 라우터 마운트. SYNC-INFRA-001 4.1 경로 구분.

에러는 SYNC-STD-004#DEV-5 — Problem 예외 하나 = problem+json 타입 하나(SYNC-API-001 2장).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from syncdoc.config import settings
from syncdoc.core.errors import Problem
from syncdoc.web import auth
from syncdoc.web.routers import account

app = FastAPI(title="SyncDoc")
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
