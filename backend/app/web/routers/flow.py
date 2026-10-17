"""routers/flow — SYNC-API-001 3.12 흐름 보기(카드 CF)·기록 도구의 준비(카드 CJ).

흐름 보기는 화면 UI-19가, trace-spans는 기록 도구(SEQ-36 — 개인 토큰으로도)가 부른다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core import queries
from app.core.account.models import User
from app.web.auth import current_user, token_or_session_user
from app.web.schemas.code import FlowView
from app.web.schemas.trace import TraceSpans

router = APIRouter(prefix="/api", tags=["flow"])


@router.get("/projects/{code}/flow", response_model=FlowView)
async def flow_view(code: str, user: User = Depends(current_user)) -> FlowView:
    """SYNC-API-001#GET/api/projects/{code}/flow — 흐름 보기 (UI-19)"""
    return FlowView.model_validate(await queries.flow_view(code, user))


@router.get("/projects/{code}/trace-spans", response_model=TraceSpans)
async def trace_spans(code: str, user: User = Depends(token_or_session_user)) -> TraceSpans:
    """SYNC-API-001#GET/api/projects/{code}/trace-spans — 기록 도구가 감쌀 함수 (SEQ-36)"""
    return TraceSpans.model_validate(await queries.trace_spans(code, user))
