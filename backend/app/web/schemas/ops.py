"""SYNC-API-001 4장 — Graph · RepoStatus · RebuildResult · SaveResult · Revert · DownstreamView."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import DownstreamView as DownstreamViewDto
from app.core.types import Graph as GraphDto
from app.web.schemas.common import Base, ItemRef


class GraphNode(Base):
    id: str
    doc_id: str
    item_id: str | None
    stage: int | None
    isolated: bool
    has_flag: bool  # UI-8 3.1 — 노드 테두리·배경과 ▲


class GraphEdge(Base):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    from_: str = Field(alias="from", serialization_alias="from")
    to: str | None
    raw_target: str
    is_missing: bool


class Graph(Base):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    project_name: str

    @classmethod
    def of(cls, g: GraphDto) -> Graph:
        return cls(
            project_name=g.project_name,
            nodes=[GraphNode.model_validate(n) for n in g.nodes],
            edges=[
                GraphEdge(from_=e.from_, to=e.to, raw_target=e.raw_target, is_missing=e.is_missing)
                for e in g.edges
            ],
        )


class RepoStatus(Base):
    code: str
    remote_url: str
    last_processed_commit: str | None
    synced_at: datetime | None
    behind_by: int | None
    fetched_at: datetime | None
    backed_up_at: datetime | None = None
    backup_stale: bool = False
    error: str | None


class RebuildError(Base):
    doc_id: str
    detail: str


class Dropped(Base):
    """새 버전에 이어 붙일 수 없어 버린 추적 행 (UI-14 5.3)."""

    kind: str
    count: int
    reason: str


class RebuildResult(Base):
    docs: int
    items: int
    references: int
    versions: int
    convention_errors: list[RebuildError]
    dropped: list[Dropped] = []


class RestoreResult(Base):
    """SYNC-API-001 RestoreResult — dropped가 RebuildResult와 같은 모양이다 (UI-14 5.3)."""

    flags: int
    decisions: int
    comments: int
    skipped: int
    dropped: list[Dropped] = []


class SaveResult(Base):
    doc_id: str
    version_no: int
    commit_hash: str
    status: str
    pending_decision_version_id: int | None
    warnings: list[str]


class Revert(BaseModel):
    to_version: int = Field(ge=1)
    confirm_item_deletion: bool = False


class DownstreamDoc(Base):
    doc_id: str
    title: str
    items: list[str]


class DownstreamView(Base):
    by_item: dict[str, list[ItemRef]]
    by_document: list[DownstreamDoc]

    @classmethod
    def of(cls, d: DownstreamViewDto) -> DownstreamView:
        return cls.model_validate(d)
