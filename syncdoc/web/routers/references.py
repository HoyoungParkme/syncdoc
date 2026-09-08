"""routers/references — SYNC-API-001 3.4 참조. queries.item_references_view."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from syncdoc.core import queries
from syncdoc.core.account.models import User
from syncdoc.web.auth import current_user
from syncdoc.web.schemas.documents import ItemReferences

router = APIRouter(prefix="/api/docs", tags=["references"])


@router.get("/{doc_id}/items/{item_id}/references", response_model=ItemReferences)
async def item_references(
    doc_id: str, item_id: str, user: User = Depends(current_user)
) -> ItemReferences:
    """SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/references — itemId '~'→'/'"""
    return ItemReferences.of(await queries.item_references_view(doc_id, item_id.replace("~", "/")))
