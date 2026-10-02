"""SYNC-API-001 4장 — ConversationBrief · Conversation · Turn · AttachmentMeta (3.5 대화·첨부)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.web.schemas.common import Base


class AttachmentMeta(Base):
    id: int
    name: str
    mime: str
    size: int
    turn_id: int | None
    created_at: datetime


class Progress(Base):
    kind: Literal["note", "read"]
    text: str


class Turn(Base):
    id: int
    seq: int
    question: str
    answer: str | None
    progress: list[Progress]
    context_item_ids: list[str]
    error: str | None
    attachments: list[AttachmentMeta]
    created_at: datetime
    missing_refs: list[str] = []  # 답 속 없는 참조 (#290)


class ConversationBrief(Base):
    id: int
    title: str
    turn_count: int
    updated_at: datetime


class Conversation(ConversationBrief):
    turns: list[Turn]
    pending: list[AttachmentMeta]


class CreateConversation(BaseModel):
    """POST /api/projects/{code}/conversations — 비우면 「새 대화」."""

    title: str | None = None
