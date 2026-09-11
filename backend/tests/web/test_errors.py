"""SYNC-API-001 2장 — 표에 없는 예외도 problem+json으로 나간다 (#7)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.web.routers import projects
from tests.web.conftest import login


def test_unhandled_exception_is_problem_json(
    client: TestClient, scoped: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client, scoped)

    async def boom() -> None:
        raise RuntimeError("설계에 없는 예외")

    monkeypatch.setattr(projects.queries, "project_summary", boom)
    # TestClient는 기본으로 서버 예외를 다시 던진다 — 실제 응답을 봐야 하므로 끈다
    app.dependency_overrides[get_session] = lambda: scoped
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies = client.cookies
        r = c.get("/api/projects")

    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "urn:syncdoc:internal"
    assert body["status"] == 500
    # 예외 종류·메시지·스택은 본문에 안 담는다 — 로그로만 (내부 구조가 새어 나간다)
    assert "설계에 없는 예외" not in body["detail"]
    assert "RuntimeError" not in body["detail"]
