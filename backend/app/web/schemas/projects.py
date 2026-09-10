"""SYNC-API-001 4장 — StageSummary · ProjectSummary · ProjectDetail · Version · 요청 InitProject."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.types import ProjectDetail as ProjectDetailDto
from app.core.types import ProjectSummary as ProjectSummaryDto
from app.core.types import Version as VersionDto
from app.web.schemas.common import Author, Base
from app.web.schemas.documents import DocumentSummary


class StageSummary(Base):
    stage: int
    doc_type: str
    status: str | None
    doc_count: int
    gate_warning: bool
    flag_count: int


class ProjectSummary(Base):
    code: str
    name: str
    remote_url: str
    stages: list[StageSummary]
    std_docs: list[DocumentSummary]
    counts: dict[str, int]
    updated_at: datetime | None

    @classmethod
    def of(cls, p: ProjectSummaryDto) -> ProjectSummary:
        return cls(**cls._fields(p))

    @staticmethod
    def _fields(p: ProjectSummaryDto) -> dict:
        return {
            "code": p.code,
            "name": p.name,
            "remote_url": p.remote_url,
            "stages": [StageSummary.model_validate(s) for s in p.stages],
            "std_docs": [DocumentSummary.of(d) for d in p.std_docs],
            "counts": p.counts,
            "updated_at": p.updated_at,
        }


class Version(Base):
    doc_id: str
    version_no: int | None
    commit_hash: str
    message: str
    author: Author | None
    created_at: datetime

    @classmethod
    def of(cls, v: VersionDto) -> Version:
        return cls(
            doc_id=v.doc_id,
            version_no=v.version_no,
            commit_hash=v.commit_hash,
            message=v.message,
            author=Author.of(v.author_view),
            created_at=v.created_at,
        )


class ProjectDetail(ProjectSummary):
    docs: list[DocumentSummary]
    recent_changes: list[Version]
    last_processed_commit: str | None
    behind_by: int | None

    @classmethod
    def of(cls, p: ProjectDetailDto) -> ProjectDetail:  # type: ignore[override]
        return cls(
            **cls._fields(p),
            docs=[DocumentSummary.of(d) for d in p.docs],
            recent_changes=[Version.of(v) for v in p.recent_changes],
            last_processed_commit=p.last_processed_commit,
            behind_by=p.behind_by,
        )


class InitProject(BaseModel):
    remote_url: str
    code: str = Field(pattern=r"^[A-Z]{1,4}$")
    name: str = Field(max_length=100)
    import_existing: bool = False
