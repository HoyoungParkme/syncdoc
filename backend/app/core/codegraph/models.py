"""SYNC-DOM-002 2.10 코드 그래프 — CodeGraph. 테이블은 SYNC-DOM-003#code_graphs.

명세 표를 가리키지 않는다 — projects만 FK이고 PK가 곧 project_id라 프로젝트마다 한 행이다.
항목 ID는 graph(JSONB) 안의 글자다. 프로젝트 행이 지워지면 cascade로 함께 사라진다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CodeGraph(Base):
    """SYNC-DOM-002#CodeGraph"""

    __tablename__ = "code_graphs"

    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    commit_hash: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(String(10))  # repo · server (앱 검증)
    graph: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    function_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error: Mapped[str | None] = mapped_column(String(300))
