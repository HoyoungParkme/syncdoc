"""SYNC-DOM-002 4.12 — traces 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.trace.models import Trace


class TraceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_key(self, project_id: int, trace_key: str) -> Trace | None:
        return self.session.scalar(
            select(Trace).where(Trace.project_id == project_id, Trace.trace_key == trace_key)
        )

    def get(self, project_id: int, trace_id: int) -> Trace | None:
        return self.session.scalar(
            select(Trace).where(Trace.id == trace_id, Trace.project_id == project_id)
        )

    def add(self, row: Trace) -> Trace:
        self.session.add(row)
        self.session.flush()
        return row

    def keep_recent(self, project_id: int, keep: int) -> None:
        """최근 keep개만 남긴다 — 받은 때(같으면 id) 내림차순."""
        recent = (
            select(Trace.id)
            .where(Trace.project_id == project_id)
            .order_by(Trace.received_at.desc(), Trace.id.desc())
            .limit(keep)
        )
        self.session.execute(
            delete(Trace).where(Trace.project_id == project_id, Trace.id.not_in(recent))
        )

    def recent(self, project_id: int, limit: int) -> list:
        """머리 컬럼만 — record는 읽지 않는다."""
        cols = [
            c for c in Trace.__table__.columns if c.name not in ("record", "project_id", "user_id")
        ]
        return list(
            self.session.execute(
                select(*cols)
                .where(Trace.project_id == project_id)
                .order_by(Trace.received_at.desc(), Trace.id.desc())
                .limit(limit)
            )
        )

    def events_of(self, project_id: int) -> list:
        return list(
            self.session.scalars(
                select(Trace.record["events"]).where(Trace.project_id == project_id)
            )
        )

    def delete(self, project_id: int, trace_id: int | None) -> int:
        q = delete(Trace).where(Trace.project_id == project_id)
        if trace_id is not None:
            q = q.where(Trace.id == trace_id)
        return self.session.execute(q).rowcount or 0

    def count(self, project_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count()).select_from(Trace).where(Trace.project_id == project_id)
            )
            or 0
        )

    def delete_by_project(self, project_id: int) -> None:
        self.session.execute(delete(Trace).where(Trace.project_id == project_id))
