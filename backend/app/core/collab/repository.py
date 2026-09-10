"""SYNC-DOM-002 4.5 — comments 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.collab.models import Comment
from app.core.spec.models import Document


class CommentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def all_of(self, document_id: int) -> list[Comment]:
        stmt = select(Comment).where(Comment.document_id == document_id)
        return list(self.session.scalars(stmt.order_by(Comment.created_at, Comment.id)))

    def by_id(self, comment_id: int) -> Comment | None:
        return self.session.get(Comment, comment_id)

    def add(self, row: Comment) -> Comment:
        self.session.add(row)
        self.session.flush()
        return row

    def unresolved_count_of(self, document_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Comment)
            .where(
                Comment.document_id == document_id,
                Comment.parent_comment_id.is_(None),
                Comment.is_resolved.is_(False),
            )
        )
        return self.session.scalar(stmt) or 0

    def unresolved_in(self, document_ids: list[int]) -> list[tuple[Comment, str, User]]:
        if not document_ids:
            return []
        stmt = (
            select(Comment, Document.doc_id, User)
            .join(Document, Document.id == Comment.document_id)
            .join(User, User.id == Comment.author_user_id)
            .where(Comment.document_id.in_(document_ids), Comment.is_resolved.is_(False))
            .order_by(Comment.created_at, Comment.id)
        )
        return [(c, d, u) for c, d, u in self.session.execute(stmt)]

    def unresolved_of(self, document_id: int) -> list[Comment]:
        stmt = select(Comment).where(
            Comment.document_id == document_id, Comment.is_resolved.is_(False)
        )
        return list(self.session.scalars(stmt.order_by(Comment.id)))

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
