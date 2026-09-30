"""SYNC-MS-011 테스트 관점 — CodeGraphService 넷(카드 AX)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.codegraph.service import CodeGraphService
from tests.core.spec.test_service import make_project

G1 = {"functions": [{"key": "a.py:1"}, {"key": "a.py:5"}], "calls": [["a.py:1", "a.py:5", "graphify"]]}  # fmt: skip
G2 = {"functions": [{"key": "b.py:1"}], "calls": []}


def test_save_replaces_one_row_and_clears_error(db_session: Session) -> None:
    p = make_project(db_session)
    svc = CodeGraphService(db_session)
    assert svc.get(p.id) is None
    svc.fail(p.id, "a" * 40, "시간 초과")
    row = svc.save(p.id, "b" * 40, "server", G1)
    assert (row.commit_hash, row.source, row.function_count, row.call_count, row.error) == (
        "b" * 40, "server", 2, 1, None,
    )  # fmt: skip
    svc.save(p.id, "c" * 40, "repo", G2)
    n = db_session.execute(text("select count(*) from code_graphs")).scalar()
    assert n == 1 and svc.get(p.id).graph == G2 and svc.get(p.id).source == "repo"


def test_fail_keeps_old_graph_and_first_failure_is_empty(db_session: Session) -> None:
    p = make_project(db_session)
    svc = CodeGraphService(db_session)
    first = svc.fail(p.id, "d" * 40, "graph.json 없음")
    assert first.graph == {"functions": [], "calls": []} and first.commit_hash is None
    assert first.error == "ddddddd: graph.json 없음"
    svc.save(p.id, "e" * 40, "server", G1)
    row = svc.fail(p.id, "f" * 40, "x" * 400)
    assert row.graph == G1 and row.commit_hash == "e" * 40  # 옛 그래프는 그대로
    assert row.error.startswith("fffffff: ") and len(row.error) == 300  # 300자에서 자른다


def test_delete_by_project(db_session: Session) -> None:
    p = make_project(db_session)
    CodeGraphService(db_session).save(p.id, "a" * 40, "server", G1)
    CodeGraphService(db_session).delete_by_project(p.id)
    assert CodeGraphService(db_session).get(p.id) is None


async def test_delete_project_removes_code_graph(db_session: Session) -> None:
    """MS-001 delete_project 2a — 해제하면 코드 그래프도 없다."""
    from app.core.project.service import ProjectService
    from tests.core.spec.test_service import owner

    p = make_project(db_session)
    CodeGraphService(db_session).save(p.id, "a" * 40, "server", G1)
    await ProjectService(db_session).delete_project("EXMP", owner(db_session))
    assert db_session.execute(text("select count(*) from code_graphs")).scalar() == 0


# ── read (카드 AY) — 실제 git으로 ──
async def test_read_uses_graph_commit_denies_secrets_and_caps(
    db_session: Session, repos: dict
) -> None:
    import pytest

    from app.core.errors import NotFound
    from tests.conftest import git, write_commit_push

    p = make_project(db_session)
    other, work = repos["other"], repos["work"]
    body = "\n".join(f"L{i}" for i in range(1, 401))
    write_commit_push(other, "app/a.py", body, "code")
    write_commit_push(other, ".env", "KEY=secret", "env")
    head = write_commit_push(other, "config/secrets.yaml", "k: v", "secret")
    write_commit_push(other, "app/a.py", "바뀐 뒤", "later")  # 그래프 뒤의 커밋
    git(work, "fetch", "-q", "origin")
    svc = CodeGraphService(db_session)
    with pytest.raises(NotFound):  # 그래프가 없으면
        await svc.read(p.id, work, "app/a.py", 1, 3)
    svc.save(p.id, head, "server", G1)
    t = await svc.read(p.id, work, "app/a.py", 2, 4)
    assert (t.start, t.end, t.text, t.truncated) == (
        2,
        4,
        "L2\nL3\nL4",
        False,
    )  # 그래프 커밋의 내용
    big = await svc.read(p.id, work, "app/a.py", 1, None)
    assert (big.start, big.end, big.truncated) == (1, 300, True)
    for bad in (".env", "config/secrets.yaml", "../x", "/etc/passwd", "없는.py"):
        with pytest.raises(NotFound) as e:
            await svc.read(p.id, work, bad, 1, 5)
        assert e.value.extra["resource"] == "file", bad  # 전부 같은 답 — 있는지가 새지 않는다
