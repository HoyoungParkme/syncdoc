"""SYNC-API-001 4장 — StageSummary · ProjectSummary · 요청 InitProject."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from syncdoc.core.types import ProjectSummary as ProjectSummaryDto
from syncdoc.web.schemas.common import Base
from syncdoc.web.schemas.documents import DocumentSummary


class StageSummary(Base):
    stage: int
    doc_type: str
    status: str | None
    doc_count: int
    gate_warning: bool


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
        return cls(
            code=p.code,
            name=p.name,
            remote_url=p.remote_url,
            stages=[StageSummary.model_validate(s) for s in p.stages],
            std_docs=[DocumentSummary.of(d) for d in p.std_docs],
            counts=p.counts,
            updated_at=p.updated_at,
        )


class InitProject(BaseModel):
    remote_url: str
    code: str = Field(pattern=r"^[A-Z]{1,4}$")
    name: str = Field(max_length=100)
    import_existing: bool = False
