"""SYNC-DOM-002 4.5 — comments 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from syncdoc.core.collab.models import Comment
from syncdoc.core.spec.models import Document


class CommentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def unresolved_of(self, document_id: int) -> list[Comment]:
        stmt = select(Comment).where(
            Comment.document_id == document_id, Comment.is_resolved.is_(False)
        )
        return list(self.session.scalars(stmt.order_by(Comment.id)))

    def current_version_no(self, document_id: int) -> int:
        stmt = select(Document.current_version_no).where(Document.id == document_id)
        return self.session.scalar(stmt) or 0

    def count_unresolved_in_project(self, project_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Comment)
            .join(Document, Document.id == Comment.document_id)
            .where(
                Document.project_id == project_id,
                Comment.parent_comment_id.is_(None),
                Comment.is_resolved.is_(False),
            )
        )
        return self.session.scalar(stmt) or 0

    def count_unresolved_by_document(self, document_ids: list[int]) -> dict[int, int]:
        if not document_ids:
            return {}
        stmt = (
            select(Comment.document_id, func.count())
            .where(
                Comment.document_id.in_(document_ids),
                Comment.parent_comment_id.is_(None),
                Comment.is_resolved.is_(False),
            )
            .group_by(Comment.document_id)
        )
        return {d: n for d, n in self.session.execute(stmt)}
