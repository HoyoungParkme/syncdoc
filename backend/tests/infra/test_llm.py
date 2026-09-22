"""SYNC-MS-009 테스트 관점 — llm 어댑터(카드 Y: step). 모델 응답은 httpx.MockTransport로 모킹."""

import json

import httpx
import pytest

from app.config import settings
from app.core.errors import LlmNotConfigured, LlmUnavailable
from app.core.types import ToolCall, ToolSpec
from app.infra import llm

TOOLS = [
    ToolSpec(
        "get_item",
        "항목 하나",
        {"type": "object", "properties": {"doc_id": {"type": "string"}}, "required": ["doc_id"]},
    )
]


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


def _text(text: str, usage: dict | None = None) -> httpx.Response:
    body = {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]
    }
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def _calls(arguments: str, content: str | None = None) -> httpx.Response:
    msg = {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_item", "arguments": arguments},
            }
        ],
    }
    return httpx.Response(
        200,
        json={
            "choices": [{"message": msg, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )


async def test_without_key_blocks_before_network(mock_llm, monkeypatch) -> None:
    calls = mock_llm(lambda r: _text("x"))
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    with pytest.raises(LlmNotConfigured):
        await llm.step("sys", [{"role": "user", "text": "q"}], TOOLS)
    assert calls == []


async def test_sends_tools_and_conversation_in_wire_shape(mock_llm) -> None:
    calls = mock_llm(lambda r: _text("답이다"))
    msgs = [
        {"role": "user", "text": "첫 질문"},
        {
            "role": "assistant",
            "text": "",
            "tool_calls": [ToolCall("c1", "get_item", {"doc_id": "D"})],
        },
        {"role": "tool", "tool_call_id": "c1", "text": '{"body": "본문"}'},
        {"role": "user", "text": "둘째 질문"},
    ]
    got = await llm.step("지시문", msgs, TOOLS)
    assert got.text == "답이다" and got.tool_calls == [] and got.usage.prompt_tokens == 0
    req = calls[0]
    assert req.method == "POST" and str(req.url) == settings.LLM_API_URL
    assert req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["model"] == "test-model" and body["tool_choice"] == "auto"
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_item",
                "description": "항목 하나",
                "parameters": TOOLS[0].parameters,
            },
        }
    ]
    assert body["messages"][0] == {"role": "system", "content": "지시문"}
    assert body["messages"][1] == {"role": "user", "content": "첫 질문"}
    assert body["messages"][2] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_item", "arguments": '{"doc_id": "D"}'},
            }
        ],
    }
    assert body["messages"][3] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": '{"body": "본문"}',
    }
    assert "stream" not in body


async def test_tool_choice_none_is_sent_and_no_tools_means_no_tools_key(mock_llm) -> None:
    calls = mock_llm(lambda r: _text("마무리"))
    await llm.step("s", [], TOOLS, tool_choice="none")
    assert json.loads(calls[0].content)["tool_choice"] == "none"
    await llm.step("s", [], [])
    body = json.loads(calls[1].content)
    assert "tools" not in body and "tool_choice" not in body


async def test_parses_tool_calls_and_usage(mock_llm) -> None:
    mock_llm(lambda r: _calls('{"doc_id": "EXMP-PRD-001", "reason": "근거를 본다"}', "먼저 읽자"))
    got = await llm.step("s", [{"role": "user", "text": "?"}], TOOLS)
    assert got.text == "먼저 읽자"
    assert got.tool_calls == [
        ToolCall("c1", "get_item", {"doc_id": "EXMP-PRD-001", "reason": "근거를 본다"})
    ]
    assert (got.usage.prompt_tokens, got.usage.completion_tokens) == (12, 3)


async def test_non_json_arguments_fold_into_unavailable(mock_llm) -> None:
    mock_llm(lambda r: _calls("{not json"))
    with pytest.raises(LlmUnavailable) as e:
        await llm.step("s", [], TOOLS)
    assert e.value.extra["reason"] == "도구 인자 형식이 다르다"


async def test_429_and_5xx_fold_into_unavailable(mock_llm) -> None:
    mock_llm(lambda r: httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(LlmUnavailable) as e:
        await llm.step("s", [], TOOLS)
    assert e.value.extra["reason"] == "HTTP 429"
    mock_llm(lambda r: httpx.Response(500, text="oops"))
    with pytest.raises(LlmUnavailable):
        await llm.step("s", [], TOOLS)


async def test_timeout_and_bad_shape_fold_into_unavailable(mock_llm) -> None:
    def slow(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    mock_llm(slow)
    with pytest.raises(LlmUnavailable) as e:
        await llm.step("s", [], TOOLS)
    assert e.value.extra["reason"] == "ReadTimeout"
    mock_llm(lambda r: httpx.Response(200, json={"nope": 1}))
    with pytest.raises(LlmUnavailable):
        await llm.step("s", [], TOOLS)
