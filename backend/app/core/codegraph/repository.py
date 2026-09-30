"""SYNC-DOM-002 4.11 — code_graphs 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.codegraph.models import CodeGraph


class CodeGraphRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, project_id: int) -> CodeGraph | None:
        return self.session.get(CodeGraph, project_id)

    def add(self, row: CodeGraph) -> CodeGraph:
        self.session.add(row)
        return row

    def delete_by_project(self, project_id: int) -> None:
        self.session.execute(delete(CodeGraph).where(CodeGraph.project_id == project_id))
