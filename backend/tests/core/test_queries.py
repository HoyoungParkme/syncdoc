"""SYNC-MS-008 테스트 관점 — queries (B1 넷)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import queries
from app.core.errors import NotFound
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.tracking.service import TrackingService
from app.core.types import DocType, GraphScope, Propagation
from tests.core.collab.test_service import _comment
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import author, make_project


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
    # 여섯 칸. 플래그 세 종류를 다 센다 (UI-4 3.6)
    assert x.counts == {
        "needs_check": 0,
        "broken_ref": 0,
        "upstream_impact": 0,
        "unresolved_comments": 0,
        "convention_errors": 1,
        "incomplete": 0,
    }
    assert all(s.flag_count == 0 for s in x.stages)
    assert x.remote_url == "https://x/r.git" and x.updated_at is not None


async def test_project_summary_stage_flag_count_sums_documents(scoped: Session) -> None:
    """UI-2 2.2 테두리 — 한 단계에 플래그 있는 문서가 둘이면 그 단계는 둘의 합."""
    svc, ref, tr = SpecService(scoped), ReferenceService(scoped), TrackingService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    for did in ("EXMP-PRD-001", "EXMP-PRD-002"):  # 둘 다 RFQ#Q1을 참조한다
        v = svc.create(p.id, did, DocType.PRD, PRD.replace("EXMP-PRD-001", did), "h", a, "spec: x")
        d = svc.get_document(did)
        ref.extract(d.id, v.id, d.body, {i.item_id: i.pk for i in d.items}, ["EXMP-RFQ-001"])
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    tr.raise_broken(q1)  # 끊어진 참조는 가리키는 쪽에 붙는다 — PRD 문서 둘에 하나씩
    by = {s.doc_type: s for s in (await queries.project_summary())[0].stages}
    assert (by["PRD"].doc_count, by["PRD"].flag_count) == (2, 2)
    assert by["RFQ"].flag_count == 0


# ── document_list ──
async def test_project_detail_docs_and_recent_changes_with_names(scoped: Session) -> None:
    svc = SpecService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec(EXMP-RFQ-001): 초안")
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec(EXMP-PRD-001): 초안")
    d = svc.get_document("EXMP-PRD-001")
    svc.apply_status(d, d.body.replace("status: draft", "status: review"), "c1", a.user, "검토")
    pd = await queries.project_detail("EXMP")
    assert (pd.code, pd.remote_url, [x.doc_id for x in pd.docs]) == (
        "EXMP",
        p.repository.remote_url,
        ["EXMP-RFQ-001", "EXMP-PRD-001"],
    )
    assert pd.stages[1].status == "review" and pd.docs[1].counts["needs_check"] == 0
    assert [(r.doc_id, r.version_no, r.message.split("\n")[0]) for r in pd.recent_changes] == [
        ("EXMP-PRD-001", None, "status(EXMP-PRD-001): draft → review"),
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
        await queries.project_detail("NOPE")


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
    pd = await queries.project_detail("EXMP")
    assert (pd.last_processed_commit, pd.behind_by) == (None, None)  # 아직 못 받아봤다
    scoped.execute(text("UPDATE repositories SET last_processed_commit='eb30fd6', behind_by=2"))
    scoped.expire_all()  # 폴링은 다른 세션이다 — 이쪽 캐시를 비워 그 상황을 만든다
    pd = await queries.project_detail("EXMP")
    assert (pd.last_processed_commit, pd.behind_by) == ("eb30fd6", 2)


async def test_document_list_counts_and_filters(scoped: Session) -> None:
    svc, ref, tr = SpecService(scoped), ReferenceService(scoped), TrackingService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
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
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
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
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
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
    assert g1.flags[0].cause_version_no is None  # broken_ref는 cause_version이 없다
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
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    body = PRD.replace(
        "없는 항목 [[EXMP-RFQ-001#Q9]]", "근거 [[EXMP-RFQ-001#Q1]] · 둘째 [[EXMP-RFQ-001#Q2]]"
    )
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, body, "h1", a, "spec: 테스트")
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


# ── B3: diff_with_impact · todo · decision_view · flag_view · project_items ──
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
    df = await queries.diff_with_impact("EXMP-PRD-001", 1, 2)
    assert [(h.item_id, h.downstream_count) for h in df.hunks] == [("R1", 1), ("R2", 0)]  # G1→R1
    with pytest.raises(NotFound):
        await queries.diff_with_impact("EXMP-PRD-001", 1, 9)


async def test_todo_decision_view_record_and_flag_view(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    tr = TrackingService(scoped)
    # 아무것도 없는 사용자 → 여섯 묶음 빈 배열
    empty = await queries.todo(a_prd.user)
    assert (empty.total, empty.needs_check, empty.pending_decisions, empty.unassigned) == (
        0,
        [],
        [],
        [],
    )
    # 에이전트(rfq-writer 지시)가 RFQ Q1 수정 → 미결정 (pipeline 11단계와 같은 호출)
    v2 = svc.save(
        rfq, rfq.body.replace("내용", "바뀐 내용"), "r2", a_rfq, "spec(EXMP-RFQ-001): Q1 수정", []
    )
    affected = tr.detect_impact(rfq.id, rfq.current_version_id, v2.id, ["Q1"])
    assert affected == [pks["G1"]]
    tr.create_pending(v2.id, affected, [rpk["Q1"]])
    td = await queries.todo(a_rfq.user)
    assert [
        (x.version_id, x.doc_id, x.version_no, x.affected_count) for x in td.pending_decisions
    ] == [(v2.id, "EXMP-RFQ-001", 2, 1)]
    assert td.total == 1 and (await queries.todo(a_prd.user)).pending_decisions == []  # 지시자만
    # 전파 미결정 상세 (UI-12)
    dv = await queries.decision_view(v2.id)
    assert (dv.doc_id, dv.choice, dv.version.version_no, dv.version.commit_hash) == (
        "EXMP-RFQ-001",
        "undecided",
        2,
        "r2",
    )
    assert dv.version.author_view.user.github_login == "rfq-writer"
    assert (dv.change_diff.from_version, dv.change_diff.to_version) == (1, 2)
    assert [h.item_id for h in dv.change_diff.hunks] == ["Q1"]
    assert [
        (a.doc_id, a.item_id, a.caused_by_items, a.assignee.github_login) for a in dv.affected
    ] == [("EXMP-PRD-001", "G1", ["Q1"], "prd-writer")]
    with pytest.raises(NotFound):
        await queries.decision_view(999_999)
    # 예 → G1에 확인 필요 → prd-writer 내 할 일
    assert tr.record_decision(v2.id, Propagation.propagate, None, a_rfq.user).flags_raised == 1
    td2 = await queries.todo(a_prd.user)
    f = td2.needs_check[0]
    assert (
        f.kind,
        f.target.item_id,
        f.cause.item_id,
        f.cause_version_no,
        f.assignee.github_login,
    ) == (
        "needs_check",
        "G1",
        "Q1",
        2,
        "prd-writer",
    )
    assert td2.total == 1 and (await queries.todo(a_rfq.user)).total == 0
    # 플래그 상세 (UI-11): 부여 직후에도 원인 변경이 보인다 — v1 → v2 (#10)
    # cause_change_count는 부여 **뒤** 또 바뀐 횟수라 0이다
    fv = await queries.flag_view(f.id)
    assert (fv.cause_diff.from_version, fv.cause_diff.to_version) == (1, 2)
    assert fv.cause_diff.hunks, "부여 직후에 diff가 비면 판단 재료가 없다"
    assert (fv.cause_change_count, fv.target_changed_since_raise) == (0, False)
    assert fv.target_body.startswith("#### G1 목표") and fv.id == f.id
    # 원인이 그 사이 또 바뀜(UC-H11 3a) → 누적 diff v1→v3 · 대상 저장 → 변경 있음
    rfq2 = svc.get_document("EXMP-RFQ-001")
    svc.save(rfq2, rfq2.body.replace("바뀐 내용", "또 바뀐 내용"), "r3", a_rfq, "spec: v3", [])
    # 원인만 바뀌었다 — 대상은 그대로다. 버전 id로 견주므로 저장 순서·시각과 무관하다 (#17)
    assert (await queries.flag_view(f.id)).target_changed_since_raise is False
    d2 = svc.get_document("EXMP-PRD-001")
    svc.save(d2, d2.body + "\n", "h2", a_prd, "spec: v2", [])
    fv2 = await queries.flag_view(f.id)
    assert (fv2.cause_change_count, fv2.cause_diff.from_version, fv2.cause_diff.to_version) == (
        1,
        1,
        3,
    )
    assert [h.item_id for h in fv2.cause_diff.hunks] == [
        "Q1"
    ] and fv2.target_changed_since_raise is True
    # broken_ref → cause_deleted_at · upstream_impact → cause_body · 담당 미지정 → unassigned
    scoped.execute(
        text("UPDATE items SET is_deleted=true, deleted_at=now() WHERE id=:i"), {"i": rpk["Q2"]}
    )
    scoped.expire_all()
    scoped.execute(text("UPDATE flags SET assignee_user_id=NULL WHERE id=:i"), {"i": f.id})
    tr.raise_upstream([rpk["Q1"]], d.id, d2.current_version_id, pks["R1"])
    bid = tr.repo.add(
        __import__("app.core.tracking.models", fromlist=["Flag"]).Flag(
            kind="broken_ref",
            target_item_id=pks["G1"],
            cause_item_id=rpk["Q2"],
            assignee_user_id=None,
        )
    ).id
    td3 = await queries.todo(a_rfq.user)
    assert [x.kind for x in td3.upstream_impact] == ["upstream_impact"] and td3.total == 1
    assert sorted(x.id for x in td3.unassigned) == sorted([f.id, bid])
    bv = await queries.flag_view(bid)
    assert bv.cause_deleted_at is not None and bv.cause_diff is None
    uv = await queries.flag_view(td3.upstream_impact[0].id)
    assert uv.cause_body.startswith("#### R1 기능") and uv.cause_diff is None
    with pytest.raises(NotFound):
        await queries.flag_view(999_999)
    # 프로젝트 목록 다이얼로그 (UI-4 6)
    assert [x.id for x in await queries.project_items("EXMP", "needs_check")] == [f.id]
    assert [x.id for x in await queries.project_items("EXMP", "upstream_impact")] == [uv.id]
    assert await queries.project_items("EXMP", "comments") == []
    assert await queries.project_items("EXMP", "convention_errors") == []
    scoped.execute(
        text(
            """UPDATE documents SET incomplete_warnings='["item.none"]' WHERE doc_id='EXMP-RFQ-001'"""
        )
    )
    assert [x.doc_id for x in await queries.project_items("EXMP", "incomplete")] == ["EXMP-RFQ-001"]
    with pytest.raises(ValueError):
        await queries.project_items("EXMP", "bogus")
    with pytest.raises(NotFound):
        await queries.project_items("NOPE", "comments")


async def test_todo_convention_errors_and_comments_of_my_documents(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    scoped.execute(
        text("UPDATE documents SET has_convention_error=true WHERE doc_id='EXMP-PRD-001'")
    )
    _comment(scoped, d.id, a_rfq.user.id, 3, "이 줄이 애매하다")
    _comment(scoped, rfq.id, a_prd.user.id, 2, "해결됨", resolved=True)
    td = await queries.todo(a_prd.user)
    assert [x.doc_id for x in td.convention_errors] == ["EXMP-PRD-001"]
    assert [(c.doc_id, c.line_no, c.author.github_login) for c in td.unresolved_comments] == [
        ("EXMP-PRD-001", 3, "rfq-writer")
    ]
    assert td.total == 2 and (await queries.todo(a_rfq.user)).total == 0


# ── B4: graph_view · downstream_view · document_view 4a ──
async def test_graph_view_full_stage_scope_and_isolated(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    gr = await queries.graph_view("EXMP")
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
    g_ok = await queries.graph_view("EXMP", GraphScope.approved)
    assert g_ok.nodes == [] and g_ok.edges == []
    # 플래그 있는 것: 미해결 플래그가 붙은 항목만
    TrackingService(scoped).raise_broken(rpk["Q1"])  # Q1은 RFQ 항목
    g_fl = await queries.graph_view("EXMP", GraphScope.flagged)
    flagged = {n.id for n in g_fl.nodes}
    assert flagged and all(n.has_flag for n in g_fl.nodes)
    # 범위 밖을 가리키는 간선은 그리지 않는다 — 미존재 참조와 다르다 (MS-008 5단계)
    assert all(e.from_ in flagged and (e.to is None or e.to in flagged) for e in g_fl.edges)
    assert not any(e.is_missing and e.to is None and e.from_ not in flagged for e in g_fl.edges)
    with pytest.raises(NotFound):
        await queries.graph_view("NOPE")


async def test_item_chain_closure_roles_and_eleven_rows(scoped: Session) -> None:
    """전이적 폐포 · 역할은 폐포 방향 · 빈 단계도 온다 (MS-008 item_chain)."""
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    ch = await queries.item_chain("EXMP-RFQ-001", "Q1")
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
        await queries.item_chain("EXMP-RFQ-001", "NOPE")


async def test_item_chain_is_transitive_not_just_direct(scoped: Session) -> None:
    """한 걸음이 아니라 끝까지 따라간다. SCN P1 → PRD G1 → RFQ Q1 세 단계."""
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    ref = ReferenceService(scoped)
    scn = "---\ndoc_id: EXMP-SCN-001\ntype: SCN\ntitle: 시나리오\nstatus: draft\n---\n\n"
    scn += "## 1. 페르소나\n\n#### P1 개발자\n근거 [[EXMP-PRD-001#G1]]\n"
    v = svc.create(p.id, "EXMP-SCN-001", DocType.SCN, scn, "h2", a_prd, "spec: 초안")
    sd = svc.get_document("EXMP-SCN-001")
    ref.extract(sd.id, v.id, sd.body, {i.item_id: i.pk for i in sd.items}, [])

    ch = await queries.item_chain("EXMP-RFQ-001", "Q1")
    reached = {i.ref.item_id for r in ch.rows for i in r.items}
    # P1 → G1 → Q1. Q1에서 아래로 두 걸음 떨어진 P1도 폐포에 들어온다
    assert {"G1", "P1"} <= reached
    roles = {i.ref.item_id: i.role for r in ch.rows for i in r.items}
    assert roles["P1"] == "downstream" and roles["G1"] == "downstream"
    # 반대 방향에서도 두 걸음
    up = await queries.item_chain("EXMP-SCN-001", "P1")
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

    ch = await queries.item_chain("EXMP-RFQ-001", "Q2")
    roles = {i.ref.item_id: i.role for r in ch.rows for i in r.items}
    assert roles["Q2"] == "self"
    # 단계 번호로 보면 6 > 1이라 '파생'으로 보이지만, 폐포 방향으로는 근거다
    assert roles["Document"] == "upstream"
    dom_row = next(r for r in ch.rows if r.stage == 6)
    assert [i.role for i in dom_row.items] == ["upstream"]
    assert ch.upstream_count >= 1


async def test_downstream_view_and_missing_refs(scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    dv = await queries.downstream_view("EXMP-RFQ-001")
    assert {k: [(r.doc_id, r.item_id) for r in v] for k, v in dv.by_item.items()} == {
        "Q1": [("EXMP-PRD-001", "G1")],
        "(문서)": [("EXMP-PRD-001", None)],
    }
    assert [(x.doc_id, x.title, x.items) for x in dv.by_document] == [
        ("EXMP-PRD-001", "제품", ["(문서)", "Q1"])
    ]
    assert (
        await queries.downstream_view("EXMP-PRD-001")
    ).by_document == []  # 같은 문서 안 참조(G1→R1)는 제외
    doc = await queries.document_view("EXMP-PRD-001")
    assert doc.missing_refs == ["EXMP-RFQ-001#Q9"]  # _b3의 upstream은 RFQ뿐
