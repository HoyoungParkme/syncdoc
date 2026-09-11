"""SYNC-MS-009 — infra/git.py. git CLI를 asyncio.create_subprocess_exec로 감싸는 얇은 층.

core는 이것을 통해서만 저장소를 만진다. 실패는 GitError(cmd, stderr). 토큰은 push URL에만 쓰고
.git/config·로그에 남기지 않는다(SYNC-INFRA-001 5장 · SYNC-STD-004#DEV-6).
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

from app.config import settings
from app.core.account.service import AccountService
from app.core.errors import PushFailed, Unauthorized
from app.core.types import Author, ChangedFile, Commit, spec_dir

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


def _rejected(porcelain_out: str) -> bool:
    """push --porcelain에서 거부된 ref가 있나.

    stderr 문자열(`"rejected"`)로 판정하면 git 로케일이 영어가 아닐 때 거부를 놓친다.
    --porcelain의 첫 글자 플래그는 번역되지 않는다 — 거부는 `!`.
    """
    return any(line.startswith("!") for line in porcelain_out.splitlines())


def _with_token(remote_url: str, token: str) -> str:
    """https URL에만 토큰을 붙인다. https://x-access-token:{token}@github.com/org/repo.git"""
    if remote_url.startswith("https://"):
        return f"https://x-access-token:{token}@{remote_url[len('https://') :]}"
    return remote_url


async def clone(remote_url: str, workdir: Path, token: str) -> None:
    """SYNC-MS-009#git.clone"""
    await _run(None, "clone", _with_token(remote_url, token), str(workdir))
    await _run(workdir, "remote", "set-url", "origin", remote_url)


async def fetch(workdir: Path, token: str | None = None) -> str:
    """SYNC-MS-009#git.fetch"""
    if token is None:  # v1은 public 저장소만 — 토큰 없이 된다
        await _run(workdir, "fetch", "origin")
    else:  # private(v2): clone이 config에서 토큰을 지웠으므로 URL에 다시 붙인다
        url = _with_token((await _run(workdir, "remote", "get-url", "origin")).strip(), token)
        await _run(workdir, "fetch", url, "+refs/heads/*:refs/remotes/origin/*")
    return (await _run(workdir, "rev-parse", "origin/HEAD")).strip()


async def checkout(workdir: Path, ref: str) -> None:
    """SYNC-MS-009#git.checkout"""
    await _run(workdir, "checkout", "--force", ref)


async def _has_remote_head(workdir: Path) -> bool:
    """원격에 커밋이 하나라도 있나. 빈 저장소면 `origin/HEAD`가 없다 (#6)."""
    rc, _, _ = await _exec(workdir, "rev-parse", "--verify", "--quiet", "origin/HEAD")
    return rc == 0


async def _undo(workdir: Path, onto_remote: bool) -> None:
    """push 실패 뒷정리. 빈 저장소였으면 되돌아갈 원격 커밋이 없어 로컬 커밋만 푼다."""
    if onto_remote:
        await _run(workdir, "reset", "--hard", "origin/HEAD")
    else:
        await _exec(workdir, "update-ref", "-d", "HEAD")


async def commit_push(
    workdir: Path,
    message: str,
    author: Author,
    path: str | None = None,
    content: str | None = None,
    files: dict[str, str] | None = None,
) -> str:
    """SYNC-MS-009#git.commit_push"""
    if files is None:
        if path is None or content is None:
            raise ValueError("path+content 또는 files 중 하나는 있어야 한다")
        files = {path: content}
    try:
        token = AccountService.github_token_for(author.user)
    except Unauthorized as e:
        raise PushFailed("미등록") from e
    await _run(workdir, "fetch", "origin")
    # 빈 저장소에는 되돌아갈 곳이 없다. 이 커밋이 그 저장소의 첫 커밋이 된다 (UC-A1 기본 흐름 3)
    onto_remote = await _has_remote_head(workdir)
    if onto_remote:
        await _run(workdir, "reset", "--hard", "origin/HEAD")
    to_write = files
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
    # 거부(non-fast-forward)면 rebase 후 다시 민다. PUSH_RETRIES회까지 (MS-009 6단계)
    for attempt in range(settings.PUSH_RETRIES + 1):
        rc, out, err = await _exec(workdir, "push", "--porcelain", url, "HEAD:main")
        if rc == 0:
            break
        if not _rejected(out):
            # 거부가 아닌 실패 — 권한·네트워크 따위. 재시도해도 같다
            await _undo(workdir, onto_remote)
            raise PushFailed(err.strip() or out.strip())
        if attempt == settings.PUSH_RETRIES:
            await _undo(workdir, onto_remote)
            raise PushFailed(err.strip() or out.strip())
        await _run(workdir, "fetch", "origin")
        try:
            await _run(workdir, *ident, "rebase", "origin/HEAD")
        except GitError as e:
            # 같은 줄을 남이 고쳤다. 재시도로 안 풀린다 — 에이전트가 다시 읽어 합쳐야 한다
            await _exec(workdir, "rebase", "--abort")
            await _run(workdir, "reset", "--hard", "origin/HEAD")
            raise PushFailed("conflict") from e
        # 재시도 사이에 기다리지 않는다 — 락을 쥔 채 자면 같은 프로젝트의 저장이 전부 막힌다
    return (await _run(workdir, "rev-parse", "HEAD")).strip()


async def read(workdir: Path, path: str, ref: str = "HEAD") -> str:
    """SYNC-MS-009#git.read"""
    return await _run(workdir, "show", f"{ref}:{path}")


def _login_of(name: str, email: str) -> str:
    """커밋 author → GitHub login. noreply 메일이면 앞부분(ID+ 접두어 제거), 아니면 %an.

    **%an 폴백은 GitHub 로그인이 아니다** — 사람 이름이고 공백이 들어 있을 수 있다.
    그래서 이 값만으로 사람을 찾으면 안 된다. 파이프라인은 원본 %ae로 먼저 찾고
    (AccountService.user_for_commit) 이건 2차 단서로만 쓴다(SYNC-MS-009 3a).
    """
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
    # None은 "rename으로 사라진 옛 경로" 표시 — 더 앞선 커밋의 같은 경로 항목을 막는다
    seen: dict[str, ChangedFile | None] = {}
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
            # rename(`R…\t옛\t새`)은 새 경로의 수정으로 접고 옛 경로는 버린다 (MS-009 2a, #31).
            # 파일이 옮겨진 것이지 문서가 둘이 된 게 아니다 — 옛 경로를 남기면 process_commit이
            # `git show {head}:{옛 경로}`에서 죽고 따라잡기가 그 자리에 영원히 멈춘다.
            # 커밋은 최신부터 훑는다 — rename 뒤 옛 경로에 새 파일이 생겼으면 이미 seen에 있어 산다
            if status[0] == "R" and len(paths) == 2:
                seen.setdefault(paths[0], None)
                status = "M"
            parts = Path(path).parts
            # 명세가 아닌 것은 뺀다 (MS-009 처리 4). 타입 디렉터리 밖의 파일 —
            # `docs/specs/README.md` — 은 init_specs가 만든 것이라 여기서 걸러야
            # 싱크독이 만든 파일이 싱크독의 따라잡기를 막지 않는다 (#32).
            # 알 수 없는 타입 디렉터리(`docs/specs/BOGUS/…`)는 빼지 않는다 — 사람 실수라 알려야 한다
            if "_templates" in parts or "assets" in parts or len(parts) <= 3 or path in seen:
                continue
            seen[path] = ChangedFile(
                path=path,
                status=status[0],
                commit_hash=hash_,
                author_login=_login_of(an, ae),
                message=_message(msg),
                author_email=ae,
            )
        hash_ = next_hash
    return [c for _, c in sorted(seen.items()) if c is not None]


def _message(subject_body: str) -> str:
    subject, _, body = subject_body.partition("\n")
    return f"{subject}\n\n{body.strip()}" if body.strip() else subject


async def list(workdir: Path, glob: str, ref: str = "HEAD") -> list[str]:
    """SYNC-MS-009#git.list"""
    out = await _run(workdir, "ls-tree", "-r", "--name-only", ref, "--", "docs/specs")
    return [p for p in out.splitlines() if PurePosixPath(p).match(glob)]


async def log(workdir: Path, path: str) -> list[Commit]:
    """SYNC-MS-009#git.log"""
    # --reverse를 git에 맡기지 않는다. --follow는 revision walker의 특수 처리라
    # --reverse와 조합되지 않아, 둘을 같이 주면 rename을 건너는 순간 커밋이 끊긴다.
    # 이름이 바뀐 경로의 이력을 잇는 것이 재구축의 목적이므로 --follow를 남기고
    # 순서는 받아서 뒤집는다 (SYNC-MS-009#git.log, #39)
    out = await _run(
        workdir,
        "log",
        "--follow",
        "--format=%H%x00%an%x00%ae%x00%aI%x00%s%n%b%x00",
        "--",
        path,
    )
    tokens = out.split("\0")
    commits: list[Commit] = []
    for i in range_(0, len(tokens) - 1, 5):
        h, an, ae, date, msg = (t.strip("\n") for t in tokens[i : i + 5])
        commits.append(
            Commit(
                hash=h,
                login=_login_of(an, ae),
                date=datetime.fromisoformat(date),
                message=_message(msg),
                email=ae,
            )
        )
    commits.reverse()  # git이 최신부터 준다 → 오래된 것부터
    return commits


async def rev_list_count(workdir: Path, range: str) -> int:
    """SYNC-MS-009#git.rev_list_count"""
    return int((await _run(workdir, "rev-list", "--count", range)).strip())


async def exists(workdir: Path, path: str) -> bool:
    """SYNC-MS-009#git.exists

    커밋이 하나도 없는 저장소는 False. HEAD가 가리키는 것이 없어 git이 실패하는데,
    그것을 에러로 올리면 빈 저장소로 프로젝트를 시작하는 길이 막힌다(#6).
    HEAD 없음만 삼키고 다른 git 오류는 그대로 올린다.
    """
    try:
        return bool((await _run(workdir, "ls-tree", "HEAD", "--", path)).strip())
    except GitError as e:
        if "Not a valid object name" in e.stderr or "unknown revision" in e.stderr:
            return False
        raise


_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "docs" / "specs" / "_templates"
_TYPES = ("RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE", "STD")
_README = """# docs/specs — 명세 원본

싱크독 명세 체인 11단계 + STD. 쓰는 법은 명세 작성 규약 SYNC-STD-001, 타입별 뼈대는 `_templates/`.

**위에서 아래로 읽는다.** 디렉터리 번호가 그 순서다.

| # | 디렉터리 | 무엇 |
|---|---|---|
| 1 | `01-RFQ` | 요청 — 무엇을 원하나 |
| 2 | `02-PRD` | 제품 요구사항 |
| 3 | `03-SCN` | 사용자 시나리오 |
| 4 | `04-UC` | 유스케이스 |
| 5 | `05-INFRA` | 인프라·제약 |
| 6 | `06-DOM` | 도메인 모델 · **클래스 명세** · ERD·DD (문서 셋) |
| 7 | `07-UI` | 화면 설계 · 와이어프레임 |
| 8 | `08-API` | REST · MCP 도구 |
| 9 | `09-SEQ` | 시퀀스 |
| 10 | `10-MS` | MINISPEC — 함수 단위 |
| 11 | `11-CODE` | 구현 슬라이스 카드 |
| — | `STD` | 작성 규약·뷰 규약·개발 규약 (단계 밖) |

- 경로 `docs/specs/{NN-TYPE}/{doc_id}.md` · 문서 ID `{프로젝트코드}-{TYPE}-{NNN}`
- 상태(`status`)는 frontmatter가 진실. 변경은 싱크독 웹에서만
- 첨부는 `assets/`
"""


async def init_specs(workdir: Path) -> dict[str, str]:
    """SYNC-MS-009#git.init_specs"""
    files: dict[str, str] = {}
    for t in _TYPES:
        files[f"docs/specs/{spec_dir(t)}/.gitkeep"] = ""
        files[f"docs/specs/_templates/{t}.md"] = (_TEMPLATES_DIR / f"{t}.md").read_text(
            encoding="utf-8"
        )
    files["docs/specs/assets/.gitkeep"] = ""
    files["docs/specs/README.md"] = _README
    return files
