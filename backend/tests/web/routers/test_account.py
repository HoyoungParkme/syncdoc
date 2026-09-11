"""SYNC-API-001 3.1 인증 · SYNC-SEQ-001#SEQ-8.

/auth/github 시작 · /auth/logout · 세션 · problem+json.
"""

import base64
import json
from urllib.parse import parse_qs, urlparse

import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.account.service import AccountService
from app.web import auth
from tests.conftest import github_ok
from tests.core.account.test_service import make_user


def session_of(client: TestClient) -> dict:
    """서명 쿠키의 payload(base64 JSON). 서명은 서버가 검증한다."""
    raw = client.cookies.get(auth.SESSION_COOKIE)
    assert raw, "세션 쿠키 없음"
    return json.loads(base64.b64decode(raw.split(".")[0] + "=="))


# ── GET /auth/github ──
def test_auth_github_redirects_to_consent_and_keeps_state_in_session(client: TestClient) -> None:
    r = client.get("/auth/github", params={"next": "/p/SYNC"}, follow_redirects=False)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == auth.AUTHORIZE_URL
    q = parse_qs(url.query)
    assert q["client_id"] == ["test-client-id"] and q["scope"] == ["repo"]
    assert q["redirect_uri"] == ["http://testserver/auth/github/callback"]  # SEQ-8
    sess = session_of(client)
    assert sess["oauth_state"] == q["state"][0] and len(q["state"][0]) >= 16
    assert sess["oauth_next"] == "/p/SYNC"


def test_callback_url_uses_public_base_url_for_that_host(client: TestClient, monkeypatch) -> None:
    """인프라 5장 — 터널 Host로 들어오면 PUBLIC_BASE_URL(https)을, 아니면 요청 주소를 쓴다."""
    from app.config import settings

    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://xxx.trycloudflare.com")
    r = client.get(
        "/auth/github", follow_redirects=False, headers={"Host": "xxx.trycloudflare.com"}
    )
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["redirect_uri"] == ["https://xxx.trycloudflare.com/auth/github/callback"]
    r = client.get("/auth/github", follow_redirects=False)  # 다른 Host면 요청에서
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["redirect_uri"] == ["http://testserver/auth/github/callback"]


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
    db_session.execute(sqlalchemy.text("DELETE FROM users WHERE github_login='gone'"))
    assert client.get("/__test/whoami").status_code == 401


# ── E2E: SEQ-8 GitHub로 로그인한다 (GitHub 응답 모킹) ──
def test_oauth_e2e_login_then_session_then_logout(
    client: TestClient, db_session: Session, mock_github
) -> None:
    calls = mock_github(github_ok(42, "hoyoung", "박호영"))
    r = client.get("/auth/github", params={"next": "/p/SYNC"}, follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get(
        "/auth/github/callback", params={"code": "the-code", "state": state}, follow_redirects=False
    )
    assert r.status_code == 302 and r.headers["location"] == "/p/SYNC"
    assert [c.url.path for c in calls] == ["/login/oauth/access_token", "/user"]
    assert session_of(client) == {"login": "hoyoung"}
    assert client.get("/__test/whoami").json() == {"login": "hoyoung"}
    row = db_session.execute(
        sqlalchemy.text("SELECT github_user_id, github_token_encrypted FROM users")
    ).one()
    assert row[0] == 42 and row[1] is not None and b"gho_" not in bytes(row[1])
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/__test/whoami").status_code == 401


def test_oauth_callback_state_mismatch_is_401(client: TestClient, mock_github) -> None:
    calls = mock_github(github_ok())
    client.get("/auth/github", follow_redirects=False)
    r = client.get("/auth/github/callback", params={"code": "c", "state": "wrong"})
    assert r.status_code == 401 and r.json()["type"] == "urn:syncdoc:unauthorized"
    assert calls == []  # GitHub를 부르기 전에 거부
    r = client.get("/auth/github/callback", params={"code": "c", "state": ""})
    assert r.status_code == 401


def test_oauth_callback_without_next_goes_root(client: TestClient, mock_github) -> None:
    mock_github(github_ok())
    r = client.get("/auth/github", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get(
        "/auth/github/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert r.status_code == 302 and r.headers["location"] == "/"


# ── /api/me · /api/me/tokens ──
def test_me_and_tokens_issue_list_revoke(client: TestClient, db_session: Session) -> None:
    from tests.web.conftest import login

    assert client.get("/api/me").status_code == 401
    u = login(client, db_session)
    me = client.get("/api/me").json()
    assert (me["id"], me["github_login"], me["display_name"]) == (
        u.id,
        "hoyoung",
        "hoyoung",
    ) and "created_at" in me
    r = client.post("/api/me/tokens", json={"label": "Claude Code 노트북"})
    assert r.status_code == 201
    issued = r.json()
    assert issued["token"].startswith("syncdoc_pat_") and issued["label"] == "Claude Code 노트북"
    assert (
        issued["expires_at"] is None and issued["revoked_at"] is None and "token_hash" not in issued
    )
    lst = client.get("/api/me/tokens").json()
    assert [t["label"] for t in lst] == ["Claude Code 노트북"] and "token" not in lst[0]
    assert client.delete(f"/api/me/tokens/{issued['id']}").status_code == 204
    assert client.get("/api/me/tokens").json()[0]["revoked_at"] is not None  # 폐기돼도 행은 남는다
    assert client.delete("/api/me/tokens/999999").status_code == 404
    assert AccountService(db_session).authenticate_token(issued["token"]) is None


# ── /api/me/emails (#34) ──
def test_commit_emails_add_list_remove(client: TestClient, db_session: Session) -> None:
    from tests.web.conftest import login

    assert client.get("/api/me/emails").status_code == 401
    login(client, db_session)
    assert client.get("/api/me/emails").json() == []
    r = client.post("/api/me/emails", json={"email": "Me@Example.COM"})
    assert r.status_code == 201 and r.json()["email"] == "me@example.com"  # 소문자로
    row = r.json()
    # 같은 이메일을 두 번 → 같은 행. 두 번 눌러도 오류가 아니다
    assert client.post("/api/me/emails", json={"email": "me@example.com"}).json()["id"] == row["id"]
    assert [e["email"] for e in client.get("/api/me/emails").json()] == ["me@example.com"]
    assert client.post("/api/me/emails", json={"email": "notanemail"}).status_code == 422
    assert client.delete(f"/api/me/emails/{row['id']}").status_code == 204
    assert client.get("/api/me/emails").json() == []
    assert client.delete("/api/me/emails/999999").status_code == 404


def test_commit_email_taken_by_someone_else_is_409(client: TestClient, db_session: Session) -> None:
    from tests.web.conftest import login

    other = make_user(db_session, login="somebody")
    AccountService(db_session).add_commit_email(other, "shared@example.com")
    db_session.flush()
    login(client, db_session)
    r = client.post("/api/me/emails", json={"email": "shared@example.com"})
    assert r.status_code == 409
    assert r.json()["type"] == "urn:syncdoc:email-taken"
    assert r.json()["email"] == "shared@example.com"
    # 남의 이메일은 목록에도 안 보인다
    assert client.get("/api/me/emails").json() == []
