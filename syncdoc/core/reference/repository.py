"""SYNC-DOM-002 4.3 — references 조회·저장. DB만 안다."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from syncdoc.core.reference.models import Reference
from syncdoc.core.spec.models import Document, Item


class ReferenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def from_document(self, document_id: int) -> list[Reference]:
        stmt = select(Reference).where(Reference.from_document_id == document_id)
        return list(self.session.scalars(stmt))

    def to_item(self, item_pk: int) -> list[Reference]:
        return list(self.session.scalars(select(Reference).where(Reference.to_item_id == item_pk)))

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
