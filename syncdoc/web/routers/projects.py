"""routers/projects — SYNC-API-001 3.3. ProjectService(한 묶음) 또는 queries(집계)만 부른다.

GET /api/projects/{code}(ProjectDetail)는 recent_changes가 versions.message 없이는 못 만든다(보고).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from syncdoc.core import queries
from syncdoc.core.account.models import User
from syncdoc.core.project.service import ProjectService
from syncdoc.db import get_session
from syncdoc.web.auth import current_user
from syncdoc.web.schemas.documents import DocumentSummary
from syncdoc.web.schemas.projects import InitProject, ProjectSummary

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
async def list_projects(user: User = Depends(current_user)) -> list[ProjectSummary]:
    """SYNC-API-001#GET/api/projects"""
    return [ProjectSummary.of(p) for p in await queries.project_summary()]


@router.post("", response_model=ProjectSummary, status_code=201)
async def init_project(
    req: InitProject, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> ProjectSummary:
    """SYNC-API-001#POST/api/projects"""
    await ProjectService(session).init_project(
        req.remote_url, req.code, req.name, user, req.import_existing
    )
    session.commit()
    summary = next(p for p in await queries.project_summary() if p.code == req.code)
    return ProjectSummary.of(summary)


@router.get("/{code}/docs", response_model=list[DocumentSummary])
async def list_docs(
    code: str,
    stage: int | None = Query(None, ge=1, le=11),
    status: str | None = Query(None, pattern="^(draft|review|approved)$"),
    user: User = Depends(current_user),
) -> list[DocumentSummary]:
    """SYNC-API-001#GET/api/projects/{code}/docs"""
    return [DocumentSummary.of(d) for d in await queries.document_list(code, stage, status)]
