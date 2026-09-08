"""SYNC-STD-004#DEV-5 — problem+json 타입 하나에 예외 클래스 하나. SYNC-API-001 2장 에러 표와 1:1.

카드 A·B1이 던지는 것. 새 에러는 API 명세부터.
"""

from __future__ import annotations

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

    def __init__(self, resource: str, id: str | int, **extra: Any) -> None:
        super().__init__(f"{resource} {id} 없음", resource=resource, id=id, **extra)


class PushFailed(Problem):
    type = "urn:syncdoc:push-failed"
    status = 502
    title = "push-failed"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, reason=reason)


class ItemDeleted(Problem):
    type = "urn:syncdoc:item-deleted"
    status = 410
    title = "item-deleted"

    def __init__(self, deleted_at: Any) -> None:
        super().__init__("삭제된 항목", deleted_at=deleted_at)


class ConventionViolation(Problem):
    type = "urn:syncdoc:convention-violation"
    status = 422
    title = "convention-violation"

    def __init__(self, violations: list[Any], warnings: list[Any] | None = None) -> None:
        super().__init__(
            "규약 위반",
            violations=[
                v if isinstance(v, dict) else {"line": v.line, "rule": v.rule, "message": v.message}
                for v in violations
            ],
            warnings=[
                w if isinstance(w, dict) else {"rule": w.rule, "message": w.message}
                for w in warnings or []
            ],
        )


class VersionConflict(Problem):
    type = "urn:syncdoc:version-conflict"
    status = 409
    title = "version-conflict"

    def __init__(self, current_version: int, current_body: str) -> None:
        super().__init__("버전 불일치", current_version=current_version, current_body=current_body)


class ItemDeletionNeedsConfirm(Problem):
    type = "urn:syncdoc:item-deletion-needs-confirm"
    status = 409
    title = "item-deletion-needs-confirm"

    def __init__(self, deleted_items: list[dict[str, Any]]) -> None:
        super().__init__("항목 삭제에 하위 참조가 있음", deleted_items=deleted_items)


class ProjectCodeConflict(Problem):
    type = "urn:syncdoc:project-code-conflict"
    status = 409
    title = "project-code-conflict"

    def __init__(self, code: str) -> None:
        super().__init__(f"이미 쓰이는 코드 {code}", code=code)


class ProjectCodeInvalid(Problem):
    type = "urn:syncdoc:project-code-invalid"
    status = 422
    title = "project-code-invalid"

    def __init__(self, rule: str) -> None:
        super().__init__("프로젝트 코드 형식", rule=rule)


class ExistingSpecs(Problem):
    type = "urn:syncdoc:existing-specs"
    status = 409
    title = "existing-specs"

    def __init__(self, doc_count: int) -> None:
        super().__init__("docs/specs/가 이미 있음", doc_count=doc_count)


class NotImplementedYet(Problem):
    """CODE-001 B1 스텁 — 뒤 카드에서 해제되는 기능."""

    type = "urn:syncdoc:not-implemented"
    status = 501
    title = "not-implemented"

    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature}: 아직 구현되지 않음", feature=feature)
