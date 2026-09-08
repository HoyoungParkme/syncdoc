"""routers/documents — SYNC-API-001 3.4. SpecService 또는 queries."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from syncdoc.core import queries
from syncdoc.core.account.models import User
from syncdoc.core.spec.service import SpecService
from syncdoc.db import get_session
from syncdoc.web.auth import current_user
from syncdoc.web.schemas.documents import ChangeStatus, Document, DocumentSummary, UpstreamCheck

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
    session: Session = Depends(get_session),
) -> DocumentSummary:
    """SYNC-API-001#POST/api/docs/{docId}/status"""
    d = await SpecService(session).change_status(
        doc_id, req.to, user, req.reason, req.upstream_reviewed, req.upstream_mismatch
    )
    session.commit()
    return DocumentSummary.of(await queries.document_view(d.doc_id))
