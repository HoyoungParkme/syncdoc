"""SYNC-DOM-002 2.5 협업 — Comment. 테이블은 SYNC-DOM-003#comments."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from syncdoc.db import Base


class Comment(Base):
    """SYNC-DOM-002#Comment"""

    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_document_id_is_resolved", "document_id", "is_resolved"),
        Index("ix_comments_parent_comment_id", "parent_comment_id"),
        Index("ix_comments_author_user_id", "author_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    parent_comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"))
    line_no: Mapped[int]
    line_hash: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_resolved: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    original_location: Mapped[str | None] = mapped_column(String(50))
