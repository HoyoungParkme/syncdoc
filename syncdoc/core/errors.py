"""SYNC-STD-004#DEV-5 — problem+json 타입 하나에 예외 클래스 하나. SYNC-API-001 2장 에러 표와 1:1.

카드 A가 던지는 것만: unauthorized · not-found · push-failed. 새 에러는 API 명세부터.
"""

from typing import Any


class Problem(Exception):
    type: str = "about:blank"
    status: int = 500
    title: str = "error"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": self.type, "title": self.title, "status": self.status}
        if self.detail:
            body["detail"] = self.detail
        body.update(self.extra)
        return body


class Unauthorized(Problem):
    type = "urn:syncdoc:unauthorized"
    status = 401
    title = "unauthorized"


class NotFound(Problem):
    type = "urn:syncdoc:not-found"
    status = 404
    title = "not-found"

    def __init__(self, resource: str, id: str | int) -> None:
        super().__init__(f"{resource} {id} 없음", resource=resource, id=id)


class PushFailed(Problem):
    type = "urn:syncdoc:push-failed"
    status = 502
    title = "push-failed"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, reason=reason)
