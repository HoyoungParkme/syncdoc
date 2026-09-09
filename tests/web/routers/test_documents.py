"""SYNC-API-001 3.4 — GET /api/docs/{docId} · /upstream · POST /status · 참조 · 댓글."""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import DocType
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import PRD as FULL_PRD
from tests.core.spec.test_service import author, make_project
from tests.core.test_pipeline import create
from tests.web.conftest import login


def _seed(scoped: Session):
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
    return d


def test_get_document_upstream_references(client: TestClient, scoped: Session) -> None:
    login(client, scoped, "minjun")
    _seed(scoped)
    d = client.get("/api/docs/EXMP-PRD-001").json()
    assert (d["doc_id"], d["stage"], d["status"], d["current_version_no"], d["commit_hash"]) == (
        "EXMP-PRD-001",
        2,
        "draft",
        1,
        "h1",
    )
    assert d["items"] == [
        {"item_id": "G1", "display_name": "목표", "flags": ["broken_ref"]},
        {"item_id": "R1", "display_name": "기능", "flags": []},
    ]
    assert (
        d["prev_doc_id"] == "EXMP-RFQ-001"
        and d["body"] == PRD
        and d["last_author"]["kind"] == "agent"
    )
    assert client.get("/api/docs/EXMP-PRD-404").status_code == 404
    up = client.get("/api/docs/EXMP-PRD-001/upstream").json()
    assert [(u["target"]["doc_id"], u["target"]["item_id"], u["referenced_from"]) for u in up] == [
        ("EXMP-RFQ-001", None, ["(문서)"]),
        ("EXMP-RFQ-001", "Q1", ["G1"]),
        ("EXMP-PRD-001", "R1", ["G1"]),
    ]
    refs = client.get("/api/docs/EXMP-PRD-001/items/G1/references").json()
    assert sorted((r["doc_id"], r["item_id"]) for r in refs["upstream"]) == [
        ("EXMP-PRD-001", "R1"),
        ("EXMP-RFQ-001", "Q1"),
    ]
    assert refs["flags"][0]["kind"] == "broken_ref" and refs["flags"][0]["cause"]["item_id"] == "Q1"
    assert refs["flags"][0]["assignee"]["github_login"] == "hoyoung"
    r1 = client.get("/api/docs/EXMP-PRD-001/items/R1/references").json()
    assert r1["upstream"] == [
        {
            "doc_id": None,
            "item_id": None,
            "display_name": None,
            "raw_target": "EXMP-RFQ-001#Q9",
            "is_missing": True,
        }
    ]
    r = client.get("/api/docs/EXMP-PRD-001/items/R9/references")
    assert (
        r.status_code == 404 and r.json()["available_items"]
        if "available_items" in r.json()
        else r.status_code == 404
    )
    scoped.execute(text("UPDATE items SET is_deleted=true, deleted_at=now() WHERE item_id='R1'"))
    assert client.get("/api/docs/EXMP-PRD-001/items/R1/references").status_code == 410


async def test_change_status_via_api(client: TestClient, scoped: Session, proj) -> None:
    login(client, scoped)
    await create(proj, DocType.RFQ, RFQ)
    await create(proj, DocType.PRD, FULL_PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1"))
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"})
    assert r.status_code == 422 and r.json()["type"] == "urn:syncdoc:upstream-review-required"
    # 절이 빠진(미완성) 문서는 생성 직후부터 승인 불가 — upstream 검사보다 먼저
    incomplete = await create(
        proj,
        DocType.PRD,
        PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1").replace(
            "doc_id: EXMP-PRD-001", "doc_id: "
        ),
    )
    r = client.post(f"/api/docs/{incomplete.doc_id}/status", json={"to": "approved"})
    assert r.status_code == 409 and "section.missing: 비목표" in r.json()["warnings"]
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "review", "reason": "검토"})
    assert (
        r.status_code == 200
        and r.json()["status"] == "review"
        and r.json()["current_version_no"] == 1
    )
    r = client.post(
        "/api/docs/EXMP-PRD-001/status",
        json={
            "to": "approved",
            "upstream_reviewed": True,
            "upstream_mismatch": ["EXMP-RFQ-001#Q1"],
        },
    )
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert (
        scoped.execute(text("SELECT count(*) FROM flags WHERE kind='upstream_impact'")).scalar()
        == 1
    )
    scoped.execute(
        text(
            "UPDATE documents SET has_convention_error=true, convention_error_detail='x' WHERE doc_id='EXMP-RFQ-001'"
        )
    )
    r = client.post(
        "/api/docs/EXMP-RFQ-001/status", json={"to": "approved", "upstream_reviewed": True}
    )
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:status-blocked"


def test_comments_thread_and_resolve(client: TestClient, scoped: Session) -> None:
    login(client, scoped, "minjun")
    _seed(scoped)
    assert client.get("/api/docs/EXMP-PRD-001/comments").json() == []
    r = client.post("/api/docs/EXMP-PRD-001/comments", json={"line_no": 10, "body": "애매하다"})
    assert (
        r.status_code == 201
        and r.json()["author"]["github_login"] == "minjun"
        and r.json()["line_no"] == 10
    )
    top = r.json()
    r = client.post(
        "/api/docs/EXMP-PRD-001/comments",
        json={"line_no": 10, "body": "답글", "parent_comment_id": top["id"]},
    )
    assert r.status_code == 201
    assert (
        client.post(
            "/api/docs/EXMP-PRD-001/comments", json={"line_no": 999, "body": "x"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/docs/EXMP-PRD-001/comments",
            json={"line_no": 1, "body": "x", "parent_comment_id": 999999},
        ).status_code
        == 404
    )
    lst = client.get("/api/docs/EXMP-PRD-001/comments").json()
    assert (
        len(lst) == 1
        and [x["body"] for x in lst[0]["replies"]] == ["답글"]
        and lst[0]["doc_id"] == "EXMP-PRD-001"
    )
    docs = client.get("/api/projects/EXMP/docs").json()
    assert (
        next(d for d in docs if d["doc_id"] == "EXMP-PRD-001")["counts"]["unresolved_comments"] == 1
    )
    r = client.post(f"/api/comments/{top['id']}/resolve")
    assert r.status_code == 200 and r.json()["is_resolved"] is True
    assert (
        next(
            d for d in client.get("/api/projects/EXMP/docs").json() if d["doc_id"] == "EXMP-PRD-001"
        )["counts"]["unresolved_comments"]
        == 0
    )
    r = client.post(f"/api/comments/{top['id']}/resolve", json={"resolved": False})
    assert r.json()["is_resolved"] is False
    assert client.post("/api/comments/999999/resolve").status_code == 404
