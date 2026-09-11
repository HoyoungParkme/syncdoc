"""SYNC-MS-007 테스트 관점 — save_pipeline (B1: mcp·github 경로) · change_status (B2)."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import pipeline
from app.core.errors import (
    AlreadyCurrent,
    ConventionViolation,
    ItemDeletionNeedsConfirm,
    NotFound,
    PushFailed,
    RebuildFailed,
    VersionConflict,
)
from app.core.project.models import Project, Repository
from app.core.spec.service import SpecService
from app.core.types import Author, AuthorKind, DocType, Entry
from tests.conftest import git as g
from tests.conftest import write_commit_push
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
    u = make_user(scoped, login="hoyoung")
    scoped.add(
        Repository(
            project_id=p.id,
            remote_url=str(repos["remote"]),
            workdir_path=str(repos["work"]),
            registered_by_user_id=u.id,
        )
    )
    scoped.flush()
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
    assert "docs/specs/01-RFQ/EXMP-RFQ-001.md" in remote_files(proj["repos"])
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


async def test_web_status_entry_commits_status_only(scoped: Session, proj) -> None:
    await create(proj)
    human = Author(
        kind=AuthorKind.human, user=proj["user"], instructed_by=None, via=Entry.web_status
    )
    body = PRD_BODY.replace("status: draft", "status: review")
    r = await pipeline.save_pipeline(
        Entry.web_status,
        "EXMP-PRD-001",
        None,
        body,
        1,
        None,
        human,
        "status(EXMP-PRD-001): draft → review\n\n이유",
        reason="이유",  # 커밋 메시지를 다시 파싱하지 않는다 (MS-002 apply_status 근거)
    )
    assert (r.version_no, r.status, r.pending_decision_version_id) == (1, "review", None)
    assert scoped.execute(text("SELECT count(*) FROM versions")).scalar() == 1
    assert scoped.execute(text("SELECT reason, commit_hash FROM status_changes")).one() == (
        "이유",
        r.commit_hash,
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


# ── change_status (pipeline — 검사 → web_status 저장 → 승인 대조 플래그) ──
async def test_change_status_commits_frontmatter_no_version(scoped: Session, proj) -> None:
    from app.core.errors import StatusBlocked, UpstreamReviewRequired

    await create(proj, DocType.RFQ, RFQ)
    r = await create(proj)
    svc = SpecService(scoped)
    user = proj["user"]
    # review로 — 상위 대조 없이 됨
    d = await pipeline.change_status("EXMP-PRD-001", "review", user, "검토 시작")
    assert d.status == "review" and d.current_version_no == 1
    assert (
        g(proj["repos"]["remote"], "log", "-1", "--format=%s", "main")
        == "status(EXMP-PRD-001): draft → review"
    )
    row = scoped.execute(
        text("SELECT from_status, to_status, reason, commit_hash FROM status_changes")
    ).one()
    assert row[:3] == ("draft", "review", "검토 시작") and row[3] == g(
        proj["repos"]["remote"], "rev-parse", "main"
    )
    assert (
        scoped.execute(
            text("SELECT count(*) FROM versions WHERE document_id=:d"), {"d": d.id}
        ).scalar()
        == 1
    )
    assert "status: review" in svc.get_document("EXMP-PRD-001").body
    # 같은 상태로 다시 → 커밋 없음
    head = g(proj["repos"]["remote"], "rev-parse", "main")
    await pipeline.change_status("EXMP-PRD-001", "review", user, None)
    assert g(proj["repos"]["remote"], "rev-parse", "main") == head
    # approved인데 upstream_reviewed=false → 거부
    with pytest.raises(UpstreamReviewRequired):
        await pipeline.change_status("EXMP-PRD-001", "approved", user, None)
    # 정상 승인 + 어긋난 상위 지정 → Q2에 upstream_impact 플래그
    d2 = await pipeline.change_status(
        "EXMP-PRD-001",
        "approved",
        user,
        "합의",
        upstream_reviewed=True,
        upstream_mismatch=["EXMP-RFQ-001#Q2"],
    )
    assert d2.status == "approved"
    q2 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q2")
    assert scoped.execute(text("SELECT kind, target_item_id FROM flags")).all() == [
        ("upstream_impact", q2)
    ]
    # 미완성 경고가 있는 문서는 approved 불가 — 생성 직후부터 경고가 남는다 (MS-002 create 1단계)
    scn = await create(proj, DocType.SCN, "# 시나리오\n\n## 배경\n\n아직 항목이 없다.\n")
    assert "item.none" in scn.warnings
    assert "item.none" in svc.get_document(scn.doc_id).incomplete_warnings
    with pytest.raises(StatusBlocked) as ei:
        await pipeline.change_status(scn.doc_id, "approved", user, None, upstream_reviewed=True)
    assert "item.none" in ei.value.extra["warnings"]
    # mcp 수정 저장에도 남는다 (MS-007 8단계, 모든 경로)
    body = svc.get_document(scn.doc_id).body + "\n한 줄 더.\n"
    r3 = await update(proj, scn.doc_id, body, 1)
    assert "item.none" in r3.warnings
    assert "item.none" in svc.get_document(scn.doc_id).incomplete_warnings
    with pytest.raises(StatusBlocked):
        await pipeline.change_status(scn.doc_id, "approved", user, None, upstream_reviewed=True)
    assert r.doc_id == "EXMP-PRD-001"


# ── 11단계: 변경 영향 → 전파 미결정 (B3, detect_impact 스텁 해제) ──
async def test_update_with_changed_items_creates_pending_decision(scoped: Session, proj) -> None:
    await create(proj, DocType.RFQ, RFQ)
    r1 = await create(proj)
    svc = SpecService(scoped)
    rfq = svc.get_document("EXMP-RFQ-001")
    r = await update(
        proj, "EXMP-RFQ-001", rfq.body.replace("내용", "바뀐 내용"), 1, changed_items=["Q1"]
    )
    assert r.pending_decision_version_id is not None and r.version_no == 2
    dec = scoped.execute(
        text("SELECT version_id, choice, affected_pks, changed_pks FROM propagation_decisions")
    ).one()
    r1_pk = next(i.pk for i in svc.get_document("EXMP-PRD-001").items if i.item_id == "R1")
    q1 = next(i.pk for i in rfq.items if i.item_id == "Q1")
    assert dec == (r.pending_decision_version_id, "undecided", [r1_pk], [q1])  # R1이 Q1 참조
    # 영향 없음 선언 → 미결정 없음 · diff 판정(changed_items None)도 같은 결과
    r2 = await update(
        proj, "EXMP-RFQ-001", svc.get_document("EXMP-RFQ-001").body + "\n", 2, changed_items=[]
    )
    assert r2.pending_decision_version_id is None
    body = svc.get_document("EXMP-RFQ-001").body.replace("바뀐 내용", "또 바뀐 내용")
    r3 = await update(proj, "EXMP-RFQ-001", body, 3, changed_items=None)
    assert (
        r3.pending_decision_version_id == r3.version_no
        and False
        or r3.pending_decision_version_id is not None
    )
    assert r1.doc_id == "EXMP-PRD-001"


# ── revert (B4) ──
async def test_revert_creates_new_version_and_asks_confirm_for_vanishing_items(
    scoped: Session, proj
) -> None:
    await create(proj, DocType.RFQ, RFQ)
    r1 = await create(proj)
    svc = SpecService(scoped)
    user = proj["user"]
    v1_body = svc.get_document("EXMP-PRD-001").body
    # v2: R2 추가 → 시나리오가 R2를 참조
    await update(proj, "EXMP-PRD-001", v1_body + "#### R2 둘째 기능\n내용\n", 1, changed_items=[])
    scn = await pipeline.save_pipeline(
        Entry.mcp,
        None,
        DocType.SCN,
        "# 시나리오\n\n## 1. 페르소나\n\n#### P1 사람\n근거 [[EXMP-PRD-001#R2]]\n",
        None,
        "EXMP",
        proj["author"],
        "spec(SCN): 초안",
        changed_items=[],
    )
    with pytest.raises(AlreadyCurrent):
        await pipeline.revert("EXMP-PRD-001", 2, user)
    with pytest.raises(NotFound):
        await pipeline.revert("EXMP-PRD-001", 9, user)
    # v1로 되돌리면 R2가 사라지고 하위 참조가 있다 → 확인 요구 → confirm
    with pytest.raises(ItemDeletionNeedsConfirm) as ei:
        await pipeline.revert("EXMP-PRD-001", 1, user)
    assert ei.value.extra["deleted_items"][0]["item_id"] == "R2"
    r = await pipeline.revert("EXMP-PRD-001", 1, user, confirm_item_deletion=True)
    assert (r.version_no, r.doc_id) == (3, "EXMP-PRD-001")
    d = svc.get_document("EXMP-PRD-001")
    assert d.body == v1_body and d.current_version_no == 3  # v2는 이력에 남는다
    assert (
        g(proj["repos"]["remote"], "log", "-1", "--format=%s", "main")
        == "revert(EXMP-PRD-001): v2 → v1 내용으로"
    )
    assert scoped.execute(
        text("SELECT via, author_kind FROM versions WHERE version_no=3")
    ).one() == ("web", "human")
    assert scoped.execute(text("SELECT kind FROM flags")).scalars().all() == ["broken_ref"]  # P1에
    assert r1.version_no == 1 and scn.doc_id == "EXMP-SCN-001"


# ── process_commit (B4, UC-G1) ──
RFQ_FILE = "docs/specs/01-RFQ/EXMP-RFQ-001.md"
PRD_FILE = "docs/specs/02-PRD/EXMP-PRD-001.md"


def _repo_row(proj):
    return proj["project"].repository


async def test_process_commit_two_files_one_commit_and_catch_up(scoped: Session, proj) -> None:
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")  # 시드 커밋은 처리 완료로 본다
    scoped.flush()
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other / RFQ_FILE).write_text(RFQ, encoding="utf-8")
    (other / PRD_FILE).write_text(PRD_BODY, encoding="utf-8")
    g(other, "add", "-A")
    g(
        other,
        "commit",
        "-q",
        "--author=hoyoung <hoyoung@users.noreply.github.com>",
        "-m",
        "spec: RFQ·PRD 추가",
    )
    g(other, "push", "-q", "origin", "HEAD:main")
    head = g(remote, "rev-parse", "main")
    results = await pipeline.process_commit(repo, head)
    assert sorted((r.doc_id, r.version_no, r.commit_hash) for r in results) == [
        ("EXMP-PRD-001", 1, head),
        ("EXMP-RFQ-001", 1, head),
    ]
    svc = SpecService(scoped)
    d = svc.get_document("EXMP-PRD-001")
    assert (d.has_convention_error, d.last_author.via, d.last_author.user_id) == (
        False,
        "github",
        proj["user"].id,
    )
    assert [i.item_id for i in d.items] == ["G1", "R1", "N1"]
    assert scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar() == head
    assert await pipeline.process_commit(repo, head) == []  # 같은 head → 아무것도 안 함
    # 밀린 커밋 셋에 같은 파일 → 버전 하나(최종 상태) · 미등록 작성자 → 자리표시 + author.unknown
    for n in (1, 2, 3):
        write_commit_push(
            other, PRD_FILE, PRD_BODY.replace("한 줄로.", f"{n}줄로."), f"spec: 수정 {n}"
        )
    head2 = g(remote, "rev-parse", "main")
    results = await pipeline.process_commit(repo, head2)
    assert [(r.doc_id, r.version_no) for r in results] == [("EXMP-PRD-001", 2)]
    d = svc.get_document("EXMP-PRD-001")
    assert (
        "3줄로." in d.body
        and d.has_convention_error
        and "author.unknown: seed" in d.convention_error_detail
    )
    seed = scoped.execute(
        text("SELECT github_user_id, display_name FROM users WHERE github_login='seed'")
    ).one()
    assert seed == (None, "seed")


async def test_process_commit_mismatched_filename_deleted_file_and_partial_failure(
    scoped: Session, proj
) -> None:
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other / RFQ_FILE).write_text(RFQ, encoding="utf-8")
    # 파일명 ≠ frontmatter doc_id (EXMP-PRD-002 파일에 EXMP-PRD-001 본문)
    (other / "docs/specs/02-PRD").mkdir(parents=True, exist_ok=True)
    (other / "docs/specs/02-PRD/EXMP-PRD-002.md").write_text(PRD_BODY, encoding="utf-8")
    g(other, "add", "-A")
    g(
        other,
        "commit",
        "-q",
        "--author=hoyoung <hoyoung@users.noreply.github.com>",
        "-m",
        "spec: 초안",
    )
    g(other, "push", "-q", "origin", "HEAD:main")
    results = await pipeline.process_commit(repo, g(remote, "rev-parse", "main"))
    assert sorted(r.doc_id for r in results) == ["EXMP-PRD-002", "EXMP-RFQ-001"]
    svc = SpecService(scoped)
    d = svc.get_document("EXMP-PRD-002")
    assert (
        d.has_convention_error
        and "frontmatter.doc_id: 파일명 EXMP-PRD-002" in d.convention_error_detail
    )
    # 파일 삭제 → 문서는 남고 draft + file.deleted, 항목 전부 삭제, 하위(PRD G1)에 끊어진 참조
    g(other, "rm", "-q", RFQ_FILE)
    g(
        other,
        "commit",
        "-q",
        "--author=hoyoung <hoyoung@users.noreply.github.com>",
        "-m",
        "spec: RFQ 삭제",
    )
    g(other, "push", "-q", "origin", "HEAD:main")
    head = g(remote, "rev-parse", "main")
    assert await pipeline.process_commit(repo, head) == []
    rfq = svc.get_document("EXMP-RFQ-001")
    assert (rfq.status, rfq.convention_error_detail, rfq.items) == (
        "draft",
        f"file.deleted: {head}",
        [],
    )
    assert scoped.execute(text("SELECT kind FROM flags")).scalars().all() == ["broken_ref"]
    assert scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar() == head
    # 되살리면 복구다 — 항목 ID가 item.reused 위반에 걸리면 안 된다 (#15, MS-002 미결 결정)
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other / RFQ_FILE).write_text(RFQ, encoding="utf-8")
    g(other, "add", "-A")
    g(
        other,
        "commit",
        "-q",
        "--author=hoyoung <hoyoung@users.noreply.github.com>",
        "-m",
        "spec(EXMP-RFQ-001): 되살림",
    )
    g(other, "push", "-q", "origin", "HEAD:main")
    back = g(remote, "rev-parse", "main")
    restored = await pipeline.process_commit(repo, back)
    assert [x.doc_id for x in restored] == ["EXMP-RFQ-001"]
    rfq = svc.get_document("EXMP-RFQ-001")
    assert (rfq.has_convention_error, rfq.convention_error_detail) == (False, None)
    assert {i.item_id for i in rfq.items} == {"Q1", "Q2"}
    # 본문에 다시 나타난 항목은 is_deleted가 풀린다 — 안 풀면 항목 조회가 410을 계속 던진다
    assert (
        scoped.execute(
            text("SELECT count(*) FROM items WHERE is_deleted AND document_id = :d"),
            {"d": rfq.id},
        ).scalar()
        == 0
    )
    # 한 파일 실패(알 수 없는 디렉터리) → 나머지는 처리, last_processed_commit 안 바뀜
    (other / "docs/specs/BOGUS").mkdir(parents=True, exist_ok=True)
    (other / "docs/specs/BOGUS/EXMP-BOGUS-001.md").write_text("# x\n", encoding="utf-8")
    (other / "docs/specs/02-PRD/EXMP-PRD-002.md").write_text(PRD_BODY + "\n", encoding="utf-8")
    g(other, "add", "-A")
    g(
        other,
        "commit",
        "-q",
        "--author=hoyoung <hoyoung@users.noreply.github.com>",
        "-m",
        "spec: 둘",
    )
    g(other, "push", "-q", "origin", "HEAD:main")
    head3 = g(remote, "rev-parse", "main")
    results = await pipeline.process_commit(repo, head3)
    assert [(r.doc_id, r.version_no) for r in results] == [("EXMP-PRD-002", 2)]
    # 한 파일이 실패하면 last_processed_commit이 안 나간다 — 직전 성공(되살림)에 머문다
    assert scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar() == back


# ── rebuild (B4, UC-S6) ──
def _push_history(other, remote):
    """RFQ v1 · PRD v1(→Q1) · PRD v2 · status 커밋(review) — 저장소에만. DB는 비어 있다."""
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other / PRD_FILE).parent.mkdir(parents=True, exist_ok=True)
    write_commit_push(other, RFQ_FILE, RFQ, "spec(EXMP-RFQ-001): 초안")
    write_commit_push(other, PRD_FILE, PRD_BODY, "spec(EXMP-PRD-001): 초안")
    write_commit_push(
        other, PRD_FILE, PRD_BODY.replace("한 줄로.", "두 줄로."), "spec(EXMP-PRD-001): 수정"
    )
    write_commit_push(
        other,
        PRD_FILE,
        PRD_BODY.replace("한 줄로.", "두 줄로.").replace("status: draft", "status: review"),
        "status(EXMP-PRD-001): draft → review",
    )
    return g(remote, "rev-parse", "main")


async def test_rebuild_restores_versions_references_and_keeps_flags(
    scoped: Session, proj, monkeypatch
) -> None:
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    head = _push_history(other, remote)
    r = await pipeline.rebuild("EXMP")
    # 시드 SYNC-PRD-001(repos 픽스처) + RFQ + PRD · 항목 G1·R1·N1·Q1·Q2 · 참조 R1→Q1, 문서 upstream · 버전 1+1+2
    assert (r.docs, r.items, r.references, r.versions) == (3, 5, 2, 4)
    # 커밋 작성자 seed는 미등록이라 세 문서 전부 author.unknown (#34). 시드는 frontmatter도 미완
    assert sorted(e["doc_id"] for e in r.convention_errors) == [
        "EXMP-PRD-001",
        "EXMP-RFQ-001",
        "SYNC-PRD-001",
    ]
    assert all("author.unknown: seed" in e["detail"] for e in r.convention_errors)
    svc = SpecService(scoped)
    prd = svc.get_document("EXMP-PRD-001")
    assert (prd.current_version_no, prd.status, "두 줄로." in prd.body) == (2, "review", True)
    assert [v.version_no for v in svc.list_versions("EXMP-PRD-001")] == [
        None,
        2,
        1,
    ]  # status 커밋은 Version 안 늘림
    assert (
        scoped.execute(
            text("SELECT count(*) FROM status_changes WHERE commit_hash IS NOT NULL")
        ).scalar()
        == 1
    )
    assert (
        scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 0
    )  # 7단계 해제
    assert scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar() == head
    # 플래그·댓글이 있는 상태에서 다시 → 그대로 남고 버전은 다시 3
    from app.core.tracking.service import TrackingService

    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    TrackingService(scoped).raise_broken(q1)
    scoped.commit()
    r2 = await pipeline.rebuild("EXMP")
    assert r2.versions == 4 and scoped.execute(text("SELECT count(*) FROM flags")).scalar() == 1
    assert svc.get_document("EXMP-PRD-001").current_version_no == 2
    # 중간 실패 → 롤백, DB는 재구축 전과 같음
    from app.infra import git as gitmod

    async def boom(workdir, path, ref="HEAD"):
        raise RuntimeError("읽기 실패")

    monkeypatch.setattr(gitmod, "read", boom)
    with pytest.raises(RebuildFailed):
        await pipeline.rebuild("EXMP")
    assert scoped.execute(text("SELECT count(*) FROM versions")).scalar() == 4
    assert scoped.execute(text('SELECT count(*) FROM "references"')).scalar() == 2


async def test_repo_status_and_rebuild_index(scoped: Session, proj) -> None:
    from app.core.project.service import ProjectService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    ps = ProjectService(scoped)
    st = (await ps.repo_status())[0]
    assert (st.code, st.last_processed_commit, st.behind_by) == ("EXMP", None, None)
    head = _push_history(other, remote)
    r = await ps.rebuild_index("EXMP")
    assert r.docs == 3
    st = (await ps.repo_status())[0]
    assert (st.last_processed_commit, st.behind_by) == (head, 0) and st.synced_at is not None
    write_commit_push(other, RFQ_FILE, RFQ + "\n", "spec: 하나 더")
    # repo_status는 DB만 읽는다(MS-001). 폴링이 재기 전까지는 밖의 push를 모른다
    assert (await ps.repo_status())[0].behind_by == 0
    with pytest.raises(NotFound):
        await ps.rebuild_index("NOPE")


async def test_process_commit_skips_commits_the_app_pushed_itself(scoped: Session, proj) -> None:
    """mcp 저장·상태 변경 커밋은 이미 기록돼 있다 — 폴링이 다시 저장하면 안 된다."""
    remote = proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    await create(proj, DocType.RFQ, RFQ)
    r = await create(proj)
    await pipeline.change_status("EXMP-PRD-001", "review", proj["user"], "검토")
    head = g(remote, "rev-parse", "main")
    assert await pipeline.process_commit(repo, head) == []
    d = SpecService(scoped).get_document("EXMP-PRD-001")
    assert (d.current_version_no, d.status) == (1, "review")
    assert scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar() == head
    assert r.doc_id == "EXMP-PRD-001"


async def test_save_resolves_missing_refs_waiting_for_this_document(scoped: Session, proj) -> None:
    """하위(PRD)가 먼저 저장돼 상위 참조가 미존재였다가 상위(RFQ)가 생기면 즉시 풀린다 (10a)."""
    await create(proj)  # PRD가 EXMP-RFQ-001#Q1을 참조 — 아직 없다
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 2
    await create(proj, DocType.RFQ, RFQ)
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 0


async def test_rebuild_fetch_failure_is_rebuild_failed(scoped: Session, proj, monkeypatch) -> None:
    from app.infra import git as gitmod

    async def boom(workdir):
        raise gitmod.GitError(["git", "fetch"], "could not read Username")

    monkeypatch.setattr(gitmod, "fetch", boom)
    with pytest.raises(RebuildFailed) as ei:
        await pipeline.rebuild("EXMP")
    assert "Username" in ei.value.extra["reason"]


async def test_process_commit_treats_directory_rename_as_modify_not_delete(
    scoped: Session, proj
) -> None:
    """디렉터리에 번호를 붙이면(STD-001 1.1) git이 rename으로 본다 — 삭제로 처리하면 안 된다."""
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    write_commit_push(other, RFQ_FILE, RFQ, "spec(EXMP-RFQ-001): 초안")
    await pipeline.process_commit(repo, g(remote, "rev-parse", "main"))
    svc = SpecService(scoped)
    assert svc.get_document("EXMP-RFQ-001").current_version_no == 1
    # 번호 없는 옛 경로로 옮긴다 — 파일명(doc_id)은 그대로
    (other / "docs/specs/RFQ").mkdir(parents=True, exist_ok=True)
    g(other, "mv", RFQ_FILE, "docs/specs/RFQ/EXMP-RFQ-001.md")
    g(other, "commit", "-q", "-m", "chore: 디렉터리 이동")
    g(other, "push", "-q", "origin", "HEAD:main")
    head = g(remote, "rev-parse", "main")
    r = await pipeline.process_commit(repo, head)
    assert [x.doc_id for x in r] == ["EXMP-RFQ-001"]
    d = svc.get_document("EXMP-RFQ-001")
    assert (d.current_version_no, d.status, len(d.items)) == (2, "draft", 2)  # 삭제 아님
    assert scoped.execute(text("SELECT count(*) FROM flags")).scalar() == 0
    assert "file.deleted" not in (d.convention_error_detail or "")


# ── #34 커밋 작성자를 계정으로 잇는다 ──
async def test_process_commit_marks_author_unknown_on_every_doc(scoped: Session, proj) -> None:
    """미등록 작성자가 문서 둘을 커밋하면 둘 다 author.unknown.

    판정이 「방금 자리표시를 만들었나」였을 때는 먼저 처리된 하나만 걸렸다 (#34).
    """
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    (other / RFQ_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other / RFQ_FILE).write_text(RFQ, encoding="utf-8")
    (other / PRD_FILE).write_text(PRD_BODY, encoding="utf-8")
    g(other, "add", "-A")
    g(other, "commit", "-q", "-m", "spec: RFQ·PRD 추가")  # 작성자 seed — 미등록
    g(other, "push", "-q", "origin", "HEAD:main")
    await pipeline.process_commit(repo, g(remote, "rev-parse", "main"))
    svc = SpecService(scoped)
    for doc_id in ("EXMP-RFQ-001", "EXMP-PRD-001"):
        d = svc.get_document(doc_id)
        assert d.has_convention_error and "author.unknown: seed" in d.convention_error_detail


async def test_rebuild_attributes_by_commit_email(scoped: Session, proj) -> None:
    """커밋 이메일을 등록하면 재구축이 그 사람에게 붙이고 author.unknown이 사라진다."""
    from app.core.account.service import AccountService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)
    AccountService(scoped).add_commit_email(proj["user"], "seed@example.com")
    scoped.flush()
    r = await pipeline.rebuild("EXMP")
    # 시드 문서만 남는다 — frontmatter 미완이지 작성자 때문이 아니다
    assert [e["doc_id"] for e in r.convention_errors] == ["SYNC-PRD-001"]
    assert "author.unknown" not in r.convention_errors[0]["detail"]
    assert (
        scoped.execute(
            text("SELECT count(*) FROM versions WHERE author_user_id <> :u"),
            {"u": proj["user"].id},
        ).scalar()
        == 0
    )


async def test_rebuild_reassigns_open_flag_to_new_author(scoped: Session, proj) -> None:
    """재구축이 열린 플래그의 담당자를 다시 계산한다 (MS-007 rebuild 7a).

    clear_index는 flags를 남기고 담당자는 만들 때 한 번만 정해진다 — 이게 없으면
    버전은 옮겨 가는데 플래그는 옛 자리표시를 계속 가리킨다 (#34).
    """
    from app.core.account.service import AccountService
    from app.core.tracking.service import TrackingService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)
    await pipeline.rebuild("EXMP")
    svc = SpecService(scoped)
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    TrackingService(scoped).raise_broken(q1)
    scoped.commit()
    placeholder = scoped.execute(
        text("SELECT assignee_user_id FROM flags WHERE resolved_at IS NULL")
    ).scalar()
    assert placeholder is not None and placeholder != proj["user"].id  # 자리표시가 담당
    AccountService(scoped).add_commit_email(proj["user"], "seed@example.com")
    scoped.commit()
    await pipeline.rebuild("EXMP")
    assert (
        scoped.execute(
            text("SELECT assignee_user_id FROM flags WHERE resolved_at IS NULL")
        ).scalar()
        == proj["user"].id
    )


# ── #35 끊어진 참조가 승인을 막는다 (읽을 때 계산) ──
async def test_missing_ref_blocks_approve_and_clears_when_target_arrives(
    scoped: Session, proj
) -> None:
    """미존재 참조는 컬럼이 아니라 읽을 때 센다.

    그래서 상대 문서가 들어오면 이 문서를 다시 저장하지 않아도 승인된다 (#35).
    """
    from app.core import queries
    from app.core.errors import StatusBlocked

    user = proj["user"]
    svc = SpecService(scoped)
    # RFQ 없이 PRD만 — R1이 EXMP-RFQ-001#Q1을 가리키는데 아직 없다
    await create(proj)
    assert svc.get_document("EXMP-PRD-001").incomplete_warnings == []  # 컬럼에는 안 들어간다
    assert "EXMP-RFQ-001#Q1" in (await queries.document_view("EXMP-PRD-001")).missing_refs
    with pytest.raises(StatusBlocked) as ei:
        await pipeline.change_status("EXMP-PRD-001", "approved", user, None, upstream_reviewed=True)
    assert "ref.missing: EXMP-RFQ-001#Q1" in ei.value.extra["warnings"]
    # review로는 간다 — 저장은 됐고 승인만 막힌다
    await pipeline.change_status("EXMP-PRD-001", "review", user, None)
    assert svc.get_document("EXMP-PRD-001").status == "review"
    # 상대 문서가 들어오면 resolve_missing이 풀고, PRD를 다시 저장하지 않아도 승인된다
    await create(proj, DocType.RFQ, RFQ)
    assert (await queries.document_view("EXMP-PRD-001")).missing_refs == []
    await pipeline.change_status("EXMP-PRD-001", "approved", user, None, upstream_reviewed=True)
    assert svc.get_document("EXMP-PRD-001").status == "approved"
