"""SYNC-DOM-002 4.3 — references 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from syncdoc.core.reference.models import Reference
from syncdoc.core.spec.models import Document, Item


class ReferenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def from_item(self, item_pk: int) -> list[Reference]:
        return list(
            self.session.scalars(select(Reference).where(Reference.from_item_id == item_pk))
        )

    def to_document_only(self, document_id: int) -> list[Reference]:
        stmt = select(Reference).where(
            Reference.to_document_id == document_id, Reference.to_item_id.is_(None)
        )
        return list(self.session.scalars(stmt))

    def from_document(self, document_id: int, include_missing: bool = True) -> list[Reference]:
        stmt = select(Reference).where(Reference.from_document_id == document_id)
        if not include_missing:
            stmt = stmt.where(Reference.is_missing.is_(False))
        return list(self.session.scalars(stmt.order_by(Reference.id)))

    def to_item(self, item_pk: int) -> list[Reference]:
        return list(self.session.scalars(select(Reference).where(Reference.to_item_id == item_pk)))

    def count_to_items(self, item_pks: list[int]) -> dict[int, int]:
        if not item_pks:
            return {}
        stmt = (
            select(Reference.to_item_id, func.count())
            .where(Reference.to_item_id.in_(item_pks))
            .group_by(Reference.to_item_id)
        )
        return {pk: n for pk, n in self.session.execute(stmt)}

    def document_id_of(self, doc_id: str) -> int | None:
        return self.session.scalar(select(Document.id).where(Document.doc_id == doc_id))

    def item_pk_of(self, document_id: int, item_id: str) -> int | None:
        return self.session.scalar(
            select(Item.id).where(
                Item.document_id == document_id, Item.item_id == item_id, Item.is_deleted.is_(False)
            )
        )

    def add(self, row: Reference) -> None:
        self.session.add(row)

    def delete(self, row: Reference) -> None:
        self.session.delete(row)
