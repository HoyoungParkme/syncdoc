"""SYNC-API-001 3.4 — GET /api/docs/{docId} · POST /status(토글) · 참조."""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.types import DocType
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import PRD as FULL_PRD
from tests.core.spec.test_service import author, make_project
from tests.core.test_pipeline import create
from tests.web.conftest import login


def _seed(scoped: Session):
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
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
    # 항목마다 대상이 없는 참조의 raw_target (API-002 items[].missing_refs). R1 → Q9는 아직 없다
    assert d["items"] == [
        {"item_id": "G1", "display_name": "목표", "missing_refs": []},
        {"item_id": "R1", "display_name": "기능", "missing_refs": ["EXMP-RFQ-001#Q9"]},
    ]
    assert (
        d["prev_doc_id"] == "EXMP-RFQ-001"
        and d["body"] == PRD
        and d["last_author"]["kind"] == "agent"
    )
    assert client.get("/api/docs/EXMP-PRD-404").status_code == 404
    refs = client.get("/api/docs/EXMP-PRD-001/items/G1/references").json()
    assert sorted((r["doc_id"], r["item_id"]) for r in refs["upstream"]) == [
        ("EXMP-PRD-001", "R1"),
        ("EXMP-RFQ-001", "Q1"),
    ]
    assert "flags" not in refs
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
    """토글 하나 — 초안 ⇄ 완료 (UC-H8). 상위 대조가 없고, 완료 게이트(status-blocked)만 남는다."""
    login(client, scoped)
    await create(proj, DocType.RFQ, RFQ)
    await create(proj, DocType.PRD, FULL_PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1"))
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["current_version_no"] == 1  # 상태 변경은 Version을 안 만든다
    # 검토중은 없다 — 값 자체가 안 받아진다
    assert client.post("/api/docs/EXMP-PRD-001/status", json={"to": "review"}).status_code == 422
    # 절이 빠진(미완성) 문서는 생성 직후부터 완료 불가
    incomplete = await create(
        proj,
        DocType.PRD,
        PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1").replace(
            "doc_id: EXMP-PRD-001", "doc_id: "
        ),
    )
    r = client.post(f"/api/docs/{incomplete.doc_id}/status", json={"to": "approved"})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:status-blocked"
    assert "section.missing: 비목표" in r.json()["warnings"]
    # 다시 초안으로. reason은 선택 — 이력(UI-7)에 남는다
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "draft", "reason": "다시 본다"})
    assert (
        r.status_code == 200
        and r.json()["status"] == "draft"
        and r.json()["current_version_no"] == 1
    )
    scoped.execute(
        text(
            "UPDATE documents SET has_convention_error=true, convention_error_detail='x' WHERE doc_id='EXMP-RFQ-001'"
        )
    )
    r = client.post("/api/docs/EXMP-RFQ-001/status", json={"to": "approved"})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:status-blocked"
