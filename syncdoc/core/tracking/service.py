"""SYNC-MS-004 — TrackingService. flags·propagation_decisions만.

B1: raise_broken · raise_upstream · flags_for_items · count_flags · count_flags_by_document.
detect_impact는 스텁(빈 목록, CODE-001 B1 카드) — B3에서 해제.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.models import Flag
from syncdoc.core.tracking.repository import TrackingRepository
from syncdoc.core.types import FlagKind, FlagSummary


class TrackingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TrackingRepository(session)
        self.spec = SpecService(session)
        self.references = ReferenceService(session)

    def _assignee_of(self, target_pk: int) -> int | None:
        doc_id = self.repo.document_id_of_item(target_pk)
        la = self.spec.last_author(doc_id) if doc_id is not None else None
        return la.user_id if la else None

    def detect_impact(
        self,
        document_id: int,
        prev_version_id: int | None,
        new_version_id: int,
        changed_items: list[str] | None,
    ) -> list[int]:
        """SYNC-MS-004#TrackingService.detect_impact

        B1 스텁: 빈 목록(CODE-001 B1 카드). B3에서 해제.
        """
        return []

    def raise_broken(self, cause_item_pk: int) -> int:
        """SYNC-MS-004#TrackingService.raise_broken"""
        n = 0
        for ref in self.references.downstream(cause_item_pk):
            if ref.from_item_pk is None:
                continue
            self.repo.add(
                Flag(
                    kind=FlagKind.broken_ref,
                    target_item_id=ref.from_item_pk,
                    cause_item_id=cause_item_pk,
                    cause_version_id=None,
                    assignee_user_id=self._assignee_of(ref.from_item_pk),
                    raised_at=datetime.now(UTC),
                )
            )
            n += 1
        return n

    def raise_upstream(
        self,
        target_item_pks: list[int],
        cause_document_id: int,
        cause_version_id: int,
        cause_item_pk: int | None,
    ) -> int:
        """SYNC-MS-004#TrackingService.raise_upstream"""
        n = 0
        for target_pk in target_item_pks:
            if self.repo.has_unresolved_upstream(target_pk, cause_document_id):
                continue
            self.repo.add(
                Flag(
                    kind=FlagKind.upstream_impact,
                    target_item_id=target_pk,
                    cause_item_id=cause_item_pk,
                    cause_version_id=cause_version_id,
                    assignee_user_id=self._assignee_of(target_pk),
                    raised_at=datetime.now(UTC),
                )
            )
            n += 1
        return n

    def flags_for_items(self, item_pks: list[int]) -> dict[int, list[FlagSummary]]:
        """SYNC-MS-004#TrackingService.flags_for_items"""
        out: dict[int, list[FlagSummary]] = {}
        for f in self.repo.unresolved_for_items(item_pks):
            out.setdefault(f.target_item_id, []).append(
                FlagSummary(
                    id=f.id,
                    kind=f.kind,
                    target_item_pk=f.target_item_id,
                    cause_item_pk=f.cause_item_id,
                    cause_version_id=f.cause_version_id,
                    assignee_user_id=f.assignee_user_id,
                    raised_at=f.raised_at,
                    resolved_at=f.resolved_at,
                )
            )
        return out

    def count_flags(self, project_id: int) -> dict[str, int]:
        """SYNC-MS-004#TrackingService.count_flags"""
        counts = self.repo.count_by_kind(project_id)
        return {k: counts.get(k, 0) for k in ("needs_check", "broken_ref", "upstream_impact")}

    def count_flags_by_document(self, document_ids: list[int]) -> dict[int, dict[str, int]]:
        """SYNC-MS-004#TrackingService.count_flags_by_document"""
        return self.repo.count_by_document_kind(document_ids)
