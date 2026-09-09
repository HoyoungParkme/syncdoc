"""routers/projects — SYNC-API-001 3.3. ProjectService(한 묶음) 또는 queries(집계)만 부른다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from syncdoc.core import queries
from syncdoc.core.account.models import User
from syncdoc.core.project.service import ProjectService
from syncdoc.core.types import DocumentSummary as DocumentSummaryDto
from syncdoc.core.types import FlagSummary as FlagSummaryDto
from syncdoc.db import get_session
from syncdoc.web.auth import current_user
from syncdoc.web.schemas.comments import CommentSummary
from syncdoc.web.schemas.common import FlagSummary
from syncdoc.web.schemas.documents import DocumentSummary
from syncdoc.web.schemas.projects import InitProject, ProjectDetail, ProjectSummary

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


@router.get("/{code}", response_model=ProjectDetail)
async def get_project(code: str, user: User = Depends(current_user)) -> ProjectDetail:
    """SYNC-API-001#GET/api/projects/{code}"""
    return ProjectDetail.of(await queries.project_detail(code))


@router.get("/{code}/docs", response_model=list[DocumentSummary])
async def list_docs(
    code: str,
    stage: int | None = Query(None, ge=1, le=11),
    status: str | None = Query(None, pattern="^(draft|review|approved)$"),
    user: User = Depends(current_user),
) -> list[DocumentSummary]:
    """SYNC-API-001#GET/api/projects/{code}/docs"""
    return [DocumentSummary.of(d) for d in await queries.document_list(code, stage, status)]


@router.get("/{code}/flags", response_model=list[FlagSummary | CommentSummary | DocumentSummary])
async def list_items(
    code: str,
    kind: str = Query(
        pattern="^(needs_check|broken_ref|upstream_impact|comments|convention_errors|incomplete)$"
    ),
    user: User = Depends(current_user),
) -> list:
    """SYNC-API-001#GET/api/projects/{code}/flags"""
    out = []
    for x in await queries.project_items(code, kind):
        if isinstance(x, FlagSummaryDto):
            out.append(FlagSummary.of(x))
        elif isinstance(x, DocumentSummaryDto):
            out.append(DocumentSummary.of(x))
        else:
            out.append(CommentSummary.model_validate(x))
    return out
