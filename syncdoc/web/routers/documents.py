"""routers/documents — SYNC-API-001 3.4. queries(읽기) · SpecService(이력) · pipeline(상태·되돌림).

이력의 작성자 이름은 users_by_ids로(3.1 예외).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from syncdoc.core import pipeline, queries
from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.types import ApiAuthor, DocStatus
from syncdoc.db import get_session
from syncdoc.web.auth import current_user
from syncdoc.web.schemas.documents import ChangeStatus, Document, DocumentSummary, UpstreamCheck
from syncdoc.web.schemas.ops import DownstreamView, Revert, SaveResult
from syncdoc.web.schemas.projects import Version
from syncdoc.web.schemas.tracking import Diff

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.get("/{doc_id}", response_model=Document)
async def get_document(doc_id: str, user: User = Depends(current_user)) -> Document:
    """SYNC-API-001#GET/api/docs/{docId}"""
    return Document.of(await queries.document_view(doc_id))


@router.get("/{doc_id}/upstream", response_model=list[UpstreamCheck])
async def upstream(doc_id: str, user: User = Depends(current_user)) -> list[UpstreamCheck]:
    """SYNC-API-001#GET/api/docs/{docId}/upstream"""
    return [UpstreamCheck.of(u) for u in await queries.upstream_checklist(doc_id)]


@router.post("/{doc_id}/status", response_model=DocumentSummary)
async def change_status(
    doc_id: str,
    req: ChangeStatus,
    user: User = Depends(current_user),
) -> DocumentSummary:
    """SYNC-API-001#POST/api/docs/{docId}/status"""
    d = await pipeline.change_status(
        doc_id, DocStatus(req.to), user, req.reason, req.upstream_reviewed, req.upstream_mismatch
    )
    return DocumentSummary.of(await queries.document_view(d.doc_id))


@router.get("/{doc_id}/diff", response_model=Diff)
async def diff(
    doc_id: str,
    from_: int = Query(alias="from", ge=1),
    to: int = Query(ge=1),
    user: User = Depends(current_user),
) -> Diff:
    """SYNC-API-001#GET/api/docs/{docId}/diff"""
    return Diff.model_validate(await queries.diff_with_impact(doc_id, from_, to))


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
    return DownstreamView.of(await queries.downstream_view(doc_id))


@router.post("/{doc_id}/revert", response_model=SaveResult, status_code=201)
async def revert(doc_id: str, req: Revert, user: User = Depends(current_user)) -> SaveResult:
    """SYNC-API-001#POST/api/docs/{docId}/revert"""
    r = await pipeline.revert(doc_id, req.to_version, user, req.confirm_item_deletion)
    return SaveResult.model_validate(r)
