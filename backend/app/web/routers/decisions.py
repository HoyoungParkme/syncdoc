"""routers/decisions — SYNC-API-001 3.6. 상세는 queries, 결정은 TrackingService."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import queries
from app.core.account.models import User
from app.core.tracking.service import TrackingService
from app.core.types import Propagation
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.tracking import Decide, DecisionDetail, DecisionResult

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("/{version_id}", response_model=DecisionDetail)
async def get_decision(version_id: int, user: User = Depends(current_user)) -> DecisionDetail:
    """SYNC-API-001#GET/api/decisions/{versionId}"""
    return DecisionDetail.of(await queries.decision_view(version_id))


@router.post("/{version_id}", response_model=DecisionResult)
async def decide(
    version_id: int,
    req: Decide,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> DecisionResult:
    """SYNC-API-001#POST/api/decisions/{versionId}"""
    r = TrackingService(session).record_decision(
        version_id, Propagation(req.choice), req.reason, user
    )
    session.commit()
    return DecisionResult.of(r)
