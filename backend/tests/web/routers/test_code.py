"""SYNC-API-001 3.6 — 코드 그래프 네 조회(카드 AY)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.core.codegraph.test_queries import _seed
from tests.web.conftest import login


def test_code_endpoints(client: TestClient, scoped: Session, monkeypatch) -> None:
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
    nodes = client.get("/api/projects/EXMP/code-graph").json()  # UI-17 (카드 BD)
    assert (
        set(nodes) == {"graph", "communities", "functions", "calls"}
        and len(nodes["functions"]) == 4
    )
    assert nodes["functions"][0]["status"] == "code_only" and nodes["communities"] == []
    miss = client.get("/api/docs/EXMP-MS-001/items/svc.gone/code/source")
    assert miss.status_code == 404 and miss.json()["resource"] == "function"
    # 코드 그래프의 코드 — 파일·줄로, 항목 없는 함수도 (UI-17 4.6, 카드 BF)
    from app.core.codegraph import service as cg_service

    async def fake_read(workdir, path, ref="HEAD"):
        return "\n".join(f"line {i}" for i in range(1, 21))

    monkeypatch.setattr(cg_service.git, "read", fake_read)
    src = client.get("/api/projects/EXMP/code/source", params={"file": "a.py", "line": 13})
    assert src.status_code == 200 and (src.json()["start"], src.json()["end"]) == (13, 15)
    assert src.json()["text"] == "line 13\nline 14\nline 15"
    assert src.json()["commit_hash"] == "c" * 40
    gone = client.get("/api/projects/EXMP/code/source", params={"file": "a.py", "line": 2})
    assert gone.status_code == 404 and gone.json()["resource"] == "function"
    assert client.get("/api/projects/EXMP/code/source", params={"file": "a.py"}).status_code == 422
    # 남의 프로젝트
    login(client, scoped, "minjun")
    assert client.get("/api/docs/EXMP-MS-001/items/svc.save/code").status_code == 404
    assert client.get("/api/projects/EXMP/code-calls").status_code == 404
    assert client.get("/api/projects/EXMP/code-graph").status_code == 404
    r = client.get("/api/projects/EXMP/code/source", params={"file": "a.py", "line": 1})
    assert r.status_code == 404


def test_code_ask_endpoint_streams_with_key(
    client: TestClient, scoped: Session, monkeypatch
) -> None:
    """POST /api/projects/{code}/code/ask (카드 BI) — start에 key, 뒤는 /api/docs/{docId}/ask와 같다."""
    from app.config import settings
    from app.core import queries
    from app.core.types import LlmStep, LlmUsage
    from tests.web.routers.test_documents import _sse

    _seed(scoped)
    login(client, scoped, "hoyoung")
    r = client.post("/api/projects/EXMP/conversations", json={})
    conv = r.json()["id"]
    body = {"question": "이게 뭐야?", "conversation_id": conv, "key": "a.py:1"}
    assert client.post("/api/projects/EXMP/code/ask", json=body).status_code == 503  # 키 없음
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    steps: list = [LlmStep("저장 함수다", [], LlmUsage())]

    async def step_stream(system, messages, tools, tool_choice="auto"):
        assert "[보는 함수] svc.save" in system
        yield steps.pop(0)

    monkeypatch.setattr(queries.llm, "step_stream", step_stream)
    r = client.post("/api/projects/EXMP/code/ask", json=body)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert _sse(r.text) == [
        ("start", {"doc_id": None, "item_id": None, "key": "a.py:1"}),
        ("answer", {"answer": "저장 함수다", "context_item_ids": [], "missing_refs": []}),
    ]
    miss = client.post("/api/projects/EXMP/code/ask", json={**body, "key": "a.py:2"})
    assert miss.status_code == 404 and miss.json()["resource"] == "function"
    login(client, scoped, "minjun")
    assert client.post("/api/projects/EXMP/code/ask", json=body).status_code == 404
