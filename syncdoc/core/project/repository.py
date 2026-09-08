"""SYNC-DOM-002 4.1 — projects·repositories 조회·저장. DB만 안다."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from syncdoc.core.project.models import Project, Repository


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_code(self, code: str) -> Project | None:
        stmt = select(Project).options(joinedload(Project.repository)).where(Project.code == code)
        return self.session.scalar(stmt)

    def add(self, row: Project | Repository) -> None:
        self.session.add(row)
        self.session.flush()
