"""SYNC-MS-009 — infra/llm.py. 읽는 중 질의(PRD R11)의 모델 호출.

core는 이것을 통해서만 모델을 만진다.

OpenAI 호환 Chat Completions 하나(INFRA 5.3). 한 번 호출 + 도구 호출 파싱(카드 Y). 루프는
부르는 쪽(queries.ask_item)이 돈다. 와이어 형식(content·function.arguments)은 여기만 안다.
"""

from __future__ import annotations

import json
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


async def step(
    system: str, messages: list[dict], tools: list[ToolSpec], tool_choice: str = "auto"
) -> LlmStep:
    """SYNC-MS-009#llm.step

    한 번 호출하고 답(text)이나 도구 호출(tool_calls)을 돌려준다. 스트리밍하지 않는다.
    키가 비면 네트워크를 타기 전에 막는다. 그 밖의 모든 실패(429·타임아웃·인자 비JSON 포함)는
    llm-unavailable로 접는다 — git.commit_push가 GitHub 실패를 push-failed로 접는 것과 같다.
    """
    if not settings.LLM_API_KEY:
        raise LlmNotConfigured()
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
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                settings.LLM_API_URL,
                json=body,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
    except httpx.HTTPError as e:  # 타임아웃·연결 실패
        raise LlmUnavailable(f"{type(e).__name__}") from e
    if not r.is_success:
        raise LlmUnavailable(f"HTTP {r.status_code}")
    try:
        data = r.json()
        msg = data["choices"][0]["message"]
        calls = [
            ToolCall(
                id=c["id"],
                name=c["function"]["name"],
                arguments=json.loads(c["function"].get("arguments") or "{}"),
            )
            for c in (msg.get("tool_calls") or [])
        ]
        u = data.get("usage") or {}
        usage = LlmUsage(int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0))
    except json.JSONDecodeError as e:
        raise LlmUnavailable("도구 인자 형식이 다르다") from e
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LlmUnavailable("응답 형식이 다르다") from e
    for c in calls:
        if not isinstance(c.arguments, dict):
            raise LlmUnavailable("도구 인자 형식이 다르다")
    return LlmStep(text=msg.get("content") or None, tool_calls=calls, usage=usage)
