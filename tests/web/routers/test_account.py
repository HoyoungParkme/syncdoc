"""SYNC-API-001 3.1 인증 · SYNC-SEQ-001#SEQ-8.

/auth/github 시작 · /auth/logout · 세션 · problem+json.
"""

import base64
import json
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService
from syncdoc.db import get_session
from syncdoc.main import app
from syncdoc.web import auth
from tests.core.account.test_service import make_user


def session_of(client: TestClient) -> dict:
    """서명 쿠키의 payload(base64 JSON). 서명은 서버가 검증한다."""
    raw = client.cookies.get(auth.SESSION_COOKIE)
    assert raw, "세션 쿠키 없음"
    return json.loads(base64.b64decode(raw.split(".")[0] + "=="))


# 테스트 전용 입구 — 콜백(보류)을 대신해 auth.login으로 세션을 만든다 · current_user 확인
@app.get("/__test/login/{login}", status_code=204)
def _test_login(login: str, request: Request, session: Session = Depends(get_session)) -> None:
    user = AccountService(session).user_by_login(login)
    assert user is not None
    auth.login(request, user)


@app.get("/__test/whoami")
def _test_whoami(user: User = Depends(auth.current_user)) -> dict[str, str]:
    return {"login": user.github_login}


# ── GET /auth/github ──
def test_auth_github_redirects_to_consent_and_keeps_state_in_session(client: TestClient) -> None:
    r = client.get("/auth/github", params={"next": "/p/SYNC"}, follow_redirects=False)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == auth.AUTHORIZE_URL
    q = parse_qs(url.query)
    assert q["client_id"] == ["test-client-id"] and q["scope"] == ["repo"]
    sess = session_of(client)
    assert sess["oauth_state"] == q["state"][0] and len(q["state"][0]) >= 16
    assert sess["oauth_next"] == "/p/SYNC"


def test_auth_github_rejects_external_next(client: TestClient) -> None:
    assert client.get("/auth/github", params={"next": "https://evil"}).status_code == 422
    assert client.get("/auth/github", params={"next": "//evil"}).status_code == 422
    assert client.get("/auth/github", follow_redirects=False).status_code == 302


# ── 세션 · current_user · problem+json ──
def test_current_user_401_problem_json_without_session(client: TestClient) -> None:
    r = client.get("/__test/whoami")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json() == {
        "type": "urn:syncdoc:unauthorized",
        "title": "unauthorized",
        "status": 401,
        "detail": "세션 없음",
    }


def test_login_session_then_logout_clears(client: TestClient, db_session: Session) -> None:
    make_user(db_session, login="hoyoung")
    client.get("/auth/github", follow_redirects=False)
    assert client.get("/__test/login/hoyoung").status_code == 204
    assert session_of(client) == {"login": "hoyoung"}  # OAuth 임시값은 지워진다
    assert client.get("/__test/whoami").json() == {"login": "hoyoung"}
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/__test/whoami").status_code == 401


def test_session_of_unknown_user_is_401(client: TestClient, db_session: Session) -> None:
    make_user(db_session, login="gone")
    client.get("/__test/login/gone")
    db_session.execute(__import__("sqlalchemy").text("DELETE FROM users WHERE github_login='gone'"))
    assert client.get("/__test/whoami").status_code == 401
