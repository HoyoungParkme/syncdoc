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
    """SYNC-API-001 2장 — 앱 밖(GitHub)이 실패했다.

    424다. 502면 앞단 Cloudflare가 자기 오류 페이지로 덮어 reason이 사라진다 (#76).
    """

    type = "urn:syncdoc:push-failed"
    status = 424
    title = "push-failed"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, reason=reason)


class RepoCreateFailed(Problem):
    """SYNC-API-001 2장 — GitHub가 저장소를 안 만들어 줬다. PushFailed와 같은 이유로 424 (#76)."""

    type = "urn:syncdoc:repo-create-failed"
    status = 424
    title = "repo-create-failed"

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


class PreconditionUnmet(Problem):
    """DOM 셋의 순서 — 클래스 명세 ← API 문서, ERD ← 클래스 명세 (STD-001 2.6)."""

    type = "urn:syncdoc:precondition-unmet"
    status = 422
    title = "precondition-unmet"

    def __init__(self, requires: str, have: list[str]) -> None:
        super().__init__(f"먼저 있어야 한다: {requires}", requires=requires, have=have)


class DocumentHasHistory(Problem):
    """완전 삭제 문지기 (UC-H18 7) — 아직 가리키는 곳. 미존재 참조는 안 센다 (MS-007 purge 2)."""

    type = "urn:syncdoc:document-has-history"
    status = 409
    title = "document-has-history"

    def __init__(self, inbound_refs: list[str]) -> None:
        super().__init__("아직 가리키는 곳이 있어 완전히 지울 수 없다", inbound_refs=inbound_refs)


class DocumentDeletionNeedsConfirm(Problem):
    """휴지통 넣기 전 확인 (UC-A7 2~4). 끊어질 것을 담는다 — 막지 않는다."""

    type = "urn:syncdoc:document-deletion-needs-confirm"
    status = 409
    title = "document-deletion-needs-confirm"

    def __init__(
        self, doc_id: str, title: str, version_count: int, inbound_refs: list[str]
    ) -> None:
        super().__init__(
            "휴지통에 넣기는 사람 확인이 필요함",
            doc_id=doc_id,
            title=title,
            version_count=version_count,
            inbound_refs=inbound_refs,
        )


class DocumentTrashed(Problem):
    """휴지통에 있는 문서 — 저장·상태 변경·다시 넣기 불가. 되살린 뒤에 (UC-A7 1a)."""

    type = "urn:syncdoc:document-trashed"
    status = 409
    title = "document-trashed"

    def __init__(self, trashed_at: str) -> None:
        super().__init__("휴지통에 있는 문서", trashed_at=trashed_at)


class DocumentNotTrashed(Problem):
    """휴지통에 없는 문서를 되살리거나 완전히 지우려 함 (UC-A8 1a)."""

    type = "urn:syncdoc:document-not-trashed"
    status = 409
    title = "document-not-trashed"

    def __init__(self) -> None:
        super().__init__("휴지통에 없는 문서")


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

    def __init__(self, card: str) -> None:
        super().__init__(f"{card}: 아직 구현되지 않음", card=card)


class StatusBlocked(Problem):
    type = "urn:syncdoc:status-blocked"
    status = 409
    title = "status-blocked"

    def __init__(self, convention_error_detail: str | None, warnings: list[str]) -> None:
        super().__init__(
            "규약 오류 또는 미완성 문서는 완료로 올릴 수 없음",
            convention_error_detail=convention_error_detail,
            warnings=warnings,
        )


class AlreadyCurrent(Problem):
    type = "urn:syncdoc:already-current"
    status = 422
    title = "already-current"

    def __init__(self) -> None:
        super().__init__("현재 버전으로는 되돌릴 수 없음")


class RebuildFailed(Problem):
    type = "urn:syncdoc:rebuild-failed"
    status = 500
    title = "rebuild-failed"

    def __init__(self, reason: str) -> None:
        super().__init__("재구축 실패, 롤백됨", reason=reason)


class RepositoryAlreadyRegistered(Problem):
    type = "urn:syncdoc:repository-already-registered"
    status = 409
    title = "repository-already-registered"

    def __init__(self, code: str) -> None:
        super().__init__(f"{code} 프로젝트가 이미 쓰는 저장소", code=code)


class EmailTaken(Problem):
    """SYNC-API-001 2장 — 남이 이미 등록한 커밋 이메일.

    이메일 하나는 사람 하나여야 user_for_commit이 답을 하나로 낸다.
    """

    type = "urn:syncdoc:email-taken"
    status = 409
    title = "email-taken"

    def __init__(self, email: str) -> None:
        super().__init__(f"{email}은 다른 사람이 이미 등록했다", email=email)


class AttachmentType(Problem):
    """SYNC-API-001 2장 — 받지 않는 파일 종류 (UC-H19 1b, 카드 AR)."""

    type = "urn:syncdoc:attachment-type"
    status = 415
    title = "attachment-type"

    def __init__(self, mime: str) -> None:
        super().__init__(f"받지 않는 종류: {mime}", mime=mime)


class AttachmentTooLarge(Problem):
    """SYNC-API-001 2장 — 상한 초과. 이미지 10MB, 글자·PDF 1MB (UC-H19 1b)."""

    type = "urn:syncdoc:attachment-too-large"
    status = 413
    title = "attachment-too-large"

    def __init__(self, limit: int, size: int) -> None:
        super().__init__(f"너무 큽니다: {size}B > {limit}B", limit=limit, size=size)


class AttachmentLimit(Problem):
    """SYNC-API-001 2장 — 아직 안 보낸 첨부가 이미 8개 (UC-H19 1b)."""

    type = "urn:syncdoc:attachment-limit"
    status = 409
    title = "attachment-limit"

    def __init__(self, limit: int) -> None:
        super().__init__(f"한 질문에 {limit}개까지", limit=limit)


class AttachmentSent(Problem):
    """SYNC-API-001 3.5 — 이미 보낸 첨부는 턴의 일부라 못 뺀다."""

    type = "urn:syncdoc:attachment-sent"
    status = 409
    title = "attachment-sent"

    def __init__(self, attachment_id: int) -> None:
        super().__init__("이미 보낸 첨부는 뺄 수 없다", attachment_id=attachment_id)


class LlmNotConfigured(Problem):
    """SYNC-API-001 2장 — 모델 키가 없다. 읽는 중 질의가 꺼져 있다 (UC-H19 2a)."""

    type = "urn:syncdoc:llm-not-configured"
    status = 503
    title = "llm-not-configured"

    def __init__(self) -> None:
        super().__init__("모델 키가 없다 — 읽는 중 질의가 꺼져 있다")


class LlmUnavailable(Problem):
    """SYNC-API-001 2장 — 모델 호출 실패. 사용량 초과도 여기 접힌다 (UC-H19 4a)."""

    type = "urn:syncdoc:llm-unavailable"
    status = 424  # 앱 밖(모델) 실패 — PushFailed와 같은 규칙 (#76)
    title = "llm-unavailable"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, reason=reason)


class InvalidRequest(Problem):
    """SYNC-API-001 2장 — 요청 본문·쿼리·경로 값이 정의에 안 맞다(입력 검증).

    FastAPI가 먼저 잡는 것을 처리기가 바꿔 낸다 — 전에는 `{"detail": […]}`로 새어 화면이
    상태 문구만 보였다 (#158).
    """

    type = "urn:syncdoc:invalid-request"
    status = 422
    title = "invalid-request"

    def __init__(self, errors: list[dict[str, str]]) -> None:
        first = errors[0] if errors else {"loc": "", "msg": "입력이 정의에 맞지 않습니다"}
        super().__init__(
            f"{first['loc']} — {first['msg']}" if first["loc"] else first["msg"], errors=errors
        )


class MethodNotAllowed(Problem):
    """SYNC-API-001 2장 — 경로는 있는데 그 메서드는 없다. `allow`는 그 경로의 라우트 전부 (#158)."""

    type = "urn:syncdoc:method-not-allowed"
    status = 405
    title = "method-not-allowed"

    def __init__(self, method: str, allow: list[str]) -> None:
        super().__init__(f"이 경로에 {method} 메서드는 없습니다", allow=allow)


class HttpError(Problem):
    """SYNC-API-001 2장 — 위 어느 것도 아닌 프레임워크 HTTP 오류.

    `about:blank` + 상태 문구(RFC 9457) (#158).
    """

    type = "about:blank"

    def __init__(self, status: int, title: str) -> None:
        self.status = status
        self.title = title
        super().__init__(None)


class Internal(Problem):
    """SYNC-API-001 2장 — 표에 없는 예외. 포괄 핸들러가 만든다.

    detail은 고정 문구다. 예외 종류·메시지·스택은 로그로만 보낸다 — 본문에 실으면
    내부 구조가 그대로 새어 나간다.
    """

    type = "urn:syncdoc:internal"
    status = 500
    title = "internal"

    def __init__(self) -> None:
        super().__init__("서버에서 처리하지 못한 오류입니다. 로그를 확인하세요.")


class CodeGraphFailed(Exception):
    """코드 그래프를 못 만들었다 — SYNC-MS-011·MS-009 graphify.extract. problem 타입이 아니다.

    그래프 만들기는 사람이 기다리지 않는 배치라(UC-S8) HTTP로 나가지 않는다. 받는 곳은
    pipeline.build_code_graph 하나이고, 이유를 code_graphs.error에 남긴다.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
