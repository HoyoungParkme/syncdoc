"""SEQ-C2 — MCP 인증. Authorization: Bearer {raw} → AccountService.authenticate_token → User.

없음·폐기·만료면 401 problem+json(unauthorized). 어느 쪽이 틀렸는지 알려주지 않는다.
토큰 원문은 헤더에만 있고 로그·컨텍스트에 남기지 않는다(DEV-6) — 통과한 요청에는 user id만 둔다.
"""

from __future__ import annotations

import json

from app import db
from app.core.account.service import AccountService
from app.core.errors import Unauthorized
from app.mcp.tools import current_user_id


class BearerAuth:
    """ASGI 미들웨어 — mcp 앱 앞에 둔다."""

    def __init__(self, app, guard_prefix: str = "/mcp") -> None:
        self.app = app
        self.guard_prefix = guard_prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.guard_prefix):
            await self.app(scope, receive, send)
            return
        header = dict(scope.get("headers") or {}).get(b"authorization", b"").decode()
        raw = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        user_id = None
        if raw:
            with db.session_scope() as s:
                user = AccountService(s).authenticate_token(raw)
                user_id = user.id if user else None
        if user_id is None:
            body = json.dumps(
                Unauthorized("토큰 없음·폐기·만료").to_dict(), ensure_ascii=False
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/problem+json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        token = current_user_id.set(user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user_id.reset(token)
