"""SYNC-MS-004 — TrackingService. flags·propagation_decisions만.

변경 영향 감지는 SpecService.diff·ReferenceService.downstream을 직접 부른다(DOM-002 3.2 예외).
B1: raise_broken · raise_upstream · flags_for_items · count_flags*. B3: 나머지 11개.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.errors import AlreadyDecided, AlreadyResolved, NotFound, ReasonRequired
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.tracking.models import Flag, PropagationDecision
from app.core.tracking.repository import TrackingRepository
from app.core.types import DecisionResult, FlagKind, FlagSummary, ItemRef, Propagation


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
        """SYNC-MS-004#TrackingService.detect_impact"""
        if prev_version_id is None:
            return []  # 신규 문서 (UC-S3 1a)
        doc_id = self.spec.describe_documents([document_id])[document_id].doc_id
        if changed_items is not None:
            changed = changed_items
        else:
            vb = self.spec.versions_by_ids([prev_version_id, new_version_id])
            d = self.spec.diff(
                doc_id, vb[prev_version_id].version_no, vb[new_version_id].version_no
            )
            changed = [h.item_id for h in d.hunks if h.item_id]  # 공백만 바뀐 건 hunk가 없다
        if not changed:
            return []
        pks = self.spec.resolve_items(doc_id, changed)
        affected: set[int] = set()
        for pk in pks:
            affected.update(
                e.from_item_pk for e in self.references.downstream(pk) if e.from_item_pk
            )
        affected.update(
            e.from_item_pk
            for e in self.references.downstream_of_document(document_id)
            if e.from_item_pk
        )
        return sorted(affected - set(pks))  # 원인 항목은 대상이 아니다

    def create_pending(
        self, version_id: int, affected_pks: list[int], changed_pks: list[int]
    ) -> int:
        """SYNC-MS-004#TrackingService.create_pending"""
        row = PropagationDecision(
            version_id=version_id,
            choice=Propagation.undecided,
            affected_pks=affected_pks,
            changed_pks=changed_pks,
        )
        self.repo.add(row)
        return row.id

    def get_decision(self, version_id: int) -> PropagationDecision:
        """SYNC-MS-004#TrackingService.get_decision"""
        row = self.repo.decision_by_version(version_id)
        if row is None:
            raise NotFound("decision", version_id)
        return row

    def record_decision(
        self, version_id: int, choice: Propagation, reason: str | None, user: User
    ) -> DecisionResult:
        """SYNC-MS-004#TrackingService.record_decision"""
        dec = self.get_decision(version_id)
        if dec.choice != Propagation.undecided:
            raise AlreadyDecided(dec.choice, dec.decided_at.isoformat() if dec.decided_at else None)
        if choice == Propagation.skip and not reason:
            raise ReasonRequired()
        dec.choice, dec.reason = str(choice), reason
        dec.decided_by_user_id, dec.decided_at = user.id, datetime.now(UTC)
        self.session.flush()
        n = (
            self.raise_flags(version_id, list(dec.affected_pks))
            if choice == Propagation.propagate
            else 0
        )
        return DecisionResult(choice=str(choice), flags_raised=n)

    def raise_flags(self, version_id: int, target_item_pks: list[int]) -> int:
        """SYNC-MS-004#TrackingService.raise_flags"""
        changed = set(self.get_decision(version_id).changed_pks)
        n = 0
        for target_pk in target_item_pks:
            causes = [
                e.to_item_pk for e in self.references.upstream(target_pk) if e.to_item_pk in changed
            ]
            assignee = self._assignee_of(target_pk)
            for cause_pk in causes or [
                None
            ]:  # 원인 하나에 플래그 하나. 문서 단위 참조면 원인 항목 없음
                if self.repo.has_unresolved(FlagKind.needs_check, target_pk, cause_pk, version_id):
                    continue
                self.repo.add(
                    Flag(
                        kind=FlagKind.needs_check,
                        target_item_id=target_pk,
                        cause_item_id=cause_pk,
                        cause_version_id=version_id,
                        assignee_user_id=assignee,
                        raised_at=datetime.now(UTC),
                    )
                )
                n += 1
        return n

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

    def get_flag(self, flag_id: int) -> Flag:
        """SYNC-MS-004#TrackingService.get_flag"""
        f = self.repo.flag_by_id(flag_id)
        if f is None:
            raise NotFound("flag", flag_id)
        return f

    def resolve(self, flag_id: int, user: User, target_changed: bool) -> FlagSummary:
        """SYNC-MS-004#TrackingService.resolve"""
        f = self.get_flag(flag_id)
        if f.resolved_at is not None:
            raise AlreadyResolved(f.resolved_at.isoformat())
        f.resolved_by_user_id, f.resolved_at, f.resolved_with_edit = (
            user.id,
            datetime.now(UTC),
            target_changed,
        )
        self.session.flush()
        names = self.spec.describe_items(
            [f.target_item_id] + ([f.cause_item_id] if f.cause_item_id else [])
        )
        vb = self.spec.versions_by_ids([f.cause_version_id] if f.cause_version_id else [])
        return FlagSummary(
            id=f.id,
            kind=f.kind,
            target=names.get(f.target_item_id) or ItemRef(None, None, None),
            cause=names.get(f.cause_item_id) if f.cause_item_id else None,
            cause_version_no=vb[f.cause_version_id].version_no
            if f.cause_version_id in vb
            else None,
            assignee=None,  # UserRef는 라우터가 users_by_ids로 (assignee_id)
            raised_at=f.raised_at,
            resolved_at=f.resolved_at,
            assignee_id=f.assignee_user_id,
        )

    def flags_for_items(self, item_pks: list[int]) -> dict[int, list[Flag]]:
        """SYNC-MS-004#TrackingService.flags_for_items"""
        out: dict[int, list[Flag]] = {}
        for f in self.repo.unresolved_for_items(item_pks):
            out.setdefault(f.target_item_id, []).append(f)
        return out

    def flags_for_assignee(self, user_id: int) -> tuple[list[Flag], list[Flag], list[Flag]]:
        """SYNC-MS-004#TrackingService.flags_for_assignee"""
        rows = self.repo.unresolved_by_assignee(user_id)
        return tuple([f for f in rows if f.kind == k] for k in FlagKind)  # type: ignore[return-value]

    def flags_unassigned(self) -> list[Flag]:
        """SYNC-MS-004#TrackingService.flags_unassigned"""
        return self.repo.unresolved_unassigned()

    def flags_in_project(self, project_id: int, kind: FlagKind) -> list[Flag]:
        """SYNC-MS-004#TrackingService.flags_in_project"""
        return self.repo.unresolved_in_project(project_id, str(kind))

    def count_flags(self, project_id: int) -> dict[str, int]:
        """SYNC-MS-004#TrackingService.count_flags"""
        counts = self.repo.count_by_kind(project_id)
        return {k: counts.get(k, 0) for k in ("needs_check", "broken_ref", "upstream_impact")}

    def count_flags_by_document(self, document_ids: list[int]) -> dict[int, dict[str, int]]:
        """SYNC-MS-004#TrackingService.count_flags_by_document"""
        return self.repo.count_by_document_kind(document_ids)

    def reassign_open_flags(self, project_id: int) -> int:
        """SYNC-MS-004#TrackingService.reassign_open_flags

        재구축은 git을 진실로 삼아 versions를 다시 만든다. assignee_user_id는
        거기서 파생된 값인데 플래그를 만들 때 한 번만 계산되고 다시 계산되지
        않는다 — clear_index는 flags를 남기므로, 이게 없으면 재구축이 절반만
        끝난다(#34). 해제된 플래그는 그때의 사실이라 안 건드린다.
        """
        changed = 0
        for f in self.repo.unresolved_of_project(project_id):
            a = self._assignee_of(f.target_item_id)
            if a != f.assignee_user_id:
                f.assignee_user_id = a
                changed += 1
        self.session.flush()
        return changed

    def pending_decisions_for(self, user_id: int) -> list[int]:
        """SYNC-MS-004#TrackingService.pending_decisions_for"""
        return self.repo.undecided_version_ids()  # 누가 저장했는지는 모른다 — queries가 거른다
