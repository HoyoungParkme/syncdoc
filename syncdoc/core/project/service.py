"""SYNC-MS-001 — ProjectService. projects·repositories만. documents를 모른다 — 요약은 queries."""

from __future__ import annotations

from sqlalchemy.orm import Session

from syncdoc.core.errors import NotFound
from syncdoc.core.project.models import Project
from syncdoc.core.project.repository import ProjectRepository


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProjectRepository(session)

    def get(self, code: str) -> Project:
        """SYNC-MS-001#ProjectService.get"""
        project = self.repo.by_code(code)
        if project is None:
            raise NotFound("project", code)
        return project
