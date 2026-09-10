"""SYNC-DOM-002 4.2 — documents·items·versions·status_changes 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.spec.models import Document, Item, StatusChange
from app.core.spec.models import Version as VersionRow


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

    def items_by_item_ids(self, document_id: int, item_ids: list[str]) -> list[Item]:
        if not item_ids:
            return []
        stmt = select(Item).where(
            Item.document_id == document_id, Item.item_id.in_(item_ids), Item.is_deleted.is_(False)
        )
        return list(self.session.scalars(stmt.order_by(Item.id)))

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

    def version_ids_by_user(self, ids: list[int], user_id: int) -> list[int]:
        if not ids:
            return []
        stmt = select(VersionRow.id).where(
            VersionRow.id.in_(ids),
            (VersionRow.instructed_by_user_id == user_id) | (VersionRow.author_user_id == user_id),
        )
        return list(self.session.scalars(stmt.order_by(VersionRow.id)))

    def documents_last_authored_by(self, user_id: int) -> list[Document]:
        """최근 버전의 author_user_id가 user_id인 문서. 쿼리 한 번."""
        latest = (
            select(VersionRow.document_id, func.max(VersionRow.version_no).label("no"))
            .group_by(VersionRow.document_id)
            .subquery()
        )
        stmt = (
            select(Document)
            .join(VersionRow, VersionRow.document_id == Document.id)
            .join(
                latest,
                (VersionRow.document_id == latest.c.document_id)
                & (VersionRow.version_no == latest.c.no),
            )
            .where(VersionRow.author_user_id == user_id)
            .order_by(Document.id)
        )
        return list(self.session.scalars(stmt))

    def versions_of(self, document_id: int) -> list[VersionRow]:
        stmt = select(VersionRow).where(VersionRow.document_id == document_id)
        return list(self.session.scalars(stmt.order_by(VersionRow.version_no.desc())))

    def status_changes_with_commit(self, document_id: int) -> list[StatusChange]:
        stmt = select(StatusChange).where(
            StatusChange.document_id == document_id, StatusChange.commit_hash.is_not(None)
        )
        return list(self.session.scalars(stmt.order_by(StatusChange.changed_at.desc())))

    def items_of_project(self, project_id: int) -> list[tuple[Item, Document]]:
        stmt = (
            select(Item, Document)
            .join(Document, Document.id == Item.document_id)
            .where(Document.project_id == project_id, Item.is_deleted.is_(False))
            .order_by(Document.doc_id, Item.id)
        )
        return [(i, d) for i, d in self.session.execute(stmt)]

    def delete_versions_of_project(self, project_id: int) -> int:
        doc_ids = select(Document.id).where(Document.project_id == project_id)
        return self.session.execute(
            delete(VersionRow).where(VersionRow.document_id.in_(doc_ids))
        ).rowcount

    def version_count(self, document_id: int) -> int:
        stmt = select(func.count()).where(VersionRow.document_id == document_id)
        return int(self.session.scalar(stmt) or 0)

    def version_bodies(self, document_id: int, nos: list[int]) -> dict[int, str]:
        stmt = select(VersionRow.version_no, VersionRow.body).where(
            VersionRow.document_id == document_id, VersionRow.version_no.in_(nos)
        )
        return {no: body for no, body in self.session.execute(stmt)}

    def versions_by_ids(self, ids: list[int]) -> list[VersionRow]:
        if not ids:
            return []
        return list(self.session.scalars(select(VersionRow).where(VersionRow.id.in_(ids))))

    def recent_versions(self, project_id: int, n: int) -> list[tuple[VersionRow, str]]:
        stmt = (
            select(VersionRow, Document.doc_id)
            .join(Document, Document.id == VersionRow.document_id)
            .where(Document.project_id == project_id)
            .order_by(VersionRow.created_at.desc(), VersionRow.id.desc())
            .limit(n)
        )
        return [(v, d) for v, d in self.session.execute(stmt)]

    def recent_status_changes(self, project_id: int, n: int) -> list[tuple[StatusChange, str]]:
        stmt = (
            select(StatusChange, Document.doc_id)
            .join(Document, Document.id == StatusChange.document_id)
            .where(Document.project_id == project_id, StatusChange.commit_hash.is_not(None))
            .order_by(StatusChange.changed_at.desc(), StatusChange.id.desc())
            .limit(n)
        )
        return [(c, d) for c, d in self.session.execute(stmt)]

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
