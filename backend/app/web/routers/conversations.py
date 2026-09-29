"""routers/conversations — /api/projects/{code}/conversations · /api/conversations/{id}.

SYNC-API-001 3.5 · SEQ-24 · UI-5 8.11~8.13. ConversationService만 본다(DOM-002 3.1).
질문(ask)은 routers/documents에 그대로 있고 queries.ask_item이 대화를 읽고 쓴다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.conversation.service import ConversationService
from app.db import get_session
from app.web import auth
from app.web.schemas.conversations import Conversation, ConversationBrief, CreateConversation

router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/projects/{code}/conversations", response_model=list[ConversationBrief])
async def list_conversations(
    code: str, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> list[ConversationBrief]:
    """SYNC-API-001#GET/api/projects/{code}/conversations — 내 대화, 최근순 (UI-5 8.11)"""
    briefs = ConversationService(session).list(code, user)
    return [ConversationBrief.model_validate(c) for c in briefs]


@router.post("/projects/{code}/conversations", response_model=ConversationBrief, status_code=201)
async def create_conversation(
    code: str,
    req: CreateConversation | None = None,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> ConversationBrief:
    """SYNC-API-001#GET/api/projects/{code}/conversations post — 새 대화 (UI-5 8.12)"""
    conv = ConversationService(session).create(code, user, req.title if req else None)
    session.commit()
    return ConversationBrief(id=conv.id, title=conv.title, turn_count=0, updated_at=conv.updated_at)


@router.get("/conversations/{id}", response_model=Conversation)
async def get_conversation(
    id: int, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> Conversation:
    """SYNC-API-001#GET/api/conversations/{id} — 턴 전부 + 첨부 메타 (UI-5 8.7)"""
    return Conversation.model_validate(ConversationService(session).get(id, user))


@router.delete("/conversations/{id}", status_code=204)
async def delete_conversation(
    id: int, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> Response:
    """SYNC-API-001#GET/api/conversations/{id} delete — 턴·첨부까지 (UI-5 8.13)"""
    ConversationService(session).delete(id, user)
    session.commit()
    return Response(status_code=204)
