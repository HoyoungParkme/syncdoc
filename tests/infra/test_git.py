"""SYNC-MS-009 테스트 관점 — git 어댑터. 임시 저장소로."""

from pathlib import Path

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
