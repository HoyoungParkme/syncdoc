"""SYNC-API-001 4장 — 실행 기록(카드 CJ). TraceRecord는 기록 도구가 올리는 꼴.

TraceRecord는 꼴만 본다 — 저장하는 것은 받은 JSON 그대로다(SYNC-MS-025, 서버는 기록을
고치지 않는다).
사건은 필수 키와 장비 표시만 본다 — 나머지는 기록 도구의 것이다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.web.schemas.common import Base


class TraceInfraIn(BaseModel):
    kind: Literal["db", "http", "redis", "s3"]
    target: str
    op: str | None = None


class TraceEventIn(BaseModel):
    i: int
    parent: int
    fn: str
    t0: float
    infra: TraceInfraIn | None = None


class TraceRecord(BaseModel):
    """SYNC-API-001 4장 TraceRecord — 기록 하나(사건 2만 개까지)."""

    version: Literal[1]
    id: str = Field(max_length=64)
    kind: Literal["back", "front", "job"]
    method: str = Field(max_length=10)
    path: str = Field(max_length=500)
    status: int | None = None
    error: str | None = None
    startedAt: str  # noqa: N815 — 기록 도구의 키 그대로
    ms: int = Field(ge=0)
    commit: str | None = Field(default=None, max_length=40)
    query: str | None = None
    page: str | None = None
    truncated: bool
    events: list[TraceEventIn] = Field(max_length=20000)


class TraceBrief(Base):
    """SYNC-API-001 4장 TraceBrief — 실행 기록의 머리."""

    id: int
    trace_key: str
    kind: str
    method: str | None
    path: str
    status: int | None
    error: str | None
    started_at: datetime
    ms: int
    commit_hash: str | None
    event_count: int
    truncated: bool
    received_at: datetime


class TraceView(TraceBrief):
    """SYNC-API-001 4장 TraceView — 머리와 기록 전체."""

    record: dict


class TraceCoverage(Base):
    traces: int
    keys: list[str]
    infra: list[dict]


class TraceSpan(Base):
    key: str
    file: str
    line: int
    end: int
    name: str
    qual: str
    route: dict | None


class TraceSpans(Base):
    """SYNC-API-001 4장 TraceSpans — 기록 도구의 준비."""

    commit_hash: str | None
    spans: list[TraceSpan]
    infra: list[dict]


class Deleted(Base):
    deleted: int
