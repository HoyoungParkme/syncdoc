"""SYNC-API-001 2장 — 표에 없는 예외도 problem+json으로 나간다 (#7)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.web.routers import projects
from tests.web.conftest import login


def test_unhandled_exception_is_problem_json(
    client_raw: TestClient, scoped: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TestClient는 기본으로 서버 예외를 다시 던진다 — 실제 응답을 봐야 하므로 끈 클라이언트를
    # 쓴다. 여기서 두 번째 TestClient를 열면 전역 app의 lifespan이 두 번 드나들며 MCP
    # 세션 매니저가 취소된다 — 그 뒤 테스트들이 오염된 앱 위에서 돈다 (#17)
    login(client_raw, scoped)

    async def boom() -> None:
        raise RuntimeError("설계에 없는 예외")

    monkeypatch.setattr(projects.queries, "project_summary", boom)
    r = client_raw.get("/api/projects")

    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "urn:syncdoc:internal"
    assert body["status"] == 500
    # 예외 종류·메시지·스택은 본문에 안 담는다 — 로그로만 (내부 구조가 새어 나간다)
    assert "설계에 없는 예외" not in body["detail"]
    assert "RuntimeError" not in body["detail"]
