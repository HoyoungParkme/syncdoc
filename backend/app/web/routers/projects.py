"""routers/projects — SYNC-API-001 3.3. ProjectService(한 묶음) 또는 queries(집계)만 부른다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core import queries
from app.core.account.models import User
from app.core.project.service import ProjectService
from app.core.types import DocumentSummary as DocumentSummaryDto
from app.core.types import GraphScope
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.common import BrokenRefSummary
from app.web.schemas.documents import DocumentSummary
from app.web.schemas.ops import Graph
from app.web.schemas.projects import InitProject, ProjectDetail, ProjectSummary

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
        req.remote_url, req.code, req.name, user, req.import_existing, req.create_repo
    )
    session.commit()
    summary = next(p for p in await queries.project_summary() if p.code == req.code)
    return ProjectSummary.of(summary)


@router.get("/{code}", response_model=ProjectDetail)
async def get_project(code: str, user: User = Depends(current_user)) -> ProjectDetail:
    """SYNC-API-001#GET/api/projects/{code}"""
    return ProjectDetail.of(await queries.project_detail(code))


@router.get("/{code}/trash", response_model=list[DocumentSummary])
async def trash_list(code: str, user: User = Depends(current_user)) -> list[DocumentSummary]:
    """SYNC-API-001#GET/api/projects/{code}/trash"""
    return [DocumentSummary.of(d) for d in await queries.trash_list(code)]


@router.get("/{code}/docs", response_model=list[DocumentSummary])
async def list_docs(
    code: str,
    stage: int | None = Query(None, ge=1, le=11),
    status: str | None = Query(None, pattern="^(draft|approved)$"),
    user: User = Depends(current_user),
) -> list[DocumentSummary]:
    """SYNC-API-001#GET/api/projects/{code}/docs"""
    return [DocumentSummary.of(d) for d in await queries.document_list(code, stage, status)]


@router.get("/{code}/flags", response_model=list[BrokenRefSummary | DocumentSummary])
async def list_items(
    code: str,
    kind: str = Query(pattern="^(broken_ref|convention_errors|incomplete)$"),
    user: User = Depends(current_user),
) -> list:
    """SYNC-API-001#GET/api/projects/{code}/flags

    경로 이름은 flags로 남았다 — 항목 ID라 바꾸면 은퇴+신설. 끊어진 참조는 references.is_missing.
    """
    return [
        DocumentSummary.of(x) if isinstance(x, DocumentSummaryDto) else BrokenRefSummary.of(x)
        for x in await queries.project_items(code, kind)
    ]


@router.get("/{code}/graph", response_model=Graph)
async def graph(
    code: str,
    scope: GraphScope = GraphScope.all,
    user: User = Depends(current_user),
) -> Graph:
    """SYNC-API-001#GET/api/projects/{code}/graph"""
    return Graph.of(await queries.graph_view(code, scope))


@router.delete("/{code}", status_code=204)
async def delete_project(
    code: str, session: Session = Depends(get_session), user: User = Depends(current_user)
) -> None:
    """SYNC-API-001#DELETE/api/projects/{code}"""
    await ProjectService(session).delete_project(code)
    session.commit()
