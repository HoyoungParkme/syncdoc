"""SYNC-MS-010 ConversationService — 카드 AQ(대화 여덟). 첨부 여섯은 카드 AR."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.conversation.service import NEW_TITLE, ConversationService
from app.core.errors import NotFound
from tests.core.spec.test_service import make_project, owner


def _svc(session: Session) -> ConversationService:
    return ConversationService(session)


def _count(session: Session, table: str) -> int:
    return int(session.execute(text(f"select count(*) from {table}")).scalar())


# ── list · create ──
def test_create_defaults_title_and_list_is_recent_first(db_session: Session) -> None:
    make_project(db_session)
    u = owner(db_session)
    a = _svc(db_session).create("EXMP", u)
    assert a.title == NEW_TITLE and a.updated_at == a.created_at
    b = _svc(db_session).create("EXMP", u, "둘째")
    briefs = _svc(db_session).list("EXMP", u)
    assert [c.id for c in briefs] == [b.id, a.id]  # 최근순
    assert briefs[0].title == "둘째" and briefs[0].turn_count == 0


def test_list_and_create_of_other_owner_are_not_found(db_session: Session) -> None:
    make_project(db_session)
    minjun = owner(db_session, "minjun")
    with pytest.raises(NotFound) as e:
        _svc(db_session).list("EXMP", minjun)
    assert e.value.extra["resource"] == "project"
    with pytest.raises(NotFound):
        _svc(db_session).create("EXMP", minjun)


# ── add_turn · finish_turn · get · history ──
def test_turns_seq_title_and_view(db_session: Session) -> None:
    make_project(db_session)
    u = owner(db_session)
    svc = _svc(db_session)
    conv = svc.create("EXMP", u)
    q = "이 요구사항의 근거가 뭐라고 했어? 마흔 자를 넘기는 긴 질문입니다 정말로"
    t1 = svc.add_turn(conv.id, q, [])
    assert t1.seq == 1
    assert len(q) > 40 and svc.get(conv.id, u).title == q[:40]
    svc.finish_turn(t1.id, "Q1이다", [{"kind": "note", "text": "읽는다"}], ["EXMP-RFQ-001#Q1"])
    t2 = svc.add_turn(conv.id, "둘째", [])
    assert t2.seq == 2
    view = svc.get(conv.id, u)
    assert [t.seq for t in view.turns] == [1, 2] and view.turn_count == 2
    assert view.turns[0].answer == "Q1이다" and view.turns[0].error is None
    assert view.turns[0].progress == [{"kind": "note", "text": "읽는다"}]
    assert view.turns[0].context_item_ids == ["EXMP-RFQ-001#Q1"]
    assert view.turns[1].answer is None and view.pending == [] and view.project_code == "EXMP"
    assert view.title == view.turns[0].question[:40]  # 둘째 질문은 제목을 안 바꾼다


def test_finish_turn_error_and_history_skips_failed_and_open_turns(db_session: Session) -> None:
    make_project(db_session)
    u = owner(db_session)
    svc = _svc(db_session)
    conv = svc.create("EXMP", u)
    ok = svc.add_turn(conv.id, "첫째", [])
    svc.finish_turn(ok.id, "답1", [], [])
    bad = svc.add_turn(conv.id, "둘째", [])
    svc.finish_turn(bad.id, None, [], [], error="llm-unavailable")
    cut = svc.add_turn(conv.id, "셋째", [])
    svc.finish_turn(cut.id, None, [], [])  # 답도 error도 없으면 「답 없이 끊겼다」
    svc.add_turn(conv.id, "넷째(열림)", [])
    view = svc.get(conv.id, u)
    assert view.turns[1].error == "llm-unavailable" and view.turns[1].answer is None
    assert view.turns[2].error == "답 없이 끊겼다"
    assert svc.history(conv.id, 10) == [
        {"role": "user", "text": "첫째"},
        {"role": "assistant", "text": "답1"},
    ]
    assert svc.history(conv.id, 0) == []


def test_history_limit_counts_from_the_end(db_session: Session) -> None:
    make_project(db_session)
    u = owner(db_session)
    svc = _svc(db_session)
    conv = svc.create("EXMP", u)
    for i in range(4):
        t = svc.add_turn(conv.id, f"q{i}", [])
        svc.finish_turn(t.id, f"a{i}", [], [])
    h = svc.history(conv.id, 2)
    assert [m["text"] for m in h] == ["q2", "a2", "q3", "a3"]


# ── get · delete · delete_by_project ──
def test_get_and_delete_of_other_owner_is_not_found_and_deletes_nothing(db_session: Session) -> None:
    make_project(db_session)
    u, minjun = owner(db_session), owner(db_session, "minjun")
    svc = _svc(db_session)
    conv = svc.create("EXMP", u)
    with pytest.raises(NotFound) as e:
        svc.get(conv.id, minjun)
    assert e.value.extra["resource"] == "conversation"
    with pytest.raises(NotFound):
        svc.delete(conv.id, minjun)
    with pytest.raises(NotFound):
        svc.get(conv.id + 999, u)
    assert _count(db_session, "conversations") == 1


def test_delete_cascades_turns_and_other_conversation_stays(db_session: Session) -> None:
    make_project(db_session)
    u = owner(db_session)
    svc = _svc(db_session)
    a, b = svc.create("EXMP", u), svc.create("EXMP", u)
    svc.add_turn(a.id, "q", [])
    svc.add_turn(b.id, "q", [])
    svc.delete(a.id, u)
    assert _count(db_session, "conversations") == 1 and _count(db_session, "turns") == 1
    assert svc.list("EXMP", u)[0].id == b.id


def test_delete_by_project_removes_only_that_project(db_session: Session) -> None:
    p = make_project(db_session)
    q = make_project(db_session, code="OTHR")
    u = owner(db_session)
    svc = _svc(db_session)
    svc.add_turn(svc.create("EXMP", u).id, "q", [])
    svc.add_turn(svc.create("OTHR", u).id, "q", [])
    svc.delete_by_project(p.id)
    assert _count(db_session, "conversations") == 1 and _count(db_session, "turns") == 1
    assert svc.list("OTHR", u)[0].turn_count == 1
    assert q.id is not None
