"""SYNC-MS-009 — infra/git.py. git CLI를 asyncio.create_subprocess_exec로 감싸는 얇은 층.

core는 이것을 통해서만 저장소를 만진다. 실패는 GitError(cmd, stderr). 토큰은 push URL에만 쓰고
.git/config·로그에 남기지 않는다(SYNC-INFRA-001 5장 · SYNC-STD-004#DEV-6).
"""

import asyncio
import re
from pathlib import Path

from syncdoc.core.account.service import AccountService
from syncdoc.core.errors import PushFailed, Unauthorized
from syncdoc.core.types import Author, ChangedFile

range_ = range  # changed_files의 인자 이름 range(MS-009 시그니처)가 내장을 가린다
_TOKEN_IN_URL = re.compile(r"(x-access-token:)[^@]+@")
_HASH = re.compile(r"[0-9a-f]{40}")


class GitError(Exception):
    def __init__(self, cmd: list[str], stderr: str) -> None:
        self.cmd = [_TOKEN_IN_URL.sub(r"\1***@", c) for c in cmd]
        self.stderr = _TOKEN_IN_URL.sub(r"\1***@", stderr)
        super().__init__(f"{' '.join(self.cmd)}: {self.stderr.strip()}")


async def _exec(workdir: Path | None, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=workdir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(), err.decode(errors="replace")


async def _run(workdir: Path | None, *args: str) -> str:
    """git 명령 하나. 실패(returncode≠0)면 GitError."""
    code, out, err = await _exec(workdir, *args)
    if code != 0:
        raise GitError(["git", *args], err)
    return out


def _with_token(remote_url: str, token: str) -> str:
    """https URL에만 토큰을 붙인다. https://x-access-token:{token}@github.com/org/repo.git"""
    if remote_url.startswith("https://"):
        return f"https://x-access-token:{token}@{remote_url[len('https://') :]}"
    return remote_url


async def fetch(workdir: Path) -> str:
    """SYNC-MS-009#git.fetch"""
    await _run(workdir, "fetch", "origin")
    return (await _run(workdir, "rev-parse", "origin/HEAD")).strip()


async def checkout(workdir: Path, ref: str) -> None:
    """SYNC-MS-009#git.checkout"""
    await _run(workdir, "checkout", "--force", ref)


async def commit_push(
    workdir: Path,
    path: str,
    content: str,
    message: str,
    author: Author,
    files: dict[str, str] | None = None,
) -> str:
    """SYNC-MS-009#git.commit_push"""
    try:
        token = AccountService.github_token_for(author.user)
    except Unauthorized as e:
        raise PushFailed("미등록") from e
    await _run(workdir, "fetch", "origin")
    await _run(workdir, "reset", "--hard", "origin/HEAD")
    to_write = files if files is not None else {path: content}
    for p, c in to_write.items():
        f = workdir / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c, encoding="utf-8")
    await _run(workdir, "add", "--", *to_write)
    unchanged, _, _ = await _exec(workdir, "diff", "--cached", "--quiet")
    if unchanged == 0:
        return (await _run(workdir, "rev-parse", "HEAD")).strip()
    user = author.user
    ident = (
        "-c",
        f"user.name={user.display_name}",
        "-c",
        f"user.email={user.github_login}@users.noreply.github.com",
    )
    await _run(workdir, *ident, "commit", "-q", "-m", message)
    url = _with_token((await _run(workdir, "remote", "get-url", "origin")).strip(), token)
    try:
        await _run(workdir, "push", url, "HEAD:main")
    except GitError as first:
        if "rejected" not in first.stderr:
            await _run(workdir, "reset", "--hard", "origin/HEAD")
            raise PushFailed(first.stderr.strip()) from first
        await _run(workdir, "fetch", "origin")
        try:
            await _run(workdir, *ident, "rebase", "origin/HEAD")
        except GitError as e:
            await _exec(workdir, "rebase", "--abort")
            await _run(workdir, "reset", "--hard", "origin/HEAD")
            raise PushFailed("conflict") from e
        try:
            await _run(workdir, "push", url, "HEAD:main")
        except GitError as e:
            await _run(workdir, "reset", "--hard", "origin/HEAD")
            raise PushFailed(e.stderr.strip()) from e
    return (await _run(workdir, "rev-parse", "HEAD")).strip()


async def read(workdir: Path, path: str, ref: str = "HEAD") -> str:
    """SYNC-MS-009#git.read"""
    return await _run(workdir, "show", f"{ref}:{path}")


def _login_of(name: str, email: str) -> str:
    """커밋 author → GitHub login. *@users.noreply.github.com이면 앞부분(ID+ 접두어 제거), 아니면 %an."""
    if email.endswith("@users.noreply.github.com"):
        return email.split("@")[0].split("+")[-1]
    return name


async def changed_files(workdir: Path, range: str, prefix: str) -> list[ChangedFile]:
    """SYNC-MS-009#git.changed_files"""
    out = await _run(
        workdir,
        "log",
        "--name-status",
        "--format=%H%x00%an%x00%ae%x00%s%n%b%x00",
        range,
        "--",
        prefix,
    )
    seen: dict[str, ChangedFile] = {}
    tokens = out.split("\0")
    # 레코드: hash, an, ae, "subject\nbody", "\n<status lines>\n<next hash>" — 첫 hash 뒤로 4개 단위
    hash_ = tokens[0].strip()
    for i in range_(4, len(tokens), 4):
        an, ae, msg = tokens[i - 3], tokens[i - 2], tokens[i - 1]
        lines = tokens[i].split("\n")
        next_hash = lines[-1].strip() if _HASH.fullmatch(lines[-1].strip()) else ""
        for line in lines:
            if "\t" not in line:
                continue
            status, *paths = line.split("\t")
            path = paths[-1]
            parts = Path(path).parts
            if "_templates" in parts or "assets" in parts or path in seen:
                continue
            seen[path] = ChangedFile(
                path=path,
                status=status[0],
                commit_hash=hash_,
                author_login=_login_of(an, ae),
                message=_message(msg),
            )
        hash_ = next_hash
    return [seen[p] for p in sorted(seen)]


def _message(subject_body: str) -> str:
    subject, _, body = subject_body.partition("\n")
    return f"{subject}\n\n{body.strip()}" if body.strip() else subject
