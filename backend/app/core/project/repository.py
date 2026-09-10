"""SYNC-DOM-002 4.1 — projects·repositories 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import select, text
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

    def delete_all_of(self, project_id: int) -> None:
        """프로젝트에 딸린 행을 자식부터 지운다 (MS-001 delete_project 2단계).

        ORM cascade를 안 쓴다 — 관계가 flags·references처럼 항목을 건너 물려 있어
        지우는 순서를 코드가 쥐고 있어야 한다.
        """
        self.session.execute(
            text("""
            with d as (select id from documents where project_id = :pid),
                 i as (select id from items where document_id in (select id from d))
            delete from flags
             where target_item_id in (select id from i) or cause_item_id in (select id from i)
            """),
            {"pid": project_id},
        )
        for stmt in (
            'delete from "references" where from_document_id in'
            " (select id from documents where project_id = :pid)",
            'delete from "references" where to_document_id in'
            " (select id from documents where project_id = :pid)",
            'delete from "references" where to_item_id in (select id from items'
            " where document_id in (select id from documents where project_id = :pid))",
            "delete from propagation_decisions where version_id in (select id from versions"
            " where document_id in (select id from documents where project_id = :pid))",
            "delete from comments where document_id in"
            " (select id from documents where project_id = :pid)",
            "delete from status_changes where document_id in"
            " (select id from documents where project_id = :pid)",
            "delete from items where document_id in"
            " (select id from documents where project_id = :pid)",
            "delete from versions where document_id in"
            " (select id from documents where project_id = :pid)",
            "delete from documents where project_id = :pid",
            "delete from repositories where project_id = :pid",
            "delete from projects where id = :pid",
        ):
            self.session.execute(text(stmt), {"pid": project_id})

    def add(self, row: Project | Repository) -> None:
        self.session.add(row)
        self.session.flush()
