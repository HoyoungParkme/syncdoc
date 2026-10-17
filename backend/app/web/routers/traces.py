"""routers/traces — SYNC-API-001 3.12 실행 기록(카드 CJ). 화면 UI-19와 기록 도구(SEQ-36)가 부른다.

소유를 ProjectService.get_owned로 먼저 보고 TraceService를 바로 부른다(DOM-002 3장 — 한 묶음만
필요하다). 올리기만 개인 토큰으로도 된다(API-001 1장). 저장하는 것은 받은 JSON 그대로다 —
TraceRecord는 꼴만 본다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.errors import TraceInvalid
from app.core.project.service import ProjectService
from app.core.trace.service import MAX_BYTES, TraceService
from app.db import get_session
from app.web import auth
from app.web.schemas.trace import Deleted, TraceBrief, TraceCoverage, TraceRecord, TraceView

router = APIRouter(prefix="/api", tags=["traces"])


async def _within_limit(request: Request) -> None:
    """본문 4MB — 넘으면 상태만 413인 trace-invalid (API-001 3.12)."""
    if len(await request.body()) > MAX_BYTES:
        raise TraceInvalid("본문이 4MB를 넘는다", status=413)


@router.post("/projects/{code}/traces", response_model=TraceBrief, status_code=201)
async def upload_trace(
    code: str,
    record: TraceRecord,
    request: Request,
    response: Response,
    user: User = Depends(auth.token_or_session_user),
    _limit: None = Depends(_within_limit),
    session: Session = Depends(get_session),
) -> TraceBrief:
    """SYNC-API-001#POST/api/projects/{code}/traces — 기록 하나를 올린다 (SEQ-36)"""
    project = ProjectService(session).get_owned(code, user)
    brief, new = TraceService(session).save(project.id, user.id, await request.json())
    session.commit()
    if not new:
        response.status_code = 200  # 같은 기록 — 있는 것을 그대로
    return TraceBrief.model_validate(brief)


@router.get("/projects/{code}/traces", response_model=list[TraceBrief])
async def list_traces(
    code: str, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> list[TraceBrief]:
    """SYNC-API-001#GET/api/projects/{code}/traces — 최근 실행 기록 (UI-19 5.3)"""
    project = ProjectService(session).get_owned(code, user)
    return [TraceBrief.model_validate(b) for b in TraceService(session).list_recent(project.id)]


@router.delete("/projects/{code}/traces", response_model=Deleted)
async def delete_traces(
    code: str, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> Deleted:
    """SYNC-API-001#DELETE/api/projects/{code}/traces — 실행 기록을 다 지운다 (UI-19 5.11)"""
    project = ProjectService(session).get_owned(code, user)
    n = TraceService(session).delete(project.id)
    session.commit()
    return Deleted(deleted=n)


@router.get("/projects/{code}/traces/coverage", response_model=TraceCoverage)
async def trace_coverage(
    code: str, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> TraceCoverage:
    """SYNC-API-001#GET/api/projects/{code}/traces/coverage — 기록 커버리지 (UI-19 2.3·5.8)"""
    project = ProjectService(session).get_owned(code, user)
    return TraceCoverage.model_validate(TraceService(session).coverage(project.id))


@router.get("/projects/{code}/traces/{trace_id}", response_model=TraceView)
async def get_trace(
    code: str,
    trace_id: int,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> TraceView:
    """SYNC-API-001#GET/api/projects/{code}/traces/{id} — 실행 기록 하나 (UI-19 7)"""
    project = ProjectService(session).get_owned(code, user)
    return TraceView.model_validate(TraceService(session).get(project.id, trace_id))


@router.delete("/projects/{code}/traces/{trace_id}", status_code=204)
async def delete_trace(
    code: str,
    trace_id: int,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> Response:
    """SYNC-API-001#DELETE/api/projects/{code}/traces/{id} — 실행 기록 하나를 지운다"""
    project = ProjectService(session).get_owned(code, user)
    TraceService(session).delete(project.id, trace_id)
    session.commit()
    return Response(status_code=204)
