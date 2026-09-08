"""SYNC-MS-003 테스트 관점 — ReferenceService."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.types import DocType
from tests.core.spec.test_service import author, make_project

RFQ = "---\ndoc_id: EXMP-RFQ-001\ntype: RFQ\ntitle: 요구\nstatus: draft\n---\n# RFQ\n## 1. 배경\n#### Q1 첫 요구\n내용\n#### Q2 둘째\n"
PRD = """---
doc_id: EXMP-PRD-001
type: PRD
title: 제품
status: draft
upstream: [EXMP-RFQ-001, EXMP-NONE-001]
---
# PRD
절 본문의 참조 [[EXMP-RFQ-001]] — 항목 밖
## 1. 목표
#### G1 목표
근거 [[EXMP-RFQ-001#Q1]] · 같은 문서 [[#R1]]
#### R1 기능
`인라인 [[EXMP-RFQ-001#Q2]]`는 무시
```
코드블록 [[EXMP-RFQ-001#Q2]]도 무시
```
없는 항목 [[EXMP-RFQ-001#Q9]]
"""
UPSTREAM = ["EXMP-RFQ-001", "EXMP-NONE-001"]


def _setup(db_session: Session):
    svc, ref = SpecService(db_session), ReferenceService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    return svc, ref, d, v, pks, a


def rows(db_session: Session):
    return db_session.execute(
        text(
            'SELECT from_item_id, to_item_id, to_document_id, raw_target, is_missing FROM "references" ORDER BY id'
        )
    ).all()


# ── extract ──
def test_extract_items_document_upstream_missing_and_code_skip(db_session: Session) -> None:
    svc, ref, d, v, pks, _ = _setup(db_session)
    r = ref.extract(d.id, v.id, d.body, pks, UPSTREAM)
    assert (r.added, r.removed, r.missing) == (5, 0, 2)
    rfq = svc.get_document("EXMP-RFQ-001")
    q1 = next(i.pk for i in rfq.items if i.item_id == "Q1")
    assert set(rows(db_session)) == {
        (None, None, rfq.id, "EXMP-RFQ-001", False),  # 절 본문·upstream → from_item None (같은 키)
        (pks["G1"], q1, None, "EXMP-RFQ-001#Q1", False),
        (pks["G1"], pks["R1"], None, "#R1", False),  # 같은 문서
        (pks["R1"], None, None, "EXMP-RFQ-001#Q9", True),  # 미존재, raw_target 보존
        (None, None, None, "EXMP-NONE-001", True),  # upstream 미존재 문서
    }
    assert not any("Q2" in raw for _, _, _, raw, _ in rows(db_session))  # 코드·인라인 무시


def test_extract_same_body_again_is_noop_and_removed_refs_deleted(db_session: Session) -> None:
    svc, ref, d, v, pks, a = _setup(db_session)
    ref.extract(d.id, v.id, d.body, pks, UPSTREAM)
    ids_before = [
        r[0] for r in db_session.execute(text('SELECT id FROM "references" ORDER BY id')).all()
    ]
    v2 = svc.save(d, d.body, "h2", a, [])
    r = ref.extract(d.id, v2.id, d.body, pks, UPSTREAM)
    assert (r.added, r.removed) == (0, 0)
    ids_after = [
        r[0] for r in db_session.execute(text('SELECT id FROM "references" ORDER BY id')).all()
    ]
    assert ids_before == ids_after  # 행을 지우고 다시 넣지 않는다
    assert (
        db_session.execute(text('SELECT DISTINCT extracted_version_id FROM "references"')).scalar()
        == v2.id
    )
    body3 = d.body.replace(
        "근거 [[EXMP-RFQ-001#Q1]] · 같은 문서 [[#R1]]", "근거 [[EXMP-RFQ-001#Q2]]"
    )
    r = ref.extract(d.id, v2.id, body3, pks, [])
    assert (r.added, r.removed) == (1, 3)


# ── downstream ──
def test_downstream_lists_edges_pointing_to_item(db_session: Session) -> None:
    svc, ref, d, v, pks, _ = _setup(db_session)
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    edges = ref.downstream(q1)
    assert [(e.from_item_pk, e.raw_target, e.is_missing) for e in edges] == [
        (pks["G1"], "EXMP-RFQ-001#Q1", False)
    ]
    assert [e.from_item_pk for e in ref.downstream(pks["R1"])] == [pks["G1"]]
    assert ref.downstream(pks["G1"]) == []


# ── upstream · upstream_of_document · downstream_of_document ──
def test_upstream_edges_including_missing(db_session: Session) -> None:
    svc, ref, d, v, pks, _ = _setup(db_session)
    ref.extract(d.id, v.id, d.body, pks, UPSTREAM)
    g1 = ref.upstream(pks["G1"])
    assert sorted(e.raw_target for e in g1) == ["#R1", "EXMP-RFQ-001#Q1"]
    r1 = ref.upstream(pks["R1"])
    assert [(e.raw_target, e.is_missing) for e in r1] == [("EXMP-RFQ-001#Q9", True)]  # 미존재 포함
    assert ref.upstream(999_999) == []


def test_upstream_of_document_excludes_missing_includes_frontmatter(db_session: Session) -> None:
    svc, ref, d, v, pks, _ = _setup(db_session)
    ref.extract(d.id, v.id, d.body, pks, UPSTREAM)
    edges = ref.upstream_of_document(d.id)
    raws = sorted((e.from_item_pk is None, e.raw_target) for e in edges)
    assert raws == [(False, "#R1"), (False, "EXMP-RFQ-001#Q1"), (True, "EXMP-RFQ-001")]
    assert all(not e.is_missing for e in edges)


def test_downstream_of_document_only_whole_document_refs(db_session: Session) -> None:
    svc, ref, d, v, pks, _ = _setup(db_session)
    ref.extract(d.id, v.id, d.body, pks, UPSTREAM)
    rfq = svc.get_document("EXMP-RFQ-001")
    edges = ref.downstream_of_document(rfq.id)
    assert [(e.from_item_pk, e.raw_target) for e in edges] == [
        (None, "EXMP-RFQ-001")
    ]  # 절 본문·upstream
    assert ref.downstream_of_document(d.id) == []
