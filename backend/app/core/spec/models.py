"""SYNC-DOM-002 2.2 명세 — Document · Item · Version · StatusChange.

테이블은 SYNC-DOM-003#documents · #items · #versions · #status_changes. 인덱스는 DOM-003 3장.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Document(Base):
    """SYNC-DOM-002#Document"""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("current_version_no >= 1", name="ck_documents_version_no"),
        Index("ix_documents_project_id_doc_type", "project_id", "doc_type"),
        Index(
            "ix_documents_has_convention_error",
            "has_convention_error",
            postgresql_where="has_convention_error",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    doc_id: Mapped[str] = mapped_column(String(30), unique=True)
    doc_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))
    current_body: Mapped[str] = mapped_column(Text)
    current_version_no: Mapped[int]
    has_convention_error: Mapped[bool] = mapped_column(Boolean, server_default=false())
    convention_error_detail: Mapped[str | None] = mapped_column(Text)
    incomplete_warnings: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Item(Base):
    """SYNC-DOM-002#Item"""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("document_id", "item_id", name="uq_items_document_id_item_id"),
        Index("ix_items_document_id_is_deleted", "document_id", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    item_id: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str | None] = mapped_column(String(200))
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=false())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Version(Base):
    """SYNC-DOM-002#Version"""

    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_versions_document_id_version_no"),
        Index("ix_versions_document_id_version_no_desc", "document_id", text("version_no DESC")),
        Index("ix_versions_author_user_id_created_at", "author_user_id", "created_at"),
        Index("ix_versions_instructed_by_user_id", "instructed_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    version_no: Mapped[int]
    commit_hash: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    author_kind: Mapped[str] = mapped_column(String(10))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    instructed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    via: Mapped[str] = mapped_column(String(8))  # mcp | web | github — Author.via를 접은 것
    message: Mapped[str] = mapped_column(Text)  # 커밋 메시지 전문 사본 (DOM-003)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StatusChange(Base):
    """SYNC-DOM-002#StatusChange"""

    __tablename__ = "status_changes"
    __table_args__ = (
        Index("ix_status_changes_document_id_changed_at", "document_id", "changed_at"),
        Index("ix_status_changes_changed_by_user_id", "changed_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    from_status: Mapped[str | None] = mapped_column(String(10))
    to_status: Mapped[str] = mapped_column(String(10))
    changed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    commit_hash: Mapped[str | None] = mapped_column(String(40))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
