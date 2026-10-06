"""SYNC-MS-009 — infra/llm.py. 읽는 중 질의(PRD R11)의 모델 호출.

core는 이것을 통해서만 모델을 만진다.

OpenAI 호환 Chat Completions 하나(INFRA 5.3). 한 번 호출 + 도구 호출 파싱(카드 Y), 스트림으로
글자 조각을 흘린다(카드 AW). 루프는 부르는 쪽(queries.ask_item)이 돈다.
와이어 형식(content·function.arguments)은 여기만 안다.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.core.errors import LlmNotConfigured, LlmUnavailable
from app.core.types import LlmStep, LlmUsage, ToolCall, ToolSpec

_TIMEOUT = 60.0  # 초. 모델이 느려도 요청 하나가 앱을 붙들지 않게


def _wire(m: dict) -> dict[str, Any]:
    """우리 대화록 항목 → OpenAI 호환 메시지."""
    if m["role"] == "tool":
        return {"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["text"]}
    out: dict[str, Any] = {"role": m["role"], "content": m.get("text") or None}
    if m["role"] == "user" and m.get("images"):
        # 이 턴에 붙인 이미지 — content 파트 배열(vision). 뒤 턴에는 안 실린다 (MS-009, 카드 AR)
        parts: list[dict[str, Any]] = [{"type": "text", "text": m.get("text") or ""}]
        for mime, data in m["images"]:
            b64 = base64.b64encode(data).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        out["content"] = parts
        return out
    if m.get("tool_calls"):
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in m["tool_calls"]
        ]
    if out["content"] is None and "tool_calls" not in out:
        out["content"] = ""
    return out


def _body(system: str, messages: list[dict], tools: list[ToolSpec], tool_choice: str) -> dict:
    body: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "system", "content": system}] + [_wire(m) for m in messages],
    }
    if tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        body["tool_choice"] = tool_choice
    return body


def _usage(u: dict | None) -> LlmUsage:
    u = u or {}
    return LlmUsage(int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0))


def _calls(raw: list[dict]) -> list[ToolCall]:
    """와이어 tool_calls → ToolCall. arguments가 JSON이 아니거나 dict가 아니면 llm-unavailable."""
    try:
        calls = [
            ToolCall(
                id=c["id"],
                name=c["function"]["name"],
                arguments=json.loads(c["function"].get("arguments") or "{}"),
            )
            for c in raw
        ]
    except json.JSONDecodeError as e:
        raise LlmUnavailable("도구 인자 형식이 다르다") from e
    except (ValueError, KeyError, TypeError) as e:
        raise LlmUnavailable("응답 형식이 다르다") from e
    for c in calls:
        if not isinstance(c.arguments, dict):
            raise LlmUnavailable("도구 인자 형식이 다르다")
    return calls


def _single(data: dict) -> LlmStep:
    """단발 응답(choices[0].message) → LlmStep (MS-009 llm.step 4단계)."""
    try:
        msg = data["choices"][0]["message"]
        calls = _calls(msg.get("tool_calls") or [])
        usage = _usage(data.get("usage"))
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LlmUnavailable("응답 형식이 다르다") from e
    return LlmStep(text=msg.get("content") or None, tool_calls=calls, usage=usage)


async def step_stream(
    system: str, messages: list[dict], tools: list[ToolSpec], tool_choice: str = "auto"
) -> AsyncIterator[str | LlmStep]:
    """SYNC-MS-009#llm.step_stream

    스트림으로 한 번 호출한다. 글자 조각(str)을 오는 대로 내고 끝에 LlmStep 하나를 낸다 — 조각은
    화면용이고 LlmStep이 진실이다. 스트림을 무시하는 호환 서버(Content-Type이 text/event-stream이
    아님)면 본문을 JSON 하나로 읽는다. 실패는 step과 같이 llm-unavailable로 접는다.
    """
    if not settings.llm_enabled:  # 키와 주소 — 싱크독_로컬은 주소 기본값이 없다 (카드 BU)
        raise LlmNotConfigured()
    body = _body(system, messages, tools, tool_choice)
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}
    text_parts: list[str] = []
    slots: dict[int, dict[str, str]] = {}  # index → {id, name, arguments 조각 이어 붙임}
    usage = LlmUsage()
    single: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream(
                "POST",
                settings.llm_url,
                json=body,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            ) as r:
                if not r.is_success:
                    raise LlmUnavailable(f"HTTP {r.status_code}")
                if not r.headers.get("content-type", "").startswith("text/event-stream"):
                    single = json.loads(await r.aread())
                else:
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        chunk = json.loads(payload)
                        if chunk.get("usage"):
                            usage = _usage(chunk["usage"])
                        for ch in chunk.get("choices") or []:
                            d = ch.get("delta") or {}
                            if d.get("content"):
                                text_parts.append(d["content"])
                                yield d["content"]
                            for tc in d.get("tool_calls") or []:
                                idx = int(tc.get("index") or 0)
                                empty = {"id": "", "name": "", "arguments": ""}
                                slot = slots.setdefault(idx, empty)
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] = fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments"] += fn["arguments"]
    except httpx.HTTPError as e:  # 타임아웃·연결 실패
        raise LlmUnavailable(f"{type(e).__name__}") from e
    except json.JSONDecodeError as e:
        raise LlmUnavailable("응답 형식이 다르다") from e
    except (ValueError, KeyError, TypeError) as e:
        raise LlmUnavailable("응답 형식이 다르다") from e
    if single is not None:
        yield _single(single)
        return
    raw = [
        {"id": s["id"], "function": {"name": s["name"], "arguments": s["arguments"]}}
        for _, s in sorted(slots.items())
    ]
    yield LlmStep(text="".join(text_parts) or None, tool_calls=_calls(raw), usage=usage)


async def step(
    system: str, messages: list[dict], tools: list[ToolSpec], tool_choice: str = "auto"
) -> LlmStep:
    """SYNC-MS-009#llm.step

    한 번 호출하고 답(text)이나 도구 호출(tool_calls)을 돌려준다 — step_stream을 끝까지 돌려
    마지막 LlmStep을 돌려주는 것이다. 키가 비면 네트워크를 타기 전에 막는다. 그 밖의 모든
    실패(429·타임아웃·인자 비JSON 포함)는 llm-unavailable로 접는다 — git.commit_push가 GitHub
    실패를 push-failed로 접는 것과 같다.
    """
    last: LlmStep | None = None
    async for part in step_stream(system, messages, tools, tool_choice):
        if isinstance(part, LlmStep):
            last = part
    if last is None:
        raise LlmUnavailable("응답 형식이 다르다")
    return last
