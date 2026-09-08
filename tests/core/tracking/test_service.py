"""SYNC-MS-004 테스트 관점 — TrackingService (B1 다섯 + detect_impact 스텁)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import DocType
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import author, make_project


def _setup(db_session: Session):
    """RFQ(Q1·Q2, 작성자 rfq-writer) ← PRD(G1→Q1, G1→R1, R1→Q9 미존재, 문서 참조)."""
    svc, ref, tr = (
        SpecService(db_session),
        ReferenceService(db_session),
        TrackingService(db_session),
    )
    p = make_project(db_session)
    a_rfq, a_prd = author(db_session, "rfq-writer"), author(db_session, "prd-writer")
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a_rfq)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a_prd)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    rfq = svc.get_document("EXMP-RFQ-001")
    rpk = {i.item_id: i.pk for i in rfq.items}
    return svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd


def flags(db_session: Session):
    return db_session.execute(
        text(
            "SELECT kind, target_item_id, cause_item_id, cause_version_id, assignee_user_id FROM flags ORDER BY id"
        )
    ).all()


# ── raise_broken ──
def test_raise_broken_flags_downstream_items_with_last_author(db_session: Session) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    assert tr.raise_broken(rpk["Q1"]) == 1  # G1이 Q1을 참조
    assert flags(db_session) == [("broken_ref", pks["G1"], rpk["Q1"], None, a_prd.user.id)]
    assert tr.raise_broken(rpk["Q2"]) == 0  # 코드블록 참조는 추출 안 됨


# ── raise_upstream ──
def test_raise_upstream_once_per_cause_document_assignee_upstream_author(
    db_session: Session,
) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    assert tr.raise_upstream([rpk["Q1"], rpk["Q2"]], d.id, v.id, pks["R1"]) == 2
    assert (
        tr.raise_upstream([rpk["Q1"]], d.id, v.id, None) == 0
    )  # 같은 하위 문서가 같은 상위를 두 번 → 하나
    assert flags(db_session) == [
        ("upstream_impact", rpk["Q1"], pks["R1"], v.id, a_rfq.user.id),
        ("upstream_impact", rpk["Q2"], pks["R1"], v.id, a_rfq.user.id),
    ]
    db_session.execute(text("UPDATE flags SET resolved_at=now()"))
    assert tr.raise_upstream([rpk["Q1"]], d.id, v.id, None) == 1  # 해결된 뒤엔 다시


# ── flags_for_items · count_flags · count_flags_by_document ──
def test_flags_for_items_and_counts(db_session: Session) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    tr.raise_broken(rpk["Q1"])  # G1에 broken_ref
    tr.raise_upstream([rpk["Q1"]], d.id, v.id, None)  # Q1에 upstream_impact
    got = tr.flags_for_items([pks["G1"], pks["R1"], rpk["Q1"]])
    assert set(got) == {pks["G1"], rpk["Q1"]}
    assert [f.kind for f in got[pks["G1"]]] == ["broken_ref"] and got[pks["G1"]][
        0
    ].assignee_user_id == a_prd.user.id
    assert tr.count_flags(p.id) == {"needs_check": 0, "broken_ref": 1, "upstream_impact": 1}
    assert tr.count_flags_by_document([d.id, rfq.id, 999]) == {
        d.id: {"broken_ref": 1},
        rfq.id: {"upstream_impact": 1},
    }
    db_session.execute(text("UPDATE flags SET resolved_at=now() WHERE kind='broken_ref'"))
    assert tr.flags_for_items([pks["G1"]]) == {} and tr.count_flags(p.id)["broken_ref"] == 0
    assert tr.flags_for_items([]) == {} and tr.count_flags_by_document([]) == {}


# ── detect_impact 스텁 ──
def test_detect_impact_stub_returns_empty(db_session: Session) -> None:
    svc, tr, p, d, v, pks, *_ = _setup(db_session)
    assert tr.detect_impact(d.id, None, v.id, ["G1"]) == []
    assert tr.detect_impact(d.id, v.id, v.id, None) == []
