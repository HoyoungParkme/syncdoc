"""SYNC-DOM-002 4.2 — documents·items·versions·status_changes 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from syncdoc.core.spec.models import Document, Item, StatusChange
from syncdoc.core.spec.models import Version as VersionRow


class SpecRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # documents
    def document_by_doc_id(self, doc_id: str) -> Document | None:
        return self.session.scalar(select(Document).where(Document.doc_id == doc_id))

    def document_by_id(self, document_id: int) -> Document | None:
        return self.session.get(Document, document_id)

    def documents_by_ids(self, ids: list[int]) -> list[Document]:
        if not ids:
            return []
        return list(self.session.scalars(select(Document).where(Document.id.in_(ids))))

    def documents_of_project(self, project_id: int) -> list[Document]:
        stmt = select(Document).where(Document.project_id == project_id)
        return list(self.session.scalars(stmt))

    def max_doc_number(self, project_id: int, doc_type: str) -> int:
        stmt = select(Document.doc_id).where(
            Document.project_id == project_id, Document.doc_type == doc_type
        )
        return max((int(d.rsplit("-", 1)[1]) for d in self.session.scalars(stmt)), default=0)

    def add(self, row: Document | Item | VersionRow | StatusChange) -> None:
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

    def items_with_doc_id(self, pks: list[int]) -> list[tuple[Item, str]]:
        if not pks:
            return []
        stmt = (
            select(Item, Document.doc_id)
            .join(Document, Document.id == Item.document_id)
            .where(Item.id.in_(pks))
        )
        return [(i, d) for i, d in self.session.execute(stmt)]

    # versions
    def latest_version(self, document_id: int) -> VersionRow | None:
        stmt = (
            select(VersionRow)
            .where(VersionRow.document_id == document_id)
            .order_by(VersionRow.version_no.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def versions_by_ids(self, ids: list[int]) -> list[VersionRow]:
        if not ids:
            return []
        return list(self.session.scalars(select(VersionRow).where(VersionRow.id.in_(ids))))

    def latest_versions(self, document_ids: list[int]) -> dict[int, VersionRow]:
        """문서마다 최근 버전 하나. 쿼리 한 번."""
        if not document_ids:
            return {}
        latest = (
            select(VersionRow.document_id, func.max(VersionRow.version_no).label("no"))
            .where(VersionRow.document_id.in_(document_ids))
            .group_by(VersionRow.document_id)
            .subquery()
        )
        stmt = select(VersionRow).join(
            latest,
            (VersionRow.document_id == latest.c.document_id)
            & (VersionRow.version_no == latest.c.no),
        )
        return {v.document_id: v for v in self.session.scalars(stmt)}
