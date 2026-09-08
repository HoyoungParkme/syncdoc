"""SYNC-MS-009 — infra/git.py. git CLI를 asyncio.create_subprocess_exec로 감싸는 얇은 층.

core는 이것을 통해서만 저장소를 만진다. 실패는 GitError(cmd, stderr). 토큰은 push URL에만 쓰고
.git/config·로그에 남기지 않는다(SYNC-INFRA-001 5장 · SYNC-STD-004#DEV-6).
"""

import asyncio
import re
from pathlib import Path

_TOKEN_IN_URL = re.compile(r"(x-access-token:)[^@]+@")


class GitError(Exception):
    def __init__(self, cmd: list[str], stderr: str) -> None:
        self.cmd = [_TOKEN_IN_URL.sub(r"\1***@", c) for c in cmd]
        self.stderr = _TOKEN_IN_URL.sub(r"\1***@", stderr)
        super().__init__(f"{' '.join(self.cmd)}: {self.stderr.strip()}")


async def _run(workdir: Path | None, *args: str) -> str:
    """git 명령 하나. 실패(returncode≠0)면 GitError."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=workdir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise GitError(["git", *args], err.decode(errors="replace"))
    return out.decode()


def _with_token(remote_url: str, token: str) -> str:
    """https URL에만 토큰을 붙인다. https://x-access-token:{token}@github.com/org/repo.git"""
    if remote_url.startswith("https://"):
        return f"https://x-access-token:{token}@{remote_url[len('https://') :]}"
    return remote_url


async def fetch(workdir: Path) -> str:
    """SYNC-MS-009#git.fetch"""
    await _run(workdir, "fetch", "origin")
    return (await _run(workdir, "rev-parse", "origin/HEAD")).strip()
