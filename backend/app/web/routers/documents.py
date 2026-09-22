"""routers/documents — SYNC-API-001 3.4. queries(읽기) · SpecService(이력) · pipeline(상태·되돌림).

이력의 작성자 이름은 users_by_ids로(3.1 예외).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core import pipeline, queries
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import Problem
from app.core.spec.service import SpecService
from app.core.types import ApiAuthor, AskEvent, Author, AuthorKind, DocStatus, Entry
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.documents import (
    AskAnswer,
    AskNote,
    AskRead,
    AskRequest,
    AskStart,
    ChangeStatus,
    Diff,
    Document,
    DocumentSummary,
)
from app.web.schemas.ops import DownstreamView, Revert, SaveResult, TrashResult
from app.web.schemas.projects import Version

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.get("/{doc_id}", response_model=Document)
async def get_document(doc_id: str, user: User = Depends(current_user)) -> Document:
    """SYNC-API-001#GET/api/docs/{docId}"""
    return Document.of(await queries.document_view(doc_id, user))


def _human(user: User) -> Author:
    return Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.web_status)


@router.delete("/{doc_id}", response_model=TrashResult)
async def trash_document(
    doc_id: str, confirm: bool = Query(False), user: User = Depends(current_user)
) -> TrashResult:
    """SYNC-API-001#DELETE/api/docs/{docId}

    confirm 없이 부르면 끊어질 것을 담은 document-deletion-needs-confirm이 온다 — 화면(UI-5 13.2)이
    그것을 보여주고 confirm=true로 다시 부른다.
    """
    return TrashResult.model_validate(await pipeline.trash_document(doc_id, _human(user), confirm))


@router.post("/{doc_id}/restore", response_model=SaveResult, status_code=201)
async def restore_document(doc_id: str, user: User = Depends(current_user)) -> SaveResult:
    """SYNC-API-001#POST/api/docs/{docId}/restore"""
    author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.web_revert)
    return SaveResult.model_validate(await pipeline.restore_document(doc_id, author))


@router.post("/{doc_id}/purge", status_code=204, response_class=Response)
async def purge_document(doc_id: str, user: User = Depends(current_user)) -> Response:
    """SYNC-API-001#POST/api/docs/{docId}/purge"""
    await pipeline.purge_document(doc_id, _human(user))
    return Response(status_code=204)


@router.post("/{doc_id}/status", response_model=DocumentSummary)
async def change_status(
    doc_id: str,
    req: ChangeStatus,
    user: User = Depends(current_user),
) -> DocumentSummary:
    """SYNC-API-001#POST/api/docs/{docId}/status

    토글. 완료로 올릴 때 규약 오류·미완성·끊어진 참조가 있으면 status-blocked (UC-H8 1a).
    """
    d = await pipeline.change_status(doc_id, DocStatus(req.to), user, req.reason)
    return DocumentSummary.of(await queries.document_view(d.doc_id, user))


@router.get("/{doc_id}/diff", response_model=Diff)
async def diff(
    doc_id: str,
    from_: int = Query(alias="from", ge=1),
    to: int = Query(ge=1),
    user: User = Depends(current_user),
) -> Diff:
    """SYNC-API-001#GET/api/docs/{docId}/diff"""
    return Diff.model_validate(await queries.diff_with_impact(doc_id, from_, to, user))


@router.get("/{doc_id}/versions", response_model=list[Version])
async def versions(
    doc_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[Version]:
    """SYNC-API-001#GET/api/docs/{docId}/versions"""
    rows = SpecService(session).list_versions(doc_id)
    ids = [v.author.user_id for v in rows] + [
        v.author.instructed_by_id for v in rows if v.author.instructed_by_id
    ]
    names = AccountService(session).users_by_ids(ids)
    for v in rows:
        v.author_view = ApiAuthor(
            kind=v.author.kind,
            user=names.get(v.author.user_id),
            instructed_by=names.get(v.author.instructed_by_id)
            if v.author.instructed_by_id
            else None,
            via=v.author.via,
        )
    return [Version.of(v) for v in rows]


@router.get("/{doc_id}/downstream", response_model=DownstreamView)
async def downstream(doc_id: str, user: User = Depends(current_user)) -> DownstreamView:
    """SYNC-API-001#GET/api/docs/{docId}/downstream"""
    return DownstreamView.of(await queries.downstream_view(doc_id, user))


@router.post("/{doc_id}/revert", response_model=SaveResult, status_code=201)
async def revert(doc_id: str, req: Revert, user: User = Depends(current_user)) -> SaveResult:
    """SYNC-API-001#POST/api/docs/{docId}/revert"""
    r = await pipeline.revert(doc_id, req.to_version, user, req.confirm_item_deletion)
    return SaveResult.model_validate(r)


def _frame(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event(ev: AskEvent) -> str:
    """queries의 이벤트 DTO → SSE 프레임. 이름은 API-001 3.4 표 그대로."""
    if isinstance(ev, queries.AskStart):
        return _frame("start", AskStart.model_validate(ev).model_dump())
    if isinstance(ev, queries.AskNote):
        return _frame("note", AskNote.model_validate(ev).model_dump())
    if isinstance(ev, queries.AskRead):
        return _frame("read", AskRead.model_validate(ev).model_dump())
    return _frame("answer", AskAnswer.model_validate(ev).model_dump())


@router.post("/{doc_id}/ask")
async def ask(doc_id: str, req: AskRequest, user: User = Depends(current_user)) -> Response:
    """SYNC-API-001#POST/api/docs/{docId}/ask

    보고 있는 문서가 시작 맥락이고 항목은 힌트다(UC-H19). 모델이 도구로 같은 프로젝트를 읽는
    동안 note·read 이벤트를 흘리고 answer로 끝난다(SSE). 첫 이벤트(start) 전의 오류는 상태 코드,
    뒤의 오류는 error 이벤트. 아무것도 저장하지 않는다.
    """
    history = [{"role": t.role, "text": t.text} for t in req.history]
    gen = queries.ask_item(doc_id, req.item_id, req.question, history, user)
    first = await anext(gen)  # 여기서 나는 Problem은 problem_handler가 상태 코드로 낸다

    async def body():
        yield _event(first)
        try:
            async for ev in gen:
                yield _event(ev)
        except Problem as p:
            yield _frame("error", p.to_dict())

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
