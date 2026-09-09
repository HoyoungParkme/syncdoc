"""SYNC-MS-001 — ProjectService. projects·repositories만. documents를 모른다 — 요약은 queries."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from syncdoc.config import settings
from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService
from syncdoc.core.errors import (
    ExistingSpecs,
    NotFound,
    ProjectCodeConflict,
    ProjectCodeInvalid,
    PushFailed,
    RepositoryAlreadyRegistered,
)
from syncdoc.core.project.models import Project, Repository
from syncdoc.core.project.repository import ProjectRepository
from syncdoc.core.types import Author, AuthorKind, Entry, RebuildResult, RepoStatus
from syncdoc.infra import git
from syncdoc.infra.git import GitError

_locks: dict[str, asyncio.Lock] = {}


def _lock(code: str) -> asyncio.Lock:
    """코드 단위 락 (MS-001 0단계 · UC-A1 2c) — 동시 초기화가 서로의 작업 사본을 지운다."""
    return _locks.setdefault(code, asyncio.Lock())


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
        async with _lock(code):  # 0. 같은 코드 동시 초기화 (UC-A1 2c)
            return await self._init(remote_url, code, name, user, import_existing)

    async def _init(
        self, remote_url: str, code: str, name: str, user: User, import_existing: bool
    ) -> Project:
        if not re.fullmatch(r"[A-Z]{1,4}", code):
            raise ProjectCodeInvalid("^[A-Z]{1,4}$")
        if self.repo.exists(code):
            raise ProjectCodeConflict(code)
        # 2a — 한 저장소를 두 프로젝트가 쓰면 문서 ID가 겹쳐 이력을 덮어쓴다 (UC-A1 2d)
        owner = self.repo.by_remote_url(remote_url)
        if owner is not None:
            raise RepositoryAlreadyRegistered(owner.code)
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
        savepoint = self.session.begin_nested()
        project = Project(code=code, name=name)
        self.repo.add(project)
        repository = Repository(
            project_id=project.id,
            remote_url=remote_url,
            workdir_path=str(workdir),
            registered_by_user_id=user.id,
        )
        self.repo.add(repository)
        if has and import_existing:  # 3a2 — 기존 명세를 재구축으로 가져온다. 락·트랜잭션은 그쪽
            from syncdoc.core import pipeline  # 서비스가 pipeline을 부르는 유일한 곳(DOM-002 3.2)

            await pipeline.rebuild(code, session=self.session)
            return self.repo.by_code(code)
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

    async def repo_status(self) -> list[RepoStatus]:
        """SYNC-MS-001#ProjectService.repo_status"""
        out: list[RepoStatus] = []
        for p in self.repo.all():
            r = p.repository
            behind, error = None, None
            try:  # public이라 토큰 없이. 실패해도 화면은 뜨고 사유를 보여준다 (MS-001)
                await git.fetch(Path(r.workdir_path))
                if r.last_processed_commit:
                    behind = await git.rev_list_count(
                        Path(r.workdir_path), f"{r.last_processed_commit}..origin/HEAD"
                    )
            except GitError as e:
                error = e.stderr.strip().splitlines()[-1] if e.stderr.strip() else str(e)
            out.append(
                RepoStatus(
                    p.code, r.remote_url, r.last_processed_commit, r.synced_at, behind, error
                )
            )
        return out

    async def rebuild_index(self, code: str) -> RebuildResult:
        """SYNC-MS-001#ProjectService.rebuild_index"""
        from syncdoc.core import pipeline  # 서비스가 pipeline을 부르는 유일한 곳(DOM-002 3.2)

        self.get(code)
        return await pipeline.rebuild(code)
