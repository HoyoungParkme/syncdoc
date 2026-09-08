"""SYNC-MS-005 테스트 관점 — CommentService (B1 셋)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.collab.models import Comment
from syncdoc.core.collab.service import CommentService, line_hash
from syncdoc.core.spec.service import SpecService
from syncdoc.core.types import DocType
from tests.core.spec.test_service import PRD, author, make_project


def _doc(db_session: Session):
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    return svc, p, a, svc.get_document("EXMP-PRD-001")


def _comment(
    db_session: Session,
    doc_id: int,
    user_id: int,
    line_no: int,
    body: str,
    resolved=False,
    parent=None,
):
    c = Comment(
        document_id=doc_id,
        parent_comment_id=parent,
        line_no=line_no,
        line_hash=line_hash(body),
        body="댓글",
        author_user_id=user_id,
        is_resolved=resolved,
    )
    db_session.add(c)
    db_session.flush()
    return c


# ── relocate ──
def test_relocate_moves_lines_marks_missing_picks_nearest(db_session: Session) -> None:
    svc, p, a, d = _doc(db_session)
    lines = PRD.split("\n")
    n_r1 = lines.index("#### R1 첫 기능") + 1
    n_g1 = lines.index("#### G1 첫 목표") + 1
    c_r1 = _comment(db_session, d.id, a.user.id, n_r1, "#### R1 첫 기능")
    c_g1 = _comment(db_session, d.id, a.user.id, n_g1, "#### G1 첫 목표")
    c_done = _comment(db_session, d.id, a.user.id, n_g1, "#### G1 첫 목표", resolved=True)
    # 위에 줄 3개 삽입 · G1 헤딩 삭제 · 같은 내용 줄이 둘(R1 헤딩을 끝에 하나 더) → 가까운 쪽
    new = PRD.replace("# 예시 제품 PRD", "# 예시 제품 PRD\n추가1\n추가2\n추가3").replace(
        "#### G1 첫 목표\n", ""
    )
    new = new.replace("## 5. 미결사항", "#### R1 첫 기능\n## 5. 미결사항")
    svc.save(d, new, "h2", a, "spec: 테스트", [])
    assert CommentService(db_session).relocate(d.id, PRD, new, old_version_no=1) == 1
    assert c_r1.line_no == n_r1 + 3 - 1 and c_r1.original_location is None
    assert c_g1.line_no == n_g1 and c_g1.original_location == f"v1:{n_g1}"
    assert c_done.line_no == n_g1 and c_done.original_location is None  # 해결된 건 안 옮김
    CommentService(db_session).relocate(d.id, new, new, old_version_no=2)
    assert c_g1.original_location == f"v1:{n_g1}"  # 이미 있으면 그대로


# ── count_unresolved · count_unresolved_by_document ──
def test_counts_top_level_unresolved_only(db_session: Session) -> None:
    svc, p, a, d = _doc(db_session)
    other = make_project(db_session, "OTHR")
    svc.create(
        other.id, "OTHR-PRD-001", DocType.PRD, PRD.replace("EXMP", "OTHR"), "h", a, "spec: 테스트"
    )
    d2 = svc.get_document("OTHR-PRD-001")
    top = _comment(db_session, d.id, a.user.id, 1, "x")
    _comment(db_session, d.id, a.user.id, 1, "x", parent=top.id)  # 답글은 안 센다
    _comment(db_session, d.id, a.user.id, 2, "y", resolved=True)
    _comment(db_session, d2.id, a.user.id, 1, "z")
    cs = CommentService(db_session)
    assert cs.count_unresolved(p.id) == 1 and cs.count_unresolved(other.id) == 1
    assert cs.count_unresolved_by_document([d.id, d2.id, 999]) == {d.id: 1, d2.id: 1}
    assert cs.count_unresolved_by_document([]) == {}
    assert db_session.execute(text("SELECT count(*) FROM comments")).scalar() == 4


# ── list · add · resolve · unresolved_count · unresolved_in ──
def test_add_list_thread_resolve_and_counts(db_session: Session) -> None:
    from syncdoc.core.errors import NotFound

    svc, p, a, d = _doc(db_session)
    cs = CommentService(db_session)
    line = PRD.split("\n")[9]
    c1 = cs.add(d.id, 10, line, "애매하다", a.user, None)
    c2 = cs.add(d.id, 10, line, "나도", a.user, None)  # 같은 줄에 둘 → 스레드 둘
    r = cs.add(d.id, 10, line, "답글", a.user, c1.id)
    assert c1.line_hash == line_hash(line) and r.parent_comment_id == c1.id
    top = cs.list(d.id)
    assert (
        [c.id for c in top] == [c1.id, c2.id]
        and [x.id for x in top[0].replies] == [r.id]
        and top[1].replies == []
    )
    assert cs.unresolved_count(d.id) == 2  # 최상위만
    other = make_project(db_session, "OTHR")
    svc.create(
        other.id, "OTHR-PRD-001", DocType.PRD, PRD.replace("EXMP", "OTHR"), "h", a, "spec: 테스트"
    )
    with pytest.raises(NotFound):
        cs.add(
            svc.get_document("OTHR-PRD-001").id, 1, "x", "y", a.user, c1.id
        )  # 다른 문서의 parent
    got = cs.unresolved_in([d.id])
    assert [(s.id, s.doc_id, s.line_no, s.excerpt, s.author.github_login) for s in got] == [
        (c1.id, "EXMP-PRD-001", 10, "애매하다", "hoyoung"),
        (c2.id, "EXMP-PRD-001", 10, "나도", "hoyoung"),
        (r.id, "EXMP-PRD-001", 10, "답글", "hoyoung"),
    ]  # 답글도 포함
    assert cs.resolve(c1.id, True).is_resolved is True and cs.unresolved_count(d.id) == 1
    assert [c.id for c in cs.list(d.id)] == [c1.id, c2.id]  # 해결된 것도 목록에
    assert cs.resolve(c1.id, False).is_resolved is False and cs.unresolved_count(d.id) == 2
    with pytest.raises(NotFound):
        cs.resolve(999_999, True)
