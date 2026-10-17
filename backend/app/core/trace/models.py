"""SYNC-DOM-002 2.11 실행 기록 — Trace. 테이블은 SYNC-DOM-003#traces.

명세 표·code_graphs와 선이 없다 — projects·users만 FK. 사건의 함수는 그래프 함수 열쇠를 글자로 든다.
record는 기록 도구가 보낸 그대로(비밀은 기록 도구가 이미 가렸다). 목록에 쓰는 머리는 컬럼에 둔다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Trace(Base):
    """SYNC-DOM-002#Trace"""

    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_key", name="uq_traces_project_key"),
        Index("ix_traces_project_recent", "project_id", text("id DESC")),
        Index("ix_traces_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    trace_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # back · front · job (앱 검증)
    method: Mapped[str | None] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ms: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_hash: Mapped[str | None] = mapped_column(String(40))
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    record: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
