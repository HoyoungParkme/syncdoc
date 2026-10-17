"""routers/flow — SYNC-API-001 3.12 흐름 보기(카드 CF). 화면 UI-19가 부른다."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core import queries
from app.core.account.models import User
from app.web.auth import current_user
from app.web.schemas.code import FlowView

router = APIRouter(prefix="/api", tags=["flow"])


@router.get("/projects/{code}/flow", response_model=FlowView)
async def flow_view(code: str, user: User = Depends(current_user)) -> FlowView:
    """SYNC-API-001#GET/api/projects/{code}/flow — 흐름 보기 (UI-19)"""
    return FlowView.model_validate(await queries.flow_view(code, user))
