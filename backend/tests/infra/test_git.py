"""SYNC-MS-009 테스트 관점 — git 어댑터. 임시 저장소로."""

from pathlib import Path

import pytest

from app.core.account.models import User
from app.core.account.service import _fernet
from app.core.errors import PushFailed
from app.core.types import Author, AuthorKind, Entry
from app.infra import git as g
from tests.infra.conftest import SEED, git, write_commit_push


# ── clone ──
async def test_clone_full_history_and_no_token_in_config(repos: dict[str, Path]) -> None:
    write_commit_push(repos["other"], SEED, "v2", "second")
    write_commit_push(repos["other"], SEED, "v3", "third")
    target = repos["work"].parent / "cloned"
    await g.clone(str(repos["remote"]), target, "s3cr3t")
    assert git(target, "rev-parse", "HEAD") == git(repos["remote"], "rev-parse", "main")
    assert git(target, "rev-list", "--count", "HEAD") == "3"  # 전체 이력 (--depth 없음)
    assert git(target, "remote", "get-url", "origin") == str(repos["remote"])
    assert "s3cr3t" not in (target / ".git" / "config").read_text(encoding="utf-8")
    assert await g.fetch(target) == git(repos["remote"], "rev-parse", "main")


async def test_clone_failure_is_git_error(tmp_path: Path) -> None:
    with pytest.raises(g.GitError):
        await g.clone(str(tmp_path / "nope.git"), tmp_path / "x", "t")


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
    h = await g.commit_push(
        repos["work"], "spec(SYNC-PRD-001): v2", _author(), path=SEED, content="v2"
    )
    assert h == git(repos["remote"], "rev-parse", "main")
    assert git(repos["work"], "log", "-1", "--format=%an <%ae>") == (
        "박호영 <hoyoung@users.noreply.github.com>"
    )
    assert git(repos["work"], "log", "-1", "--format=%s") == "spec(SYNC-PRD-001): v2"


async def test_commit_push_same_content_makes_no_commit(repos: dict[str, Path]) -> None:
    head = git(repos["remote"], "rev-parse", "main")
    body = (repos["work"] / SEED).read_text(encoding="utf-8")
    assert await g.commit_push(repos["work"], "noop", _author(), path=SEED, content=body) == head
    assert git(repos["remote"], "rev-parse", "main") == head


async def test_commit_push_rebases_when_remote_moved_on_other_file(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_exec = g._exec
    pushed: list[str] = []

    async def racing_exec(workdir: Path | None, *args: str) -> tuple[int, str, str]:
        # push는 _exec로 나간다 — 종료 코드와 --porcelain 출력을 함께 봐야 하므로 (MS-009)
        if args[:1] == ("push",) and not pushed:
            pushed.append(write_commit_push(repos["other"], "docs/specs/01-RFQ/X.md", "x", "race"))
        return await real_exec(workdir, *args)

    monkeypatch.setattr(g, "_exec", racing_exec)
    h = await g.commit_push(repos["work"], "spec: mine", _author(), path=SEED, content="mine")
    assert h == git(repos["remote"], "rev-parse", "main")
    assert git(repos["remote"], "rev-parse", "main~1") == pushed[0]
    assert git(repos["work"], "show", "HEAD:docs/specs/01-RFQ/X.md") == "x"


async def test_commit_push_conflict_restores_workdir(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_exec = g._exec
    pushed: list[str] = []

    async def racing_exec(workdir: Path | None, *args: str) -> tuple[int, str, str]:
        if args[:1] == ("push",) and not pushed:
            pushed.append(write_commit_push(repos["other"], SEED, "theirs", "race"))
        return await real_exec(workdir, *args)

    monkeypatch.setattr(g, "_exec", racing_exec)
    with pytest.raises(PushFailed) as ei:
        await g.commit_push(repos["work"], "spec: mine", _author(), path=SEED, content="mine")
    assert ei.value.extra["reason"] == "conflict"
    assert git(repos["work"], "status", "--porcelain") == ""
    assert git(repos["work"], "rev-parse", "HEAD") == pushed[0]
    assert (repos["work"] / SEED).read_text(encoding="utf-8") == "theirs"


async def test_commit_push_retries_when_remote_moves_twice(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """연달아 두 번 끼어들어도 건진다 — PUSH_RETRIES 기본 3 (MS-009 6단계)."""
    real_exec = g._exec
    races: list[str] = []

    async def racing_exec(workdir: Path | None, *args: str) -> tuple[int, str, str]:
        if args[:1] == ("push",) and len(races) < 2:  # 첫 push와 첫 재시도 직전에 각각
            races.append(write_commit_push(repos["other"], f"docs/specs/01-RFQ/{len(races)}.md", "x", "race"))
        return await real_exec(workdir, *args)

    monkeypatch.setattr(g, "_exec", racing_exec)
    h = await g.commit_push(repos["work"], "spec: mine", _author(), path=SEED, content="mine")
    assert len(races) == 2
    assert h == git(repos["remote"], "rev-parse", "main")


async def test_commit_push_rejection_detected_without_english_stderr(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """거부 판정은 --porcelain의 `!` 플래그로 한다. stderr가 영어가 아니어도 잡는다."""
    real_exec = g._exec
    seen: list[str] = []
    raced: list[str] = []

    async def localized_exec(workdir: Path | None, *args: str) -> tuple[int, str, str]:
        if args[:1] == ("push",) and not raced:  # 밀기 직전에 남이 끼어든다
            raced.append(write_commit_push(repos["other"], "docs/specs/01-RFQ/Y.md", "y", "race"))
        rc, out, err = await real_exec(workdir, *args)
        if args[:1] == ("push",):
            seen.append(out)
            if rc != 0:
                err = "오류: 일부 참조를 푸시하지 못했습니다"  # 번역된 stderr
        return rc, out, err

    monkeypatch.setattr(g, "_exec", localized_exec)
    h = await g.commit_push(repos["work"], "spec: mine", _author(), path=SEED, content="mine")
    # stderr에 "rejected"가 없어도 --porcelain의 `!`로 거부를 잡아 재시도했다
    assert any(line.startswith("!") for o in seen for line in o.splitlines())
    assert h == git(repos["remote"], "rev-parse", "main")


async def test_commit_push_leaves_no_token_in_config(repos: dict[str, Path]) -> None:
    await g.commit_push(repos["work"], "m", _author(), path=SEED, content="v2")
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
        await g.commit_push(repos["work"], "m", _author(token=None), path=SEED, content="v2")
    assert ei.value.extra["reason"] == "미등록"


# ── read ──
async def test_read_returns_file_at_ref_or_raises(repos: dict[str, Path]) -> None:
    first = git(repos["work"], "rev-parse", "HEAD")
    write_commit_push(repos["other"], SEED, "v2", "second")
    await g.fetch(repos["work"])
    assert await g.read(repos["work"], SEED, "origin/HEAD") == "v2"
    assert (await g.read(repos["work"], SEED, first)).startswith("---\ndoc_id: SYNC-PRD-001")
    with pytest.raises(g.GitError):
        await g.read(repos["work"], "docs/specs/none.md")


# ── changed_files ──
async def test_changed_files_keeps_last_commit_per_file_and_skips_templates(
    repos: dict[str, Path],
) -> None:
    base = git(repos["work"], "rev-parse", "HEAD")
    o = repos["other"]
    write_commit_push(o, SEED, "v2", "spec(SYNC-PRD-001): v2")
    h3 = write_commit_push(o, SEED, "v3", "spec(SYNC-PRD-001): v3\n\n이유가 있다")
    h4 = write_commit_push(o, "docs/specs/03-SCN/SYNC-SCN-001.md", "s", "spec(SYNC-SCN-001): new")
    write_commit_push(o, "docs/specs/_templates/PRD.md", "t", "chore: template")
    write_commit_push(o, "docs/specs/assets/a.png", "img", "chore: asset")
    write_commit_push(o, "README.md", "outside", "chore: outside prefix")
    head = await g.fetch(repos["work"])
    got = await g.changed_files(repos["work"], f"{base}..{head}", "docs/specs/")
    assert [(c.path, c.status, c.commit_hash) for c in got] == [
        (SEED, "M", h3),
        ("docs/specs/03-SCN/SYNC-SCN-001.md", "A", h4),
    ]
    assert got[0].message == "spec(SYNC-PRD-001): v3\n\n이유가 있다"
    assert got[0].author_login == "seed"
    assert got[1].message == "spec(SYNC-SCN-001): new"


async def test_changed_files_login_from_noreply_email(repos: dict[str, Path]) -> None:
    assert g._login_of("박호영", "12345+hoyoung@users.noreply.github.com") == "hoyoung"
    assert g._login_of("박호영", "hoyoung@users.noreply.github.com") == "hoyoung"
    assert g._login_of("seed", "seed@example.com") == "seed"


async def test_changed_files_deleted_file_has_status_d(repos: dict[str, Path]) -> None:
    base = git(repos["work"], "rev-parse", "HEAD")
    git(repos["other"], "rm", "-q", SEED)
    git(repos["other"], "commit", "-q", "-m", "spec(SYNC-PRD-001): delete")
    git(repos["other"], "push", "-q", "origin", "HEAD:main")
    head = await g.fetch(repos["work"])
    got = await g.changed_files(repos["work"], f"{base}..{head}", "docs/specs/")
    assert [(c.path, c.status) for c in got] == [(SEED, "D")]


# ── list ──
async def test_list_filters_by_glob_at_ref(repos: dict[str, Path]) -> None:
    o = repos["other"]
    write_commit_push(o, "docs/specs/03-SCN/SYNC-SCN-001.md", "s", "a")
    write_commit_push(o, "docs/specs/_templates/PRD.md", "t", "b")
    write_commit_push(o, "docs/specs/README.md", "r", "c")
    write_commit_push(o, "README.md", "x", "d")
    await g.fetch(repos["work"])
    got = await g.list(repos["work"], "docs/specs/*/*.md", "origin/HEAD")
    assert got == [SEED, "docs/specs/03-SCN/SYNC-SCN-001.md", "docs/specs/_templates/PRD.md"]
    assert await g.list(repos["work"], "docs/specs/*/*.md") == [SEED]


# ── log ──
async def test_log_lists_file_history_oldest_first(repos: dict[str, Path]) -> None:
    o = repos["other"]
    h2 = write_commit_push(o, SEED, "v2", "spec(SYNC-PRD-001): v2\n\n왜냐하면")
    write_commit_push(o, "docs/specs/03-SCN/SYNC-SCN-001.md", "s", "other file")
    await g.fetch(repos["work"])
    await g.checkout(repos["work"], "origin/HEAD")
    got = await g.log(repos["work"], SEED)
    assert [c.message for c in got] == ["seed", "spec(SYNC-PRD-001): v2\n\n왜냐하면"]
    assert got[1].hash == h2 and got[1].login == "seed"
    assert got[0].date.tzinfo is not None and got[0].date <= got[1].date
    assert await g.log(repos["work"], "docs/specs/none.md") == []


# ── rev_list_count ──
async def test_rev_list_count_counts_commits_behind(repos: dict[str, Path]) -> None:
    write_commit_push(repos["other"], SEED, "v2", "a")
    write_commit_push(repos["other"], SEED, "v3", "b")
    await g.fetch(repos["work"])
    assert await g.rev_list_count(repos["work"], "HEAD..origin/HEAD") == 2
    assert await g.rev_list_count(repos["work"], "origin/HEAD..HEAD") == 0


# ── exists ──
async def test_exists_is_committed_not_workdir(repos: dict[str, Path]) -> None:
    assert await g.exists(repos["work"], "docs/specs") is True
    assert await g.exists(repos["work"], SEED) is True
    (repos["work"] / "docs/specs/04-UC").mkdir()
    (repos["work"] / "docs/specs/04-UC/x.md").write_text("uncommitted", encoding="utf-8")
    assert await g.exists(repos["work"], "docs/specs/04-UC") is False
    assert await g.exists(repos["work"], "docs/specs/04-UC/x.md") is False


# ── init_specs ──
async def test_init_specs_returns_26_files_and_commit_push_writes_them(
    repos: dict[str, Path],
) -> None:
    files = await g.init_specs(repos["work"])
    assert len(files) == 26
    dirs = {p.split("/")[2] for p in files if p.endswith("/.gitkeep")}
    assert dirs == {  # 11단계는 번호 + 타입, 단계 밖 STD는 번호 없음 (STD-001 1.1)
        "01-RFQ",
        "02-PRD",
        "03-SCN",
        "04-UC",
        "05-INFRA",
        "06-DOM",
        "07-UI",
        "08-API",
        "09-SEQ",
        "10-MS",
        "11-CODE",
        "STD",
        "assets",
    }
    assert "| 6 | `06-DOM` |" in files["docs/specs/README.md"]  # 읽는 순서표
    assert files["docs/specs/_templates/PRD.md"].startswith("---\ndoc_id:")
    assert "SYNC-STD-001" in files["docs/specs/README.md"]
    h = await g.commit_push(repos["work"], "chore(SYNC): init syncdoc", _author(), files=files)
    assert h == git(repos["remote"], "rev-parse", "main")
    assert await g.exists(repos["work"], "docs/specs/_templates/STD.md")
    assert len(await g.list(repos["work"], "docs/specs/_templates/*.md")) == 12


async def test_commit_push_requires_path_content_or_files(repos: dict[str, Path]) -> None:
    with pytest.raises(ValueError):
        await g.commit_push(repos["work"], "m", _author())
    with pytest.raises(ValueError):
        await g.commit_push(repos["work"], "m", _author(), path=SEED)
