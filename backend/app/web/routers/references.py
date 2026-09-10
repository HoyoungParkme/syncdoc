"""routers/references — SYNC-API-001 3.4 참조. queries.item_references_view."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core import queries
from app.core.account.models import User
from app.web.auth import current_user
from app.web.schemas.documents import ItemChain, ItemReferences

router = APIRouter(prefix="/api/docs", tags=["references"])


@router.get("/{doc_id}/items/{item_id}/references", response_model=ItemReferences)
async def item_references(
    doc_id: str, item_id: str, user: User = Depends(current_user)
) -> ItemReferences:
    """SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/references — itemId '~'→'/'"""
    return ItemReferences.of(await queries.item_references_view(doc_id, item_id.replace("~", "/")))


@router.get("/{doc_id}/items/{item_id}/chain", response_model=ItemChain)
async def item_chain(doc_id: str, item_id: str, user: User = Depends(current_user)) -> ItemChain:
    """SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/chain — itemId '~'→'/'"""
    return ItemChain.of(await queries.item_chain(doc_id, item_id.replace("~", "/")))
