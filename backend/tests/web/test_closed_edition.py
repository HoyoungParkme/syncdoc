"""폐쇄망판 웹 — SYNC-SEQ-001#SEQ-C3 · SYNC-API-001 1장·3.10 · SYNC-PRD-001#R15 (카드 BC).

로그인 없이 로컬 사용자 · Host·Origin 가드(forbidden-origin) · GitHub 로그인·통지 경로 404 ·
이미지 안 규약 사본(/specs). 인터넷판은 그대로인지도 본다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from tests.conftest import _client


@pytest.fixture
def closed(scoped: Session, monkeypatch: pytest.MonkeyPatch):
    """EDITION=closed로 앱을 켠다. 켜질 때 만드는 로컬 사용자는 테스트 트랜잭션 안에 남는다(scoped).

    TestClient의 Host는 `testserver`라 PUBLIC_BASE_URL로 허용 목록에 넣는다.
    """
    monkeypatch.setattr(settings, "EDITION", "closed")
    monkeypatch.setattr(settings, "LOCAL_LOGIN", "local")
    monkeypatch.setattr(settings, "LOCAL_NAME", "박호영")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://testserver")
    yield from _client(scoped, raise_server_exceptions=False)


def test_starts_with_one_local_user_and_needs_no_login(closed: TestClient, scoped: Session) -> None:
    rows = scoped.execute(text("SELECT github_login, display_name, kind FROM users")).all()
    assert rows == [("local", "박호영", "local")]  # 켜질 때 만들었다 (MS-006 ensure_local_user)
    me = closed.get("/api/me")
    assert me.status_code == 200  # 세션 없이
    body = me.json()
    assert (body["github_login"], body["edition"], body["storage_modes"]) == (
        "local",
        "closed",
        ["server"],
    )
    # 토큰도 로그인 없이 — MCP·git은 이 토큰으로 (SEQ-C2·29)
    issued = closed.post("/api/me/tokens", json={"label": "노트북"})
    assert issued.status_code == 201 and issued.json()["token"].startswith("syncdoc_pat_")


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost", "[::1]:8000", "testserver"])
def test_hosts_on_the_list_pass(closed: TestClient, host: str) -> None:
    assert closed.get("/api/me", headers={"host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.evil.example", "", "[::1"])
def test_other_hosts_are_forbidden_origin(closed: TestClient, host: str) -> None:
    """다른 이름으로 들어오는 요청(DNS rebinding) — 이름을 127.0.0.1로 풀어도 Host가 그 이름이다."""
    r = closed.get("/api/me", headers={"host": host})
    assert r.status_code == 403
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["type"] == "urn:syncdoc:forbidden-origin" and r.json()["host"] == host


def test_writes_from_another_site_are_forbidden_origin(closed: TestClient) -> None:
    """다른 사이트의 폼·fetch(CSRF) — 쓰기 요청의 Origin이 이 서버가 아니면 403."""
    r = closed.post("/api/me/tokens", json={"label": "x"}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["origin"] == "http://evil.example"
    ok = closed.post("/api/me/tokens", json={"label": "x"}, headers={"origin": "http://testserver"})
    assert ok.status_code == 201  # 같은 곳
    # 읽기는 Origin을 보지 않는다 · 토큰 입구(/mcp)는 토큰이 사람을 정한다 — 가드가 아니라 401
    assert closed.get("/api/me", headers={"origin": "http://evil.example"}).status_code == 200
    mcp = closed.post("/mcp", json={}, headers={"origin": "http://evil.example"})
    assert mcp.status_code == 401


def test_github_login_and_hook_paths_do_not_exist(closed: TestClient) -> None:
    for method, path in (
        ("GET", "/auth/github"),
        ("GET", "/auth/github/callback?code=x&state=y"),
        ("POST", "/hooks/github"),
    ):
        r = closed.request(method, path)
        assert r.status_code == 404 and r.json()["type"] == "urn:syncdoc:not-found", path


def test_internet_edition_is_untouched(client: TestClient) -> None:
    """인터넷판 — 가드가 그대로 지나간다. 로그인 없으면 401, GitHub 로그인 경로가 있다."""
    assert client.get("/api/me", headers={"host": "evil.example"}).status_code == 401
    assert client.get("/auth/github", follow_redirects=False).status_code == 302


# ── GET /specs/{path} (API-001 3.10) ──
def test_specs_serves_std_and_templates_as_text(client: TestClient) -> None:
    r = client.get("/specs/STD/SYNC-STD-001.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "doc_id: SYNC-STD-001" in r.text
    listing = client.get("/specs/_templates")  # README가 슬래시 없이 건다
    assert listing.status_code == 200 and 'href="/specs/_templates/PRD.md"' in listing.text
    assert "doc_id:" in client.get("/specs/_templates/PRD.md").text


@pytest.mark.parametrize(
    "path",
    [
        "/specs",
        "/specs/",
        "/specs/10-MS/SYNC-MS-001.md",  # STD·_templates 밖
        "/specs/STD/../10-MS/SYNC-MS-001.md",
        "/specs/STD/%2e%2e/%2e%2e/backend/pyproject.toml",
        "/specs/STD/nothing.md",
    ],
)
def test_specs_outside_the_two_folders_is_not_found(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 404 and r.json()["type"] == "urn:syncdoc:not-found", path
