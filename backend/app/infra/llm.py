"""SYNC-MS-009 — infra/llm.py. 읽는 중 질의(PRD R11)의 모델 호출.

core는 이것을 통해서만 모델을 만진다.

OpenAI 호환 Chat Completions 하나(INFRA 5.3). 주소·모델은 설정값이라 호환 서버로 바꿀 수 있다.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.core.errors import LlmNotConfigured, LlmUnavailable

_TIMEOUT = 60.0  # 초. 모델이 느려도 요청 하나가 앱을 붙들지 않게


async def ask(system: str, messages: list[dict]) -> str:
    """SYNC-MS-009#llm.ask

    맥락 조립과 자르기는 부르는 쪽(queries.ask_item)이 끝낸 상태로 온다. 스트리밍하지 않는다.
    키가 비면 네트워크를 타기 전에 막는다. 그 밖의 모든 실패(429·타임아웃 포함)는
    llm-unavailable로 접는다 — git.commit_push가 GitHub 실패를 push-failed로 접는 것과 같다.
    """
    if not settings.LLM_API_KEY:
        raise LlmNotConfigured()
    body = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "system", "content": system}]
        + [{"role": m["role"], "content": m["text"]} for m in messages],
    }
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
        return r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LlmUnavailable("응답 형식이 다르다") from e
