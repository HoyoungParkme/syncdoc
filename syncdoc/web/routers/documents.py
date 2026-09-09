"""routers/documents — SYNC-API-001 3.4. queries(읽기) · pipeline(상태 변경 — DOM-002 3.1 예외)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from syncdoc.core import pipeline, queries
from syncdoc.core.account.models import User
from syncdoc.core.types import DocStatus
from syncdoc.web.auth import current_user
from syncdoc.web.schemas.documents import ChangeStatus, Document, DocumentSummary, UpstreamCheck
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
