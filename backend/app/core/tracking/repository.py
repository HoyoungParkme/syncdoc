"""SYNC-DOM-002 4.4 — flags·propagation_decisions 조회·저장. DB만 안다."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.spec.models import Document, Item
from app.core.spec.models import Version as VersionRow
from app.core.tracking.models import Flag, PropagationDecision


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

    def unresolved_of_project(self, project_id: int) -> list[Flag]:
        """종류를 안 가린 열린 플래그. unresolved_in_project는 kind가 필수라 못 쓴다."""
        stmt = (
            select(Flag)
            .join(Item, Item.id == Flag.target_item_id)
            .join(Document, Document.id == Item.document_id)
            .where(Document.project_id == project_id, Flag.resolved_at.is_(None))
            .order_by(Flag.raised_at, Flag.id)
        )
        return list(self.session.scalars(stmt))

    def all_of_project(self, project_id: int) -> list[Flag]:
        """플래그 전량. 해제된 것도 준다 — 백업은 그때 있었던 사실이다 (#16)."""
        stmt = (
            select(Flag)
            .join(Item, Item.id == Flag.target_item_id)
            .join(Document, Document.id == Item.document_id)
            .where(Document.project_id == project_id)
            .order_by(Flag.id)
        )
        return list(self.session.scalars(stmt))

    def decisions_of_project(self, project_id: int) -> list[PropagationDecision]:
        """전파결정 전량. 결정된 것도 준다 (#16)."""
        doc_ids = select(Document.id).where(Document.project_id == project_id)
        version_ids = select(VersionRow.id).where(VersionRow.document_id.in_(doc_ids))
        stmt = select(PropagationDecision).where(PropagationDecision.version_id.in_(version_ids))
        return list(self.session.scalars(stmt.order_by(PropagationDecision.id)))

    def flag_exists(
        self,
        kind: str,
        target_item_id: int,
        cause_item_id: int | None,
        cause_version_id: int | None,
        raised_at: datetime,
    ) -> bool:
        """복원 멱등 판정. raised_at이 드는 이유는 SYNC-MS-004#restore_flags."""
        return (
            self.session.scalar(
                select(Flag.id).where(
                    Flag.kind == kind,
                    Flag.target_item_id == target_item_id,
                    Flag.cause_item_id.is_(cause_item_id)
                    if cause_item_id is None
                    else Flag.cause_item_id == cause_item_id,
                    Flag.cause_version_id.is_(cause_version_id)
                    if cause_version_id is None
                    else Flag.cause_version_id == cause_version_id,
                    Flag.raised_at == raised_at,
                )
            )
            is not None
        )

    def decisions_by_version_ids(self, version_ids: list[int]) -> list[PropagationDecision]:
        """주어진 버전 id에 매달린 전파 결정. 재구축 재연결용 (#38).

        **살아 있는 versions로 조인하면 안 된다** — 재연결 시점에는 옛 버전이 이미
        지워져 있어 하나도 안 잡힌다. 지우기 전에 뜬 id 목록으로 찾는다.
        """
        if not version_ids:
            return []
        stmt = select(PropagationDecision).where(PropagationDecision.version_id.in_(version_ids))
        return list(self.session.scalars(stmt.order_by(PropagationDecision.id)))

    def flags_with_cause_version(self, project_id: int) -> list[Flag]:
        """cause_version_id가 채워진 플래그 전부. 해제 여부를 안 가린다 — FK는 안 가린다."""
        stmt = (
            select(Flag)
            .join(Item, Item.id == Flag.target_item_id)
            .join(Document, Document.id == Item.document_id)
            .where(Document.project_id == project_id, Flag.cause_version_id.is_not(None))
            .order_by(Flag.id)
        )
        return list(self.session.scalars(stmt))

    def delete_rows(self, rows: list) -> None:
        for r in rows:
            self.session.delete(r)
        self.session.flush()

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
