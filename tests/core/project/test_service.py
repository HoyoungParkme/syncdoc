"""SYNC-MS-001 테스트 관점 — ProjectService."""

import pytest
from sqlalchemy.orm import Session

from syncdoc.core.errors import NotFound
from syncdoc.core.project.service import ProjectService
from tests.core.spec.test_service import make_project


# ── get ──
def test_get_by_code_with_repository_or_not_found(db_session: Session) -> None:
    make_project(db_session, "SYNC")
    p = ProjectService(db_session).get("SYNC")
    assert p.code == "SYNC" and p.repository.workdir_path == "/w"
    with pytest.raises(NotFound) as ei:
        ProjectService(db_session).get("NOPE")
    assert ei.value.extra == {"resource": "project", "id": "NOPE"}


# ── list_projects ──
def test_list_projects_ordered_by_code_with_repository(db_session: Session) -> None:
    make_project(db_session, "ZZ")
    make_project(db_session, "AB")
    got = ProjectService(db_session).list_projects()
    assert [p.code for p in got] == ["AB", "ZZ"] and all(p.repository is not None for p in got)
