"""SYNC-DOM-002 4.4 — flags·propagation_decisions 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from syncdoc.core.spec.models import Document, Item
from syncdoc.core.spec.models import Version as VersionRow
from syncdoc.core.tracking.models import Flag, PropagationDecision


class TrackingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, row: Flag | PropagationDecision) -> Flag | PropagationDecision:
        self.session.add(row)
        self.session.flush()
        return row

    def flag_by_id(self, flag_id: int) -> Flag | None:
        return self.session.get(Flag, flag_id)

    def decision_by_version(self, version_id: int) -> PropagationDecision | None:
        return self.session.scalar(
            select(PropagationDecision).where(PropagationDecision.version_id == version_id)
        )

    def undecided_version_ids(self) -> list[int]:
        stmt = (
            select(PropagationDecision.version_id)
            .where(PropagationDecision.choice == "undecided")
            .order_by(PropagationDecision.id)
        )
        return list(self.session.scalars(stmt))

    def has_unresolved(
        self, kind: str, target_pk: int, cause_pk: int | None, cause_version_id: int | None
    ) -> bool:
        stmt = select(Flag.id).where(
            Flag.kind == kind,
            Flag.target_item_id == target_pk,
            Flag.cause_item_id.is_(None) if cause_pk is None else Flag.cause_item_id == cause_pk,
            Flag.cause_version_id.is_(None)
            if cause_version_id is None
            else Flag.cause_version_id == cause_version_id,
            Flag.resolved_at.is_(None),
        )
        return self.session.scalar(stmt) is not None

    def unresolved_by_assignee(self, user_id: int) -> list[Flag]:
        stmt = select(Flag).where(Flag.assignee_user_id == user_id, Flag.resolved_at.is_(None))
        return list(self.session.scalars(stmt.order_by(Flag.raised_at, Flag.id)))

    def unresolved_unassigned(self) -> list[Flag]:
        stmt = select(Flag).where(Flag.assignee_user_id.is_(None), Flag.resolved_at.is_(None))
        return list(self.session.scalars(stmt.order_by(Flag.raised_at, Flag.id)))

    def unresolved_in_project(self, project_id: int, kind: str) -> list[Flag]:
        stmt = (
            select(Flag)
            .join(Item, Item.id == Flag.target_item_id)
            .join(Document, Document.id == Item.document_id)
            .where(Document.project_id == project_id, Flag.kind == kind, Flag.resolved_at.is_(None))
            .order_by(Flag.raised_at, Flag.id)
        )
        return list(self.session.scalars(stmt))

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
            .join(VersionRow, VersionRow.id == Flag.cause_version_id)
            .where(
                Flag.kind == "upstream_impact",
                Flag.target_item_id == target_pk,
                Flag.resolved_at.is_(None),
                VersionRow.document_id == cause_document_id,
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
