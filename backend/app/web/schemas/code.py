"""schemas/code — SYNC-API-001 3.6 코드 그래프(카드 AY). queries의 Code DTO를 그대로 옮긴다."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from app.web.schemas.common import Base


class CodeGraphInfo(Base):
    commit_hash: str | None
    source: str | None
    built_at: datetime
    error: str | None
    function_count: int


class CodeRef(Base):
    ms_id: str
    qual: str | None
    file: str | None
    line: int | None
    status: str | None = None


class CodeBrief(Base):
    ms_id: str
    qual: str | None
    file: str | None
    line: int | None
    same: int
    code_only: int
    spec_only: int


class CodeFunction(Base):
    ms_id: str
    qual: str
    file: str
    line: int
    end: int | None
    calls: list[CodeRef]
    callers: list[CodeRef]


class CodeView(Base):
    graph: CodeGraphInfo | None
    doc_id: str
    item_id: str | None
    is_ms: bool
    missing: bool
    function: CodeFunction | None
    functions: list[CodeBrief]


class CodeText(Base):
    path: str
    start: int
    end: int
    commit_hash: str
    text: str
    truncated: bool


class CodeCallEdge(Base):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    status: str


class CodeCalls(Base):
    graph: CodeGraphInfo | None
    edges: list[CodeCallEdge]


class CodeCommunity(Base):
    id: int
    label: str
    size: int


class CodeNode(Base):
    key: str
    name: str
    qual: str
    file: str
    line: int
    community: int | None
    item: str | None
    ms: str | None
    status: str | None


class CodeNodes(Base):
    graph: CodeGraphInfo | None
    communities: list[CodeCommunity]
    functions: list[CodeNode]
    calls: list[list[str]]
