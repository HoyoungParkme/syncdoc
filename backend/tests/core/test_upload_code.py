"""SYNC-MS-007 테스트 관점 — pipeline.upload_code (카드 BB, UC-A10)."""

import pytest
from sqlalchemy.orm import Session

from app.core import pipeline
from app.core.errors import StorageMismatch, UploadPathRefused, UploadTooLarge
from app.core.project.models import Project, Repository
from app.core.spec.service import SpecService
from app.core.types import Author, AuthorKind, Entry
from tests.conftest import git as g
from tests.conftest import write_commit_push
from tests.core.account.test_service import make_user

RFQ = "---\ndoc_id: UPL-RFQ-001\ntype: RFQ\ntitle: 요구\nstatus: draft\n---\n# RFQ\n## 1. 배경\n#### Q1 첫 요구\n내용\n"


@pytest.fixture
def srv(scoped: Session, repos: dict, code_graph_calls: list) -> dict:
    """서버 저장 프로젝트 UPL — 원격은 repos의 bare(서버 안 경로), 처리 지점은 지금 main."""
    u = make_user(scoped, login="hoyoung", token=None)  # GitHub 토큰이 없어도 된다
    p = Project(code="UPL", name="올리기", owner_user_id=u.id)
    scoped.add(p)
    scoped.flush()
    repo = Repository(
        project_id=p.id,
        storage="server",
        remote_url=str(repos["remote"]),
        workdir_path=str(repos["work"]),
        registered_by_user_id=u.id,
        last_processed_commit=g(repos["remote"], "rev-parse", "main"),
    )
    scoped.add(repo)
    scoped.flush()
    author = Author(kind=AuthorKind.agent, user=u, instructed_by=u, via=Entry.mcp)
    return {"author": author, "repos": repos, "repo": repo, "calls": code_graph_calls}


async def test_upload_two_files_and_a_delete_is_one_commit_then_processed(srv) -> None:
    remote = srv["repos"]["remote"]
    write_commit_push(srv["repos"]["other"], "old.py", "x = 0\n", "옛 파일")
    r = await pipeline.upload_code(
        "UPL",
        {"app/a.py": "def a():\n    return 1\n", "app/pkg/b.py": "B = 2\n"},
        ["old.py"],
        "code: 두 파일",
        srv["author"],
    )
    assert r.changed and (r.files, r.deleted) == (2, 1)
    assert r.commit == g(remote, "rev-parse", "main")
    assert g(remote, "log", "-1", "--format=%s|%ae", "main") == (
        "code: 두 파일|hoyoung@users.noreply.github.com"
    )
    tree = g(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert "app/a.py" in tree and "app/pkg/b.py" in tree and "old.py" not in tree
    assert srv["repo"].last_processed_commit == r.commit  # 6 — 처리 지점이 이 커밋
    assert ("UPL", r.commit) in srv["calls"]  # 코드가 바뀌었으니 그래프를 건다


async def test_same_content_makes_no_commit(srv) -> None:
    files = {"app/a.py": "A = 1\n"}
    first = await pipeline.upload_code("UPL", files, [], "code: 처음", srv["author"])
    again = await pipeline.upload_code("UPL", files, [], "code: 또", srv["author"])
    assert first.changed and not again.changed and again.commit == first.commit


async def test_over_the_limits_is_upload_too_large_and_nothing_changes(srv) -> None:
    remote = srv["repos"]["remote"]
    head = g(remote, "rev-parse", "main")
    with pytest.raises(UploadTooLarge) as ei:
        await pipeline.upload_code(
            "UPL", {"big.txt": "x" * (5 * 1024 * 1024 + 1)}, [], "m", srv["author"]
        )
    assert ei.value.extra["size"] == 5 * 1024 * 1024 + 1
    many = {f"f{i}.py": "" for i in range(500)}
    with pytest.raises(UploadTooLarge) as ei:
        await pipeline.upload_code("UPL", many, ["gone.py"], "m", srv["author"])  # 501개
    assert ei.value.extra["count"] == 501
    assert g(remote, "rev-parse", "main") == head


async def test_refused_paths_are_all_reported_and_nothing_is_committed(srv) -> None:
    remote = srv["repos"]["remote"]
    head = g(remote, "rev-parse", "main")
    files = {
        "/etc/abs.py": "x",
        "../up.py": "x",
        ".git/hooks/pre-commit": "x",
        "docs/specs/01-RFQ/UPL-RFQ-001.md": RFQ,
        ".env": "SECRET=1",
        "certs/server.pem": "x",
        "win\\path.py": "x",
        "bin.dat": "a\x00b",
        "ok.py": "OK = 1\n",  # 멀쩡한 것이 섞여 있어도 올라가지 않는다
    }
    with pytest.raises(UploadPathRefused) as ei:
        await pipeline.upload_code("UPL", files, [], "m", srv["author"])
    refused = {x["path"] for x in ei.value.extra["paths"]}
    assert refused == set(files) - {"ok.py"}
    assert g(remote, "rev-parse", "main") == head


async def test_github_stored_project_is_storage_mismatch(srv, scoped: Session) -> None:
    srv["repo"].storage = "github"
    scoped.flush()
    with pytest.raises(StorageMismatch):
        await pipeline.upload_code("UPL", {"a.py": "x"}, [], "m", srv["author"])


async def test_pending_spec_push_is_read_first_and_survives(srv, scoped: Session) -> None:
    """DEV-19 — 먼저 push된 명세 커밋을 읽고 나서 올린다. 올린 뒤에도 그 명세가 살아 있다."""
    other, remote = srv["repos"]["other"], srv["repos"]["remote"]
    write_commit_push(other, "docs/specs/01-RFQ/UPL-RFQ-001.md", RFQ, "spec(UPL-RFQ-001): 초안")
    r = await pipeline.upload_code("UPL", {"app/c.py": "C = 3\n"}, [], "code: c", srv["author"])
    assert r.changed
    tree = g(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert "docs/specs/01-RFQ/UPL-RFQ-001.md" in tree and "app/c.py" in tree
    assert SpecService(scoped).get_document("UPL-RFQ-001").doc_id == "UPL-RFQ-001"
