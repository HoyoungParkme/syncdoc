"""SYNC-MS-009 테스트 관점 — github 어댑터. GitHub 응답은 httpx.MockTransport로 모킹."""

import hashlib
import hmac
import json

import httpx
import pytest

from app.config import settings
from app.core.errors import RepoCreateFailed, Unauthorized
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


# ── create_repo (#310 · 카드 BS) ──
CLONE = "https://github.com/o/r.git"


def _no_repo_then_created(req: httpx.Request) -> httpx.Response:
    if req.method == "GET":
        return httpx.Response(404, json={"message": "Not Found"})
    return httpx.Response(201, json={"clone_url": CLONE})


@pytest.mark.parametrize("private", [True, False])
async def test_create_repo_posts_the_callers_visibility(
    mock_github, monkeypatch: pytest.MonkeyPatch, private: bool
) -> None:
    """공개 여부는 부르는 쪽이 고른 그대로 — 서버 설정을 보지 않는다(기본은 init_project가 채운다)."""
    monkeypatch.setattr(settings, "GITHUB_REPO_PRIVATE", not private)
    calls = mock_github(_no_repo_then_created)
    assert await gh.create_repo("t", "o", "r", private) == CLONE
    body = json.loads(calls[-1].content)
    assert calls[-1].method == "POST" and body["private"] is private and body["auto_init"] is False


@pytest.mark.parametrize("private", [False, True])
async def test_create_repo_keeps_existing_repo_and_warns_if_public(
    mock_github, caplog: pytest.LogCaptureFixture, private: bool
) -> None:
    """이미 있으면 만들지도 공개 여부를 바꾸지도 않는다 — 공개면 경고 로그만."""
    calls = mock_github(
        lambda req: httpx.Response(200, json={"clone_url": CLONE, "private": private})
    )
    with caplog.at_level("WARNING", logger="app.infra.github"):
        assert await gh.create_repo("t", "o", "r", True) == CLONE
    assert [c.method for c in calls] == ["GET"]
    warned = any("o/r" in r.getMessage() and "공개" in r.getMessage() for r in caplog.records)
    assert warned is (not private)


async def test_create_repo_forbidden_asks_to_log_in_again(mock_github) -> None:
    """옛 public_repo 토큰은 비공개 생성이 거절된다 — 다시 로그인을 말한다."""

    def h(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(403, json={"message": "Forbidden"})

    mock_github(h)
    with pytest.raises(RepoCreateFailed) as ei:
        await gh.create_repo("t", "o", "r", True)
    assert "403" in str(ei.value) and "다시 로그인" in str(ei.value)


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
        lambda r: httpx.Response(200, json={"id": 42, "login": "hoyoung", "name": "홍길동"})
    )
    u = await gh.get_user("gho_abc")
    assert (u.id, u.login, u.name) == (42, "hoyoung", "홍길동")
    assert calls[0].headers["authorization"] == "Bearer gho_abc"
    assert str(calls[0].url) == "https://api.github.com/user"
    mock_github(lambda r: httpx.Response(200, json={"id": 7, "login": "noname", "name": None}))
    assert (await gh.get_user("t")).name == "noname"
    mock_github(lambda r: httpx.Response(401, json={"message": "Bad credentials"}))
    with pytest.raises(Unauthorized):
        await gh.get_user("bad")


# ── delete_hook (카드 BQ) ──
@pytest.mark.parametrize("status", [204, 404])
async def test_delete_hook_done_when_deleted_or_already_gone(mock_github, status: int) -> None:
    calls = mock_github(lambda req: httpx.Response(status))
    await gh.delete_hook("t", "o", "r", 77)
    assert [(c.method, c.url.path) for c in calls] == [("DELETE", "/repos/o/r/hooks/77")]


async def test_delete_hook_forbidden_is_unauthorized(mock_github) -> None:
    mock_github(lambda req: httpx.Response(403, json={"message": "Forbidden"}))
    with pytest.raises(Unauthorized) as ei:
        await gh.delete_hook("t", "o", "r", 77)
    assert "403" in str(ei.value)


# ── repo_archived (카드 BT) ──
@pytest.mark.parametrize("archived", [True, False])
async def test_repo_archived_reads_the_flag(mock_github, archived: bool) -> None:
    calls = mock_github(lambda req: httpx.Response(200, json={"archived": archived}))
    assert await gh.repo_archived("t", "o", "r") is archived
    assert [(c.method, c.url.path) for c in calls] == [("GET", "/repos/o/r")]


async def test_repo_archived_unreachable_is_unauthorized(mock_github) -> None:
    """없거나 권한이 없으면 — GitHub은 권한 없는 비공개 저장소도 404로 답한다."""
    mock_github(lambda req: httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(Unauthorized) as ei:
        await gh.repo_archived("t", "o", "r")
    assert "404" in str(ei.value)
