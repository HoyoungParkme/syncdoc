"""SYNC-DOM-002 4.2 — documents·items·versions·status_changes 조회·저장. DB만 안다."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from syncdoc.core.spec.models import Document, Item, StatusChange, Version


class SpecRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # documents
    def document_by_doc_id(self, doc_id: str) -> Document | None:
        return self.session.scalar(select(Document).where(Document.doc_id == doc_id))

    def document_by_id(self, document_id: int) -> Document | None:
        return self.session.get(Document, document_id)

    def documents_of_project(self, project_id: int) -> list[Document]:
        stmt = select(Document).where(Document.project_id == project_id)
        return list(self.session.scalars(stmt))

    def max_doc_number(self, project_id: int, doc_type: str) -> int:
        stmt = select(Document.doc_id).where(
            Document.project_id == project_id, Document.doc_type == doc_type
        )
        return max((int(d.rsplit("-", 1)[1]) for d in self.session.scalars(stmt)), default=0)

    def add(self, row: Document | Item | Version | StatusChange) -> None:
        self.session.add(row)
        self.session.flush()

    # items
    def items_of(self, document_id: int, include_deleted: bool = False) -> list[Item]:
        stmt = select(Item).where(Item.document_id == document_id)
        if not include_deleted:
            stmt = stmt.where(Item.is_deleted.is_(False))
        return list(self.session.scalars(stmt.order_by(Item.id)))

    def item_of(self, document_id: int, item_id: str) -> Item | None:
        return self.session.scalar(
            select(Item).where(Item.document_id == document_id, Item.item_id == item_id)
        )

    def items_by_pks(self, pks: list[int]) -> list[Item]:
        if not pks:
            return []
        return list(self.session.scalars(select(Item).where(Item.id.in_(pks))))

    # versions
    def latest_version(self, document_id: int) -> Version | None:
        stmt = (
            select(Version)
            .where(Version.document_id == document_id)
            .order_by(Version.version_no.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def latest_versions(self, document_ids: list[int]) -> dict[int, Version]:
        """문서마다 최근 버전 하나. 쿼리 한 번."""
        if not document_ids:
            return {}
        latest = (
            select(Version.document_id, func.max(Version.version_no).label("no"))
            .where(Version.document_id.in_(document_ids))
            .group_by(Version.document_id)
            .subquery()
        )
        stmt = select(Version).join(
            latest,
            (Version.document_id == latest.c.document_id) & (Version.version_no == latest.c.no),
        )
        return {v.document_id: v for v in self.session.scalars(stmt)}
