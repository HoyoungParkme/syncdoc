"""routers/admin — SYNC-API-001 3.8 관리. repo_status·rebuild."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import pipeline
from app.core.account.models import User
from app.core.project.service import ProjectService
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.ops import HookStatus, MoveResult, RebuildResult, RepoStatus, SyncResult

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
    r = await ProjectService(session).ensure_hook(code, user)
    session.commit()  # 트랜잭션은 호출자(DEV-10) — 안 하면 hook_id가 안 남는다 (#145)
    return HookStatus.model_validate(r)


@router.post("/repos/{code}/sync", response_model=SyncResult)
async def sync(
    code: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> SyncResult:
    """SYNC-API-001#POST/api/admin/repos/{code}/sync"""
    return SyncResult.model_validate(await ProjectService(session).sync_now(code, user))


@router.post("/repos/{code}/move-to-server", response_model=MoveResult)
async def move_to_server(code: str, user: User = Depends(current_user)) -> MoveResult:
    """SYNC-API-001#POST/api/admin/repos/{code}/move-to-server

    GitHub 저장을 서버 저장으로 옮긴다(카드 BQ). 락·커밋·되돌리기는 pipeline이 한다.
    """
    return MoveResult.model_validate(await pipeline.move_to_server(code, user))
