"""SYNC-MS-025 — core/trace/service.py. TraceService — 실행 기록을 받아 두고(최근 300개) 내준다.

기록을 고치지 않는다 — 비밀 가리기는 기록 도구의 일이다(INFRA C13). 소유 검사는 부르는 쪽(라우터·MCP
도구)이 ProjectService.get_owned로 먼저 한다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.errors import NotFound, TraceInvalid
from app.core.trace.models import Trace
from app.core.trace.repository import TraceRepository
from app.core.types import TraceBrief, TraceCoverage, TraceView

KEEP = 300  # 프로젝트마다 남기는 수 (2026-10-12 사용자 결정)
MAX_EVENTS = 20000
MAX_BYTES = 4 * 1024 * 1024  # 본문 — 라우터가 먼저 본다


def _brief(row) -> TraceBrief:
    return TraceBrief(
        row.id,
        row.trace_key,
        row.kind,
        row.method,
        row.path,
        row.status,
        row.error,
        row.started_at,
        row.ms,
        row.commit_hash,
        row.event_count,
        row.truncated,
        row.received_at,
    )


_ISO = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?", re.ASCII
)


def _started(text: str) -> datetime:
    """`startedAt` — ISO 8601(초까지·소수 6자리까지·Z나 ±hh:mm). 시간대가 없으면 UTC."""
    try:
        if not _ISO.fullmatch(text):
            raise ValueError(text)
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise TraceInvalid("startedAt — 시각이 아니다") from None
    # 받은 시간대가 아니라 UTC로 — 넣은 직후의 머리와 목록(DB에서 읽은 것)이 같은 글이 된다
    return (t if t.tzinfo is not None else t.replace(tzinfo=UTC)).astimezone(UTC)


class TraceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TraceRepository(session)

    def save(self, project_id: int, user_id: int, record: dict) -> tuple[TraceBrief, bool]:
        """SYNC-MS-025#TraceService.save

        꼴(부모·차례)을 보고 넣는다. 같은 기록(trace_key)은 하나 — 있는 것을 돌려준다. 넣은 뒤 같은
        트랜잭션에서 최근 300개만 남긴다.
        """
        events = record["events"]
        seen: set[int] = set()
        for n, e in enumerate(events):
            if e["i"] != n:
                raise TraceInvalid(f"events[{n}] — i가 차례가 아니다")
            if e["parent"] != -1 and e["parent"] not in seen:
                raise TraceInvalid(f"events[{n}] — 부모가 없다")
            seen.add(e["i"])
        started = _started(record["startedAt"])
        old = self.repo.by_key(project_id, record["id"])
        if old is not None:
            return _brief(old), False
        kind = record["kind"]
        error = record.get("error")
        row = self.repo.add(
            Trace(
                project_id=project_id,
                user_id=user_id,
                trace_key=record["id"],
                kind=kind,
                method=None if kind == "job" else record["method"],
                path=record["path"],
                status=record.get("status"),
                error=error[:300] if error is not None else None,
                started_at=started,
                ms=record["ms"],
                commit_hash=record.get("commit"),
                event_count=len(events),
                truncated=record["truncated"],
                record=record,
                received_at=now_utc(),
            )
        )
        self.repo.keep_recent(project_id, KEEP)
        self.session.flush()
        return _brief(row), True

    def list_recent(self, project_id: int, limit: int = 300) -> list[TraceBrief]:
        """SYNC-MS-025#TraceService.list_recent"""
        return [_brief(r) for r in self.repo.recent(project_id, limit)]

    def get(self, project_id: int, trace_id: int) -> TraceView:
        """SYNC-MS-025#TraceService.get"""
        row = self.repo.get(project_id, trace_id)
        if row is None:
            raise NotFound("trace", str(trace_id))
        b = _brief(row)
        return TraceView(**{k: getattr(b, k) for k in b.__dataclass_fields__}, record=row.record)

    def delete(self, project_id: int, trace_id: int | None = None) -> int:
        """SYNC-MS-025#TraceService.delete"""
        if trace_id is not None and self.repo.get(project_id, trace_id) is None:
            raise NotFound("trace", str(trace_id))
        n = self.repo.delete(project_id, trace_id)
        self.session.flush()
        return n

    def coverage(self, project_id: int) -> TraceCoverage:
        """SYNC-MS-025#TraceService.coverage

        기록 전부의 사건 — `@`로 시작하지 않는 fn은 함수 열쇠, infra는 (종류, 대상).
        """
        rows = self.repo.events_of(project_id)
        keys: set[str] = set()
        infra: set[tuple[str, str]] = set()
        for events in rows:
            for e in events or []:
                fn = e.get("fn", "")
                if fn and not fn.startswith("@"):
                    keys.add(fn)
                i = e.get("infra")
                if i:
                    infra.add((i.get("kind", ""), i.get("target", "")))
        return TraceCoverage(
            len(rows),
            sorted(keys),
            [{"kind": k, "target": t} for k, t in sorted(infra)],
        )

    def delete_by_project(self, project_id: int) -> None:
        """SYNC-MS-025#TraceService.delete_by_project"""
        self.repo.delete_by_project(project_id)
