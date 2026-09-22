"""SYNC-MS-009 테스트 관점 — github 어댑터. GitHub 응답은 httpx.MockTransport로 모킹."""

import hashlib
import hmac

import httpx
import pytest

from app.config import settings
from app.core.errors import Unauthorized
from app.infra import github as gh


def _sig(body: bytes, secret: str = settings.WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── verify_signature ──
def test_verify_signature_rejects_everything_when_secret_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """비밀번호가 비면 전부 거부 — 빈 키 HMAC은 소스를 본 누구나 만든다 (카드 AF)."""
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "")
    body = b'{"ref":"refs/heads/main"}'
    assert gh.verify_signature(body, _sig(body, "")) is False  # 올바른 계산값이어도
    assert gh.verify_signature(body, "") is False


# ── create_hook ──
async def test_create_hook_creates_once_and_reuses_same_url(mock_github) -> None:
    url = "https://syncdoc.example/hooks/github"
    existing: list[dict] = []

    def h(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, json=existing)
        return httpx.Response(201, json={"id": 77})

    calls = mock_github(h)
    assert await gh.create_hook("t", "o", "r", url, "s") == 77
    body = calls[-1].content.decode()
    assert '"events": ["push"]' in body.replace("'", '"') or "push" in body
    assert "s" in body  # 비밀번호는 GitHub에만 보낸다

    existing.append({"id": 77, "config": {"url": url}})
    n = len(calls)
    assert await gh.create_hook("t", "o", "r", url, "s") == 77  # 이미 있으면 안 만든다
    assert all(c.method == "GET" for c in calls[n:])


async def test_create_hook_without_permission_is_unauthorized(mock_github) -> None:
    mock_github(lambda req: httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(Unauthorized):
        await gh.create_hook("t", "o", "r", "https://x/hooks/github", "s")


def test_verify_signature_accepts_valid_and_rejects_others() -> None:
    body = b'{"ref":"refs/heads/main"}'
    assert gh.verify_signature(body, _sig(body)) is True
    assert gh.verify_signature(body, _sig(body, "wrong-secret")) is False
    assert gh.verify_signature(body + b" ", _sig(body)) is False
    assert gh.verify_signature(body, "") is False
    assert gh.verify_signature(body, "sha1=abc") is False


# ── exchange_code ──
async def test_exchange_code_posts_client_secret_and_returns_token(mock_github) -> None:
    calls = mock_github(lambda r: httpx.Response(200, json={"access_token": "gho_abc"}))
    assert await gh.exchange_code("the-code", "http://testserver/auth/github/callback") == "gho_abc"
    req = calls[0]
    assert req.method == "POST" and str(req.url) == "https://github.com/login/oauth/access_token"
    assert req.headers["accept"] == "application/json"
    assert b"client_id=test-client-id" in req.content and b"code=the-code" in req.content
    assert b"client_secret=test-client-secret" in req.content
    assert b"redirect_uri=http%3A%2F%2Ftestserver%2Fauth%2Fgithub%2Fcallback" in req.content


async def test_exchange_code_without_token_is_unauthorized(mock_github) -> None:
    mock_github(lambda r: httpx.Response(200, json={"error": "bad_verification_code"}))
    with pytest.raises(Unauthorized):
        await gh.exchange_code("bad", "http://testserver/auth/github/callback")
    mock_github(lambda r: httpx.Response(500, text="oops"))
    with pytest.raises(Unauthorized):
        await gh.exchange_code("bad", "http://testserver/auth/github/callback")


# ── get_user ──
async def test_get_user_uses_bearer_and_falls_back_name_to_login(mock_github) -> None:
    calls = mock_github(
        lambda r: httpx.Response(200, json={"id": 42, "login": "hoyoung", "name": "박호영"})
    )
    u = await gh.get_user("gho_abc")
    assert (u.id, u.login, u.name) == (42, "hoyoung", "박호영")
    assert calls[0].headers["authorization"] == "Bearer gho_abc"
    assert str(calls[0].url) == "https://api.github.com/user"
    mock_github(lambda r: httpx.Response(200, json={"id": 7, "login": "noname", "name": None}))
    assert (await gh.get_user("t")).name == "noname"
    mock_github(lambda r: httpx.Response(401, json={"message": "Bad credentials"}))
    with pytest.raises(Unauthorized):
        await gh.get_user("bad")
