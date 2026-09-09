"""SYNC-MS-009 테스트 관점 — github 어댑터. GitHub 응답은 httpx.MockTransport로 모킹."""

import hashlib
import hmac

import httpx
import pytest

from syncdoc.config import settings
from syncdoc.core.errors import Unauthorized
from syncdoc.infra import github as gh


def _sig(body: bytes, secret: str = settings.WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── verify_signature ──
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
    assert await gh.exchange_code("the-code") == "gho_abc"
    req = calls[0]
    assert req.method == "POST" and str(req.url) == "https://github.com/login/oauth/access_token"
    assert req.headers["accept"] == "application/json"
    assert b"client_id=test-client-id" in req.content and b"code=the-code" in req.content
    assert b"client_secret=test-client-secret" in req.content


async def test_exchange_code_without_token_is_unauthorized(mock_github) -> None:
    mock_github(lambda r: httpx.Response(200, json={"error": "bad_verification_code"}))
    with pytest.raises(Unauthorized):
        await gh.exchange_code("bad")
    mock_github(lambda r: httpx.Response(500, text="oops"))
    with pytest.raises(Unauthorized):
        await gh.exchange_code("bad")


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
