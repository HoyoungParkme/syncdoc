"""git 어댑터 테스트 — 임시 bare 저장소(원격) + clone(작업 사본) + 다른 clone(외부 push용)."""

import subprocess
from pathlib import Path

import pytest

SEED = "docs/specs/PRD/SYNC-PRD-001.md"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=seed", "-c", "user.email=seed@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_commit_push(repo: Path, path: str, content: str, message: str = "seed") -> str:
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "commit", "-q", "-m", message)
    git(repo, "push", "-q", "origin", "HEAD:main")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, Path]:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    git(other, "checkout", "-q", "-b", "main")
    write_commit_push(other, SEED, "---\ndoc_id: SYNC-PRD-001\n---\n# PRD\n", "seed")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    return {"remote": remote, "work": work, "other": other}
