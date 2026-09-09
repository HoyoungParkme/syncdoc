"""SYNC-API-001 3.6 — GET /api/todo · /api/flags/{id}(+resolve) · /api/decisions/{versionId}(GET·POST) · /api/projects/{code}/flags · /api/docs/{docId}/diff."""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from tests.core.test_queries import _b3
from tests.web.conftest import login


def test_todo_decision_flag_flow_via_api(client: TestClient, scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    tr = TrackingService(scoped)
    v2 = svc.save(
        rfq, rfq.body.replace("내용", "바뀐 내용"), "r2", a_rfq, "spec(EXMP-RFQ-001): Q1", []
    )
    tr.create_pending(v2.id, [pks["G1"]], [rpk["Q1"]])
    # rfq-writer: 전파 미결정 1건
    login(client, scoped, "rfq-writer")
    td = client.get("/api/todo").json()
    assert td["total"] == 1 and td["pending_decisions"][0]["version_id"] == v2.id
    dv = client.get(f"/api/decisions/{v2.id}").json()
    assert (dv["doc_id"], dv["choice"], dv["version"]["author"]["user"]["github_login"]) == (
        "EXMP-RFQ-001",
        "undecided",
        "rfq-writer",
    )
    assert [h["item_id"] for h in dv["change_diff"]["hunks"]] == ["Q1"]
    assert (
        dv["affected"][0]["caused_by_items"] == ["Q1"]
        and dv["affected"][0]["assignee"]["github_login"] == "prd-writer"
    )
    assert client.get("/api/decisions/999999").status_code == 404
    r = client.post(f"/api/decisions/{v2.id}", json={"choice": "skip"})
    assert r.status_code == 422 and r.json()["type"] == "urn:syncdoc:reason-required"
    r = client.post(f"/api/decisions/{v2.id}", json={"choice": "propagate"})
    assert r.status_code == 200 and r.json() == {"choice": "propagate", "flags_raised": 1}
    r = client.post(f"/api/decisions/{v2.id}", json={"choice": "skip", "reason": "오탈자"})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:already-decided"
    assert client.get("/api/todo").json()["total"] == 0
    # prd-writer: 확인 필요 1건 → 상세 → 확인함
    login(client, scoped, "prd-writer")
    td = client.get("/api/todo").json()
    f = td["needs_check"][0]
    assert (td["total"], f["target"]["item_id"], f["cause"]["item_id"], f["cause_version_no"]) == (
        1,
        "G1",
        "Q1",
        2,
    )
    fv = client.get(f"/api/flags/{f['id']}").json()
    assert (
        fv["cause_change_count"],
        fv["target_changed_since_raise"],
        fv["cause_diff"]["hunks"],
    ) == (0, False, [])
    assert (
        fv["target_body"].startswith("#### G1 목표")
        and fv["assignee"]["github_login"] == "prd-writer"
    )
    assert client.get("/api/flags/999999").status_code == 404
    # 대상 문서를 고친 뒤 확인 → 수정 동반
    d2 = svc.get_document("EXMP-PRD-001")
    svc.save(d2, d2.body + "\n", "h2", a_prd, "spec: v2", [])
    r = client.post(f"/api/flags/{f['id']}/resolve")
    assert r.status_code == 200 and r.json()["resolved_at"] is not None
    assert (
        r.json()["assignee"]["github_login"] == "prd-writer"
        and r.json()["target"]["item_id"] == "G1"
    )
    assert (
        scoped.execute(
            text("SELECT resolved_with_edit FROM flags WHERE id=:i"), {"i": f["id"]}
        ).scalar()
        is True
    )
    r = client.post(f"/api/flags/{f['id']}/resolve")
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:already-resolved"
    assert client.get("/api/todo").json()["total"] == 0
    # 프로젝트 목록 다이얼로그 · diff
    tr.raise_upstream([rpk["Q1"]], d.id, d2.current_version_id, pks["R1"])
    lst = client.get("/api/projects/EXMP/flags", params={"kind": "upstream_impact"}).json()
    assert [(x["kind"], x["target"]["item_id"]) for x in lst] == [("upstream_impact", "Q1")]
    assert client.get("/api/projects/EXMP/flags", params={"kind": "needs_check"}).json() == []
    assert client.get("/api/projects/EXMP/flags", params={"kind": "bogus"}).status_code == 422
    assert client.get("/api/projects/EXMP/flags", params={"kind": "comments"}).json() == []
    df = client.get("/api/docs/EXMP-RFQ-001/diff", params={"from": 1, "to": 2}).json()
    assert [(h["item_id"], h["downstream_count"]) for h in df["hunks"]] == [("Q1", 1)]
    assert [ln["op"] for ln in df["hunks"][0]["lines"] if ln["op"] != "ctx"] == ["del", "add"]
    assert client.get("/api/docs/EXMP-RFQ-001/diff", params={"from": 1, "to": 9}).status_code == 404
    assert client.get("/api/docs/EXMP-RFQ-001/diff", params={"from": 1}).status_code == 422
    assert SpecService(scoped).get_document("EXMP-RFQ-001").current_version_no == 2
