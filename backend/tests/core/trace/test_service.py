"""SYNC-MS-025 테스트 관점 — TraceService(카드 CI)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import NotFound, TraceInvalid
from app.core.trace import service as trace_service
from app.core.trace.service import TraceService
from tests.core.spec.test_service import make_project, owner


def record(key: str = "t1", **over) -> dict:
    r = {
        "version": 1,
        "id": key,
        "kind": "back",
        "method": "GET",
        "path": "/api/x",
        "status": 200,
        "error": None,
        "startedAt": "2026-10-17T01:02:03Z",
        "ms": 12,
        "commit": "a" * 40,
        "truncated": False,
        "events": [
            {"i": 0, "parent": -1, "fn": "app/a.py:3", "t0": 0},
            {
                "i": 1,
                "parent": 0,
                "fn": "@infra",
                "t0": 1,
                "infra": {"kind": "db", "target": "db:5432"},
            },
            {"i": 2, "parent": 0, "fn": "app/b.py:9", "t0": 2},
        ],
    }
    r.update(over)
    return r


def test_save_returns_brief_and_same_key_once(db_session: Session) -> None:
    p = make_project(db_session)
    svc = TraceService(db_session)
    b, new = svc.save(p.id, owner(db_session).id, record())
    assert new and (b.trace_key, b.event_count, b.method, b.commit_hash) == (
        "t1",
        3,
        "GET",
        "a" * 40,
    )
    assert b.started_at.isoformat() == "2026-10-17T01:02:03+00:00"
    k, _ = svc.save(p.id, owner(db_session).id, record("kst", startedAt="2026-10-17T10:02:03.5+09:00"))
    assert k.started_at.isoformat() == "2026-10-17T01:02:03.500000+00:00"  # UTC로
    again, new2 = svc.save(p.id, owner(db_session).id, record(path="/other"))
    assert not new2 and again.id == b.id and again.path == "/api/x"
    assert db_session.execute(text("select count(*) from traces")).scalar() == 2


def test_save_keeps_recent_per_project(db_session: Session, monkeypatch) -> None:
    monkeypatch.setattr(trace_service, "KEEP", 3)
    p = make_project(db_session)
    q = make_project(db_session, code="OTHR")
    svc = TraceService(db_session)
    uid = owner(db_session).id
    svc.save(q.id, uid, record("q1"))
    for n in range(4):
        svc.save(p.id, uid, record(f"t{n}"))
    keys = [b.trace_key for b in svc.list_recent(p.id)]
    assert keys == ["t3", "t2", "t1"]  # 가장 오래된 것이 지워진다
    assert [b.trace_key for b in svc.list_recent(q.id)] == ["q1"]  # 다른 프로젝트는 그대로
    assert [b.trace_key for b in svc.list_recent(p.id, limit=2)] == ["t3", "t2"]


def test_save_job_has_no_method_and_error_is_cut(db_session: Session) -> None:
    p = make_project(db_session)
    svc = TraceService(db_session)
    long = "e" * 301
    b, _ = svc.save(p.id, owner(db_session).id, record(kind="job", method="JOB", error=long))
    assert b.method is None and len(b.error) == 300
    assert svc.get(p.id, b.id).record["error"] == long  # record는 그대로


@pytest.mark.parametrize(
    ("events", "reason"),
    [
        ([{"i": 0, "parent": 5, "fn": "a", "t0": 0}], "events[0] — 부모가 없다"),
        ([{"i": 1, "parent": -1, "fn": "a", "t0": 0}], "events[0] — i가 차례가 아니다"),
    ],
)
def test_save_rejects_bad_events(db_session: Session, events, reason) -> None:
    p = make_project(db_session)
    with pytest.raises(TraceInvalid) as e:
        TraceService(db_session).save(p.id, owner(db_session).id, record(events=events))
    assert e.value.extra == {"reason": reason}
    assert db_session.execute(text("select count(*) from traces")).scalar() == 0


def test_get_delete_and_other_project(db_session: Session) -> None:
    p = make_project(db_session)
    q = make_project(db_session, code="OTHR")
    svc = TraceService(db_session)
    uid = owner(db_session).id
    b, _ = svc.save(p.id, uid, record("a"))
    svc.save(p.id, uid, record("b"))
    svc.save(q.id, uid, record("c"))
    assert svc.get(p.id, b.id).record["id"] == "a"
    with pytest.raises(NotFound):
        svc.get(q.id, b.id)
    with pytest.raises(NotFound):
        svc.delete(q.id, b.id)
    assert svc.delete(p.id, b.id) == 1
    assert svc.delete(p.id) == 1
    assert [x.trace_key for x in svc.list_recent(q.id)] == ["c"]


def test_coverage_keys_and_infra(db_session: Session) -> None:
    p = make_project(db_session)
    svc = TraceService(db_session)
    assert svc.coverage(p.id) == trace_service.TraceCoverage(0, [], [])
    uid = owner(db_session).id
    svc.save(p.id, uid, record("a"))
    svc.save(p.id, uid, record("b", events=[{"i": 0, "parent": -1, "fn": "@fetch", "t0": 0},
                                            {"i": 1, "parent": 0, "fn": "app/a.py:3", "t0": 1}]))  # fmt: skip
    c = svc.coverage(p.id)
    assert (c.traces, c.keys, c.infra) == (
        2,
        ["app/a.py:3", "app/b.py:9"],
        [{"kind": "db", "target": "db:5432"}],
    )


async def test_delete_project_removes_traces(db_session: Session) -> None:
    """MS-001 delete_project 2b — 해제하면 실행 기록도 없다."""
    from app.core.project.service import ProjectService

    p = make_project(db_session)
    TraceService(db_session).save(p.id, owner(db_session).id, record())
    await ProjectService(db_session).delete_project("EXMP", owner(db_session))
    assert db_session.execute(text("select count(*) from traces")).scalar() == 0
