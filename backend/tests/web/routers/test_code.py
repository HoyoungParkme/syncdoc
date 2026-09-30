"""SYNC-API-001 3.6 — 코드 그래프 네 조회(카드 AY)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.core.codegraph.test_queries import _seed
from tests.web.conftest import login


def test_code_endpoints(client: TestClient, scoped: Session) -> None:
    _seed(scoped)
    login(client, scoped, "hoyoung")
    r = client.get("/api/docs/EXMP-MS-001/items/svc.save/code")
    assert r.status_code == 200
    body = r.json()
    assert body["is_ms"] and body["function"]["qual"] == "svc.save"
    assert [c["status"] for c in body["function"]["calls"]] == ["code_only", "spec_only", "same"]
    doc = client.get("/api/docs/EXMP-MS-001/code").json()
    assert len(doc["functions"]) == 4 and doc["graph"]["source"] == "server"
    calls = client.get("/api/projects/EXMP/code-calls").json()
    assert {"from", "to", "status"} <= set(calls["edges"][0])  # from 별칭
    miss = client.get("/api/docs/EXMP-MS-001/items/svc.gone/code/source")
    assert miss.status_code == 404 and miss.json()["resource"] == "function"
    # 남의 프로젝트
    login(client, scoped, "minjun")
    assert client.get("/api/docs/EXMP-MS-001/items/svc.save/code").status_code == 404
    assert client.get("/api/projects/EXMP/code-calls").status_code == 404
