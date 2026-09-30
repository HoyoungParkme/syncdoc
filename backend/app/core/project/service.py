"""SYNC-MS-001 — ProjectService. projects·repositories만. documents를 모른다 — 요약은 queries."""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import (
    ExistingSpecs,
    InvalidRequest,
    NotFound,
    ProjectCodeConflict,
    ProjectCodeInvalid,
    PushFailed,
    RepoCreateFailed,
    RepositoryAlreadyRegistered,
    StorageUnavailable,
    Unauthorized,
)
from app.core.project.models import Project, Repository
from app.core.project.repository import ProjectRepository
from app.core.types import (
    Author,
    AuthorKind,
    Entry,
    HookStatus,
    RebuildResult,
    RepoStatus,
    Storage,
    SyncResult,
)
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


def _archive_dir() -> Path:
    return settings.ORIGINS_DIR / "_archive"


def _archives(code: str) -> list[Path]:
    """그 코드의 보관본 — 이름(UTC 시각) 순이라 끝이 가장 최근이다 (MS-001 3s)."""
    d = _archive_dir()
    return sorted(d.glob(f"{code}-*.git")) if d.exists() else []


def _archive_path(code: str) -> Path:
    """보관할 자리 `_archive/{code}-{UTC %Y%m%d%H%M%S}.git`. 같은 초에 둘이면 뒤에 번호를 붙인다."""
    d = _archive_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    path, n = d / f"{code}-{stamp}.git", 1
    while path.exists():
        path, n = d / f"{code}-{stamp}-{n}.git", n + 1
    return path


def _archived_at(path: Path, code: str) -> str:
    """보관본 이름의 시각 → ISO 문자열(UTC). 읽을 수 없으면 이름 그대로."""
    stamp = path.name[len(code) + 1 : len(code) + 15]
    try:
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return path.name


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProjectRepository(session)

    async def init_project(
        self,
        remote_url: str | None,
        code: str,
        name: str,
        user: User,
        import_existing: bool = False,
        create_repo: bool = False,
        storage: Storage = Storage.github,
    ) -> Project:
        """SYNC-MS-001#ProjectService.init_project"""
        async with _lock(code):  # 0. 같은 코드 동시 초기화 (UC-A1 2c)
            return await self._init(
                remote_url, code, name, user, import_existing, create_repo, Storage(storage)
            )

    async def _init(
        self,
        remote_url: str | None,
        code: str,
        name: str,
        user: User,
        import_existing: bool,
        create_repo: bool = False,
        storage: Storage = Storage.github,
    ) -> Project:
        # 0a·0b — 저장 방식 (UC-A1 1a·1b, PRD R14). 켠 방식만, GitHub이면 주소가 있어야 한다
        if storage.value not in settings.storage_modes:
            raise StorageUnavailable(storage.value, settings.storage_modes)
        if storage == Storage.github and not remote_url:
            raise InvalidRequest(
                [{"loc": "remote_url", "msg": "GitHub 저장은 저장소 주소가 필요하다"}]
            )
        if not re.fullmatch(r"[A-Z]{1,4}", code):
            raise ProjectCodeInvalid("^[A-Z]{1,4}$")
        if self.repo.exists(code):
            raise ProjectCodeConflict(code)
        workdir = settings.REPOS_DIR / code
        origin: Path | None = None
        restored: Path | None = None  # 되살린 보관본의 원래 자리 — 실패하면 돌려놓는다
        token: str | None = None
        if storage == Storage.server:
            shutil.rmtree(workdir, ignore_errors=True)
            # 3s — 서버 안 원본. GitHub 토큰을 구하지 않는다 (카드 BA)
            origin, restored = await self._server_origin(code, import_existing)
            remote_url = str(origin)
        else:
            assert remote_url is not None  # 0b
            # 2a — 한 저장소를 두 프로젝트가 쓰면 문서 ID가 겹쳐 이력을 덮어쓴다 (UC-A1 2d)
            owner = self.repo.by_remote_url(remote_url)
            if owner is not None:
                raise RepositoryAlreadyRegistered(owner.code)
            shutil.rmtree(workdir, ignore_errors=True)
            token = AccountService.github_token_for(user)
            # 3b — 없으면 만든다. **기본값이 거짓인 이유**: 참이면 주소 오타가 조용히 새
            # 저장소를 만든다. 지금은 clone이 실패해 push-failed가 나서 오타를 알아챈다 (카드 F)
            if create_repo:
                owner_name, repo_name = _split_remote(remote_url)
                await github.create_repo(token, owner_name, repo_name)

        def undo_origin() -> None:
            """서버 저장의 되돌림 — 새로 만든 원본은 지우고, 되살린 것은 보관으로 돌려놓는다."""
            if origin is None:
                return
            if restored is not None:
                origin.rename(restored)
            else:
                shutil.rmtree(origin, ignore_errors=True)

        try:
            await git.clone(remote_url, workdir, token)
        except GitError as e:
            shutil.rmtree(workdir, ignore_errors=True)
            undo_origin()
            raise PushFailed(f"clone: {e.stderr.strip()}") from e
        has = await git.exists(workdir, "docs/specs")
        if has and not import_existing:
            n = len(await git.list(workdir, "docs/specs/*/*.md"))
            shutil.rmtree(workdir, ignore_errors=True)
            undo_origin()
            raise ExistingSpecs(n)
        savepoint = self.session.begin_nested()
        project = Project(code=code, name=name, owner_user_id=user.id)  # 등록한 사람이 소유자
        self.repo.add(project)
        repository = Repository(
            project_id=project.id,
            storage=storage.value,
            remote_url=remote_url,
            workdir_path=str(workdir),
            registered_by_user_id=user.id,
        )
        self.repo.add(repository)
        if has and import_existing:  # 3a2·3b2 — 기존 명세를 재구축으로 가져온다. 락·트랜잭션은 그쪽
            from app.core import pipeline  # 서비스가 pipeline을 부르는 유일한 곳(DOM-002 3.2)

            try:
                await pipeline.rebuild(code, session=self.session)
            except BaseException:
                undo_origin()
                raise
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
            undo_origin()
            raise
        repository.last_processed_commit = commit_hash
        self.session.flush()
        return self.repo.by_code(code)

    async def _server_origin(self, code: str, import_existing: bool) -> tuple[Path, Path | None]:
        """init_project 3s — 서버 저장소를 준비한다. (원본, 되살린 보관본의 원래 자리 | None).

        원본을 잃는 길을 두지 않는다 — 등록되지 않은 채 남은 원본(지난 실패, 사람이 넣은 것)도
        지우지 않고 보관으로 옮겨 보관본으로 다룬다.
        """
        origin = settings.ORIGINS_DIR / f"{code}.git"
        if origin.exists():
            origin.rename(_archive_path(code))
        archives = _archives(code)
        if archives:
            latest = archives[-1]
            if not import_existing:  # 3b — 되살릴지 묻는다
                try:
                    n = len(await git.list(latest, "docs/specs/*/*.md"))
                except GitError:  # 커밋이 하나도 없는 원본
                    n = 0
                raise ExistingSpecs(n, archived_at=_archived_at(latest, code))
            latest.rename(origin)  # 3b2 — 가장 최근 것을 되살린다
            return origin, latest
        await git.init_bare(origin)
        return origin, None

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
                Storage(p.repository.storage),
                public_remote(p.repository),  # 서버 저장이면 None — 서버 안 경로는 안 낸다
                p.repository.last_processed_commit,
                p.repository.synced_at,
                p.repository.behind_by,
                p.repository.fetched_at,
                error=p.repository.fetch_error,  # 폴링이 적어 둔 실패 사유 (#46)
                hook=_hook_state(p.repository),
                hook_error=p.repository.hook_error,
            )
            for p in self.list_owned(user)  # 처리 — list_owned (check_calls, 카드 AX)
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
            # 대화·턴·첨부를 먼저(MS-001 2). 순환 임포트를 피해 여기서 부른다 —
            # conversation이 project를 본다
            from app.core.codegraph.service import CodeGraphService
            from app.core.conversation.service import ConversationService

            ConversationService(self.session).delete_by_project(project.id)
            CodeGraphService(self.session).delete_by_project(project.id)  # 2a. 코드 그래프
            server = project.repository.storage == Storage.server
            origin = Path(project.repository.remote_url)
            self.repo.delete_all_of(project.id)
            self.session.flush()
            shutil.rmtree(workdir, ignore_errors=True)
            # 4a. 서버 저장이면 원본을 지우지 않고 보관 폴더로 — 같은 코드로 가져오면 되살아난다
            # (UC-H17, 카드 BA). 부르는 쪽 커밋이 뒤에 실패하면 운영자가 되돌린다(INFRA 6장)
            if server and origin.exists():
                origin.rename(_archive_path(code))

    def server_origin(self, code: str, user: User) -> Path:
        """SYNC-MS-001#ProjectService.server_origin

        git 입구(카드 BB)가 흘릴 서버 안 원본. 남의 것·GitHub 저장·원본 없음은 같은 not-found —
        git 입구는 서버 저장소에만 있고, 존재가 새지 않는다.
        """
        project = self.get_owned(code, user)
        repo = project.repository
        origin = Path(repo.remote_url)
        if repo.storage != Storage.server or not origin.is_dir():
            raise NotFound("project", code)
        return origin

    async def ensure_hook(self, code: str, user: User) -> HookStatus:
        """SYNC-MS-001#ProjectService.ensure_hook"""
        project = self.get_owned(code, user)  # 남의 것이면 not-found
        repo = project.repository
        if repo.storage == Storage.server:
            # 1a. 원본이 서버 안이라 밖에서 바뀌지 않는다 — 서버 경로를 GitHub 주소로 쪼개
            # API를 부르는 일도 막는다 (INFRA 7장, 카드 BA)
            return HookStatus("none", "서버 저장소는 통지가 없다", created=False)
        url, secret = settings.PUBLIC_BASE_URL.rstrip("/"), settings.WEBHOOK_SECRET
        if not url or not secret:
            # 받는 쪽이 빈 비밀번호를 전부 거부한다 — 걸어 봐야 안 통하므로 걸지 않는다
            return HookStatus("none", "공개 주소나 비밀번호가 없어 걸지 못한다", created=False)
        had = repo.hook_id
        owner_name, repo_name = _split_remote(repo.remote_url)
        try:
            hook_id = await github.create_hook(
                AccountService.github_token_for(user),
                owner_name,
                repo_name,
                f"{url}/hooks/github",
                secret,
            )
        except Unauthorized as e:
            # 예외로 올리지 않는다 — 사람이 화면에서 사유를 읽고 다시 누르면 된다 (MS-001)
            repo.hook_error = str(e)[:300]
            self.session.flush()
            return HookStatus("error", repo.hook_error, created=False)
        repo.hook_id, repo.hook_error = hook_id, None
        self.session.flush()
        return HookStatus("ok", None, created=had != hook_id)

    async def sync_now(self, code: str, user: User) -> SyncResult:
        """SYNC-MS-001#ProjectService.sync_now"""
        from app.core import pipeline  # 서비스가 pipeline을 부르는 유일한 곳(DOM-002 3.2)

        # 소유 검사·읽기 락·process_commit이 read_pending 안에 있다 (카드 AD) — 두 벌 만들지 않는다
        docs = await pipeline.read_pending(code, user)
        self.session.expire_all()  # read_pending이 다른 세션에서 적었다
        return SyncResult(docs, self.get_owned(code, user).repository.fetched_at)

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


def _hook_state(repo: Repository) -> str:
    """push 통지 상태 — ok · none · error (카드 AF). 둘 다 비면 아직 안 걸어 본 것이다.

    서버 저장소는 늘 none — 걸 통지가 없다 (INFRA 7장, 카드 BA).
    """
    if repo.storage == Storage.server:
        return "none"
    if repo.hook_id:
        return "ok"
    return "error" if repo.hook_error else "none"


def public_remote(repo: Repository) -> str | None:
    """밖으로 내보낼 저장소 주소 — GitHub 주소, 서버 저장이면 None(서버 안 경로는 안 낸다).

    요약·상세(queries)와 관리 표(repo_status)가 같은 규칙을 쓴다.
    """
    return None if repo.storage == Storage.server else repo.remote_url
