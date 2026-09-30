"""SYNC-MS-001 테스트 관점 — ProjectService."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import NotFound
from app.core.project.models import Project, Repository
from app.core.project.service import ProjectService
from tests.conftest import git as g
from tests.conftest import write_commit_push
from tests.core.account.test_service import make_user
from tests.core.reference.test_service import RFQ
from tests.core.spec.test_service import make_project, owner


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


# ── get_owned · list_owned (카드 W) ──
def test_get_owned_and_list_owned_hide_someone_elses_project(db_session: Session) -> None:
    me = owner(db_session)
    other = make_user(db_session, login="other")
    make_project(db_session, "MINE")
    make_project(db_session, "THEI", owner_user=other)
    svc = ProjectService(db_session)
    assert svc.get_owned("MINE", me).code == "MINE"
    # 남의 것 → get의 없음과 같은 not-found. 없는 코드도 같다
    for code in ("THEI", "NOPE"):
        with pytest.raises(NotFound) as ei:
            svc.get_owned(code, me)
        assert ei.value.extra == {"resource": "project", "id": code}
    assert [p.code for p in svc.list_owned(me)] == ["MINE"]
    assert [p.code for p in svc.list_owned(other)] == ["THEI"]
    nobody = make_user(db_session, login="nobody")
    assert svc.list_owned(nobody) == []  # 등록한 적 없는 계정 — 빈 목록, 에러 아님
    assert [p.code for p in svc.list_projects()] == ["MINE", "THEI"]  # 시스템 경로는 둘 다


# ── init_project ──
@pytest.fixture
def repos_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    return tmp_path / "repos"


async def test_init_project_empty_repo_creates_specs_commit_and_11_null_stages(
    db_session: Session, repos_dir, repos: dict
) -> None:
    from tests.core.account.test_service import make_user
    from tests.infra.conftest import git as g

    user = make_user(db_session, login="hoyoung")
    # repos 픽스처의 remote는 docs/specs/02-PRD/SYNC-PRD-001.md가 이미 있다 → 새 bare 저장소를 하나 더
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
    assert project.owner_user_id == user.id  # 등록한 사람이 소유자 (카드 W)
    assert project.code == "NEW" and project.repository.remote_url == str(bare)
    p = svc.get("NEW")
    assert p.repository.workdir_path == str(repos_dir / "NEW")
    assert p.repository.last_processed_commit == g(bare, "rev-parse", "main")
    assert g(bare, "log", "-1", "--format=%s", "main") == "chore(NEW): init syncdoc"
    tree = g(bare, "ls-tree", "-r", "--name-only", "main")
    # 규약·템플릿 사본은 넣지 않는다 — README가 링크로 가리킨다 (카드 AB)
    assert "docs/specs/STD/.gitkeep" in tree and "docs/specs/README.md" in tree
    assert "_templates" not in tree
    assert "docs/specs/README.md" in tree and "docs/specs/assets/.gitkeep" in tree


async def test_init_project_accepts_repository_with_no_commits_at_all(
    db_session: Session, repos_dir, repos: dict
) -> None:
    """#6 — 커밋이 하나도 없는 저장소. 새 프로젝트를 시작하는 가장 흔한 방법이다 (UC-A1 기본 흐름 3)."""
    from tests.core.account.test_service import make_user
    from tests.infra.conftest import git as g

    user = make_user(db_session, login="hoyoung")
    bare = repos_dir.parent / "nocommit.git"
    g(repos_dir.parent, "init", "-q", "--bare", "-b", "main", str(bare))

    project = await ProjectService(db_session).init_project(str(bare), "EMP", "빈 저장소", user)

    assert project.code == "EMP"
    assert g(bare, "log", "-1", "--format=%s", "main") == "chore(EMP): init syncdoc"
    assert "docs/specs/README.md" in g(bare, "ls-tree", "-r", "--name-only", "main")


# ── init_project 9a — 등록 때 push 통지 (#242) ──
@pytest.fixture
def hook_env(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://syncdoc.example")
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "s3cret")
    return "https://syncdoc.example/hooks/github"


def _empty_bare(repos_dir: Path, name: str) -> Path:
    bare = repos_dir.parent / f"{name}.git"
    g(repos_dir.parent, "init", "-q", "--bare", "-b", "main", str(bare))
    return bare


async def test_init_github_registers_the_push_hook_after_the_skeleton(
    db_session: Session, repos_dir, mock_github, hook_env: str
) -> None:
    """9a — GitHub 저장 새 등록은 골격 커밋 뒤 통지를 건다. 전에는 관리 화면 버튼으로만 걸렸다."""
    import json

    user = make_user(db_session, login="hoyoung")
    bare = _empty_bare(repos_dir, "hooked")
    calls = mock_github(
        lambda req: httpx.Response(200, json=[])
        if req.method == "GET"
        else httpx.Response(201, json={"id": 77})
    )
    project = await ProjectService(db_session).init_project(str(bare), "HOOK", "통지", user)
    repo = project.repository
    assert (repo.hook_id, repo.hook_error) == (77, None)
    assert repo.last_processed_commit == g(bare, "rev-parse", "main")  # 등록은 그대로
    post = next(c for c in calls if c.method == "POST")
    assert post.url.path == f"/repos/{repos_dir.parent.name}/hooked/hooks"  # 주소에서 뜬 소유자·이름
    assert json.loads(post.content)["config"]["url"] == hook_env


@pytest.mark.parametrize("failure", ["refused", "offline"])
async def test_init_github_hook_failure_keeps_the_registration(
    db_session: Session, repos_dir, mock_github, hook_env: str, failure: str
) -> None:
    """4a — 통지를 못 걸어도 등록은 된다. 사유는 hook_error — GitHub 거절이든 연결 끊김이든."""

    def handler(req: httpx.Request) -> httpx.Response:
        if failure == "offline":
            raise httpx.ConnectError("연결 끊김", request=req)
        return httpx.Response(403, json={"message": "Forbidden"})

    user = make_user(db_session, login="hoyoung")
    bare = _empty_bare(repos_dir, f"hook-{failure}")
    mock_github(handler)
    project = await ProjectService(db_session).init_project(str(bare), "HOOF", "실패", user)
    repo = project.repository
    assert repo.hook_id is None and repo.hook_error
    assert repo.last_processed_commit == g(bare, "rev-parse", "main")
    assert ProjectService(db_session).get("HOOF").code == "HOOF"


async def test_init_import_and_server_storage_do_not_call_github_for_a_hook(
    db_session: Session, repos_dir, repos: dict, mock_github, hook_env: str
) -> None:
    """가져오기(8)와 서버 저장은 9a를 부르지 않는다 — 가져오기는 그림 그대로, 서버 저장은 통지가 없다."""
    from app.core.types import Storage

    user = make_user(db_session, login="hoyoung")
    calls = mock_github(lambda req: httpx.Response(500))
    await ProjectService(db_session).init_project(
        str(repos["remote"]), "IMPT", "가져오기", user, import_existing=True
    )
    await ProjectService(db_session).init_project(None, "SRVH", "서버", user, storage=Storage.server)
    assert calls == []


async def test_create_repo_false_leaves_missing_repo_alone(
    db_session: Session, repos_dir, repos: dict, monkeypatch
) -> None:
    """#카드 F — 기본값은 거짓. 주소 오타가 조용히 새 저장소를 만들면 안 된다."""
    from app.core.errors import PushFailed
    from app.infra import github
    from tests.core.account.test_service import make_user

    calls: list[tuple] = []

    async def spy(token, owner, name):
        calls.append((owner, name))
        return "x"

    monkeypatch.setattr(github, "create_repo", spy)
    user = make_user(db_session, login="hoyoung")
    missing = repos_dir.parent / "does-not-exist.git"

    with pytest.raises(PushFailed):
        await ProjectService(db_session).init_project(str(missing), "MIS", "없는 것", user)

    assert calls == [], "create_repo=false면 저장소를 만들지 않는다"


async def test_create_repo_true_creates_then_registers(
    db_session: Session, repos_dir, repos: dict, monkeypatch
) -> None:
    """#카드 F — create_repo=true면 만들고 이어서 골격 커밋까지 간다."""
    from app.infra import github
    from tests.core.account.test_service import make_user
    from tests.infra.conftest import git as g

    bare = repos_dir.parent / "made.git"
    calls: list[tuple] = []

    async def fake_create(token, owner, name):
        calls.append((owner, name))
        g(repos_dir.parent, "init", "-q", "--bare", "-b", "main", str(bare))
        return str(bare)

    monkeypatch.setattr(github, "create_repo", fake_create)
    user = make_user(db_session, login="hoyoung")

    project = await ProjectService(db_session).init_project(
        str(bare), "NEW", "새 것", user, create_repo=True
    )

    assert calls and calls[0][1] == "made"  # 주소에서 이름을 떴다
    assert project.code == "NEW"
    assert g(bare, "log", "-1", "--format=%s", "main") == "chore(NEW): init syncdoc"
    assert "docs/specs/README.md" in g(bare, "ls-tree", "-r", "--name-only", "main")


async def test_create_repo_true_does_not_recreate_existing(
    db_session: Session, repos_dir, repos: dict, monkeypatch
) -> None:
    """#카드 F — 이미 있으면 만들지 않는다. 같은 인자로 두 번 불러도 결과가 같아야 한다."""
    from app.infra import github
    from tests.core.account.test_service import make_user

    made: list[tuple] = []

    async def fake_create(token, owner, name):
        made.append((owner, name))
        return str(repos["remote"])

    monkeypatch.setattr(github, "create_repo", fake_create)
    user = make_user(db_session, login="hoyoung")

    await ProjectService(db_session).init_project(
        str(repos["remote"]), "EXI", "있는 것", user, import_existing=True, create_repo=True
    )

    # create_repo는 불리되(있으면 만들지 않는 판정은 그 안에서 한다) 등록이 정상 완료된다
    assert made, "create_repo는 호출된다"
    assert ProjectService(db_session).get("EXI").code == "EXI"


async def test_empty_repo_project_can_fetch_afterwards(
    db_session: Session, repos_dir, repos: dict
) -> None:
    """#45 — 빈 저장소로 만든 프로젝트도 그 뒤 fetch가 돼야 한다.

    `git clone`은 빈 저장소에서 `refs/remotes/origin/HEAD`를 만들지 않는다. 그걸 보던
    시절에는 이 프로젝트의 폴링·재구축·복원·push 재시도가 **전부** 죽었다 — 그런데
    빈 저장소가 새 프로젝트를 시작하는 가장 흔한 방법이다 (UC-A1 기본 흐름 3).
    """
    from app.infra import git as gi
    from tests.core.account.test_service import make_user
    from tests.infra.conftest import git as g

    user = make_user(db_session, login="hoyoung")
    bare = repos_dir.parent / "later.git"
    g(repos_dir.parent, "init", "-q", "--bare", "-b", "main", str(bare))
    project = await ProjectService(db_session).init_project(str(bare), "LATE", "나중", user)
    workdir = Path(project.repository.workdir_path)

    # 빈 저장소를 clone하면 origin/HEAD가 **영영 안 생긴다**. fetch는 origin/main만 만든다
    assert not (workdir / ".git" / "refs" / "remotes" / "origin" / "HEAD").exists()
    head = await gi.fetch(workdir)

    assert head == g(bare, "rev-parse", "main")
    await gi.checkout(workdir, "origin/main")
    assert await gi.rev_list_count(workdir, f"HEAD..{head}") == 0


async def test_init_project_rejects_already_registered_repository(
    db_session: Session, repos_dir, repos: dict
) -> None:
    """UC-A1 2d — 한 저장소를 두 프로젝트가 쓰면 문서 ID가 겹쳐 이력을 덮어쓴다."""
    from app.core.errors import RepositoryAlreadyRegistered
    from app.core.project.repository import normalize_remote
    from tests.core.account.test_service import make_user

    user = make_user(db_session)
    svc = ProjectService(db_session)
    await svc.init_project(str(repos["remote"]), "ONE", "첫", user, import_existing=True)
    for url in (str(repos["remote"]), str(repos["remote"]) + "/", str(repos["remote"]).upper()):
        with pytest.raises(RepositoryAlreadyRegistered) as ei:
            await svc.init_project(url, "TWO", "둘", user)
        assert ei.value.extra["code"] == "ONE"
    assert normalize_remote("https://GitHub.com/o/R.git/") == "https://github.com/o/r"
    assert not (repos_dir / "TWO").exists()
    with pytest.raises(NotFound):
        svc.get("TWO")


async def test_init_project_rejects_invalid_and_duplicate_code(
    db_session: Session, repos_dir
) -> None:
    from app.core.errors import ProjectCodeConflict, ProjectCodeInvalid
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
    from app.core.errors import ExistingSpecs
    from tests.core.account.test_service import make_user

    user = make_user(db_session)
    svc = ProjectService(db_session)
    with pytest.raises(ExistingSpecs) as ei:
        await svc.init_project(str(repos["remote"]), "EXST", "n", user)
    assert ei.value.extra["doc_count"] == 1
    assert not (repos_dir / "EXST").exists()
    with pytest.raises(NotFound):
        svc.get("EXST")
    # import_existing → 재구축으로 가져온다 (3a2). 시드 PRD 하나, frontmatter가 미완이라 규약 오류
    p = await svc.init_project(str(repos["remote"]), "EXST", "n", user, import_existing=True)
    assert p.code == "EXST" and p.repository.last_processed_commit is not None
    assert (repos_dir / "EXST" / "docs/specs/02-PRD/SYNC-PRD-001.md").exists()
    from app.core.spec.service import SpecService

    d = SpecService(db_session).get_document("SYNC-PRD-001")
    assert d.has_convention_error and d.current_version_no == 1


async def test_init_project_clone_failure_leaves_nothing(
    db_session: Session, repos_dir, tmp_path
) -> None:
    from app.core.errors import PushFailed
    from tests.core.account.test_service import make_user

    user = make_user(db_session)
    with pytest.raises(PushFailed) as ei:
        await ProjectService(db_session).init_project(str(tmp_path / "nope.git"), "GONE", "n", user)
    assert ei.value.extra["reason"].startswith("clone:")
    assert not (repos_dir / "GONE").exists()
    with pytest.raises(NotFound):
        ProjectService(db_session).get("GONE")


def test_asset_path_serves_only_owned_specs_files(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    me = owner(db_session)
    other = make_user(db_session, login="other")
    make_project(db_session, "MINE")
    make_project(db_session, "THEI", owner_user=other)
    specs = tmp_path / "repos" / "MINE" / "docs" / "specs"
    (specs / "assets").mkdir(parents=True)
    (specs / "assets" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (specs / "assets" / "note.md").write_text("x")
    (tmp_path / "secret.png").write_bytes(b"\x89PNG")
    (specs / "assets" / "link.png").symlink_to(tmp_path / "secret.png")
    svc = ProjectService(db_session)
    assert svc.asset_path("MINE", "assets/a.png", me) == (specs / "assets" / "a.png").resolve()
    assert svc.asset_path("MINE", "07-UI/../assets/a.png", me).name == "a.png"  # 안쪽 ..는 된다
    # 남의 프로젝트 → get과 같은 not-found(project)
    with pytest.raises(NotFound) as ei:
        svc.asset_path("THEI", "assets/a.png", me)
    assert ei.value.extra == {"resource": "project", "id": "THEI"}
    # 탈출·바깥 심볼릭 링크·허용 밖 확장자·없는 파일 → 전부 같은 not-found(file)
    for path in ("../../secret.png", "assets/link.png", "assets/note.md", "assets/none.png"):
        with pytest.raises(NotFound) as ei:
            svc.asset_path("MINE", path, me)
        assert ei.value.extra == {"resource": "file", "id": path}


def _registered(scoped: Session, repos: dict) -> tuple[ProjectService, object]:
    """EXMP 프로젝트 + 실제 작업 사본. ensure_hook·sync_now 시험용 (카드 AF)."""
    u = make_user(scoped, login="hoyoung")
    p = Project(code="EXMP", name="예시", owner_user_id=u.id)
    scoped.add(p)
    scoped.flush()
    scoped.add(
        Repository(
            project_id=p.id,
            remote_url="https://github.com/o/r.git",
            workdir_path=str(repos["work"]),
            registered_by_user_id=u.id,
            last_processed_commit=g(repos["remote"], "rev-parse", "main"),
        )
    )
    scoped.flush()
    return ProjectService(scoped), u


# ── ensure_hook · sync_now (카드 AF) ──
async def test_ensure_hook_skips_when_no_public_url(
    scoped: Session, repos: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """주소나 비밀번호가 비면 걸지 않는다 — 받는 쪽이 빈 비밀번호를 전부 거부한다."""
    ps, user = _registered(scoped, repos)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")
    r = await ps.ensure_hook("EXMP", user)
    assert (r.hook, r.created) == ("none", False) and "주소" in (r.hook_error or "")


async def test_ensure_hook_records_error_and_then_succeeds(
    scoped: Session, repos: dict, monkeypatch: pytest.MonkeyPatch, mock_github
) -> None:
    ps, user = _registered(scoped, repos)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://syncdoc.example")
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "s3cret")
    mock_github(lambda req: httpx.Response(404, json={"message": "Not Found"}))
    r = await ps.ensure_hook("EXMP", user)
    assert r.hook == "error" and r.hook_error
    # 사람이 화면에서 사유를 읽고 다시 누른다 — 예외로 올리지 않는다
    assert (await ps.repo_status(user))[0].hook == "error"

    mock_github(
        lambda req: httpx.Response(200, json=[])
        if req.method == "GET"
        else httpx.Response(201, json={"id": 9})
    )
    r2 = await ps.ensure_hook("EXMP", user)
    assert (r2.hook, r2.hook_error, r2.created) == ("ok", None, True)
    st = (await ps.repo_status(user))[0]
    assert st.hook == "ok" and st.hook_error is None
    # 같은 훅을 다시 걸면 created는 False — 저장된 hook_id를 보고 판단한다 (#145)
    r3 = await ps.ensure_hook("EXMP", user)
    assert (r3.hook, r3.created) == ("ok", False)


async def test_sync_now_reads_pending_and_touches_fetched_at(scoped: Session, repos: dict) -> None:
    ps, user = _registered(scoped, repos)
    g(repos["other"], "pull", "-q", "--rebase", "origin", "main")
    write_commit_push(repos["other"], "docs/specs/01-RFQ/EXMP-RFQ-001.md", RFQ, "spec: 밖에서")
    r = await ps.sync_now("EXMP", user)
    assert r.docs == 1 and r.fetched_at is not None
    # 읽을 것이 없어도 확인 시각은 새로 적힌다 (UC-G2 2a)
    before = (await ps.repo_status(user))[0].fetched_at
    r2 = await ps.sync_now("EXMP", user)
    assert r2.docs == 0 and r2.fetched_at is not None and r2.fetched_at >= before
    with pytest.raises(NotFound):
        await ps.sync_now("EXMP", make_user(scoped, login="stranger"))


# ── 서버 저장 (카드 BA, PRD R14) ──
SRV_RFQ = "---\ndoc_id: SRV-RFQ-001\ntype: RFQ\ntitle: 요구\nstatus: draft\n---\n# RFQ\n## 1. 배경\n#### Q1 첫 요구\n내용\n"


async def test_init_server_storage_makes_bare_origin_and_skeleton_without_github_token(
    db_session: Session, repos_dir, origins_dir: Path
) -> None:
    """MS-001 3s — 서버 안 bare 원본, 골격 커밋. GitHub 토큰이 없는 사람도 된다(토큰을 안 구한다)."""
    from app.core.types import Storage

    user = make_user(db_session, login="local", token=None)
    project = await ProjectService(db_session).init_project(
        None, "SRV", "서버 저장", user, storage=Storage.server
    )
    origin = origins_dir / "SRV.git"
    assert project.repository.storage == "server"
    assert project.repository.remote_url == str(origin)
    assert g(origin, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert g(origin, "config", "receive.denyNonFastForwards") == "true"
    assert g(origin, "log", "-1", "--format=%s", "main") == "chore(SRV): init syncdoc"
    assert "docs/specs/README.md" in g(origin, "ls-tree", "-r", "--name-only", "main")
    assert project.repository.last_processed_commit == g(origin, "rev-parse", "main")


async def test_init_rejects_storage_the_server_did_not_turn_on(
    db_session: Session, repos_dir, origins_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UC-A1 1a — 켜지 않은 방식이면 아무것도 만들지 않는다."""
    from app.core.errors import StorageUnavailable
    from app.core.types import Storage

    monkeypatch.setattr(settings, "STORAGE_MODES", "github")
    user = make_user(db_session, login="u")
    with pytest.raises(StorageUnavailable) as ei:
        await ProjectService(db_session).init_project(None, "SRV", "x", user, storage=Storage.server)
    assert ei.value.extra == {"storage": "server", "enabled": ["github"]}
    assert not (origins_dir / "SRV.git").exists()
    assert not ProjectService(db_session).repo.exists("SRV")


async def test_github_storage_without_remote_url_is_invalid_request(
    db_session: Session, repos_dir
) -> None:
    """UC-A1 1b."""
    from app.core.errors import InvalidRequest

    user = make_user(db_session, login="u")
    with pytest.raises(InvalidRequest) as ei:
        await ProjectService(db_session).init_project(None, "GH", "x", user)
    assert ei.value.extra["errors"][0]["loc"] == "remote_url"


async def test_release_archives_server_origin_then_import_restores_documents(
    db_session: Session, repos_dir, origins_dir: Path, tmp_path: Path
) -> None:
    """UC-H17 — 해제하면 보관 폴더로. UC-A1 3b — 가져오기 없이는 알리기만, 가져오면 되살린다."""
    from app.core.errors import ExistingSpecs
    from app.core.spec.service import SpecService
    from app.core.types import Storage

    user = make_user(db_session, login="local", token=None)
    svc = ProjectService(db_session)
    await svc.init_project(None, "SRV", "서버", user, storage=Storage.server)
    origin = origins_dir / "SRV.git"
    clone = tmp_path / "c"
    g(tmp_path, "clone", "-q", str(origin), str(clone))
    write_commit_push(clone, "docs/specs/01-RFQ/SRV-RFQ-001.md", SRV_RFQ, "spec(SRV-RFQ-001): 초안")

    await svc.delete_project("SRV", user)
    archived = list((origins_dir / "_archive").glob("SRV-*.git"))
    assert not origin.exists() and len(archived) == 1
    assert not (repos_dir / "SRV").exists()

    with pytest.raises(ExistingSpecs) as ei:
        await svc.init_project(None, "SRV", "서버", user, storage=Storage.server)
    assert ei.value.extra["doc_count"] == 1
    assert ei.value.extra["archived_at"].startswith("20")
    assert not origin.exists() and archived[0].exists()  # 아무것도 안 바뀐다

    project = await svc.init_project(
        None, "SRV", "서버", user, import_existing=True, storage=Storage.server
    )
    assert origin.exists() and not archived[0].exists()
    assert project.repository.last_processed_commit == g(origin, "rev-parse", "main")
    assert SpecService(db_session).get_document("SRV-RFQ-001").doc_id == "SRV-RFQ-001"


async def test_unregistered_leftover_origin_is_archived_not_deleted(
    db_session: Session, repos_dir, origins_dir: Path
) -> None:
    """3s — 이름 없이 남은 원본(지난 실패·사람이 넣은 것)은 지우지 않고 보관으로 옮겨 묻는다."""
    from app.core.errors import ExistingSpecs
    from app.core.types import Storage

    leftover = origins_dir / "OLD.git"
    g(origins_dir, "init", "-q", "--bare", "-b", "main", str(leftover))
    user = make_user(db_session, login="u")
    with pytest.raises(ExistingSpecs) as ei:
        await ProjectService(db_session).init_project(None, "OLD", "x", user, storage=Storage.server)
    assert ei.value.extra["doc_count"] == 0  # 커밋이 없는 원본
    assert not leftover.exists()
    assert len(list((origins_dir / "_archive").glob("OLD-*.git"))) == 1


async def test_failed_server_registration_keeps_no_new_origin_and_returns_restored_one(
    db_session: Session,
    repos_dir,
    origins_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """서버 저장의 되돌림 — 새 원본은 지우고, 되살린 보관본은 보관 폴더로 돌려놓는다."""
    from app.core import pipeline
    from app.core.errors import PushFailed
    from app.core.types import Storage
    from app.infra import git as git_mod

    user = make_user(db_session, login="u", token=None)
    svc = ProjectService(db_session)

    async def fail_push(*a, **k):
        raise PushFailed("boom")

    monkeypatch.setattr(git_mod, "commit_push", fail_push)
    with pytest.raises(PushFailed):
        await svc.init_project(None, "NEW", "x", user, storage=Storage.server)
    assert not (origins_dir / "NEW.git").exists()
    assert not svc.repo.exists("NEW")

    # 보관본을 되살리다 재구축이 실패하면 보관본은 제자리로 — 원본을 잃지 않는다
    archive = origins_dir / "_archive" / "ARC-20260101000000.git"
    g(origins_dir, "init", "-q", "--bare", "-b", "main", str(archive))
    seed = tmp_path / "seed"
    g(tmp_path, "clone", "-q", str(archive), str(seed))
    g(seed, "checkout", "-q", "-b", "main")
    write_commit_push(seed, "docs/specs/01-RFQ/ARC-RFQ-001.md", SRV_RFQ, "seed")

    async def fail_rebuild(*a, **k):
        raise RuntimeError("rebuild")

    monkeypatch.setattr(pipeline, "rebuild", fail_rebuild)
    with pytest.raises(RuntimeError):
        await svc.init_project(None, "ARC", "x", user, import_existing=True, storage=Storage.server)
    assert archive.exists() and not (origins_dir / "ARC.git").exists()


async def test_ensure_hook_and_repo_status_on_server_storage(
    db_session: Session, repos_dir, mock_github, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_hook 1a — 서버 저장은 none이고 GitHub을 안 부른다. repo_status는 주소를 안 낸다."""
    from app.core.types import Storage

    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://syncdoc.example.com")
    calls = mock_github(lambda req: httpx.Response(500))
    user = make_user(db_session, login="u", token=None)
    svc = ProjectService(db_session)
    await svc.init_project(None, "SRV", "x", user, storage=Storage.server)
    r = await svc.ensure_hook("SRV", user)
    assert r.hook == "none" and r.created is False and calls == []
    [row] = await svc.repo_status(user)
    assert row.storage == Storage.server and row.remote_url is None and row.hook == "none"


async def test_server_origin_only_for_the_owner_of_a_server_project(
    db_session: Session, repos_dir, origins_dir: Path, repos: dict
) -> None:
    """MS-001 server_origin — 남의 것·GitHub 저장·원본 없음이 같은 not-found (카드 BB)."""
    from app.core.types import Storage

    me = make_user(db_session, login="me", token=None)
    other = make_user(db_session, login="other", token=None)
    svc = ProjectService(db_session)
    await svc.init_project(None, "SRV", "서버", me, storage=Storage.server)
    assert svc.server_origin("SRV", me) == origins_dir / "SRV.git"
    for code, user in (("SRV", other), ("NOPE", me)):
        with pytest.raises(NotFound) as ei:
            svc.server_origin(code, user)
        assert ei.value.extra == {"resource": "project", "id": code}
    gh = make_user(db_session, login="gh")
    await svc.init_project(str(repos["remote"]), "GH", "깃허브", gh, import_existing=True)
    with pytest.raises(NotFound):
        svc.server_origin("GH", gh)  # GitHub 저장에는 git 입구가 없다
