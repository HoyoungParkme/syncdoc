"""SYNC-DOM-002 2.4 추적 — Flag · PropagationDecision.

테이블은 SYNC-DOM-003#flags · #propagation_decisions. 인덱스는 DOM-003 3장.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from syncdoc.db import Base


class Flag(Base):
    """SYNC-DOM-002#Flag"""

    __tablename__ = "flags"
    __table_args__ = (
        Index("ix_flags_assignee_user_id_resolved_at", "assignee_user_id", "resolved_at"),
        Index("ix_flags_target_item_id_resolved_at", "target_item_id", "resolved_at"),
        Index("ix_flags_kind_resolved_at", "kind", "resolved_at"),
        Index("ix_flags_cause_item_id", "cause_item_id"),
        Index("ix_flags_cause_version_id", "cause_version_id"),
        Index("ix_flags_resolved_by_user_id", "resolved_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(15))
    target_item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    cause_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    cause_version_id: Mapped[int | None] = mapped_column(ForeignKey("versions.id"))
    assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_with_edit: Mapped[bool | None] = mapped_column(Boolean)


class PropagationDecision(Base):
    """SYNC-DOM-002#PropagationDecision"""

    __tablename__ = "propagation_decisions"
    __table_args__ = (
        Index(
            "ix_propagation_decisions_choice_undecided",
            "choice",
            postgresql_where="choice = 'undecided'",
        ),
        Index("ix_propagation_decisions_decided_by_user_id", "decided_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versions.id"), unique=True)
    choice: Mapped[str] = mapped_column(String(12))
    affected_pks: Mapped[list[int]] = mapped_column(JSONB)
    changed_pks: Mapped[list[int]] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def affected_count(self) -> int:
        """MS-004 get_decision — len(affected_pks)."""
        return len(self.affected_pks)
