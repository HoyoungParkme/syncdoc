"""SYNC-API-001 4장 — Comment(스레드) · CommentSummary · 요청 AddComment · Resolve."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from syncdoc.core.collab.models import Comment as CommentRow
from syncdoc.web.schemas.common import Base, UserRef


class Comment(Base):
    id: int
    doc_id: str
    line_no: int
    original_location: str | None
    body: str
    author: UserRef | None
    is_resolved: bool
    created_at: datetime
    replies: list[Comment] = []

    @classmethod
    def of(cls, c: CommentRow, doc_id: str, users: dict[int, UserRef]) -> Comment:
        return cls(
            id=c.id,
            doc_id=doc_id,
            line_no=c.line_no,
            original_location=c.original_location,
            body=c.body,
            author=users.get(c.author_user_id),
            is_resolved=c.is_resolved,
            created_at=c.created_at,
            replies=[cls.of(r, doc_id, users) for r in getattr(c, "replies", [])],
        )


class CommentSummary(Base):
    id: int
    doc_id: str
    line_no: int
    excerpt: str
    author: UserRef | None
    created_at: datetime


class AddComment(BaseModel):
    line_no: int = Field(ge=1)
    body: str
    parent_comment_id: int | None = None


class Resolve(BaseModel):
    resolved: bool = True
