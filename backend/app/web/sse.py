"""SSE 포장 — SYNC-API-001 3.4·3.6 질문 스트림.

라우터 둘(documents.ask · code.ask_code)이 같이 쓴다(카드 BI). 프레임은
`event: {이름}\\ndata: {JSON}\\n\\n`. 이름은 API-001 3.4 표 그대로 — 복붙으로 어긋나지 않게 한곳.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.core import queries
from app.core.errors import Problem
from app.core.types import AskEvent
from app.web.schemas.documents import AskAnswer, AskDelta, AskNote, AskRead, AskStart


def frame(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event(ev: AskEvent) -> str:
    """queries의 이벤트 DTO → SSE 프레임."""
    if isinstance(ev, queries.AskStart):
        return frame("start", AskStart.model_validate(ev).model_dump())
    if isinstance(ev, queries.AskDelta):
        return frame("delta", AskDelta.model_validate(ev).model_dump())
    if isinstance(ev, queries.AskNote):
        return frame("note", AskNote.model_validate(ev).model_dump())
    if isinstance(ev, queries.AskRead):
        return frame("read", AskRead.model_validate(ev).model_dump())
    return frame("answer", AskAnswer.model_validate(ev).model_dump())


async def stream(gen: AsyncIterator[AskEvent]) -> StreamingResponse:
    """첫 이벤트(start)를 먼저 받는다 — 그 앞의 Problem은 problem_handler가 상태 코드로 낸다.
    뒤의 Problem은 error 이벤트."""
    first = await anext(gen)

    async def body():
        yield event(first)
        try:
            async for ev in gen:
                yield event(ev)
        except Problem as p:
            yield frame("error", p.to_dict())

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
