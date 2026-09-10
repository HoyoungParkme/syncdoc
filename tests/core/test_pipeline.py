"""SYNC-MS-007 테스트 관점 — save_pipeline (B1: mcp·github 경로)."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core import pipeline
from syncdoc.core.errors import (
    ConventionViolation,
    ItemDeletionNeedsConfirm,
    NotFound,
    NotImplementedYet,
    PushFailed,
    VersionConflict,
)
from syncdoc.core.project.models import Project, Repository
from syncdoc.core.spec.service import SpecService
from syncdoc.core.types import Author, AuthorKind, DocType, Entry
from tests.conftest import git as g
from tests.core.account.test_service import make_user
from tests.core.reference.test_service import RFQ
from tests.core.spec.test_service import PRD

PRD_BODY = PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1")


@pytest.fixture
def proj(scoped: Session, repos: dict) -> dict:
    """프로젝트 EXMP + 작업 사본(repos['work']) + 에이전트 작성자."""
    p = Project(code="EXMP", name="예시")
    scoped.add(p)
    scoped.flush()
    scoped.add(
        Repository(
            project_id=p.id, remote_url=str(repos["remote"]), workdir_path=str(repos["work"])
        )
    )
    scoped.flush()
    u = make_user(scoped, login="hoyoung")
    author = Author(kind=AuthorKind.agent, user=u, instructed_by=u, via=Entry.mcp)
    return {"project": p, "author": author, "repos": repos, "user": u}


async def create(proj, doc_type=DocType.PRD, body=PRD_BODY, **kw):
    return await pipeline.save_pipeline(
        Entry.mcp,
        None,
        doc_type,
        body,
        None,
        "EXMP",
        proj["author"],
        f"spec: 생성 {doc_type}",
        **kw,
    )


async def update(proj, doc_id, body, expected, **kw):
    return await pipeline.save_pipeline(
        Entry.mcp, doc_id, None, body, expected, None, proj["author"], f"spec({doc_id}): 수정", **kw
    )


def remote_files(repos):
    return g(repos["remote"], "ls-tree", "-r", "--name-only", "main").split("\n")


# ── 생성 ──
async def test_create_issues_id_applies_frontmatter_commits_extracts(scoped: Session, proj) -> None:
    r = await create(proj, DocType.RFQ, RFQ.replace("doc_id: EXMP-RFQ-001", "doc_id: "))
    assert (r.doc_id, r.version_no, r.status, r.pending_decision_version_id) == (
        "EXMP-RFQ-001",
        1,
        "draft",
        None,
    )
    assert "section.missing: 요구" in r.warnings  # 미완성 경고는 저장되고 실린다
    assert "docs/specs/RFQ/EXMP-RFQ-001.md" in remote_files(proj["repos"])
    assert r.commit_hash == g(proj["repos"]["remote"], "rev-parse", "main")
    r2 = await create(proj)  # PRD → RFQ#Q1 참조 추출
    assert r2.doc_id == "EXMP-PRD-001" and r2.warnings == []
    d = SpecService(scoped).get_document("EXMP-PRD-001")
    assert d.commit_hash == r2.commit_hash and d.last_author.via == "mcp"
    n = scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing=false')).scalar()
    assert n == 2  # upstream 문서 참조 + R1→Q1(코드블록 아님)
    assert (
        scoped.execute(text("SELECT via FROM versions WHERE document_id=:d"), {"d": d.id}).scalar()
        == "mcp"
    )


async def test_create_convention_violation_leaves_nothing(scoped: Session, proj) -> None:
    head = g(proj["repos"]["remote"], "rev-parse", "main")
    with pytest.raises(ConventionViolation) as ei:
        await create(proj, DocType.PRD, PRD_BODY.replace("#### R1 첫 기능", "#### R01 첫 기능"))
    assert [v["rule"] for v in ei.value.extra["violations"]] == ["item.padding"]
    assert scoped.execute(text("SELECT count(*) FROM documents")).scalar() == 0
    assert g(proj["repos"]["remote"], "rev-parse", "main") == head


# ── 수정 ──
async def test_update_bumps_version_commit_and_references(scoped: Session, proj) -> None:
    await create(proj, DocType.RFQ, RFQ)
    r1 = await create(proj)
    body2 = PRD_BODY.replace("근거: [[EXMP-RFQ-001#Q1]]", "근거: [[EXMP-RFQ-001#Q2]]")
    r2 = await update(proj, "EXMP-PRD-001", body2, 1, changed_items=["R1"])
    assert (r2.version_no, r2.status) == (2, "draft") and r2.commit_hash != r1.commit_hash
    assert (
        g(proj["repos"]["remote"], "log", "-1", "--format=%s", "main") == "spec(EXMP-PRD-001): 수정"
    )
    raws = (
        scoped.execute(text('SELECT raw_target FROM "references" WHERE from_item_id IS NOT NULL'))
        .scalars()
        .all()
    )
    assert raws == ["EXMP-RFQ-001#Q2"]  # 사라진 참조 삭제, 새 참조 추가


async def test_update_version_conflict_returns_current_body(scoped: Session, proj) -> None:
    await create(proj)
    with pytest.raises(VersionConflict) as ei:
        await update(proj, "EXMP-PRD-001", PRD_BODY + "\n", 7)
    assert ei.value.extra == {"current_version": 1, "current_body": PRD_BODY}
    with pytest.raises(NotFound):
        await update(proj, "EXMP-PRD-404", PRD_BODY, 1)


async def test_update_item_deletion_needs_confirm_then_broken_ref(scoped: Session, proj) -> None:
    await create(proj, DocType.RFQ, RFQ)
    await create(proj)
    rfq = SpecService(scoped).get_document("EXMP-RFQ-001")
    no_q1 = RFQ.replace("#### Q1 첫 요구\n내용\n", "")
    with pytest.raises(ItemDeletionNeedsConfirm) as ei:
        await update(proj, "EXMP-RFQ-001", no_q1, 1)
    assert [d["item_id"] for d in ei.value.extra["deleted_items"]] == ["Q1"]
    assert SpecService(scoped).get_document("EXMP-RFQ-001").current_version_no == 1
    r = await update(proj, "EXMP-RFQ-001", no_q1, 1, confirm_item_deletion=True)
    assert r.version_no == 2
    flags = scoped.execute(text("SELECT kind, assignee_user_id FROM flags")).all()
    assert flags == [("broken_ref", proj["user"].id)]
    assert [i.item_id for i in SpecService(scoped).get_document("EXMP-RFQ-001").items] == ["Q2"]
    assert rfq.id == SpecService(scoped).get_document("EXMP-RFQ-001").id


async def test_push_failure_leaves_db_untouched(scoped: Session, proj, monkeypatch) -> None:
    await create(proj)

    async def boom(*a, **k):
        raise PushFailed("network")

    monkeypatch.setattr(pipeline.git, "commit_push", boom)
    with pytest.raises(PushFailed):
        await update(proj, "EXMP-PRD-001", PRD_BODY + "\n", 1)
    assert SpecService(scoped).get_document("EXMP-PRD-001").current_version_no == 1
    assert scoped.execute(text("SELECT count(*) FROM versions")).scalar() == 1


async def test_update_approved_document_demotes(scoped: Session, proj) -> None:
    await create(proj)
    scoped.execute(text("UPDATE documents SET status='approved'"))
    body = PRD_BODY.replace("status: draft", "status: approved").replace("한 줄로.", "두 줄로.")
    r = await update(proj, "EXMP-PRD-001", body, 1)
    assert r.status == "review"
    assert (
        scoped.execute(
            text("SELECT count(*) FROM status_changes WHERE to_status='review'")
        ).scalar()
        == 1
    )


async def test_github_entry_saves_violations_as_convention_error(scoped: Session, proj) -> None:
    await create(proj)
    gh = Author(kind=AuthorKind.human, user=proj["user"], instructed_by=None, via=Entry.github)
    bad = PRD_BODY.replace("#### R1 첫 기능", "#### R01 첫 기능")
    r = await pipeline.save_pipeline(
        Entry.github, "EXMP-PRD-001", None, bad, None, None, gh, "외부 커밋", commit_hash="deadbeef"
    )
    assert r.version_no == 2 and r.commit_hash == "deadbeef"
    d = SpecService(scoped).get_document("EXMP-PRD-001")
    assert d.has_convention_error and "item.padding" in d.convention_error_detail
    assert scoped.execute(text("SELECT via FROM versions WHERE version_no=2")).scalar() == "github"


async def test_web_status_entry_is_b2(scoped: Session, proj) -> None:
    await create(proj)
    human = Author(
        kind=AuthorKind.human, user=proj["user"], instructed_by=None, via=Entry.web_status
    )
    with pytest.raises(NotImplementedYet):
        await pipeline.save_pipeline(
            Entry.web_status, "EXMP-PRD-001", None, PRD_BODY, 1, None, human, "status(...)"
        )


async def test_concurrent_saves_are_serialized_second_conflicts(scoped: Session, proj) -> None:
    await create(proj)
    a = update(proj, "EXMP-PRD-001", PRD_BODY.replace("한 줄로.", "A"), 1)
    b = update(proj, "EXMP-PRD-001", PRD_BODY.replace("한 줄로.", "B"), 1)
    results = await asyncio.gather(a, b, return_exceptions=True)
    kinds = sorted(type(r).__name__ for r in results)
    assert kinds == ["SaveResult", "VersionConflict"]
    assert SpecService(scoped).get_document("EXMP-PRD-001").current_version_no == 2


async def test_upstream_impact_flags_upstream_item_or_warns(scoped: Session, proj) -> None:
    await create(proj, DocType.RFQ, RFQ)
    r = await create(proj, upstream_impact=["EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q9"])
    assert r.warnings == ["upstream_impact.unknown: EXMP-RFQ-001#Q9"]
    q2 = next(
        i.pk for i in SpecService(scoped).get_document("EXMP-RFQ-001").items if i.item_id == "Q2"
    )
    flags = scoped.execute(text("SELECT kind, target_item_id, assignee_user_id FROM flags")).all()
    assert flags == [("upstream_impact", q2, proj["user"].id)]


async def test_relocate_moves_comment_on_update(scoped: Session, proj) -> None:
    from tests.core.collab.test_service import _comment

    await create(proj)
    d = SpecService(scoped).get_document("EXMP-PRD-001")
    n = PRD_BODY.split("\n").index("#### R1 첫 기능") + 1
    c = _comment(scoped, d.id, proj["user"].id, n, "#### R1 첫 기능")
    await update(
        proj, "EXMP-PRD-001", PRD_BODY.replace("# 예시 제품 PRD", "# 예시 제품 PRD\n추가"), 1
    )
    assert c.line_no == n + 1
