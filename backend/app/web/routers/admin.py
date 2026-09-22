"""routers/admin — SYNC-API-001 3.8 관리. repo_status·rebuild."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.project.service import ProjectService
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.ops import HookStatus, RebuildResult, RepoStatus, SyncResult

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/repos", response_model=list[RepoStatus])
async def repos(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[RepoStatus]:
    """SYNC-API-001#GET/api/admin/repos"""
    return [RepoStatus.model_validate(r) for r in await ProjectService(session).repo_status(user)]


@router.post("/repos/{code}/rebuild", response_model=RebuildResult)
async def rebuild(
    code: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> RebuildResult:
    """SYNC-API-001#POST/api/admin/repos/{code}/rebuild"""
    return RebuildResult.model_validate(await ProjectService(session).rebuild_index(code, user))


@router.post("/repos/{code}/hook", response_model=HookStatus)
async def hook(
    code: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> HookStatus:
    """SYNC-API-001#POST/api/admin/repos/{code}/hook"""
    return HookStatus.model_validate(await ProjectService(session).ensure_hook(code, user))


@router.post("/repos/{code}/sync", response_model=SyncResult)
async def sync(
    code: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> SyncResult:
    """SYNC-API-001#POST/api/admin/repos/{code}/sync"""
    return SyncResult.model_validate(await ProjectService(session).sync_now(code, user))
