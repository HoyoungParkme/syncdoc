"""SYNC-API-001 B4 — GET /graph · /versions · /downstream · POST /revert · POST /hooks/github · GET /api/admin/repos · POST rebuild · 폴링 catch_up."""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import scheduler
from app.config import settings
from app.core.spec.service import SpecService
from app.core.types import DocType
from tests.conftest import git as g
from tests.conftest import write_commit_push
from tests.core.reference.test_service import RFQ
from tests.core.test_pipeline import PRD_BODY, PRD_FILE, RFQ_FILE, create, update
from tests.core.test_queries import _b3
from tests.web.conftest import login


def test_graph_versions_downstream_via_api(client: TestClient, scoped: Session) -> None:
    svc, p, d, rfq, pks, rpk, a_rfq, a_prd = _b3(scoped)
    login(client, scoped, "minjun")
    gr = client.get("/api/projects/EXMP/graph").json()
    assert {n["id"] for n in gr["nodes"]} >= {"EXMP-PRD-001#G1", "EXMP-RFQ-001#Q1", "EXMP-RFQ-001"}
    assert {
        "from": "EXMP-PRD-001#G1",
        "to": "EXMP-RFQ-001#Q1",
        "raw_target": "EXMP-RFQ-001#Q1",
        "is_missing": False,
    } in gr["edges"]
    assert next(n for n in gr["nodes"] if n["id"] == "EXMP-RFQ-001#Q2")["isolated"] is True
    assert client.get("/api/projects/EXMP/graph", params={"stage": 1}).status_code == 200
    assert client.get("/api/projects/EXMP/graph", params={"stage": 12}).status_code == 422
    d2 = svc.get_document("EXMP-PRD-001")
    svc.apply_status(
        d2, d2.body.replace("status: draft", "status: review"), "c1", a_prd.user, "검토"
    )
    vs = client.get("/api/docs/EXMP-PRD-001/versions").json()
    assert [
        (
            v["version_no"],
            v["commit_hash"],
            v["author"]["kind"],
            v["author"]["user"]["github_login"],
        )
        for v in vs
    ] == [
        (None, "c1", "human", "prd-writer"),
        (1, "h1", "agent", "prd-writer"),
    ]
    assert client.get("/api/docs/EXMP-PRD-404/versions").status_code == 404
    dv = client.get("/api/docs/EXMP-RFQ-001/downstream").json()
    assert [r["item_id"] for r in dv["by_item"]["Q1"]] == ["G1"] and dv["by_document"][0][
        "doc_id"
    ] == "EXMP-PRD-001"


async def test_revert_via_api(client: TestClient, scoped: Session, proj) -> None:
    login(client, scoped)
    await create(proj, DocType.RFQ, RFQ)
    await create(proj)
    v1 = SpecService(scoped).get_document("EXMP-PRD-001").body
    await update(proj, "EXMP-PRD-001", v1 + "#### R2 둘째\n내용\n", 1, changed_items=[])
    r = client.post("/api/docs/EXMP-PRD-001/revert", json={"to_version": 2})
    assert r.status_code == 422 and r.json()["type"] == "urn:syncdoc:already-current"
    r = client.post("/api/docs/EXMP-PRD-001/revert", json={"to_version": 1})
    assert r.status_code == 201 and (r.json()["version_no"], r.json()["status"]) == (3, "draft")
    assert SpecService(scoped).get_document("EXMP-PRD-001").body == v1
    assert client.post("/api/docs/EXMP-PRD-001/revert", json={"to_version": 9}).status_code == 404


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def test_webhook_admin_and_catch_up(client: TestClient, scoped: Session, proj) -> None:
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = proj["project"].repository
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other / PRD_FILE).parent.mkdir(parents=True, exist_ok=True)
    write_commit_push(other, RFQ_FILE, RFQ, "spec(EXMP-RFQ-001): 초안")
    head = g(remote, "rev-parse", "main")
    payload = json.dumps(
        {"after": head, "repository": {"clone_url": str(remote), "html_url": "x"}}
    ).encode()
    # 서명 불일치 → 401 · 모르는 저장소 → 404 · 정상 → 202, 응답 뒤 파이프라인이 돈다
    assert (
        client.post(
            "/hooks/github",
            content=payload,
            headers={"X-Hub-Signature-256": "sha256=bad", "Content-Type": "application/json"},
        ).status_code
        == 401
    )
    bogus = json.dumps({"after": head, "repository": {"clone_url": "https://x/none.git"}}).encode()
    assert (
        client.post(
            "/hooks/github",
            content=bogus,
            headers={"X-Hub-Signature-256": _sign(bogus), "Content-Type": "application/json"},
        ).status_code
        == 404
    )
    r = client.post(
        "/hooks/github",
        content=payload,
        headers={"X-Hub-Signature-256": _sign(payload), "Content-Type": "application/json"},
    )
    assert r.status_code == 202
    assert SpecService(scoped).get_document("EXMP-RFQ-001").current_version_no == 1
    assert scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar() == head
    # 관리: 동기화 상태 · 서버 꺼둔 사이 push → 밀림 1 → catch_up이 따라잡음 (UC-G1 1a)
    login(client, scoped)
    st = client.get("/api/admin/repos").json()
    assert [(s["code"], s["last_processed_commit"], s["behind_by"]) for s in st] == [
        ("EXMP", head, 0)
    ]
    write_commit_push(other, PRD_FILE, PRD_BODY, "spec(EXMP-PRD-001): 초안")
    # 화면은 DB만 읽는다(MS-001). 폴링이 재기 전까지는 밖에서 push한 걸 아직 모른다
    assert client.get("/api/admin/repos").json()[0]["behind_by"] == 0
    results = await scheduler.catch_up()
    assert [r.doc_id for r in results] == ["EXMP-PRD-001"]
    after = client.get("/api/admin/repos").json()[0]
    assert after["behind_by"] == 0 and after["fetched_at"] is not None
    # 재구축
    rb = client.post("/api/admin/repos/EXMP/rebuild").json()
    assert (rb["docs"], rb["versions"]) == (3, 3) and rb["convention_errors"][0][
        "doc_id"
    ] == "SYNC-PRD-001"
    assert client.post("/api/admin/repos/NOPE/rebuild").status_code == 404
