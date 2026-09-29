"""SYNC-API-001 3.5 — 대화 목록·생성·조회·삭제 (카드 AQ). 첨부 셋은 카드 AR."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.conversation.service import ConversationService
from tests.core.spec.test_service import make_project
from tests.web.conftest import login


def test_conversations_crud_and_ownership(client: TestClient, scoped: Session) -> None:
    make_project(scoped)
    login(client, scoped, "hoyoung")
    r = client.post("/api/projects/EXMP/conversations", json={})
    assert r.status_code == 201 and r.json()["title"] == "새 대화" and r.json()["turn_count"] == 0
    conv = r.json()["id"]
    r = client.post("/api/projects/EXMP/conversations", json={"title": "둘째"})
    assert r.status_code == 201 and r.json()["title"] == "둘째"
    r = client.get("/api/projects/EXMP/conversations")
    assert r.status_code == 200 and [c["title"] for c in r.json()] == ["둘째", "새 대화"]

    svc = ConversationService(scoped)
    svc.finish_turn(svc.add_turn(conv, "첫 질문", []).id, "답", [{"kind": "note", "text": "읽는다"}], ["EXMP-RFQ-001#Q1"])
    scoped.flush()
    r = client.get(f"/api/conversations/{conv}")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "첫 질문" and body["turn_count"] == 1 and body["pending"] == []
    t = body["turns"][0]
    assert t["seq"] == 1 and t["answer"] == "답" and t["error"] is None and t["attachments"] == []
    assert t["progress"] == [{"kind": "note", "text": "읽는다"}]
    assert t["context_item_ids"] == ["EXMP-RFQ-001#Q1"]
    assert "project_code" not in body and "bytes" not in json_dumps(body)

    # 남의 대화·프로젝트는 없는 것과 같다 (R12)
    login(client, scoped, "minjun")
    assert client.get(f"/api/conversations/{conv}").status_code == 404
    assert client.get(f"/api/conversations/{conv}").json()["resource"] == "conversation"
    assert client.delete(f"/api/conversations/{conv}").status_code == 404
    assert client.get("/api/projects/EXMP/conversations").status_code == 404
    assert client.post("/api/projects/EXMP/conversations", json={}).status_code == 404

    login(client, scoped, "hoyoung")
    assert client.delete(f"/api/conversations/{conv}").status_code == 204
    assert client.get(f"/api/conversations/{conv}").status_code == 404
    assert [c["title"] for c in client.get("/api/projects/EXMP/conversations").json()] == ["둘째"]


def json_dumps(o: object) -> str:
    import json

    return json.dumps(o, ensure_ascii=False)
