"""routers/flags — SYNC-API-001 3.6. 플래그 상세는 queries, 확인은 TrackingService.

resolve의 target_changed(수정 동반)는 라우터가 계산해 넘긴다(MS-004) — flag_view와 같은 판정.
응답의 assignee 이름은 users_by_ids로(DOM-002 3.1 예외).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import queries
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.tracking.service import TrackingService
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.common import FlagSummary
from app.web.schemas.tracking import FlagDetail

router = APIRouter(prefix="/api/flags", tags=["flags"])


@router.get("/{flag_id}", response_model=FlagDetail)
async def get_flag(flag_id: int, user: User = Depends(current_user)) -> FlagDetail:
    """SYNC-API-001#GET/api/flags/{id}"""
    return FlagDetail.of(await queries.flag_view(flag_id))


@router.post("/{flag_id}/resolve", response_model=FlagSummary)
async def resolve_flag(
    flag_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> FlagSummary:
    """SYNC-API-001#POST/api/flags/{id}/resolve"""
    changed = (await queries.flag_view(flag_id)).target_changed_since_raise
    f = TrackingService(session).resolve(flag_id, user, changed)
    session.commit()
    if f.assignee_id is not None:
        f.assignee = AccountService(session).users_by_ids([f.assignee_id]).get(f.assignee_id)
    return FlagSummary.of(f)
