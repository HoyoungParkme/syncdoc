"""SYNC-MS-004 테스트 관점 — TrackingService (B1 다섯 · B3 열하나)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.errors import AlreadyDecided, AlreadyResolved, NotFound, ReasonRequired
from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import DocType, Propagation
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
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a_rfq, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a_prd, "spec: 테스트")
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


# ── detect_impact ──
def test_detect_impact_declared_diffed_same_document_and_document_level(
    db_session: Session,
) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    ref = ReferenceService(db_session)
    assert tr.detect_impact(d.id, None, v.id, ["G1"]) == []  # 신규 문서 (UC-S3 1a)
    assert tr.detect_impact(d.id, v.id, v.id, []) == []  # 영향 없음 선언
    assert tr.detect_impact(d.id, v.id, v.id, ["R1"]) == [pks["G1"]]  # 같은 문서 G1이 R1 참조
    assert tr.detect_impact(d.id, v.id, v.id, ["R1", "G1"]) == []  # G1은 원인이지 대상이 아니다
    rv = svc.get_document("EXMP-RFQ-001")
    assert tr.detect_impact(rfq.id, rv.current_version_id, rv.current_version_id, ["Q1"]) == [
        pks["G1"]
    ]
    assert tr.detect_impact(rfq.id, rv.current_version_id, rv.current_version_id, ["Q2"]) == []
    # diff 판정 — R1 본문 변경 → G1 · 공백만 → 없음
    v2 = svc.save(d, d.body.replace("없는 항목", "없는 항목들"), "h2", a_prd, "spec: v2", [])
    assert tr.detect_impact(d.id, v.id, v2.id, None) == [pks["G1"]]
    d2 = svc.get_document("EXMP-PRD-001")
    v3 = svc.save(d2, d2.body.replace("#Q9]]", "#Q9]]  "), "h3", a_prd, "spec: v3", [])
    assert tr.detect_impact(d.id, v2.id, v3.id, None) == []
    # 문서 전체 참조(항목 본문 안) → 어느 항목이 바뀌어도 포함
    scn_body = "---\ndoc_id: EXMP-SCN-001\ntype: SCN\ntitle: 시나리오\nstatus: draft\n---\n# SCN\n## 1. 페르소나\n#### P1 사람\n근거 [[EXMP-RFQ-001]]\n"
    sv = svc.create(p.id, "EXMP-SCN-001", DocType.SCN, scn_body, "s1", a_prd, "spec: 테스트")
    sd = svc.get_document("EXMP-SCN-001")
    ref.extract(sd.id, sv.id, sd.body, {i.item_id: i.pk for i in sd.items}, [])
    p1 = sd.items[0].pk
    assert tr.detect_impact(rfq.id, rv.current_version_id, rv.current_version_id, ["Q2"]) == [p1]


# ── create_pending · get_decision · record_decision · raise_flags ──
def test_decision_flow_propagate_skip_already_decided(db_session: Session) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    body2 = d.body.replace(
        "#### R1 기능", "#### R1 기능 [[#R2]]\n#### R2 둘째 기능\n내용"
    )  # R1 본문에 R2
    v2 = svc.save(d, body2, "h2", a_prd, "spec: v2", [])
    d2 = svc.get_document("EXMP-PRD-001")
    ReferenceService(db_session).extract(
        d2.id, v2.id, d2.body, {i.item_id: i.pk for i in d2.items}, ["EXMP-RFQ-001"]
    )
    pk2 = {i.item_id: i.pk for i in d2.items}
    # R1·R2 바뀌었고 G1이 R1을, R1이 R2를 참조 → 대상은 G1(원인 R1)뿐. R1은 원인이라 제외
    affected = tr.detect_impact(d.id, v.id, v2.id, ["R1", "R2"])
    assert affected == [pks["G1"]]
    pending = tr.create_pending(v2.id, affected, [pk2["R1"], pk2["R2"]])
    dec = tr.get_decision(v2.id)
    assert (dec.id, dec.choice, dec.affected_pks, dec.affected_count) == (
        pending,
        "undecided",
        [pks["G1"]],
        1,
    )
    assert tr.pending_decisions_for(a_prd.user.id) == [v2.id]
    with pytest.raises(NotFound):
        tr.get_decision(999_999)
    with pytest.raises(ReasonRequired):
        tr.record_decision(v2.id, Propagation.skip, None, a_prd.user)
    r = tr.record_decision(v2.id, Propagation.propagate, None, a_prd.user)
    assert (r.choice, r.flags_raised) == ("propagate", 1)
    assert flags(db_session) == [("needs_check", pks["G1"], pk2["R1"], v2.id, a_prd.user.id)]
    assert tr.pending_decisions_for(a_prd.user.id) == []
    with pytest.raises(AlreadyDecided) as ei:
        tr.record_decision(v2.id, Propagation.skip, "오탈자", a_prd.user)
    assert ei.value.extra["choice"] == "propagate"
    assert tr.raise_flags(v2.id, [pks["G1"]]) == 0  # 같은 (대상, 원인, 버전) → 중복 없음
    # skip + 사유 → 플래그 없음
    d3 = svc.get_document("EXMP-PRD-001")
    v3 = svc.save(d3, d3.body + "\n", "h3", a_prd, "spec: v3", [])
    tr.create_pending(v3.id, [pks["G1"]], [pk2["R1"]])
    r3 = tr.record_decision(v3.id, Propagation.skip, "오탈자", a_prd.user)
    assert (r3.choice, r3.flags_raised, tr.get_decision(v3.id).reason) == ("skip", 0, "오탈자")
    assert len(flags(db_session)) == 1


def test_raise_flags_one_per_cause_and_unassigned(db_session: Session) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    # G1이 R1·R2 둘 다 참조하고 둘 다 바뀜 → 플래그 2개
    body2 = (
        d.body.replace("같은 문서 [[#R1]]", "같은 문서 [[#R1]] [[#R2]]") + "#### R2 둘째\n내용\n"
    )
    v2 = svc.save(d, body2, "h2", a_prd, "spec: v2", [])
    d2 = svc.get_document("EXMP-PRD-001")
    pk2 = {i.item_id: i.pk for i in d2.items}
    ReferenceService(db_session).extract(d2.id, v2.id, d2.body, pk2, ["EXMP-RFQ-001"])
    tr.create_pending(v2.id, [pks["G1"]], [pk2["R1"], pk2["R2"]])
    assert tr.raise_flags(v2.id, [pks["G1"]]) == 2
    assert sorted(f[2] for f in flags(db_session)) == sorted([pk2["R1"], pk2["R2"]])
    # 담당자 없음(대상 문서 버전 작성자 행 삭제 대신 assignee null 시나리오) → unassigned에
    db_session.execute(
        text("UPDATE flags SET assignee_user_id=NULL WHERE cause_item_id=:c"), {"c": pk2["R2"]}
    )
    assert [f.cause_item_id for f in tr.flags_unassigned()] == [pk2["R2"]]
    nc, br, ui = tr.flags_for_assignee(a_prd.user.id)
    assert ([f.cause_item_id for f in nc], br, ui) == ([pk2["R1"]], [], [])


# ── get_flag · resolve · flags_for_assignee · flags_in_project ──
def test_get_flag_resolve_and_lists(db_session: Session) -> None:
    svc, tr, p, d, v, pks, rfq, rpk, a_rfq, a_prd = _setup(db_session)
    tr.raise_broken(rpk["Q1"])  # G1 broken_ref (담당 prd-writer)
    tr.raise_upstream([rpk["Q1"]], d.id, v.id, pks["R1"])  # Q1 upstream_impact (담당 rfq-writer)
    f = tr.get_flag(db_session.execute(text("SELECT min(id) FROM flags")).scalar())
    assert (f.kind, f.target_item_id) == ("broken_ref", pks["G1"])
    with pytest.raises(NotFound):
        tr.get_flag(999_999)
    nc, br, ui = tr.flags_for_assignee(a_prd.user.id)
    assert (nc, [x.id for x in br], ui) == ([], [f.id], [])
    assert [x.kind for x in tr.flags_for_assignee(a_rfq.user.id)[2]] == ["upstream_impact"]
    assert [x.id for x in tr.flags_in_project(p.id, "broken_ref")] == [f.id]
    assert tr.flags_in_project(p.id, "needs_check") == []
    # 확인 — 수정 없음
    s = tr.resolve(f.id, a_rfq.user, target_changed=False)
    assert (s.id, s.kind, s.target.item_id, s.cause.item_id, s.cause_version_no) == (
        f.id,
        "broken_ref",
        "G1",
        "Q1",
        None,
    )
    assert s.assignee is None and s.assignee_id == a_prd.user.id and s.resolved_at is not None
    row = db_session.execute(
        text("SELECT resolved_by_user_id, resolved_with_edit FROM flags WHERE id=:i"), {"i": f.id}
    ).one()
    assert row == (a_rfq.user.id, False)
    with pytest.raises(AlreadyResolved):
        tr.resolve(f.id, a_rfq.user, False)
    assert tr.flags_for_assignee(a_prd.user.id) == ([], [], [])
    # 담당 미지정 플래그 확인 → 확인자 기록, assignee 그대로 null
    up = tr.flags_for_assignee(a_rfq.user.id)[2][0]
    db_session.execute(text("UPDATE flags SET assignee_user_id=NULL WHERE id=:i"), {"i": up.id})
    db_session.expire_all()
    s2 = tr.resolve(up.id, a_prd.user, target_changed=True)
    assert (s2.assignee_id, s2.cause_version_no, s2.cause.item_id) == (None, 1, "R1")
