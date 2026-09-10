"""routers/admin — SYNC-API-001 3.3 관리. ProjectService(repo_status·rebuild_index)만."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.project.service import ProjectService
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.ops import RebuildResult, RepoStatus

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/repos", response_model=list[RepoStatus])
async def repos(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[RepoStatus]:
    """SYNC-API-001#GET/api/admin/repos"""
    return [RepoStatus.model_validate(r) for r in await ProjectService(session).repo_status()]


@router.post("/repos/{code}/rebuild", response_model=RebuildResult)
async def rebuild(
    code: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> RebuildResult:
    """SYNC-API-001#POST/api/admin/repos/{code}/rebuild"""
    return RebuildResult.model_validate(await ProjectService(session).rebuild_index(code))
