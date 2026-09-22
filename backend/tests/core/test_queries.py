"""SYNC-MS-008 테스트 관점 — queries. 카드 V로 플래그·댓글·전파 조회는 사라졌다."""

import itertools
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core import queries
from app.core.errors import LlmNotConfigured, LlmUnavailable, NotFound
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.types import (
    AskAnswer,
    AskNote,
    AskRead,
    AskStart,
    BrokenRefSummary,
    DocType,
    GraphScope,
    LlmStep,
    LlmUsage,
    ToolCall,
)
from tests.core.reference.test_service import PRD, RFQ, UPSTREAM
from tests.core.spec.test_service import author, make_project, owner


def _mk(svc, pid, did, typ, status="draft", title="x", a=None):
    body = f"---\ndoc_id: {did}\ntype: {typ}\ntitle: {title}\nstatus: {status}\n---\n# {did}\n#### Q1 첫\n"
    svc.create(pid, did, typ, body, "h", a, "spec: 테스트")


# ── project_summary ──
async def test_project_summary_stages_counts_order(scoped: Session) -> None:
    svc = SpecService(scoped)
    make_project(scoped, "EMPT")
    p = make_project(scoped, "EXMP")
    a = author(scoped)
    _mk(svc, p.id, "EXMP-RFQ-001", "RFQ", "approved", a=a)
    _mk(svc, p.id, "EXMP-PRD-001", "PRD", "approved", a=a)
    _mk(svc, p.id, "EXMP-PRD-002", "PRD", "draft", a=a)
    _mk(svc, p.id, "EXMP-SCN-001", "SCN", "draft", a=a)
    _mk(svc, p.id, "EXMP-UC-001", "UC", "draft", a=a)  # 3단계 초안인데 4단계 문서 → gate
    _mk(svc, p.id, "EXMP-STD-001", "STD", a=a)
    scoped.execute(
        text("UPDATE documents SET has_convention_error=true WHERE doc_id='EXMP-UC-001'")
    )
    got = await queries.project_summary(owner(scoped))
    assert [x.code for x in got] == ["EXMP", "EMPT"]  # updated_at desc, 문서 없는 건 뒤
    e = got[1]
    assert len(e.stages) == 11 and all(s.status is None and s.doc_count == 0 for s in e.stages)
    x = got[0]
    by = {s.doc_type: s for s in x.stages}
    assert (by["PRD"].status, by["PRD"].doc_count) == ("draft", 2)  # 승인 1 + 초안 1 → draft
    assert by["RFQ"].gate_warning is False and by["PRD"].gate_warning is False
    assert by["UC"].gate_warning is True and by["SCN"].gate_warning is True  # 앞 단계 미승인
    assert [d.doc_id for d in x.std_docs] == ["EXMP-STD-001"] and by["CODE"].doc_count == 0
    # 세 칸 (UI-4 3.2·3.4·3.5). 플래그·댓글은 없다 — 카드 V
    assert x.counts == {"broken_ref": 0, "convention_errors": 1, "incomplete": 0}
    assert all(s.broken_count == 0 for s in x.stages)
    assert x.remote_url == "https://x/r.git" and x.updated_at is not None


async def test_project_summary_stage_broken_count_sums_documents(scoped: Session) -> None:
    """한 단계에 미존재 참조 있는 문서 둘 → 그 단계 broken_count가 둘의 합 · counts.broken_ref = 전 단계 합."""
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    ref.extract(d.id, v.id, d.body, {i.item_id: i.pk for i in d.items}, ["EXMP-RFQ-001"])
    body2 = PRD.replace("EXMP-PRD-001", "EXMP-PRD-002").replace(
        "없는 항목 [[EXMP-RFQ-001#Q9]]", "없는 항목 [[EXMP-RFQ-001#Q8]] · [[EXMP-RFQ-001#Q7]]"
    )
    v2 = svc.create(p.id, "EXMP-PRD-002", DocType.PRD, body2, "h2", a, "spec: 테스트")
    d2 = svc.get_document("EXMP-PRD-002")
    ref.extract(d2.id, v2.id, d2.body, {i.item_id: i.pk for i in d2.items}, ["EXMP-RFQ-001"])
    x = next(s for s in await queries.project_summary(owner(scoped)) if s.code == "EXMP")
    by = {s.doc_type: s for s in x.stages}
    assert (by["PRD"].doc_count, by["PRD"].broken_count) == (2, 3)  # Q9 + Q8·Q7
    assert by["RFQ"].broken_count == 0
    assert x.counts["broken_ref"] == 3  # 전 단계 합


async def test_project_detail_docs_and_recent_changes_with_names(scoped: Session) -> None:
    svc = SpecService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec(EXMP-RFQ-001): 초안")
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec(EXMP-PRD-001): 초안")
    d = svc.get_document("EXMP-PRD-001")
    svc.apply_status(d, d.body.replace("status: draft", "status: approved"), "c1", a.user, None)
    pd = await queries.project_detail("EXMP", owner(scoped))
    assert (pd.code, pd.remote_url, [x.doc_id for x in pd.docs]) == (
        "EXMP",
        p.repository.remote_url,
        ["EXMP-RFQ-001", "EXMP-PRD-001"],
    )
    assert pd.stages[1].status == "approved" and pd.docs[1].counts == {"broken_ref": 0}
    assert [(r.doc_id, r.version_no, r.message.split("\n")[0]) for r in pd.recent_changes] == [
        ("EXMP-PRD-001", None, "status(EXMP-PRD-001): draft → approved"),
        ("EXMP-PRD-001", 1, "spec(EXMP-PRD-001): 초안"),
        ("EXMP-RFQ-001", 1, "spec(EXMP-RFQ-001): 초안"),
    ]
    assert [(r.author_view.kind, r.author_view.user.github_login) for r in pd.recent_changes] == [
        ("human", "hoyoung"),
        ("agent", "hoyoung"),
        ("agent", "hoyoung"),
    ]
    assert pd.recent_changes[1].author_view.instructed_by.github_login == "hoyoung"
    with pytest.raises(NotFound):
        await queries.project_detail("NOPE", owner(scoped))


async def test_project_detail_sync_fields_read_db_without_fetch(
    scoped: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI-4 요소 7 — 폴링이 적어 둔 값을 그대로. 이 응답을 만들며 fetch를 돌리지 않는다."""
    from app.infra import git

    monkeypatch.setattr(
        git, "fetch", lambda *a, **k: pytest.fail("project_detail이 fetch를 불렀다")
    )
    p = make_project(scoped)
    _mk(SpecService(scoped), p.id, "EXMP-RFQ-001", "RFQ", a=author(scoped))
    pd = await queries.project_detail("EXMP", owner(scoped))
    assert (pd.last_processed_commit, pd.behind_by) == (None, None)  # 아직 못 받아봤다
    scoped.execute(text("UPDATE repositories SET last_processed_commit='eb30fd6', behind_by=2"))
    scoped.expire_all()  # 폴링은 다른 세션이다 — 이쪽 캐시를 비워 그 상황을 만든다
    pd = await queries.project_detail("EXMP", owner(scoped))
    assert (pd.last_processed_commit, pd.behind_by) == ("eb30fd6", 2)


async def test_document_list_counts_and_filters(scoped: Session) -> None:
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])  # R1 → Q9 미존재
    got = await queries.document_list("EXMP", owner(scoped))
    assert [x.doc_id for x in got] == ["EXMP-RFQ-001", "EXMP-PRD-001"]
    assert got[1].counts == {"broken_ref": 1}
    assert got[0].counts == {"broken_ref": 0}  # 미존재 참조 없는 문서 → 0
    assert got[0].author.user.github_login == "hoyoung" and got[0].author.kind == "agent"
    assert [x.doc_id for x in await queries.document_list("EXMP", owner(scoped), stage=2)] == [
        "EXMP-PRD-001"
    ]
    assert await queries.document_list("EXMP", owner(scoped), status="approved") == []
    with pytest.raises(NotFound):
        await queries.document_list("NOPE", owner(scoped))


# ── document_view · item_view ──
async def test_document_view_and_item_view_missing_refs_neighbors_author(scoped: Session) -> None:
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    _mk(svc, p.id, "EXMP-SCN-001", "SCN", a=a)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    doc = await queries.document_view("EXMP-PRD-001", owner(scoped))
    # 항목마다 자기 미존재 참조 (UI-5 6.1) · 문서 전체는 접은 목록 (4a)
    assert {i.item_id: i.missing_refs for i in doc.items} == {"G1": [], "R1": ["EXMP-RFQ-001#Q9"]}
    assert doc.missing_refs == ["EXMP-RFQ-001#Q9"]
    assert (doc.prev_doc_id, doc.next_doc_id) == ("EXMP-RFQ-001", "EXMP-SCN-001")
    assert doc.author.user.github_login == "hoyoung" and doc.author.instructed_by.id == a.user.id
    assert doc.author.via == "mcp" and doc.body == PRD
    first = await queries.document_view("EXMP-RFQ-001", owner(scoped))
    assert first.prev_doc_id is None
    iv = await queries.item_view("EXMP-PRD-001", "G1", owner(scoped))
    assert iv.body.startswith("#### G1 목표") and iv.doc_status == "draft"
    with pytest.raises(NotFound):
        await queries.document_view("EXMP-PRD-404", owner(scoped))


# ── item_references_view ──
async def test_item_references_view_upstream_downstream_missing_document(scoped: Session) -> None:
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    # PRD#G1: 상위 Q1·#R1, 하위 없음
    g1 = await queries.item_references_view("EXMP-PRD-001", "G1", owner(scoped))
    assert sorted((r.doc_id, r.item_id) for r in g1.upstream) == [
        ("EXMP-PRD-001", "R1"),
        ("EXMP-RFQ-001", "Q1"),
    ]
    assert g1.downstream == []
    # PRD#R1: 상위 미존재 Q9(raw_target만), 하위 G1(같은 문서 #R1)
    r1 = await queries.item_references_view("EXMP-PRD-001", "R1", owner(scoped))
    assert [(r.is_missing, r.raw_target) for r in r1.upstream] == [(True, "EXMP-RFQ-001#Q9")]
    assert [(r.doc_id, r.item_id) for r in r1.downstream] == [("EXMP-PRD-001", "G1")]
    # RFQ#Q1: 하위 G1 (문서 전체 참조는 출발 항목이 없어 패널에 안 나옴)
    q = await queries.item_references_view("EXMP-RFQ-001", "Q1", owner(scoped))
    assert [(r.doc_id, r.item_id, r.display_name) for r in q.downstream] == [
        ("EXMP-PRD-001", "G1", "목표")
    ]
    assert q.upstream == []
    with pytest.raises(NotFound):
        await queries.item_references_view("EXMP-PRD-001", "R9", owner(scoped))


# ── B3: diff_with_impact · project_items ──
def _b3(scoped: Session):
    """RFQ(Q1·Q2, rfq-writer) ← PRD(G1→Q1, G1→#R1, prd-writer). 참조 추출까지."""
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a_rfq, a_prd = author(scoped, "rfq-writer"), author(scoped, "prd-writer")
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a_rfq, "spec(EXMP-RFQ-001): 초안")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a_prd, "spec(EXMP-PRD-001): 초안")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    rfq = svc.get_document("EXMP-RFQ-001")
    rpk = {i.item_id: i.pk for i in rfq.items}
    return svc, p, d, rfq, pks, rpk, a_rfq, a_prd


async def test_diff_with_impact_counts_downstream_per_hunk(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    body2 = (
        d.body.replace("없는 항목", "없는 항목들") + "#### R2 새 항목\n내용\n"
    )  # R1 수정 + R2 추가
    svc.save(d, body2, "h2", a_prd, "spec: v2", [])
    df = await queries.diff_with_impact("EXMP-PRD-001", 1, 2, owner(scoped))
    assert [(h.item_id, h.downstream_count) for h in df.hunks] == [("R1", 1), ("R2", 0)]  # G1→R1
    with pytest.raises(NotFound):
        await queries.diff_with_impact("EXMP-PRD-001", 1, 9, owner(scoped))


async def test_project_items_broken_ref_and_other_kinds(scoped: Session) -> None:
    """UI-4 목록 다이얼로그(6) — 미존재 참조마다 한 행, 출발 항목 이름이 있다. 상대가 들어오면 사라진다."""
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    rows = await queries.project_items("EXMP", "broken_ref", owner(scoped))
    assert [
        (r.type, r.source.doc_id, r.source.item_id, r.source.display_name, r.raw_target)
        for r in rows
    ] == [("broken_ref", "EXMP-PRD-001", "R1", "기능", "EXMP-RFQ-001#Q9")]
    assert all(isinstance(r, BrokenRefSummary) for r in rows)
    assert await queries.project_items("EXMP", "convention_errors", owner(scoped)) == []
    scoped.execute(
        text(
            """UPDATE documents SET incomplete_warnings='["item.none"]' WHERE doc_id='EXMP-RFQ-001'"""
        )
    )
    assert [x.doc_id for x in await queries.project_items("EXMP", "incomplete", owner(scoped))] == [
        "EXMP-RFQ-001"
    ]
    with pytest.raises(ValueError):
        await queries.project_items("EXMP", "bogus", owner(scoped))
    with pytest.raises(NotFound):
        await queries.project_items("NOPE", "broken_ref", owner(scoped))
    # 상대(Q9)가 들어오면 그 행이 사라진다 (UC-S2 2a2)
    body = rfq.body + "#### Q9 아홉째\n내용\n"
    svc.save(rfq, body, "h9", a_rfq, "spec: Q9 추가", [])
    ReferenceService(scoped).resolve_missing(p.id)
    assert await queries.project_items("EXMP", "broken_ref", owner(scoped)) == []


async def test_project_items_broken_ref_outside_items_has_no_source_item(scoped: Session) -> None:
    """절 본문·frontmatter에서 온 참조는 source.item_id=None (MS-008 project_items 2)."""
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    # upstream에 EXMP-NONE-001 — 문서 단위 미존재 참조. RFQ 문서 자체도 없으니 절 본문 참조도 미존재
    ref.extract(d.id, v.id, d.body, {i.item_id: i.pk for i in d.items}, UPSTREAM)
    rows = await queries.project_items("EXMP", "broken_ref", owner(scoped))
    outside = [r for r in rows if r.source.item_id is None]
    assert outside and all(r.source.doc_id == "EXMP-PRD-001" for r in outside)
    assert {r.raw_target for r in outside} >= {"EXMP-NONE-001"}


# ── B4: graph_view · downstream_view · document_view 4a ──
async def test_graph_view_full_stage_scope_and_isolated(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    gr = await queries.graph_view("EXMP", owner(scoped))
    ids = {n.id for n in gr.nodes}
    # 항목 노드 + 문서 노드(문서마다 하나)
    assert ids == {
        "EXMP-RFQ-001",
        "EXMP-PRD-001",
        "EXMP-RFQ-001#Q1",
        "EXMP-RFQ-001#Q2",
        "EXMP-PRD-001#G1",
        "EXMP-PRD-001#R1",
    }
    edges = {(e.from_, e.to, e.is_missing) for e in gr.edges}
    assert ("EXMP-PRD-001#G1", "EXMP-RFQ-001#Q1", False) in edges
    assert ("EXMP-PRD-001#G1", "EXMP-PRD-001#R1", False) in edges
    assert ("EXMP-PRD-001#R1", None, True) in edges  # Q9 미존재
    assert ("EXMP-PRD-001", "EXMP-RFQ-001", False) in edges  # frontmatter·절 본문 → 문서 노드
    iso = {n.id for n in gr.nodes if n.isolated}
    assert iso == {"EXMP-RFQ-001#Q2"}  # 아무도 참조 안 함 (코드블록 참조는 추출 안 됨)
    assert {n.stage for n in gr.nodes if n.doc_id == "EXMP-PRD-001"} == {2}
    assert all(n.stage is not None for n in gr.nodes)
    # 승인만: 문서 상태가 승인인 문서의 항목만. EXMP 시드는 전부 draft라 비어야 한다
    g_ok = await queries.graph_view("EXMP", owner(scoped), GraphScope.approved)
    assert g_ok.nodes == [] and g_ok.edges == []
    # 범위 밖을 가리키는 간선은 그리지 않는다 — 미존재 참조와 다르다 (MS-008 5단계).
    # PRD만 완료로 올리면 G1→Q1(RFQ, 범위 밖)은 안 그리고 R1→Q9(미존재)만 남는다
    svc.apply_status(d, d.body.replace("status: draft", "status: approved"), "c1", a_prd.user, None)
    g_ok = await queries.graph_view("EXMP", owner(scoped), GraphScope.approved)
    ok_ids = {n.id for n in g_ok.nodes}
    assert ok_ids == {"EXMP-PRD-001", "EXMP-PRD-001#G1", "EXMP-PRD-001#R1"}
    assert all(e.from_ in ok_ids and (e.to is None or e.to in ok_ids) for e in g_ok.edges)
    assert {(e.from_, e.to, e.is_missing) for e in g_ok.edges} == {
        ("EXMP-PRD-001#G1", "EXMP-PRD-001#R1", False),
        ("EXMP-PRD-001#R1", None, True),
    }
    with pytest.raises(NotFound):
        await queries.graph_view("NOPE", owner(scoped))


async def test_item_chain_closure_roles_and_eleven_rows(scoped: Session) -> None:
    """전이적 폐포 · 역할은 폐포 방향 · 빈 단계도 온다 (MS-008 item_chain)."""
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    ch = await queries.item_chain("EXMP-RFQ-001", "Q1", owner(scoped))
    assert len(ch.rows) == 11  # 항목 없는 단계도 빈 채로
    assert [r.doc_type for r in ch.rows][:3] == ["RFQ", "PRD", "SCN"]
    roles = {i.ref.item_id: i.role for r in ch.rows for i in r.items}
    assert roles["Q1"] == "self"
    assert roles["G1"] == "downstream"  # G1이 Q1을 근거로 삼는다
    assert ch.downstream_count >= 1 and ch.upstream_count == 0
    # 2단계(PRD) 행에 G1이 있고, 항목 없는 단계는 빈 배열
    prd_row = next(r for r in ch.rows if r.stage == 2)
    assert {i.ref.item_id for i in prd_row.items} == {"G1"}
    assert next(r for r in ch.rows if r.stage == 9).items == []
    with pytest.raises(NotFound):
        await queries.item_chain("EXMP-RFQ-001", "NOPE", owner(scoped))


async def test_item_chain_is_transitive_not_just_direct(scoped: Session) -> None:
    """한 걸음이 아니라 끝까지 따라간다. SCN P1 → PRD G1 → RFQ Q1 세 단계."""
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    ref = ReferenceService(scoped)
    scn = "---\ndoc_id: EXMP-SCN-001\ntype: SCN\ntitle: 시나리오\nstatus: draft\n---\n\n"
    scn += "## 1. 페르소나\n\n#### P1 개발자\n근거 [[EXMP-PRD-001#G1]]\n"
    v = svc.create(p.id, "EXMP-SCN-001", DocType.SCN, scn, "h2", a_prd, "spec: 초안")
    sd = svc.get_document("EXMP-SCN-001")
    ref.extract(sd.id, v.id, sd.body, {i.item_id: i.pk for i in sd.items}, [])

    ch = await queries.item_chain("EXMP-RFQ-001", "Q1", owner(scoped))
    reached = {i.ref.item_id for r in ch.rows for i in r.items}
    # P1 → G1 → Q1. Q1에서 아래로 두 걸음 떨어진 P1도 폐포에 들어온다
    assert {"G1", "P1"} <= reached
    roles = {i.ref.item_id: i.role for r in ch.rows for i in r.items}
    assert roles["P1"] == "downstream" and roles["G1"] == "downstream"
    # 반대 방향에서도 두 걸음
    up = await queries.item_chain("EXMP-SCN-001", "P1", owner(scoped))
    assert {i.ref.item_id for r in up.rows for i in r.items} >= {"G1", "Q1"}
    assert {i.ref.item_id: i.role for r in up.rows for i in r.items}["Q1"] == "upstream"


async def test_item_chain_backward_reference_role_is_upstream_not_downstream(
    scoped: Session,
) -> None:
    """되돌아오는 참조 — 근거가 **오른쪽 단계**에 있을 때도 `upstream`으로 적힌다.

    역할을 단계 번호로 정하면 이걸 `downstream`으로 잘못 적는다(UI-15 규칙).
    여기서는 1단계 RFQ 항목이 6단계 DOM 항목을 근거로 삼는다.
    """
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    ref = ReferenceService(scoped)
    dom = "---\ndoc_id: EXMP-DOM-001\ntype: DOM\ntitle: 도메인\nstatus: draft\n---\n\n"
    dom += "## 1. 개념\n\n#### Document 문서\n명세 원본 하나.\n"
    v = svc.create(p.id, "EXMP-DOM-001", DocType.DOM, dom, "h3", a_prd, "spec: 초안")
    dd = svc.get_document("EXMP-DOM-001")
    ref.extract(dd.id, v.id, dd.body, {i.item_id: i.pk for i in dd.items}, [])
    # RFQ(1단계) Q2가 DOM(6단계) Document를 근거로 삼는다 — 체인을 거스르는 참조
    body = rfq.body.replace("#### Q2 둘째", "#### Q2 둘째\n근거 [[EXMP-DOM-001#Document]]")
    v2 = svc.save(rfq, body, "h4", a_rfq, "spec: Q2가 DOM을 근거로", [])
    rfq2 = svc.get_document("EXMP-RFQ-001")
    ref.extract(rfq2.id, v2.id, rfq2.body, {i.item_id: i.pk for i in rfq2.items}, [])

    ch = await queries.item_chain("EXMP-RFQ-001", "Q2", owner(scoped))
    roles = {i.ref.item_id: i.role for r in ch.rows for i in r.items}
    assert roles["Q2"] == "self"
    # 단계 번호로 보면 6 > 1이라 '파생'으로 보이지만, 폐포 방향으로는 근거다
    assert roles["Document"] == "upstream"
    dom_row = next(r for r in ch.rows if r.stage == 6)
    assert [i.role for i in dom_row.items] == ["upstream"]
    assert ch.upstream_count >= 1


async def test_downstream_view_and_missing_refs(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    dv = await queries.downstream_view("EXMP-RFQ-001", owner(scoped))
    assert {k: [(r.doc_id, r.item_id) for r in v] for k, v in dv.by_item.items()} == {
        "Q1": [("EXMP-PRD-001", "G1")],
        "(문서)": [("EXMP-PRD-001", None)],
    }
    assert [(x.doc_id, x.title, x.items) for x in dv.by_document] == [
        ("EXMP-PRD-001", "제품", ["(문서)", "Q1"])
    ]
    assert (
        await queries.downstream_view("EXMP-PRD-001", owner(scoped))
    ).by_document == []  # 같은 문서 안 참조(G1→R1)는 제외
    doc = await queries.document_view("EXMP-PRD-001", owner(scoped))
    assert doc.missing_refs == ["EXMP-RFQ-001#Q9"]  # _b3의 upstream은 RFQ뿐


# ── 카드 W — 소유: 사람용 조회는 내 것만 (MS-008 0장) ──
async def test_queries_hide_someone_elses_project(scoped: Session) -> None:
    from tests.core.account.test_service import make_user

    svc = SpecService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    _mk(svc, p.id, "EXMP-RFQ-001", "RFQ", a=a)
    stranger = make_user(scoped, login="stranger")
    # 목록에 없다 — 에러가 아니라 빈 목록 (UI-2 빈 상태)
    assert await queries.project_summary(stranger) == []
    assert [x.code for x in await queries.project_summary(owner(scoped))] == ["EXMP"]
    # 주소로 직접 열어도 없는 것과 같다 — 필드가 get의 없음과 같다
    for coro in (
        queries.project_detail("EXMP", stranger),
        queries.document_list("EXMP", stranger),
        queries.trash_list("EXMP", stranger),
        queries.document_view("EXMP-RFQ-001", stranger),
        queries.item_view("EXMP-RFQ-001", "Q1", stranger),
        queries.item_references_view("EXMP-RFQ-001", "Q1", stranger),
        queries.diff_with_impact("EXMP-RFQ-001", 1, 1, stranger),
        queries.project_items("EXMP", "broken_ref", stranger),
        queries.graph_view("EXMP", stranger),
        queries.item_chain("EXMP-RFQ-001", "Q1", stranger),
        queries.downstream_view("EXMP-RFQ-001", stranger),
    ):
        with pytest.raises(NotFound) as ei:
            await coro
        assert ei.value.extra == {"resource": "project", "id": "EXMP"}


# ── ask_item · ask_tool (카드 Y — ReAct) ──
def _seed_refs(scoped: Session):
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    ref.extract(d.id, v.id, d.body, {i.item_id: i.pk for i in d.items}, UPSTREAM)
    return d


def _rows(scoped: Session) -> dict[str, int]:
    return {
        t: scoped.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
        for t in ("documents", "items", "versions", "references", "status_changes")
    }


def _call(name: str, **args) -> ToolCall:
    return ToolCall(f"c{len(args)}-{name}", name, args)


def _step(text: str | None = None, calls: list[ToolCall] | None = None) -> LlmStep:
    return LlmStep(text=text, tool_calls=calls or [], usage=LlmUsage(10, 2))


@pytest.fixture
def script(monkeypatch):
    """llm.step을 대본으로. install([LlmStep, …]) → 받은 (system, messages, tool_choice) 기록."""
    seen: list[tuple[str, list[dict], str]] = []

    def install(steps: list[LlmStep]):
        it = iter(steps)

        async def step(system, messages, tools, tool_choice="auto"):
            seen.append((system, list(messages), tool_choice))
            try:
                return next(it)
            except StopIteration:
                raise AssertionError("대본이 끝났는데 또 불렀다") from None

        monkeypatch.setattr(queries.llm, "step", step)
        return seen

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    return install


async def _collect(gen):
    return [e async for e in gen]


async def test_ask_item_start_context_has_titles_and_item_names_but_no_body(
    scoped: Session, script
) -> None:
    _seed_refs(scoped)
    before = _rows(scoped)
    seen = script([_step("답")])
    events = await _collect(queries.ask_item("EXMP-PRD-001", "G1", "왜?", [], owner(scoped)))
    assert events == [AskStart("EXMP-PRD-001", "G1"), AskAnswer("답", [])]
    assert "먼저 보고 있는 항목을 get_item으로 읽는다" in seen[0][0]  # #110
    system, messages, choice = seen[0]
    assert "[문서] EXMP-PRD-001 제품 · 상태 draft · v1" in system
    assert "[이 문서의 항목]\nG1 목표\nR1 기능" in system
    assert "[지금 보는 항목] G1 목표" in system
    assert "근거 [[EXMP-RFQ-001#Q1]]" not in system  # 본문은 안 실린다 — 도구로 읽는다
    assert messages == [{"role": "user", "text": "왜?"}] and choice == "auto"
    assert _rows(scoped) == before


async def test_ask_item_without_item_has_no_viewing_line(scoped: Session, script) -> None:
    _seed_refs(scoped)
    seen = script([_step("답")])
    events = await _collect(queries.ask_item("EXMP-PRD-001", None, "?", [], owner(scoped)))
    assert events[0] == AskStart("EXMP-PRD-001", None)
    assert "[지금 보는 항목]" not in seen[0][0]


async def test_ask_item_loop_emits_note_read_in_order_and_records_reads(
    scoped: Session, script
) -> None:
    _seed_refs(scoped)
    before = _rows(scoped)
    seen = script(
        [
            _step(
                "먼저 읽자",
                [_call("get_item", doc_id="EXMP-PRD-001", item_id="G1", reason="G1 본문을 본다")],
            ),
            _step(
                None,
                [
                    _call(
                        "get_references",
                        doc_id="EXMP-PRD-001",
                        item_id="G1",
                        reason="근거를 따라간다",
                    ),
                    _call("get_item", doc_id="EXMP-RFQ-001", item_id="Q1", reason="Q1을 읽는다"),
                ],
            ),
            _step("Q1이 근거다"),
        ]
    )
    events = await _collect(
        queries.ask_item("EXMP-PRD-001", "G1", "근거가 뭐야?", [], owner(scoped))
    )
    assert events == [
        AskStart("EXMP-PRD-001", "G1"),
        AskNote("먼저 읽자"),
        AskNote("G1 본문을 본다"),
        AskRead("get_item", "EXMP-PRD-001#G1"),
        AskNote("근거를 따라간다"),
        AskRead("get_references", "EXMP-PRD-001#G1"),
        AskNote("Q1을 읽는다"),
        AskRead("get_item", "EXMP-RFQ-001#Q1"),
        AskAnswer("Q1이 근거다", ["EXMP-PRD-001#G1", "EXMP-RFQ-001#Q1"]),  # 중복은 접힌다
    ]
    # 대화록: 도구 결과가 tool 항목으로 쌓여 다음 호출에 실린다
    _, messages, _ = seen[2]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "tool", "assistant", "tool", "tool"]
    assert '"body"' in messages[2]["text"] and "근거 [[EXMP-RFQ-001#Q1]]" in messages[2]["text"]
    assert _rows(scoped) == before


async def test_ask_item_wraps_up_after_eight_calls(scoped: Session, script) -> None:
    _seed_refs(scoped)
    steps = [
        _step(None, [_call("get_item", doc_id="EXMP-PRD-001", item_id="G1", reason="또")])
        for _ in range(8)
    ]
    steps.append(_step("읽은 것으로 답"))
    seen = script(steps)
    events = await _collect(queries.ask_item("EXMP-PRD-001", "G1", "?", [], owner(scoped)))
    assert events[-1] == AskAnswer("읽은 것으로 답", ["EXMP-PRD-001#G1"])
    assert len(seen) == 9  # 도구 8번 + 마무리 1번
    system, messages, choice = seen[8]
    assert choice == "none" and messages[-1] == {"role": "user", "text": queries._ASK_WRAP_UP}


async def test_ask_item_wraps_up_on_time_limit_and_fails_if_still_no_answer(
    scoped: Session, script, monkeypatch
) -> None:
    _seed_refs(scoped)
    clock = itertools.chain([0.0], itertools.repeat(200.0))
    monkeypatch.setattr(queries.time, "monotonic", lambda: next(clock))
    script(
        [
            _step(None, [_call("get_item", doc_id="EXMP-PRD-001", item_id="G1", reason="한 번")]),
            _step(None),
        ]
    )
    with pytest.raises(LlmUnavailable) as e:
        await _collect(queries.ask_item("EXMP-PRD-001", "G1", "?", [], owner(scoped)))
    assert e.value.extra["reason"] == "상한 뒤에도 답이 없다"


async def test_ask_item_trims_history_and_logs_usage(
    scoped: Session, script, monkeypatch, caplog
) -> None:
    _seed_refs(scoped)
    monkeypatch.setattr(settings, "LLM_MAX_TURNS", 2)
    seen = script([_step("답")])
    hist = [{"role": "user", "text": f"q{i}"} for i in range(5)]
    with caplog.at_level("INFO", logger="app.core.queries"):
        await _collect(queries.ask_item("EXMP-PRD-001", "G1", "마지막", hist, owner(scoped)))
    _, messages, _ = seen[0]
    assert [m["text"] for m in messages] == ["q3", "q4", "마지막"]
    line = next(r.message for r in caplog.records if r.message.startswith("ask "))
    assert "calls=0" in line and "prompt=10" in line and "completion=2" in line
    assert "목표" not in line and "마지막" not in line  # 본문·질문은 로그에 없다


async def test_ask_item_without_key_blocks_before_reading(scoped: Session, monkeypatch) -> None:
    _seed_refs(scoped)
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    called = []
    monkeypatch.setattr(SpecService, "get_document", lambda *a, **k: called.append(1))
    with pytest.raises(LlmNotConfigured):
        await _collect(queries.ask_item("EXMP-PRD-001", "G1", "?", [], owner(scoped)))
    assert called == []


async def test_ask_item_of_other_owner_or_missing_item_is_not_found_before_start(
    scoped: Session, script
) -> None:
    _seed_refs(scoped)
    seen = script([_step("답")])
    gen = queries.ask_item("EXMP-PRD-001", "G1", "?", [], owner(scoped, "minjun"))
    with pytest.raises(NotFound) as e:
        await anext(gen)
    assert e.value.extra["resource"] == "project"
    gen = queries.ask_item("EXMP-PRD-001", "G9", "?", [], owner(scoped))
    with pytest.raises(NotFound) as e:
        await anext(gen)
    assert e.value.extra["resource"] == "item"
    assert seen == []  # 모델을 부르기 전에 막힌다


async def test_ask_tool_get_item_references_chain_documents_list(scoped: Session) -> None:
    _seed_refs(scoped)
    u = owner(scoped)
    r = await queries.ask_tool(
        "get_item", {"doc_id": "EXMP-PRD-001", "item_id": "G1", "reason": "r"}, "EXMP", u
    )
    got = json.loads(r.text)
    assert r.target == "EXMP-PRD-001#G1"
    assert set(got) == {"doc_id", "item_id", "display_name", "doc_status", "doc_version_no", "body"}
    assert got["body"].startswith("#### G1 목표")

    r = await queries.ask_tool(
        "get_references", {"doc_id": "EXMP-PRD-001", "item_id": "R1", "reason": "r"}, "EXMP", u
    )
    got = json.loads(r.text)
    assert r.target == "EXMP-PRD-001#R1"
    assert {"raw_target": "EXMP-RFQ-001#Q9", "note": "아직 없음"} in got["upstream"]  # 끊어진 참조
    assert got["downstream"] == [{"id": "EXMP-PRD-001#G1", "name": "목표"}]

    r = await queries.ask_tool(
        "item_chain", {"doc_id": "EXMP-PRD-001", "item_id": "G1", "reason": "r"}, "EXMP", u
    )
    got = json.loads(r.text)
    assert got["item"] == {"id": "EXMP-PRD-001#G1", "name": "목표"}
    assert len(got["rows"]) == 11 and got["rows"][3]["items"] == []  # 빈 단계도 행으로
    assert {
        "id": "EXMP-RFQ-001#Q1",
        "name": "첫 요구",
        "role": "upstream",
        "status": "draft",
    } in got["rows"][0]["items"]

    r = await queries.ask_tool("list_documents", {"reason": "r"}, "EXMP", u)
    got = json.loads(r.text)
    assert r.target is None
    assert [(d["doc_id"], d["title"], d["status"]) for d in got] == [
        ("EXMP-RFQ-001", "요구", "draft"),
        ("EXMP-PRD-001", "제품", "draft"),
    ]

    r = await queries.ask_tool("get_document", {"doc_id": "EXMP-RFQ-001", "reason": "r"}, "EXMP", u)
    got = json.loads(r.text)
    assert (
        r.target == "EXMP-RFQ-001" and got["title"] == "요구" and "#### Q1 첫 요구" in got["body"]
    )
    assert got["items"] == [
        {"item_id": "Q1", "display_name": "첫 요구"},
        {"item_id": "Q2", "display_name": "둘째"},
    ]


async def test_ask_tool_errors_are_text_not_exceptions(scoped: Session) -> None:
    _seed_refs(scoped)
    u = owner(scoped)
    r = await queries.ask_tool(
        "get_item", {"doc_id": "EXMP-PRD-001", "item_id": "G9", "reason": "r"}, "EXMP", u
    )
    assert r.target is None and json.loads(r.text)["error"] == "없음"
    assert "get_references" in json.loads(r.text)["hint"]  # 되짚을 실마리 (#110)
    r = await queries.ask_tool(
        "get_item", {"doc_id": "OTHR-PRD-001", "item_id": "G1", "reason": "r"}, "EXMP", u
    )
    assert json.loads(r.text) == {"error": "없음", "doc_id": "OTHR-PRD-001"}
    r = await queries.ask_tool("get_item", {"doc_id": "EXMP-PRD-001"}, "EXMP", u)
    assert "item_id" in json.loads(r.text)["error"] and "reason" in json.loads(r.text)["error"]
    r = await queries.ask_tool("write_document", {"reason": "r"}, "EXMP", u)
    assert "모르는 도구" in json.loads(r.text)["error"]
    # 남의 프로젝트는 텍스트가 아니라 not-found 전파(→ error 이벤트)
    with pytest.raises(NotFound):
        await queries.ask_tool("list_documents", {"reason": "r"}, "EXMP", owner(scoped, "minjun"))
