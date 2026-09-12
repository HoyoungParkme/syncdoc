"""SYNC-MS-004 — TrackingService. flags·propagation_decisions만.

변경 영향 감지는 SpecService.diff·ReferenceService.downstream을 직접 부른다(DOM-002 3.2 예외).
B1: raise_broken · raise_upstream · flags_for_items · count_flags*. B3: 나머지 11개.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.clock import now_utc
from app.core.errors import AlreadyDecided, AlreadyResolved, NotFound, ReasonRequired
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.tracking.models import Flag, PropagationDecision
from app.core.tracking.repository import TrackingRepository
from app.core.types import (
    DecisionResult,
    FlagKind,
    FlagSummary,
    ItemRef,
    Propagation,
    RelinkResult,
    RestoreDecision,
    RestoreFlag,
)


class TrackingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TrackingRepository(session)
        self.spec = SpecService(session)
        self.references = ReferenceService(session)

    def _target_of(self, target_pk: int) -> tuple[int | None, int | None]:
        """(담당자, 대상 문서의 최신 버전 id) — 세 raise_*가 공통으로 쓴다 (MS-004).

        담당자를 구하려고 이미 그 문서의 최근 작성자를 보므로 대상 버전도 같은 자리에서
        얻는다. 대상 문서에 버전이 없으면 둘 다 None.
        """
        doc_id = self.repo.document_id_of_item(target_pk)
        if doc_id is None:
            return None, None
        la = self.spec.last_author(doc_id)
        return (la.user_id if la else None), self.repo.latest_version_id_of_document(doc_id)

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
        dec.decided_by_user_id, dec.decided_at = user.id, now_utc()
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
            assignee, target_version = self._target_of(target_pk)
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
                        target_version_id=target_version,
                        assignee_user_id=assignee,
                        raised_at=now_utc(),
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
            assignee, target_version = self._target_of(ref.from_item_pk)
            self.repo.add(
                Flag(
                    kind=FlagKind.broken_ref,
                    target_item_id=ref.from_item_pk,
                    cause_item_id=cause_item_pk,
                    cause_version_id=None,
                    target_version_id=target_version,
                    assignee_user_id=assignee,
                    raised_at=now_utc(),
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
            assignee, target_version = self._target_of(target_pk)
            self.repo.add(
                Flag(
                    kind=FlagKind.upstream_impact,
                    target_item_id=target_pk,
                    cause_item_id=cause_item_pk,
                    cause_version_id=cause_version_id,
                    target_version_id=target_version,
                    assignee_user_id=assignee,
                    raised_at=now_utc(),
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
            now_utc(),
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

    def all_flags(self, project_id: int) -> list[Flag]:
        """SYNC-MS-004#TrackingService.all_flags

        해제된 것도 준다 — 백업은 지금 남은 일이 아니라 그때 있었던 사실이다 (#16).
        """
        return self.repo.all_of_project(project_id)

    def all_decisions(self, project_id: int) -> list[PropagationDecision]:
        """SYNC-MS-004#TrackingService.all_decisions"""
        return self.repo.decisions_of_project(project_id)

    def restore_flags(self, rows: list[RestoreFlag]) -> tuple[int, int]:
        """SYNC-MS-004#TrackingService.restore_flags

        자연키는 이미 pk로 풀려서 온다 — 푸는 것은 pipeline의 몫이다(묶음 경계).
        """
        added = skipped = 0
        for r in rows:
            if self.repo.flag_exists(
                r.kind, r.target_item_id, r.cause_item_id, r.cause_version_id, r.raised_at
            ):
                skipped += 1
                continue
            self.repo.add(
                Flag(
                    kind=r.kind,
                    target_item_id=r.target_item_id,
                    cause_item_id=r.cause_item_id,
                    cause_version_id=r.cause_version_id,
                    target_version_id=r.target_version_id,
                    assignee_user_id=r.assignee_user_id,
                    raised_at=r.raised_at,
                    resolved_by_user_id=r.resolved_by_user_id,
                    resolved_at=r.resolved_at,
                    resolved_with_edit=r.resolved_with_edit,
                )
            )
            added += 1
        self.session.flush()
        return added, skipped

    def restore_decisions(self, rows: list[RestoreDecision]) -> tuple[int, int]:
        """SYNC-MS-004#TrackingService.restore_decisions

        덮어쓰지 않는다 — 지금 DB의 결정은 사람이 방금 내린 것일 수 있고 백업은 옛 사실이다.
        """
        added = skipped = 0
        for r in rows:
            if self.repo.decision_by_version(r.version_id) is not None:
                skipped += 1
                continue
            self.repo.add(
                PropagationDecision(
                    version_id=r.version_id,
                    choice=r.choice,
                    affected_pks=r.affected_pks,
                    changed_pks=r.changed_pks,
                    reason=None,  # 백업에 안 싣는다 (INFRA 6.1)
                    decided_by_user_id=r.decided_by_user_id,
                    decided_at=r.decided_at,
                )
            )
            added += 1
        self.session.flush()
        return added, skipped

    def relink_versions(
        self, project_id: int, old: dict[int, tuple[int, str]], new: dict[tuple[int, str], int]
    ) -> RelinkResult:
        """SYNC-MS-004#TrackingService.relink_versions

        재구축이 versions를 다시 만들면 id가 전부 바뀐다. 전파결정과 플래그가 옛 id를
        가리키므로 (document_id, commit_hash)를 열쇠로 새 id에 다시 잇는다 (#38).

        두 버전 컬럼을 따로 잇는다 — 하나를 못 이어도 다른 하나는 살린다.
        cause_version_id를 못 이으면 행을 지운다. NULL로 비우지 않는 것은, 비우면
        UI-11의 원인 diff·"그 뒤로 N번 더 바뀜"·중복 방지 JOIN이 전부 죽어 판단
        재료 없는 빈 카드가 남기 때문이다. target_version_id는 반대로 비운다 —
        없으면 target_changed_since_raise가 False가 될 뿐 플래그는 여전히 쓸 수 있다.
        """
        relinked, drop_dec, drop_flag, taken = 0, [], [], set()

        def resolve(old_id: int | None) -> int | None:
            key = old.get(old_id) if old_id is not None else None
            return new.get(key) if key is not None else None

        for d in self.repo.decisions_by_version_ids(list(old)):
            nid = resolve(d.version_id)
            # version_id는 UNIQUE다. 두 옛 버전이 한 새 버전으로 접히면 나중 것을 버린다
            if nid is None or nid in taken:
                drop_dec.append(d)
                continue
            taken.add(nid)
            if d.version_id != nid:
                d.version_id = nid
                relinked += 1
        for f in self.repo.flags_with_version(project_id):
            tid = resolve(f.target_version_id)
            if f.target_version_id != tid:  # 못 찾으면 None — 비우고 행은 남긴다
                f.target_version_id = tid
                relinked += 1
            if f.cause_version_id is None:
                continue
            nid = resolve(f.cause_version_id)
            if nid is None:
                drop_flag.append(f)
                continue
            if f.cause_version_id != nid:
                f.cause_version_id = nid
                relinked += 1

        self.repo.delete_rows(drop_dec + drop_flag)
        self.session.flush()
        reason = "가리키던 커밋이 저장소에 없습니다"
        dropped: list[dict[str, object]] = []
        for kind, rows in (("propagation_decision", drop_dec), ("flag", drop_flag)):
            if rows:
                dropped.append({"kind": kind, "count": len(rows), "reason": reason})
        return RelinkResult(relinked=relinked, dropped=dropped)

    def reassign_open_flags(self, project_id: int) -> int:
        """SYNC-MS-004#TrackingService.reassign_open_flags

        재구축은 git을 진실로 삼아 versions를 다시 만든다. assignee_user_id는
        거기서 파생된 값인데 플래그를 만들 때 한 번만 계산되고 다시 계산되지
        않는다 — clear_index는 flags를 남기므로, 이게 없으면 재구축이 절반만
        끝난다(#34). 해제된 플래그는 그때의 사실이라 안 건드린다.
        """
        changed = 0
        for f in self.repo.unresolved_of_project(project_id):
            # target_version_id는 여기서 안 건드린다 — 부여 **시점**의 값이라 지금 것으로
            # 다시 계산하면 늘 최신과 같아져 「그 뒤로 바뀌었나」가 영영 False가 된다.
            # 재구축으로 id가 바뀐 것은 relink_versions가 7a에서 이미 이었다
            a, _ = self._target_of(f.target_item_id)
            if a != f.assignee_user_id:
                f.assignee_user_id = a
                changed += 1
        self.session.flush()
        return changed

    def pending_decisions_for(self, user_id: int) -> list[int]:
        """SYNC-MS-004#TrackingService.pending_decisions_for"""
        return self.repo.undecided_version_ids()  # 누가 저장했는지는 모른다 — queries가 거른다
