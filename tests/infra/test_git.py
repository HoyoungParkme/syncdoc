"""SYNC-MS-009 테스트 관점 — git 어댑터. 임시 저장소로."""

from pathlib import Path

import pytest

from syncdoc.core.account.models import User
from syncdoc.core.account.service import _fernet
from syncdoc.core.errors import PushFailed
from syncdoc.core.types import Author, AuthorKind, Entry
from syncdoc.infra import git as g
from tests.infra.conftest import SEED, git, write_commit_push


# ── fetch ──
async def test_fetch_returns_origin_head_without_touching_workdir(repos: dict[str, Path]) -> None:
    before = git(repos["work"], "rev-parse", "HEAD")
    new = write_commit_push(repos["other"], SEED, "changed", "external")
    assert await g.fetch(repos["work"]) == new
    assert git(repos["work"], "rev-parse", "HEAD") == before


# ── checkout ──
async def test_checkout_moves_workdir_to_ref_discarding_local_changes(
    repos: dict[str, Path],
) -> None:
    first = git(repos["work"], "rev-parse", "HEAD")
    write_commit_push(repos["other"], SEED, "v2", "second")
    await g.fetch(repos["work"])
    (repos["work"] / SEED).write_text("dirty", encoding="utf-8")
    await g.checkout(repos["work"], "origin/HEAD")
    assert (repos["work"] / SEED).read_text(encoding="utf-8") == "v2"
    await g.checkout(repos["work"], first)
    assert git(repos["work"], "rev-parse", "HEAD") == first


# ── commit_push ──
def _author(token: str | None = "gho_secret") -> Author:
    u = User(
        github_login="hoyoung",
        github_user_id=1,
        display_name="박호영",
        github_token_encrypted=None if token is None else _fernet().encrypt(token.encode()),
    )
    return Author(kind=AuthorKind.human, user=u, instructed_by=None, via=Entry.mcp)


async def test_commit_push_creates_commit_on_remote(repos: dict[str, Path]) -> None:
    h = await g.commit_push(repos["work"], SEED, "v2", "spec(SYNC-PRD-001): v2", _author())
    assert h == git(repos["remote"], "rev-parse", "main")
    assert git(repos["work"], "log", "-1", "--format=%an <%ae>") == (
        "박호영 <hoyoung@users.noreply.github.com>"
    )
    assert git(repos["work"], "log", "-1", "--format=%s") == "spec(SYNC-PRD-001): v2"


async def test_commit_push_same_content_makes_no_commit(repos: dict[str, Path]) -> None:
    head = git(repos["remote"], "rev-parse", "main")
    body = (repos["work"] / SEED).read_text(encoding="utf-8")
    assert await g.commit_push(repos["work"], SEED, body, "noop", _author()) == head
    assert git(repos["remote"], "rev-parse", "main") == head


async def test_commit_push_rebases_when_remote_moved_on_other_file(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run = g._run
    pushed: list[str] = []

    async def racing_run(workdir: Path | None, *args: str) -> str:
        if args[:1] == ("push",) and not pushed:
            pushed.append(write_commit_push(repos["other"], "docs/specs/RFQ/X.md", "x", "race"))
        return await real_run(workdir, *args)

    monkeypatch.setattr(g, "_run", racing_run)
    h = await g.commit_push(repos["work"], SEED, "mine", "spec: mine", _author())
    assert h == git(repos["remote"], "rev-parse", "main")
    assert git(repos["remote"], "rev-parse", "main~1") == pushed[0]
    assert git(repos["work"], "show", "HEAD:docs/specs/RFQ/X.md") == "x"


async def test_commit_push_conflict_restores_workdir(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run = g._run
    pushed: list[str] = []

    async def racing_run(workdir: Path | None, *args: str) -> str:
        if args[:1] == ("push",) and not pushed:
            pushed.append(write_commit_push(repos["other"], SEED, "theirs", "race"))
        return await real_run(workdir, *args)

    monkeypatch.setattr(g, "_run", racing_run)
    with pytest.raises(PushFailed) as ei:
        await g.commit_push(repos["work"], SEED, "mine", "spec: mine", _author())
    assert ei.value.extra["reason"] == "conflict"
    assert git(repos["work"], "status", "--porcelain") == ""
    assert git(repos["work"], "rev-parse", "HEAD") == pushed[0]
    assert (repos["work"] / SEED).read_text(encoding="utf-8") == "theirs"


async def test_commit_push_leaves_no_token_in_config(repos: dict[str, Path]) -> None:
    await g.commit_push(repos["work"], SEED, "v2", "m", _author())
    cfg = (repos["work"] / ".git" / "config").read_text(encoding="utf-8")
    assert "gho_secret" not in cfg and "x-access-token" not in cfg
    assert g._with_token("https://github.com/o/r.git", "tok") == (
        "https://x-access-token:tok@github.com/o/r.git"
    )
    assert "s3cr3t" not in str(
        g.GitError(["git", "push", "https://x-access-token:s3cr3t@x/r"], "e")
    )


async def test_commit_push_unregistered_user_is_push_failed(repos: dict[str, Path]) -> None:
    with pytest.raises(PushFailed) as ei:
        await g.commit_push(repos["work"], SEED, "v2", "m", _author(token=None))
    assert ei.value.extra["reason"] == "미등록"
