"""SYNC-MS-008 테스트 관점 — queries (B1 넷)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core import queries
from syncdoc.core.errors import NotFound
from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import DocType
from tests.core.collab.test_service import _comment
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import author, make_project


def _mk(svc, pid, did, typ, status="draft", title="x", a=None):
    body = f"---\ndoc_id: {did}\ntype: {typ}\ntitle: {title}\nstatus: {status}\n---\n# {did}\n#### Q1 첫\n"
    svc.create(pid, did, typ, body, "h", a)


# ── project_summary ──
async def test_project_summary_stages_counts_order(scoped: Session) -> None:
    svc = SpecService(scoped)
    make_project(scoped, "EMPT")
    p = make_project(scoped, "EXMP")
    a = author(scoped)
    _mk(svc, p.id, "EXMP-RFQ-001", "RFQ", "approved", a=a)
    _mk(svc, p.id, "EXMP-PRD-001", "PRD", "approved", a=a)
    _mk(svc, p.id, "EXMP-PRD-002", "PRD", "draft", a=a)
    _mk(svc, p.id, "EXMP-SCN-001", "SCN", "review", a=a)
    _mk(svc, p.id, "EXMP-UC-001", "UC", "draft", a=a)  # 3단계 검토중인데 4단계 문서 → gate
    _mk(svc, p.id, "EXMP-STD-001", "STD", a=a)
    scoped.execute(
        text("UPDATE documents SET has_convention_error=true WHERE doc_id='EXMP-UC-001'")
    )
    got = await queries.project_summary()
    assert [x.code for x in got] == ["EXMP", "EMPT"]  # updated_at desc, 문서 없는 건 뒤
    e = got[1]
    assert len(e.stages) == 11 and all(s.status is None and s.doc_count == 0 for s in e.stages)
    x = got[0]
    by = {s.doc_type: s for s in x.stages}
    assert (by["PRD"].status, by["PRD"].doc_count) == ("draft", 2)  # 승인 1 + 초안 1 → draft
    assert by["RFQ"].gate_warning is False and by["PRD"].gate_warning is False
    assert by["UC"].gate_warning is True and by["SCN"].gate_warning is True  # 앞 단계 미승인
    assert [d.doc_id for d in x.std_docs] == ["EXMP-STD-001"] and by["CODE"].doc_count == 0
    assert x.counts == {
        "needs_check": 0,
        "broken_ref": 0,
        "unresolved_comments": 0,
        "convention_errors": 1,
        "incomplete": 0,
    }
    assert x.remote_url == "https://x/r.git" and x.updated_at is not None


# ── document_list ──
async def test_document_list_counts_and_filters(scoped: Session) -> None:
    svc, ref, tr = SpecService(scoped), ReferenceService(scoped), TrackingService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    tr.raise_broken(q1)
    _comment(scoped, d.id, a.user.id, 1, "x")
    got = await queries.document_list("EXMP")
    assert [x.doc_id for x in got] == ["EXMP-RFQ-001", "EXMP-PRD-001"]
    assert got[1].counts == {"needs_check": 0, "broken_ref": 1, "unresolved_comments": 1}
    assert got[0].counts == {"needs_check": 0, "broken_ref": 0, "unresolved_comments": 0}
    assert got[0].author.user.github_login == "hoyoung" and got[0].author.kind == "agent"
    assert [x.doc_id for x in await queries.document_list("EXMP", stage=2)] == ["EXMP-PRD-001"]
    assert await queries.document_list("EXMP", status="approved") == []
    with pytest.raises(NotFound):
        await queries.document_list("NOPE")


# ── document_view · item_view ──
async def test_document_view_and_item_view_flags_neighbors_author(scoped: Session) -> None:
    svc, ref, tr = SpecService(scoped), ReferenceService(scoped), TrackingService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
    _mk(svc, p.id, "EXMP-SCN-001", "SCN", a=a)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    tr.raise_broken(q1)  # G1에 broken_ref
    doc = await queries.document_view("EXMP-PRD-001")
    assert {i.item_id: i.flags for i in doc.items} == {"G1": ["broken_ref"], "R1": []}
    assert (doc.prev_doc_id, doc.next_doc_id) == ("EXMP-RFQ-001", "EXMP-SCN-001")
    assert doc.author.user.github_login == "hoyoung" and doc.author.instructed_by.id == a.user.id
    assert doc.author.via == "mcp" and doc.body == PRD
    first = await queries.document_view("EXMP-RFQ-001")
    assert first.prev_doc_id is None
    iv = await queries.item_view("EXMP-PRD-001", "G1")
    assert iv.flags == ["broken_ref"] and iv.body.startswith("#### G1 목표")
    assert (await queries.item_view("EXMP-PRD-001", "R1")).flags == []
    with pytest.raises(NotFound):
        await queries.document_view("EXMP-PRD-404")


# ── item_references_view · upstream_checklist ──
async def test_item_references_view_upstream_downstream_missing_document(scoped: Session) -> None:
    svc, ref, tr = SpecService(scoped), ReferenceService(scoped), TrackingService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    rfq = svc.get_document("EXMP-RFQ-001")
    q1 = next(i.pk for i in rfq.items if i.item_id == "Q1")
    tr.raise_broken(q1)
    # PRD#G1: 상위 Q1·#R1, 하위 없음
    g1 = await queries.item_references_view("EXMP-PRD-001", "G1")
    assert sorted((r.doc_id, r.item_id) for r in g1.upstream) == [
        ("EXMP-PRD-001", "R1"),
        ("EXMP-RFQ-001", "Q1"),
    ]
    assert g1.downstream == [] and [f.kind for f in g1.flags] == ["broken_ref"]
    assert (g1.flags[0].cause.item_id, g1.flags[0].assignee.github_login) == ("Q1", "hoyoung")
    # PRD#R1: 상위 미존재 Q9(raw_target만), 하위 G1(같은 문서 #R1)
    r1 = await queries.item_references_view("EXMP-PRD-001", "R1")
    assert [(r.is_missing, r.raw_target) for r in r1.upstream] == [(True, "EXMP-RFQ-001#Q9")]
    assert [(r.doc_id, r.item_id) for r in r1.downstream] == [("EXMP-PRD-001", "G1")]
    # RFQ#Q1: 하위 G1 (문서 전체 참조는 출발 항목이 없어 패널에 안 나옴)
    q = await queries.item_references_view("EXMP-RFQ-001", "Q1")
    assert [(r.doc_id, r.item_id, r.display_name) for r in q.downstream] == [
        ("EXMP-PRD-001", "G1", "목표")
    ]
    assert q.upstream == []
    with pytest.raises(NotFound):
        await queries.item_references_view("EXMP-PRD-001", "R9")


async def test_upstream_checklist_groups_by_target_in_stage_order(scoped: Session) -> None:
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a)
    body = PRD.replace(
        "없는 항목 [[EXMP-RFQ-001#Q9]]", "근거 [[EXMP-RFQ-001#Q1]] · 둘째 [[EXMP-RFQ-001#Q2]]"
    )
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, body, "h1", a)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    got = await queries.upstream_checklist("EXMP-PRD-001")
    rows = [
        (u.target.doc_id, u.target.item_id, u.target_status, u.target_version_no, u.referenced_from)
        for u in got
    ]
    assert rows == [
        ("EXMP-RFQ-001", None, "draft", 1, ["(문서)"]),  # frontmatter upstream + 절 본문
        ("EXMP-RFQ-001", "Q1", "draft", 1, ["G1", "R1"]),  # 같은 상위를 두 항목이 참조 → 한 행
        ("EXMP-RFQ-001", "Q2", "draft", 1, ["R1"]),
        ("EXMP-PRD-001", "R1", "draft", 1, ["G1"]),  # 같은 문서 참조도 상위
    ]
    assert await queries.upstream_checklist("EXMP-RFQ-001") == []  # 참조 없는 문서 → 빈 목록
