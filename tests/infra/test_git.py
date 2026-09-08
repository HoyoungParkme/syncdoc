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
