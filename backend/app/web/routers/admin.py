"""routers/admin — SYNC-API-001 3.8 관리. repo_status·rebuild·restore."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import pipeline
from app.core.account.models import User
from app.core.project.service import ProjectService
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.ops import RebuildResult, RepoStatus, RestoreResult

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


@router.post("/repos/{code}/restore", response_model=RestoreResult)
async def restore(
    code: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> RestoreResult:
    """SYNC-API-001#POST/api/admin/repos/{code}/restore"""
    # 재구축과 같은 성격이라 pipeline을 직접 부른다 (DOM-002 3.1이 허용)
    return RestoreResult.model_validate(await pipeline.import_tracking(code))
