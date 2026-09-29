"""SYNC-DOM-002 4.10 — conversations·turns·attachments 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, load_only

from app.core.conversation.models import Attachment, Conversation, Turn


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, conv_id: int) -> Conversation | None:
        return self.session.get(Conversation, conv_id)

    def list_for(self, project_id: int, user_id: int) -> list[tuple[Conversation, int]]:
        """(대화, 턴 수) — updated_at 내림차순."""
        n = (
            select(func.count(Turn.id))
            .where(Turn.conversation_id == Conversation.id)
            .correlate(Conversation)
            .scalar_subquery()
        )
        stmt = (
            select(Conversation, n)
            .where(Conversation.project_id == project_id, Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        )
        return [(c, int(cnt)) for c, cnt in self.session.execute(stmt)]

    def add(self, conv: Conversation) -> Conversation:
        self.session.add(conv)
        self.session.flush()
        return conv

    def delete(self, conv_id: int) -> None:
        self.session.execute(delete(Conversation).where(Conversation.id == conv_id))

    def delete_by_project(self, project_id: int) -> None:
        self.session.execute(delete(Conversation).where(Conversation.project_id == project_id))

    def turns(self, conv_id: int) -> list[Turn]:
        return list(
            self.session.scalars(
                select(Turn).where(Turn.conversation_id == conv_id).order_by(Turn.seq)
            )
        )

    def turn(self, turn_id: int) -> Turn | None:
        return self.session.get(Turn, turn_id)

    def max_seq(self, conv_id: int) -> int:
        return int(
            self.session.scalar(select(func.max(Turn.seq)).where(Turn.conversation_id == conv_id))
            or 0
        )

    def add_turn(self, turn: Turn) -> Turn:
        self.session.add(turn)
        self.session.flush()
        return turn

    def attachment_metas(self, conv_id: int) -> list[Attachment]:
        """바이트·추출 글자는 읽지 않는다 — 메타만."""
        stmt = (
            select(Attachment)
            .options(
                load_only(
                    Attachment.id,
                    Attachment.conversation_id,
                    Attachment.turn_id,
                    Attachment.user_id,
                    Attachment.name,
                    Attachment.mime,
                    Attachment.size,
                    Attachment.created_at,
                )
            )
            .where(Attachment.conversation_id == conv_id)
            .order_by(Attachment.id)
        )
        return list(self.session.scalars(stmt))

    def attach_pending(self, conv_id: int, turn_id: int, ids: list[int]) -> None:
        """아직 안 보낸(turn_id null) 이 대화의 첨부만 턴에 붙인다. 남의 것·보낸 것은 건너뛴다."""
        if not ids:
            return
        self.session.execute(
            update(Attachment)
            .where(
                Attachment.id.in_(ids),
                Attachment.conversation_id == conv_id,
                Attachment.turn_id.is_(None),
            )
            .values(turn_id=turn_id)
        )
