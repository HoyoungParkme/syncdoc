"""SYNC-SEQ-001#SEQ-C2 — MCP 인증. Bearer 토큰 없음·오타·폐기 → 401 problem+json. 유효하면 MCP 앱에 닿는다."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.account.service import AccountService
from tests.core.account.test_service import make_user

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
HDR = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def test_mcp_requires_valid_bearer(client: TestClient, db_session: Session, scoped) -> None:
    u = make_user(db_session)
    issued = AccountService(db_session).issue_token(u, "cc")
    r = client.post("/mcp", json=INIT, headers=HDR)
    assert r.status_code == 401 and r.json()["type"] == "urn:syncdoc:unauthorized"
    r = client.post("/mcp", json=INIT, headers={**HDR, "Authorization": "Bearer nope"})
    assert r.status_code == 401
    AccountService(db_session).revoke_token(u, issued.token.id)
    r = client.post("/mcp", json=INIT, headers={**HDR, "Authorization": f"Bearer {issued.raw}"})
    assert r.status_code == 401
    live = AccountService(db_session).issue_token(u, "cc2")
    r = client.post("/mcp", json=INIT, headers={**HDR, "Authorization": f"Bearer {live.raw}"})
    assert r.status_code == 200 and "serverInfo" in r.text  # MCP initialize 응답
    assert client.get("/health").status_code == 200  # /mcp 밖은 인증 없음
