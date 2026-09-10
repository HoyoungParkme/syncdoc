"""SYNC-MS-001 — ProjectService. projects·repositories만. documents를 모른다 — 요약은 queries."""

from __future__ import annotations

import re
import shutil

from sqlalchemy.orm import Session

from syncdoc.config import settings
from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService
from syncdoc.core.errors import (
    ExistingSpecs,
    NotFound,
    NotImplementedYet,
    ProjectCodeConflict,
    ProjectCodeInvalid,
    PushFailed,
)
from syncdoc.core.project.models import Project, Repository
from syncdoc.core.project.repository import ProjectRepository
from syncdoc.core.types import Author, AuthorKind, Entry
from syncdoc.infra import git
from syncdoc.infra.git import GitError


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProjectRepository(session)

    async def init_project(
        self,
        remote_url: str,
        code: str,
        name: str,
        user: User,
        import_existing: bool = False,
    ) -> Project:
        """SYNC-MS-001#ProjectService.init_project"""
        if not re.fullmatch(r"[A-Z]{1,4}", code):
            raise ProjectCodeInvalid("^[A-Z]{1,4}$")
        if self.repo.exists(code):
            raise ProjectCodeConflict(code)
        workdir = settings.REPOS_DIR / code
        shutil.rmtree(workdir, ignore_errors=True)
        token = AccountService.github_token_for(user)
        try:
            await git.clone(remote_url, workdir, token)
        except GitError as e:
            shutil.rmtree(workdir, ignore_errors=True)
            raise PushFailed(f"clone: {e.stderr.strip()}") from e
        has = await git.exists(workdir, "docs/specs")
        if has and not import_existing:
            n = len(await git.list(workdir, "docs/specs/*/*.md"))
            shutil.rmtree(workdir, ignore_errors=True)
            raise ExistingSpecs(n)
        if has and import_existing:
            shutil.rmtree(workdir, ignore_errors=True)
            raise NotImplementedYet("init_project(import_existing=true) — B4 pipeline.rebuild")
        savepoint = self.session.begin_nested()
        project = Project(code=code, name=name)
        self.repo.add(project)
        repository = Repository(
            project_id=project.id, remote_url=remote_url, workdir_path=str(workdir)
        )
        self.repo.add(repository)
        files = await git.init_specs(workdir)
        author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.mcp)
        try:
            commit_hash = await git.commit_push(
                workdir, f"chore({code}): init syncdoc", author, files=files
            )
        except PushFailed:
            savepoint.rollback()
            shutil.rmtree(workdir, ignore_errors=True)
            raise
        repository.last_processed_commit = commit_hash
        self.session.flush()
        return self.repo.by_code(code)

    def list_projects(self) -> list[Project]:
        """SYNC-MS-001#ProjectService.list_projects"""
        return self.repo.all()

    def get(self, code: str) -> Project:
        """SYNC-MS-001#ProjectService.get"""
        project = self.repo.by_code(code)
        if project is None:
            raise NotFound("project", code)
        return project
