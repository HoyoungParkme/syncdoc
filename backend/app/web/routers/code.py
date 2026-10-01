"""routers/code — SYNC-API-001 3.6 코드 그래프(카드 AY). queries만 본다(DOM-002 3.1).

대조는 부를 때 계산한다 — 그래프는 code_graphs에서, 「호출하는 것」은 명세에서. itemId의 `~`는 `/`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core import queries
from app.core.account.models import User
from app.web.auth import current_user
from app.web.schemas.code import CodeCalls, CodeNodes, CodeText, CodeView

router = APIRouter(prefix="/api", tags=["code"])


@router.get("/docs/{doc_id}/code", response_model=CodeView)
async def doc_code(doc_id: str, user: User = Depends(current_user)) -> CodeView:
    """SYNC-API-001#GET/api/docs/{docId}/code — 문서의 함수 대조 (UI-5 8.22)"""
    return CodeView.model_validate(await queries.code_view(doc_id, None, user))


@router.get("/docs/{doc_id}/items/{item_id}/code", response_model=CodeView)
async def item_code(doc_id: str, item_id: str, user: User = Depends(current_user)) -> CodeView:
    """SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code — 코드 탭 (UI-5 8.18~8.22)"""
    return CodeView.model_validate(await queries.code_view(doc_id, item_id.replace("~", "/"), user))


@router.get("/docs/{doc_id}/items/{item_id}/code/source", response_model=CodeText)
async def item_code_source(
    doc_id: str, item_id: str, user: User = Depends(current_user)
) -> CodeText:
    """SYNC-API-001#GET/api/docs/{docId}/items/{itemId}/code/source — 코드 보기 (UI-5 8.21)"""
    return CodeText.model_validate(
        await queries.code_source(doc_id, item_id.replace("~", "/"), user)
    )


@router.get("/projects/{code}/code-calls", response_model=CodeCalls)
async def code_calls(code: str, user: User = Depends(current_user)) -> CodeCalls:
    """SYNC-API-001#GET/api/projects/{code}/code-calls — 관계도 코드 호출 (UI-8 2.6)"""
    return CodeCalls.model_validate(await queries.code_calls(code, user))


@router.get("/projects/{code}/code-graph", response_model=CodeNodes)
async def code_nodes(code: str, user: User = Depends(current_user)) -> CodeNodes:
    """SYNC-API-001#GET/api/projects/{code}/code-graph — 코드 그래프 노드 전부 (UI-17)"""
    return CodeNodes.model_validate(await queries.code_nodes(code, user))
