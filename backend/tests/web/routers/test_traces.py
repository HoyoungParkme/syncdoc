"""SYNC-API-001 3.12 — 실행 기록·기록 도구의 준비(카드 CJ). 토큰·세션·남의 것·4MB·같은 기록 200."""

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.account.service import AccountService
from app.core.trace import service as trace_service
from tests.core.codegraph.test_queries import _seed
from tests.core.trace.test_service import record
from tests.web.conftest import login

GRAPH = {
    "functions": [
        {"key": "a.py:1", "name": "f", "qual": "a.f", "file": "a.py", "line": 1, "end": 4,
         "route": {"method": "GET", "path": "/x"}},
        {"key": "b.ts:3", "name": "g", "qual": "b.g", "file": "b.ts", "line": 3, "end": None},
    ],
    "calls": [],
    "infra": {"nodes": [{"id": "infra:db", "host": "db:5432"}, {"id": "infra:http", "host": None}],
              "links": []},
}  # fmt: skip


def _token(scoped: Session, login_: str = "hoyoung") -> str:
    user = AccountService(scoped).user_by_login(login_)
    return AccountService(scoped).issue_token(user, "기록").raw


def test_trace_spans_with_token_and_session(client: TestClient, scoped: Session) -> None:
    _seed(scoped, GRAPH)
    login(client, scoped, "hoyoung")
    raw = _token(scoped)
    client.cookies.clear()
    r = client.get("/api/projects/EXMP/trace-spans", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    body = r.json()
    assert body["commit_hash"] == "c" * 40
    assert body["spans"] == [{"key": "a.py:1", "file": "a.py", "line": 1, "end": 4, "name": "f",
                              "qual": "a.f", "route": {"method": "GET", "path": "/x"}}]  # fmt: skip
    assert body["infra"] == [{"id": "infra:db", "host": "db:5432"}]
    bad = client.get("/api/projects/EXMP/trace-spans", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert client.get("/api/projects/EXMP/trace-spans").status_code == 401  # 세션도 없다
    login(client, scoped, "hoyoung")
    assert client.get("/api/projects/EXMP/trace-spans").json()["commit_hash"] == "c" * 40


def test_trace_spans_without_graph_is_empty(client: TestClient, scoped: Session) -> None:
    _seed(scoped, None)
    login(client, scoped, "hoyoung")
    assert client.get("/api/projects/EXMP/trace-spans").json() == {
        "commit_hash": None, "spans": [], "infra": []
    }  # fmt: skip


def test_upload_list_get_coverage_delete(client: TestClient, scoped: Session) -> None:
    _seed(scoped, GRAPH)
    login(client, scoped, "hoyoung")
    raw = _token(scoped)
    client.cookies.clear()
    h = {"Authorization": f"Bearer {raw}"}
    r = client.post("/api/projects/EXMP/traces", json=record("k1"), headers=h)
    assert r.status_code == 201 and r.json()["trace_key"] == "k1" and r.json()["event_count"] == 3
    again = client.post("/api/projects/EXMP/traces", json=record("k1"), headers=h)
    assert again.status_code == 200 and again.json()["id"] == r.json()["id"]
    # 목록·하나·커버리지·지우기는 세션
    assert client.get("/api/projects/EXMP/traces", headers=h).status_code == 401
    login(client, scoped, "hoyoung")
    lst = client.get("/api/projects/EXMP/traces").json()
    assert [b["trace_key"] for b in lst] == ["k1"] and "record" not in lst[0]
    one = client.get(f"/api/projects/EXMP/traces/{lst[0]['id']}").json()
    assert one["record"]["id"] == "k1" and one["record"]["commit"] == "a" * 40
    cov = client.get("/api/projects/EXMP/traces/coverage").json()
    assert cov == {"traces": 1, "keys": ["app/a.py:3", "app/b.py:9"],
                   "infra": [{"kind": "db", "target": "db:5432"}]}  # fmt: skip
    assert client.delete(f"/api/projects/EXMP/traces/{lst[0]['id']}").status_code == 204
    assert client.get(f"/api/projects/EXMP/traces/{lst[0]['id']}").status_code == 404
    client.post("/api/projects/EXMP/traces", json=record("k2"))
    assert client.delete("/api/projects/EXMP/traces").json() == {"deleted": 1}


def test_upload_checks(client_raw: TestClient, scoped: Session, monkeypatch) -> None:
    _seed(scoped, GRAPH)
    login(client_raw, scoped, "hoyoung")
    bad = client_raw.post("/api/projects/EXMP/traces", json=record(events=[
        {"i": 0, "parent": 3, "fn": "a", "t0": 0}]))  # fmt: skip
    assert bad.status_code == 422 and bad.json()["type"] == "urn:syncdoc:trace-invalid"
    assert bad.json()["reason"] == "events[0] — 부모가 없다"
    when = client_raw.post("/api/projects/EXMP/traces", json=record(startedAt="2026-13-01T00:00:00"))
    assert when.status_code == 422 and when.json()["reason"] == "startedAt — 시각이 아니다"
    shape = client_raw.post("/api/projects/EXMP/traces", json=record(kind="other"))
    assert shape.status_code == 422 and shape.json()["type"] == "urn:syncdoc:invalid-request"
    monkeypatch.setattr(trace_service, "MAX_BYTES", 100)
    from app.web.routers import traces as traces_router

    monkeypatch.setattr(traces_router, "MAX_BYTES", 100)
    big = client_raw.post("/api/projects/EXMP/traces", content=json.dumps(record("big")))
    assert big.status_code == 413 and big.json()["type"] == "urn:syncdoc:trace-invalid"
    monkeypatch.undo()
    # 남의 프로젝트 — 토큰이어도 없는 것과 같다
    login(client_raw, scoped, "minjun")
    other = _token(scoped, "minjun")
    client_raw.cookies.clear()
    r = client_raw.post("/api/projects/EXMP/traces", json=record("x"),
                        headers={"Authorization": f"Bearer {other}"})  # fmt: skip
    assert r.status_code == 404 and r.json()["resource"] == "project"
    login(client_raw, scoped, "minjun")
    assert client_raw.get("/api/projects/EXMP/traces").status_code == 404
    assert client_raw.get("/api/projects/EXMP/traces/coverage").status_code == 404
    assert client_raw.get("/api/projects/EXMP/trace-spans").status_code == 404
