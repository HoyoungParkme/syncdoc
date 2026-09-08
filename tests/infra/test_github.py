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


@pytest.fixture
def mock_github(monkeypatch: pytest.MonkeyPatch):
    """gh 모듈의 httpx.AsyncClient를 MockTransport로 바꾼다. handler(request) -> Response."""
    real = httpx.AsyncClient
    calls: list[httpx.Request] = []

    def install(handler):
        def h(req: httpx.Request) -> httpx.Response:
            calls.append(req)
            return handler(req)

        monkeypatch.setattr(
            gh.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(h), **kw)
        )
        return calls

    return install


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
