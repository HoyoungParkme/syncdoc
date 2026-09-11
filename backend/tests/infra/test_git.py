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
            races.append(
                write_commit_push(repos["other"], f"docs/specs/01-RFQ/{len(races)}.md", "x", "race")
            )
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
    # login과 별개로 %ae 원본이 실린다 — 파이프라인이 이메일로 먼저 사람을 찾는다 (#34)
    assert got[0].author_email == "seed@example.com"
    assert got[1].message == "spec(SYNC-SCN-001): new"


async def test_changed_files_login_from_noreply_email(repos: dict[str, Path]) -> None:
    assert g._login_of("박호영", "12345+hoyoung@users.noreply.github.com") == "hoyoung"
    assert g._login_of("박호영", "hoyoung@users.noreply.github.com") == "hoyoung"
    assert g._login_of("seed", "seed@example.com") == "seed"


async def test_changed_files_range_across_rename_drops_the_old_path(
    repos: dict[str, Path],
) -> None:
    """#31 — 범위가 rename 커밋을 가로지르면 옛 경로가 따로 남아 따라잡기를 멈춰 세웠다.

    옛 경로를 남기면 process_commit이 `git show {head}:{옛 경로}`에서 죽고,
    한 파일이 실패하면 last_processed_commit이 안 올라가 그 자리에 영원히 멈춘다.
    """
    base = git(repos["work"], "rev-parse", "HEAD")
    o, new_path = repos["other"], "docs/specs/10-MS/SYNC-MS-001.md"
    # rename 앞에 옛 경로를 건드리는 커밋 둘
    write_commit_push(o, "docs/specs/MS/SYNC-MS-001.md", "v1", "spec(SYNC-MS-001): 초안")
    write_commit_push(o, "docs/specs/MS/SYNC-MS-001.md", "v2", "spec(SYNC-MS-001): 보강")
    # 디렉터리를 {NN-TYPE}로 옮긴다
    (o / "docs/specs/10-MS").mkdir(parents=True, exist_ok=True)
    git(o, "mv", "docs/specs/MS/SYNC-MS-001.md", new_path)
    git(o, "commit", "-q", "-m", "chore: 디렉터리 이동")
    git(o, "push", "-q", "origin", "HEAD:main")
    head = await g.fetch(repos["work"])

    got = await g.changed_files(repos["work"], f"{base}..{head}", "docs/specs/")

    assert [c.path for c in got if "/specs/MS/" in c.path] == [], "옛 경로가 남으면 안 된다"
    assert (new_path, "M") in [(c.path, c.status) for c in got]
    assert {c.status for c in got} <= {"A", "M", "D"}, "R은 M으로 접힌다 (MS-009 처리 3)"


async def test_changed_files_new_file_at_the_old_path_after_rename_survives(
    repos: dict[str, Path],
) -> None:
    """#31 2b — rename 뒤에 옛 경로로 새 파일이 생겼으면 그건 살린다."""
    base = git(repos["work"], "rev-parse", "HEAD")
    o = repos["other"]
    write_commit_push(o, "docs/specs/MS/SYNC-MS-001.md", "v1", "spec(SYNC-MS-001): 초안")
    (o / "docs/specs/10-MS").mkdir(parents=True, exist_ok=True)
    git(o, "mv", "docs/specs/MS/SYNC-MS-001.md", "docs/specs/10-MS/SYNC-MS-001.md")
    git(o, "commit", "-q", "-m", "chore: 디렉터리 이동")
    git(o, "push", "-q", "origin", "HEAD:main")
    write_commit_push(o, "docs/specs/MS/SYNC-MS-002.md", "다시 생김", "spec(SYNC-MS-002): 초안")
    head = await g.fetch(repos["work"])

    got = await g.changed_files(repos["work"], f"{base}..{head}", "docs/specs/")

    paths = {c.path for c in got}
    assert "docs/specs/MS/SYNC-MS-002.md" in paths
    assert "docs/specs/MS/SYNC-MS-001.md" not in paths


async def test_changed_files_skips_files_outside_a_type_directory(
    repos: dict[str, Path],
) -> None:
    """#32 — init_specs가 만든 docs/specs/README.md가 따라잡기를 막고 있었다."""
    base = git(repos["work"], "rev-parse", "HEAD")
    o = repos["other"]
    write_commit_push(o, "docs/specs/README.md", "순서표", "chore: README")
    h = write_commit_push(o, "docs/specs/03-SCN/SYNC-SCN-001.md", "s", "spec(SYNC-SCN-001): new")
    # 알 수 없는 타입 디렉터리는 빼지 않는다 — 사람 실수라 process_commit이 알려야 한다
    hb = write_commit_push(o, "docs/specs/BOGUS/EXMP-BOGUS-001.md", "x", "spec: 잘못 넣음")
    head = await g.fetch(repos["work"])

    got = await g.changed_files(repos["work"], f"{base}..{head}", "docs/specs/")

    assert [(c.path, c.commit_hash) for c in got] == [
        ("docs/specs/03-SCN/SYNC-SCN-001.md", h),
        ("docs/specs/BOGUS/EXMP-BOGUS-001.md", hb),
    ]


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
    # _templates는 glob에 걸리지만 명세가 아니라 빠진다 (#40)
    assert got == [SEED, "docs/specs/03-SCN/SYNC-SCN-001.md"]
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
    assert got[1].email == "seed@example.com"
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
    # git.list는 명세만 준다 — 템플릿 수는 init_specs가 만든 파일 목록에서 센다 (#40)
    assert len([k for k in files if k.startswith("docs/specs/_templates/")]) == 12
    assert await g.list(repos["work"], "docs/specs/_templates/*.md") == []


async def test_commit_push_requires_path_content_or_files(repos: dict[str, Path]) -> None:
    with pytest.raises(ValueError):
        await g.commit_push(repos["work"], "m", _author())
    with pytest.raises(ValueError):
        await g.commit_push(repos["work"], "m", _author(), path=SEED)


async def test_list_skips_templates_and_assets(repos: dict[str, Path]) -> None:
    """명세가 아닌 것은 빼고 준다 (#40).

    템플릿을 세면 재구축 결과가 없는 규약 오류를 보여주고, init_project가
    세는 기존 명세 수(UI-3 2.5)도 부풀려진다.
    """
    o = repos["other"]
    for path in (
        "docs/specs/01-RFQ/SYNC-RFQ-001.md",
        "docs/specs/_templates/RFQ.md",
        "docs/specs/assets/메모.md",
    ):
        write_commit_push(o, path, "x", f"seed {path}")
    await g.fetch(repos["work"])
    await g.checkout(repos["work"], "origin/HEAD")

    got = await g.list(repos["work"], "docs/specs/*/*.md")

    assert "docs/specs/01-RFQ/SYNC-RFQ-001.md" in got
    assert not [p for p in got if "_templates" in p or "assets" in p]


async def test_log_follows_renamed_path_oldest_first(repos: dict[str, Path]) -> None:
    """이름이 바뀐 경로도 옛 이름 시절 커밋까지 나온다 (#39).

    --follow는 revision walker의 특수 처리라 --reverse와 조합되지 않는다.
    둘을 같이 주면 rename을 건너는 순간 커밋이 끊긴다.
    """
    o = repos["other"]
    old_path, new_path = "docs/specs/DOM/SYNC-DOM-001.md", "docs/specs/06-DOM/SYNC-DOM-001.md"
    write_commit_push(o, old_path, "v1", "spec(SYNC-DOM-001): 초안")
    write_commit_push(o, old_path, "v2", "spec(SYNC-DOM-001): 수정")
    (o / "docs/specs/06-DOM").mkdir(parents=True, exist_ok=True)
    git(o, "mv", old_path, new_path)
    git(o, "commit", "-q", "-m", "code(C): 명세 디렉터리를 {NN-TYPE}로")
    git(o, "push", "-q", "origin", "HEAD:main")
    write_commit_push(o, new_path, "v3", "spec(SYNC-DOM-001): 옮긴 뒤 수정")
    await g.fetch(repos["work"])
    await g.checkout(repos["work"], "origin/HEAD")

    got = await g.log(repos["work"], new_path)

    assert [c.message for c in got] == [
        "spec(SYNC-DOM-001): 초안",
        "spec(SYNC-DOM-001): 수정",
        "code(C): 명세 디렉터리를 {NN-TYPE}로",
        "spec(SYNC-DOM-001): 옮긴 뒤 수정",
    ]
    # path는 그 커밋 시점의 경로다 — 지금 경로로 읽으면 옛 커밋에서 죽는다
    assert [c.path for c in got] == [old_path, old_path, new_path, new_path]
    for c in got:
        assert await g.read(repos["work"], c.path, c.hash)  # 전부 읽힌다


async def test_log_separates_path_from_multiline_message(repos: dict[str, Path]) -> None:
    """본문에 빈 줄이 있어도 경로를 제대로 떼어 낸다 (#39)."""
    o = repos["other"]
    path = "docs/specs/02-PRD/SYNC-PRD-002.md"
    (o / path).parent.mkdir(parents=True, exist_ok=True)
    (o / path).write_text("x", encoding="utf-8")
    git(o, "add", path)
    git(o, "commit", "-q", "-m", "spec(SYNC-PRD-002): 초안\n\n첫 줄\n\n빈 줄 뒤 둘째 줄")
    git(o, "push", "-q", "origin", "HEAD:main")
    await g.fetch(repos["work"])
    await g.checkout(repos["work"], "origin/HEAD")

    got = await g.log(repos["work"], path)

    assert len(got) == 1 and got[0].path == path
    assert got[0].message == "spec(SYNC-PRD-002): 초안\n\n첫 줄\n\n빈 줄 뒤 둘째 줄"


async def test_last_commit_at_reads_from_origin_head(repos: dict[str, Path]) -> None:
    """백업 파일의 마지막 커밋 시각. 원격 기준이고 fetch를 안 부른다 (#16)."""
    o = repos["other"]
    assert await g.last_commit_at(repos["work"], "backup/tracking.json") is None  # 없는 경로
    write_commit_push(o, "backup/tracking.json", "{}", "chore: 백업")
    await g.fetch(repos["work"])
    first = await g.last_commit_at(repos["work"], "backup/tracking.json")
    assert first is not None and first.tzinfo is not None
    write_commit_push(o, "backup/tracking.json", '{"x": 1}', "chore: 백업")
    await g.fetch(repos["work"])
    assert (await g.last_commit_at(repos["work"], "backup/tracking.json")) >= first
