"""SYNC-MS-010 — ConversationService. conversations·turns·attachments만.

읽는 중 질의(R11)의 보관. 명세 표를 읽지도 쓰지도 않는다 — 프로젝트·사용자를 ID로만 가리킨다.
소유 판정은 대화의 프로젝트로 한다(ProjectService.get_owned).
남의 것은 있는지 없는지를 말하지 않는다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.clock import now_utc
from app.core.conversation.models import Attachment, Conversation, Turn
from app.core.conversation.repository import ConversationRepository
from app.core.errors import NotFound
from app.core.project.models import Project
from app.core.project.service import ProjectService
from app.core.types import AttachmentMeta, ConversationBrief, ConversationView, TurnView

NEW_TITLE = "새 대화"
TITLE_LEN = 40


def _meta(a: Attachment) -> AttachmentMeta:
    return AttachmentMeta(
        id=a.id, name=a.name, mime=a.mime, size=a.size, turn_id=a.turn_id, created_at=a.created_at
    )


class ConversationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ConversationRepository(session)

    def _owned(self, conv_id: int, user: User) -> tuple[Conversation, Project]:
        """대화 → 프로젝트 소유 판정. 없거나 남의 것이면 같은 not-found(conversation)."""
        conv = self.repo.get(conv_id)
        project = self.session.get(Project, conv.project_id) if conv is not None else None
        if conv is None or project is None or project.owner_user_id != user.id:
            raise NotFound("conversation", conv_id)  # 있는지 없는지를 말하지 않는다 (R12)
        return conv, project

    def list(self, code: str, user: User) -> list[ConversationBrief]:
        """SYNC-MS-010#ConversationService.list"""
        project = ProjectService(self.session).get_owned(code, user)
        return [
            ConversationBrief(id=c.id, title=c.title, turn_count=n, updated_at=c.updated_at)
            for c, n in self.repo.list_for(project.id, user.id)
        ]

    def create(self, code: str, user: User, title: str | None = None) -> Conversation:
        """SYNC-MS-010#ConversationService.create"""
        project = ProjectService(self.session).get_owned(code, user)
        t = now_utc()
        return self.repo.add(
            Conversation(
                project_id=project.id,
                user_id=user.id,
                title=(title or "").strip()[:TITLE_LEN * 2] or NEW_TITLE,
                created_at=t,
                updated_at=t,
            )
        )

    def get(self, conv_id: int, user: User) -> ConversationView:
        """SYNC-MS-010#ConversationService.get

        턴 전부 + 첨부 메타. 바이트·글자는 안 읽는다.
        """
        conv, project = self._owned(conv_id, user)
        metas = [_meta(a) for a in self.repo.attachment_metas(conv.id)]
        turns = [
            TurnView(
                id=t.id,
                seq=t.seq,
                question=t.question,
                answer=t.answer,
                progress=list(t.progress or []),
                context_item_ids=list(t.context_item_ids or []),
                error=t.error,
                attachments=[m for m in metas if m.turn_id == t.id],
                created_at=t.created_at,
            )
            for t in self.repo.turns(conv.id)
        ]
        return ConversationView(
            id=conv.id,
            title=conv.title,
            turn_count=len(turns),
            updated_at=conv.updated_at,
            turns=turns,
            pending=[m for m in metas if m.turn_id is None],
            project_code=project.code,
        )

    def delete(self, conv_id: int, user: User) -> None:
        """SYNC-MS-010#ConversationService.delete

        턴·첨부는 cascade.
        """
        conv, _ = self._owned(conv_id, user)
        self.repo.delete(conv.id)

    def delete_by_project(self, project_id: int) -> None:
        """SYNC-MS-010#ConversationService.delete_by_project

        소유 판정은 부르는 쪽이 했다.
        """
        self.repo.delete_by_project(project_id)

    def add_turn(self, conv_id: int, question: str, attachment_ids: list[int]) -> Turn:
        """SYNC-MS-010#ConversationService.add_turn"""
        conv = self.repo.get(conv_id)
        if conv is None:
            raise NotFound("conversation", conv_id)
        seq = self.repo.max_seq(conv.id) + 1
        turn = self.repo.add_turn(
            Turn(
                conversation_id=conv.id,
                seq=seq,
                question=question,
                progress=[],
                context_item_ids=[],
                created_at=now_utc(),
            )
        )
        self.repo.attach_pending(conv.id, turn.id, attachment_ids)
        if seq == 1 or conv.title == NEW_TITLE:
            conv.title = question.strip()[:TITLE_LEN] or NEW_TITLE
        conv.updated_at = now_utc()
        self.session.flush()
        return turn

    def finish_turn(
        self,
        turn_id: int,
        answer: str | None,
        progress: list[dict],
        context_item_ids: list[str],
        error: str | None = None,
    ) -> Turn:
        """SYNC-MS-010#ConversationService.finish_turn

        답이거나 error 하나.
        """
        turn = self.repo.turn(turn_id)
        if turn is None:
            raise NotFound("turn", turn_id)
        if answer is None and not error:
            error = "답 없이 끊겼다"
        turn.answer = None if error else answer
        turn.error = error
        turn.progress = list(progress)
        turn.context_item_ids = list(context_item_ids)
        conv = self.repo.get(turn.conversation_id)
        if conv is not None:
            conv.updated_at = now_utc()
        self.session.flush()
        return turn

    def history(self, conv_id: int, limit: int) -> list[dict]:
        """SYNC-MS-010#ConversationService.history

        실패한 턴은 빠진다. 뒤에서 limit턴.
        """
        if limit <= 0:
            return []
        done = [t for t in self.repo.turns(conv_id) if t.error is None and t.answer is not None]
        out: list[dict] = []
        for t in done[-limit:]:
            out.append({"role": "user", "text": t.question})
            out.append({"role": "assistant", "text": t.answer})
        return out
