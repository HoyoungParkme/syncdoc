"""SYNC-MS-009 테스트 관점 — llm 어댑터. 모델 응답은 httpx.MockTransport로 모킹."""

import json

import httpx
import pytest

from app.config import settings
from app.core.errors import LlmNotConfigured, LlmUnavailable
from app.infra import llm


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch):
    """infra/llm의 httpx.AsyncClient를 MockTransport로. install(handler) → 요청 기록 list."""
    real = httpx.AsyncClient
    calls: list[httpx.Request] = []

    def install(handler):
        def h(req: httpx.Request) -> httpx.Response:
            calls.append(req)
            return handler(req)

        monkeypatch.setattr(
            llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(h), **kw)
        )
        return calls

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_MODEL", "test-model")
    return install


def _ok(text: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": text}}]}
    )


async def test_without_key_blocks_before_network(mock_llm, monkeypatch) -> None:
    calls = mock_llm(lambda r: _ok("x"))
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    with pytest.raises(LlmNotConfigured):
        await llm.ask("sys", [{"role": "user", "text": "q"}])
    assert calls == []


async def test_sends_system_and_messages_as_is_and_returns_content(mock_llm) -> None:
    calls = mock_llm(lambda r: _ok("답이다"))
    msgs = [{"role": "user", "text": "첫 질문"}, {"role": "assistant", "text": "첫 답"}]
    msgs.append({"role": "user", "text": "둘째 질문"})
    assert await llm.ask("지시문", msgs) == "답이다"
    req = calls[0]
    assert req.method == "POST" and str(req.url) == settings.LLM_API_URL
    assert req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["model"] == "test-model"
    assert body["messages"] == [{"role": "system", "content": "지시문"}] + [
        {"role": m["role"], "content": m["text"]} for m in msgs
    ]
    assert "stream" not in body


async def test_429_and_5xx_fold_into_unavailable(mock_llm) -> None:
    mock_llm(lambda r: httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(LlmUnavailable) as e:
        await llm.ask("s", [])
    assert e.value.extra["reason"] == "HTTP 429"
    mock_llm(lambda r: httpx.Response(500, text="oops"))
    with pytest.raises(LlmUnavailable):
        await llm.ask("s", [])


async def test_timeout_and_bad_shape_fold_into_unavailable(mock_llm) -> None:
    def slow(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    mock_llm(slow)
    with pytest.raises(LlmUnavailable) as e:
        await llm.ask("s", [])
    assert e.value.extra["reason"] == "ReadTimeout"
    mock_llm(lambda r: httpx.Response(200, json={"nope": 1}))
    with pytest.raises(LlmUnavailable):
        await llm.ask("s", [])
