"""SYNC-DOM-002 4.4 — flags·propagation_decisions 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from syncdoc.core.spec.models import Document, Item, Version
from syncdoc.core.tracking.models import Flag


class TrackingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, row: Flag) -> Flag:
        self.session.add(row)
        self.session.flush()
        return row

    def document_id_of_item(self, item_pk: int) -> int | None:
        return self.session.scalar(select(Item.document_id).where(Item.id == item_pk))

    def unresolved_for_items(self, item_pks: list[int]) -> list[Flag]:
        if not item_pks:
            return []
        stmt = select(Flag).where(Flag.target_item_id.in_(item_pks), Flag.resolved_at.is_(None))
        return list(self.session.scalars(stmt.order_by(Flag.id)))

    def has_unresolved_upstream(self, target_pk: int, cause_document_id: int) -> bool:
        stmt = (
            select(Flag.id)
            .join(Version, Version.id == Flag.cause_version_id)
            .where(
                Flag.kind == "upstream_impact",
                Flag.target_item_id == target_pk,
                Flag.resolved_at.is_(None),
                Version.document_id == cause_document_id,
            )
        )
        return self.session.scalar(stmt) is not None

    def count_by_kind(self, project_id: int) -> dict[str, int]:
        stmt = (
            select(Flag.kind, func.count())
            .join(Item, Item.id == Flag.target_item_id)
            .join(Document, Document.id == Item.document_id)
            .where(Document.project_id == project_id, Flag.resolved_at.is_(None))
            .group_by(Flag.kind)
        )
        return {k: n for k, n in self.session.execute(stmt)}

    def count_by_document_kind(self, document_ids: list[int]) -> dict[int, dict[str, int]]:
        if not document_ids:
            return {}
        stmt = (
            select(Item.document_id, Flag.kind, func.count())
            .join(Item, Item.id == Flag.target_item_id)
            .where(Item.document_id.in_(document_ids), Flag.resolved_at.is_(None))
            .group_by(Item.document_id, Flag.kind)
        )
        out: dict[int, dict[str, int]] = {}
        for doc_id, kind, n in self.session.execute(stmt):
            out.setdefault(doc_id, {})[kind] = n
        return out
