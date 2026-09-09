"""SYNC-DOM-002 2.3 참조 — Reference. 테이블은 SYNC-DOM-003#references.

to_item_id·to_document_id는 CHECK로 하나만. is_missing=true면 둘 다 null(DOM-003 설계 규칙).
"""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, false
from sqlalchemy.orm import Mapped, mapped_column

from syncdoc.db import Base


class Reference(Base):
    """SYNC-DOM-002#Reference"""

    __tablename__ = "references"
    __table_args__ = (
        CheckConstraint(
            "(is_missing AND to_item_id IS NULL AND to_document_id IS NULL) OR "
            "(NOT is_missing AND ((to_item_id IS NULL) <> (to_document_id IS NULL)))",
            name="ck_references_target",
        ),
        Index("ix_references_from_item_id", "from_item_id"),
        Index("ix_references_to_item_id", "to_item_id"),
        Index("ix_references_to_document_id", "to_document_id"),
        Index("ix_references_from_document_id", "from_document_id"),
        Index("ix_references_extracted_version_id", "extracted_version_id"),
        Index("ix_references_is_missing", "is_missing", postgresql_where="is_missing"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    from_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    to_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    to_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    raw_target: Mapped[str] = mapped_column(String(100))
    is_missing: Mapped[bool] = mapped_column(Boolean, server_default=false())
    extracted_version_id: Mapped[int] = mapped_column(ForeignKey("versions.id"))
