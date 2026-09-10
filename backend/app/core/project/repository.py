"""SYNC-DOM-002 4.1 — projects·repositories 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.project.models import Project, Repository


def normalize_remote(url: str) -> str:
    """저장소 주소 비교용 — 소문자, 끝 `/`·`.git` 제거 (web/routers/hooks.py 와 같은 규칙)."""
    return url.strip().rstrip("/").lower().removesuffix(".git")  # 소문자 먼저 — .GIT 도 잡는다


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_code(self, code: str) -> Project | None:
        stmt = select(Project).options(joinedload(Project.repository)).where(Project.code == code)
        return self.session.scalar(stmt)

    def all(self) -> list[Project]:
        stmt = select(Project).options(joinedload(Project.repository)).order_by(Project.code)
        return list(self.session.scalars(stmt))

    def by_remote_url(self, remote_url: str) -> Project | None:
        """같은 저장소를 쓰는 프로젝트. 정규화 비교라 파이썬에서 — 행이 적다."""
        want = normalize_remote(remote_url)
        for p in self.all():
            if p.repository and normalize_remote(p.repository.remote_url) == want:
                return p
        return None

    def exists(self, code: str) -> bool:
        return self.session.scalar(select(Project.id).where(Project.code == code)) is not None

    def add(self, row: Project | Repository) -> None:
        self.session.add(row)
        self.session.flush()
