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


# ── init_project ──
@pytest.fixture
def repos_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from syncdoc.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    return tmp_path / "repos"


async def test_init_project_empty_repo_creates_specs_commit_and_11_null_stages(
    db_session: Session, repos_dir, repos: dict
) -> None:
    from tests.core.account.test_service import make_user
    from tests.infra.conftest import git as g

    user = make_user(db_session, login="hoyoung")
    # repos 픽스처의 remote는 docs/specs/PRD/SYNC-PRD-001.md가 이미 있다 → 새 bare 저장소를 하나 더
    bare = repos_dir.parent / "empty.git"
    g(repos_dir.parent, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = repos_dir.parent / "seed"
    g(repos_dir.parent, "clone", "-q", str(bare), str(seed))
    g(seed, "checkout", "-q", "-b", "main")
    (seed / "README.md").write_text("x", encoding="utf-8")
    g(seed, "add", "README.md")
    g(seed, "commit", "-q", "-m", "init")
    g(seed, "push", "-q", "origin", "HEAD:main")
    svc = ProjectService(db_session)
    project = await svc.init_project(str(bare), "NEW", "새 프로젝트", user)
    assert project.code == "NEW" and project.repository.remote_url == str(bare)
    p = svc.get("NEW")
    assert p.repository.workdir_path == str(repos_dir / "NEW")
    assert p.repository.last_processed_commit == g(bare, "rev-parse", "main")
    assert g(bare, "log", "-1", "--format=%s", "main") == "chore(NEW): init syncdoc"
    tree = g(bare, "ls-tree", "-r", "--name-only", "main")
    assert "docs/specs/_templates/PRD.md" in tree and "docs/specs/STD/.gitkeep" in tree
    assert "docs/specs/README.md" in tree and "docs/specs/assets/.gitkeep" in tree


async def test_init_project_rejects_invalid_and_duplicate_code(
    db_session: Session, repos_dir
) -> None:
    from syncdoc.core.errors import ProjectCodeConflict, ProjectCodeInvalid
    from tests.core.account.test_service import make_user

    user = make_user(db_session)
    make_project(db_session, "SYNC")
    with pytest.raises(ProjectCodeInvalid):
        await ProjectService(db_session).init_project("https://x", "sync", "n", user)
    with pytest.raises(ProjectCodeConflict):
        await ProjectService(db_session).init_project("https://x", "SYNC", "n", user)


async def test_init_project_existing_specs_rejects_and_removes_workdir(
    db_session: Session, repos_dir, repos: dict
) -> None:
    from syncdoc.core.errors import ExistingSpecs, NotImplementedYet
    from tests.core.account.test_service import make_user

    user = make_user(db_session)
    svc = ProjectService(db_session)
    with pytest.raises(ExistingSpecs) as ei:
        await svc.init_project(str(repos["remote"]), "EXST", "n", user)
    assert ei.value.extra["doc_count"] == 1
    assert not (repos_dir / "EXST").exists()
    with pytest.raises(NotFound):
        svc.get("EXST")
    with pytest.raises(NotImplementedYet):  # B1 스텁 — B4에서 rebuild로 해제
        await svc.init_project(str(repos["remote"]), "EXST", "n", user, import_existing=True)


async def test_init_project_clone_failure_leaves_nothing(
    db_session: Session, repos_dir, tmp_path
) -> None:
    from syncdoc.core.errors import PushFailed
    from tests.core.account.test_service import make_user

    user = make_user(db_session)
    with pytest.raises(PushFailed) as ei:
        await ProjectService(db_session).init_project(str(tmp_path / "nope.git"), "GONE", "n", user)
    assert ei.value.extra["reason"].startswith("clone:")
    assert not (repos_dir / "GONE").exists()
    with pytest.raises(NotFound):
        ProjectService(db_session).get("GONE")
