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


def test_successful_call_commits_last_used_at(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    """#49 — v1은 토큰에 만료가 없어 이 값이 「아직 쓰는 토큰인가」의 유일한 단서다 (INFRA 9장).

    예전에는 `authenticate_token`이 flush만 하고 `session_scope`가 커밋 없이 닫아
    그대로 롤백됐다 — 실물에서 25번 넘게 부른 토큰도 `last_used_at`이 NULL이었다.

    **커밋 자체를 본다.** 테스트는 한 세션을 공유하므로 flush만 해도 값이 보인다 —
    그래서 값만 확인하면 이 회귀를 못 잡는다.
    """
    from contextlib import contextmanager

    from app import db

    commits: list[int] = []

    @contextmanager
    def _scope():
        real = db_session.commit
        db_session.commit = lambda: commits.append(1)  # type: ignore[method-assign]
        try:
            yield db_session
        finally:
            db_session.commit = real  # type: ignore[method-assign]

    monkeypatch.setattr(db, "session_scope", _scope)
    u = make_user(db_session, login="tokenuser")
    live = AccountService(db_session).issue_token(u, "cc3")
    assert live.token.last_used_at is None

    r = client.post("/mcp", json=INIT, headers={**HDR, "Authorization": f"Bearer {live.raw}"})

    assert r.status_code == 200
    assert commits, "인증이 커밋하지 않으면 last_used_at이 롤백된다"
    assert AccountService(db_session).list_tokens(u)[-1].last_used_at is not None
