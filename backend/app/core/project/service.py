"""SYNC-MS-001 — ProjectService. projects·repositories만. documents를 모른다 — 요약은 queries."""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import replace
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import (
    ExistingSpecs,
    NotFound,
    ProjectCodeConflict,
    ProjectCodeInvalid,
    PushFailed,
    RepoCreateFailed,
    RepositoryAlreadyRegistered,
)
from app.core.project.models import Project, Repository
from app.core.project.repository import ProjectRepository
from app.core.types import Author, AuthorKind, Entry, RebuildResult, RepoStatus
from app.infra import git, github
from app.infra.git import GitError

# 첨부로 주는 확장자 — 이 밖은 없는 것과 같다 (API-001 GET …/files/{path})
_ASSET_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "woff", "woff2", "ttf"}

_locks: dict[str, asyncio.Lock] = {}


def _lock(code: str) -> asyncio.Lock:
    """코드 단위 락 (MS-001 0단계 · UC-A1 2c) — 동시 초기화가 서로의 작업 사본을 지운다."""
    return _locks.setdefault(code, asyncio.Lock())


def _split_remote(remote_url: str) -> tuple[str, str]:
    """`https://github.com/owner/repo(.git)` → `(owner, repo)` (MS-001 3b).

    ssh 형태(`git@github.com:owner/repo.git`)도 받는다 — clone은 그것도 되므로
    여기서만 막으면 경로가 갈린다.
    """
    s = remote_url.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[: -len(".git")]
    if ":" in s and "//" not in s:  # ssh
        s = s.split(":", 1)[1]
    parts = [x for x in s.split("/") if x]
    if len(parts) < 2:
        raise RepoCreateFailed(f"저장소 주소에서 소유자·이름을 못 읽었다: {remote_url}")
    return parts[-2], parts[-1]


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
        create_repo: bool = False,
    ) -> Project:
        """SYNC-MS-001#ProjectService.init_project"""
        async with _lock(code):  # 0. 같은 코드 동시 초기화 (UC-A1 2c)
            return await self._init(remote_url, code, name, user, import_existing, create_repo)

    async def _init(
        self,
        remote_url: str,
        code: str,
        name: str,
        user: User,
        import_existing: bool,
        create_repo: bool = False,
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
        # 3b — 없으면 만든다. **기본값이 거짓인 이유**: 참이면 주소 오타가 조용히 새
        # 저장소를 만든다. 지금은 clone이 실패해 push-failed가 나서 오타를 알아챈다 (카드 F)
        if create_repo:
            owner_name, repo_name = _split_remote(remote_url)
            await github.create_repo(token, owner_name, repo_name)
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
        project = Project(code=code, name=name, owner_user_id=user.id)  # 등록한 사람이 소유자
        self.repo.add(project)
        repository = Repository(
            project_id=project.id,
            remote_url=remote_url,
            workdir_path=str(workdir),
            registered_by_user_id=user.id,
        )
        self.repo.add(repository)
        if has and import_existing:  # 3a2 — 기존 명세를 재구축으로 가져온다. 락·트랜잭션은 그쪽
            from app.core import pipeline  # 서비스가 pipeline을 부르는 유일한 곳(DOM-002 3.2)

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
        """SYNC-MS-001#ProjectService.list_projects

        시스템 경로 전용(폴링·웹훅). 사람 경로는 list_owned — 여기서 부르면 남의 것이 샌다.
        """
        return self.repo.all()

    def get(self, code: str) -> Project:
        """SYNC-MS-001#ProjectService.get

        시스템 경로 전용(GitHub 처리·폴링·재구축). 사람 경로는 get_owned.
        """
        project = self.repo.by_code(code)
        if project is None:
            raise NotFound("project", code)
        return project

    def get_owned(self, code: str, user: User) -> Project:
        """SYNC-MS-001#ProjectService.get_owned

        남의 프로젝트는 없는 것과 같다 — get의 없음과 **같은** not-found를 낸다. 403을 두면
        남의 프로젝트가 있다는 사실이 샌다. `get(code, user | None)`으로 합치지 않는 이유는
        None이 「필터 없음」이 되어 빠뜨린 자리가 조용히 전체 열람이 되기 때문이다(DOM-002 4.1).
        """
        project = self.get(code)
        if project.owner_user_id != user.id:
            raise NotFound("project", code)
        return project

    def asset_path(self, code: str, path: str, user: User) -> Path:
        """SYNC-MS-001#ProjectService.asset_path

        작업 사본 `docs/specs/` 아래의 첨부 파일 경로. 소유 검사는 get_owned. `..`·바깥
        심볼릭 링크·허용 밖 확장자·없는 파일은 전부 같은 not-found(file) — 무엇이 있는지 새지
        않는다. 이진 파일이라 git.read(str)를 쓰지 않는다.
        """
        self.get_owned(code, user)
        base = (settings.REPOS_DIR / code / "docs" / "specs").resolve()
        target = (base / path).resolve()
        if not target.is_relative_to(base):
            raise NotFound("file", path)
        if target.suffix.lower().lstrip(".") not in _ASSET_EXTENSIONS:
            raise NotFound("file", path)
        if not target.is_file():
            raise NotFound("file", path)
        return target

    def list_owned(self, user: User) -> list[Project]:
        """SYNC-MS-001#ProjectService.list_owned"""
        return self.repo.owned_by(user.id)

    async def repo_status(self, user: User) -> list[RepoStatus]:
        """SYNC-MS-001#ProjectService.repo_status

        원격을 안 탄다. fetch는 폴링(scheduler.catch_up)이 하고 여기는 그 결과를 본다 —
        화면이 열릴 때마다 저장소 수만큼 fetch가 돌면 느리고, 폴링과 이중이 된다.
        내가 소유한 저장소만 — 관리 화면(UI-14)도 소유로 가른다.
        """
        return [
            RepoStatus(
                p.code,
                p.name,
                p.repository.remote_url,
                p.repository.last_processed_commit,
                p.repository.synced_at,
                p.repository.behind_by,
                p.repository.fetched_at,
                error=p.repository.fetch_error,  # 폴링이 적어 둔 실패 사유 (#46)
            )
            for p in self.repo.owned_by(user.id)
        ]

    async def delete_project(self, code: str, user: User) -> None:
        """SYNC-MS-001#ProjectService.delete_project

        저장소는 건드리지 않는다 — docs/specs/는 원격에 그대로 남고 다시 등록하면
        import_existing으로 돌아온다. 돌아오지 않는 것은 상태 변경 이력뿐이다.
        부르는 쪽이 사람에게 확인을 받아야 한다. 소유자만 지운다.
        """
        async with _lock(code):
            project = self.get_owned(code, user)
            workdir = Path(project.repository.workdir_path)
            self.repo.delete_all_of(project.id)
            self.session.flush()
            shutil.rmtree(workdir, ignore_errors=True)

    async def rebuild_index(self, code: str, user: User) -> RebuildResult:
        """SYNC-MS-001#ProjectService.rebuild_index"""
        from app.core import pipeline  # 서비스가 pipeline을 부르는 유일한 곳(DOM-002 3.2)

        project = self.get_owned(code, user)  # 소유 검사는 여기서. pipeline.rebuild는 get을 쓴다
        # README를 인덱스보다 **먼저** 맞춘다 — 그 커밋이 rebuild의 fetch head에 들어가 밀림이 0으로
        # 끝난다. push가 실패하면 인덱스는 건드리지 않는다 (UC-S6 1a, 카드 AB)
        author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.web_status)
        hash_ = await git.sync_readme(Path(project.repository.workdir_path), author, code)
        result = await pipeline.rebuild(code)
        return replace(result, readme_updated=hash_ is not None)
