"""SYNC-API-001 4장 — Diff · FlagDetail · Todo · DecisionDetail · Decide · DecisionResult."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.types import DecisionDetail as DecisionDetailDto
from app.core.types import DecisionResult as DecisionResultDto
from app.core.types import Diff as DiffDto
from app.core.types import FlagDetail as FlagDetailDto
from app.core.types import Todo as TodoDto
from app.web.schemas.comments import CommentSummary
from app.web.schemas.common import Base, FlagSummary, ItemRef, UserRef
from app.web.schemas.documents import DocumentSummary
from app.web.schemas.projects import Version


class DiffLine(Base):
    op: Literal["add", "del", "ctx"]
    text: str


class Hunk(Base):
    item_id: str | None
    downstream_count: int
    lines: list[DiffLine]


class Diff(Base):
    from_version: int
    to_version: int
    hunks: list[Hunk]

    @classmethod
    def of(cls, d: DiffDto | None) -> Diff | None:
        return cls.model_validate(d) if d else None


class FlagDetail(FlagSummary):
    cause_diff: Diff | None
    cause_change_count: int
    target_body: str
    target_version_no: int
    target_changed_since_raise: bool
    cause_deleted_at: datetime | None  # MS-008 flag_view 4 (API 스키마에 없음, 보고)
    cause_body: str | None  # MS-008 flag_view 4a

    @classmethod
    def of(cls, f: FlagDetailDto) -> FlagDetail:  # type: ignore[override]
        return cls.model_validate(f)


class PendingDecision(Base):
    version_id: int
    doc_id: str
    version_no: int
    message: str
    affected_count: int
    created_at: datetime


class Todo(Base):
    needs_check: list[FlagSummary]
    broken_ref: list[FlagSummary]
    upstream_impact: list[FlagSummary]
    pending_decisions: list[PendingDecision]
    convention_errors: list[DocumentSummary]
    unresolved_comments: list[CommentSummary]
    unassigned: list[FlagSummary]
    total: int

    @classmethod
    def of(cls, t: TodoDto) -> Todo:
        return cls(
            needs_check=[FlagSummary.of(f) for f in t.needs_check],
            broken_ref=[FlagSummary.of(f) for f in t.broken_ref],
            upstream_impact=[FlagSummary.of(f) for f in t.upstream_impact],
            pending_decisions=[PendingDecision.model_validate(p) for p in t.pending_decisions],
            convention_errors=[DocumentSummary.of(d) for d in t.convention_errors],
            unresolved_comments=[CommentSummary.model_validate(c) for c in t.unresolved_comments],
            unassigned=[FlagSummary.of(f) for f in t.unassigned],
            total=t.total,
        )


class AffectedItem(ItemRef):
    caused_by_items: list[str]
    assignee: UserRef | None


class DecisionDetail(Base):
    version: Version
    doc_id: str
    change_diff: Diff
    affected: list[AffectedItem]
    choice: Literal["propagate", "skip", "undecided"]

    @classmethod
    def of(cls, d: DecisionDetailDto) -> DecisionDetail:
        return cls(
            version=Version.of(d.version),
            doc_id=d.doc_id,
            change_diff=Diff.model_validate(d.change_diff),
            affected=[AffectedItem.model_validate(a) for a in d.affected],
            choice=d.choice,  # type: ignore[arg-type]
        )


class Decide(BaseModel):
    choice: Literal["propagate", "skip"]
    reason: str | None = None


class DecisionResult(Base):
    choice: str
    flags_raised: int

    @classmethod
    def of(cls, r: DecisionResultDto) -> DecisionResult:
        return cls.model_validate(r)
