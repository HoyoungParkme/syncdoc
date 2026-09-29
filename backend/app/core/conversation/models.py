"""SYNC-DOM-002 2.9 대화 — Conversation · Turn · Attachment. 테이블은 SYNC-DOM-003의 같은 이름.

명세 표를 가리키지 않는다 — projects·users만 FK. 프로젝트 행이 지워지면 cascade로 함께 사라진다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Conversation(Base):
    """SYNC-DOM-002#Conversation"""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_project_user", "project_id", "user_id"),
        Index("ix_conversations_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Turn(Base):
    """SYNC-DOM-002#Turn — 질문 하나와 그 답. 진행 줄·본 것도 함께(화면이 다시 그린다)."""

    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="uq_turns_conversation_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    context_item_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # 있으면 다음 질문의 history에 안 실린다 — 실패한 답을 모델이 앞 대화로 보게 하지 않는다
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attachment(Base):
    """SYNC-DOM-002#Attachment — 질문에 붙인 파일. 바이트까지 여기(bytea). 카드 AR가 채운다."""

    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_conversation", "conversation_id"),
        Index("ix_attachments_turn_id", "turn_id"),
        Index("ix_attachments_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    # null이면 아직 안 보낸 것(입력 칸에 올려 둔 상태)
    turn_id: Mapped[int | None] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[bytes] = mapped_column(LargeBinary)
    text_cache: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
