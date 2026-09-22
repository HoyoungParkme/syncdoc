"""SYNC-MS-007 테스트 관점 — save_pipeline (B1: mcp·github 경로) · change_status (B2·V 토글)."""

import asyncio
import re

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
from app.core.types import Author, AuthorKind, DocStatus, DocType, Entry
from tests.conftest import git as g
from tests.conftest import write_commit_push
from tests.core.account.test_service import make_user
from tests.core.reference.test_service import RFQ
from tests.core.spec.test_service import PRD

PRD_BODY = PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1")


@pytest.fixture
def proj(scoped: Session, repos: dict) -> dict:
    """프로젝트 EXMP + 작업 사본(repos['work']) + 에이전트 작성자."""
    u = make_user(scoped, login="hoyoung")
    p = Project(code="EXMP", name="예시", owner_user_id=u.id)  # 등록한 사람이 소유자 (카드 W)
    scoped.add(p)
    scoped.flush()
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
    assert (r.doc_id, r.version_no, r.status) == ("EXMP-RFQ-001", 1, "draft")
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
    assert r.version_no == 2 and "ref.broken: 1" in r.warnings
    # 그 항목을 가리키던 참조가 그 자리에서 미존재가 된다 — 플래그가 아니다 (MS-003 mark_missing)
    missing = scoped.execute(
        text('SELECT to_item_id, to_document_id, raw_target FROM "references" WHERE is_missing')
    ).all()
    assert missing == [(None, None, "EXMP-RFQ-001#Q1")]
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
    assert r.status == "draft"  # 완료 문서를 고치면 초안으로 (MS-002 save 6)
    assert (
        scoped.execute(text("SELECT count(*) FROM status_changes WHERE to_status='draft'")).scalar()
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
    body = PRD_BODY.replace("status: draft", "status: approved")
    r = await pipeline.save_pipeline(
        Entry.web_status,
        "EXMP-PRD-001",
        None,
        body,
        1,
        None,
        human,
        "status(EXMP-PRD-001): draft → approved\n\n이유",
        reason="이유",  # 커밋 메시지를 다시 파싱하지 않는다 (MS-002 apply_status 근거)
    )
    assert (r.version_no, r.status) == (1, "approved")
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


# ── change_status (pipeline — 검사 → web_status 저장. 초안 ⇄ 완료 토글, 카드 V) ──
async def test_write_paths_do_not_revert_unread_commits(scoped: Session, proj) -> None:
    """#137 — 저장소에 아직 안 읽은 커밋이 있어도 그 내용이 사라지지 않는다 (DEV-19).

    옛 구현은 DB의 current_body로 본문을 만들어 커밋했다. commit_push가 reset --hard 뒤에
    그것을 덮어쓰므로 push가 거부되지도 않고, 밀린 커밋이 통째로 되돌아갔다.
    """
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    await create(proj, DocType.RFQ, RFQ)
    await create(proj)
    user = proj["user"]
    g(other, "pull", "-q", "--rebase", "origin", "main")

    # 밖에서 한 줄 더한 뒤(앱은 아직 안 읽었다) 상태 토글
    ahead = PRD_BODY.replace("한 줄로.", "한 줄로. 밖에서 더한 문장.")
    write_commit_push(other, PRD_FILE, ahead, "spec(EXMP-PRD-001): 밖에서 수정")
    d = await pipeline.change_status("EXMP-PRD-001", "approved", user, None)

    pushed = g(remote, "show", f"main:{PRD_FILE}")
    assert "밖에서 더한 문장." in pushed  # 밀린 커밋의 내용이 살아 있다
    assert "status: approved" in pushed
    # 상태 커밋은 한 줄만 바꾼다 — 제목만 보던 테스트가 못 잡던 것 (DEV-19)
    assert g(remote, "show", "--numstat", "--format=", "main").split()[:2] == ["1", "1"]
    assert d.status == "approved"
    assert "밖에서 더한 문장." in SpecService(scoped).get_document("EXMP-PRD-001").body


async def test_read_pending_is_idempotent_and_skips_github_path(scoped: Session, proj) -> None:
    """읽을 것이 없으면 0이고 커밋도 안 생긴다. github 경로는 부르지 않는다(무한 재귀)."""
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    await create(proj)
    user = proj["user"]
    # 등록된 프로젝트 모양으로 — init_project가 첫 커밋 해시를 적어 둔다 (MS-001)
    proj["project"].repository.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    g(other, "pull", "-q", "--rebase", "origin", "main")
    write_commit_push(other, RFQ_FILE, RFQ, "spec(EXMP-RFQ-001): 밖에서 생성")

    assert await pipeline.read_pending("EXMP", user) == 1
    head = g(remote, "rev-parse", "main")
    assert await pipeline.read_pending("EXMP", user) == 0  # 멱등
    assert g(remote, "rev-parse", "main") == head  # 커밋이 안 생긴다
    assert SpecService(scoped).get_document("EXMP-RFQ-001").current_version_no == 1
    with pytest.raises(NotFound):
        await pipeline.read_pending("EXMP", make_user(scoped, login="stranger"))


async def test_revert_and_trash_do_not_revert_unread_commits(scoped: Session, proj) -> None:
    """되돌리기·휴지통도 쓰기 전에 읽는다 (DEV-19, #137)."""
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    await create(proj, DocType.RFQ, RFQ)
    await create(proj)
    user, author = proj["user"], proj["author"]
    await update(proj, "EXMP-PRD-001", PRD_BODY.replace("한 줄로.", "두 줄로."), 1)
    proj["project"].repository.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    g(other, "pull", "-q", "--rebase", "origin", "main")

    # 밖에서 **다른 문서**를 고친 뒤(앱은 아직 안 읽었다) 되돌리기
    write_commit_push(other, RFQ_FILE, RFQ + "\n밖에서 더한 줄.\n", "spec(EXMP-RFQ-001): 밖에서")
    await pipeline.revert("EXMP-PRD-001", 1, user)
    assert "밖에서 더한 줄." in g(remote, "show", f"main:{RFQ_FILE}")
    # 밀린 커밋을 읽었으니 그 문서가 DB에도 들어와 있다
    assert "밖에서 더한 줄." in SpecService(scoped).get_document("EXMP-RFQ-001").body

    # 휴지통도 같다
    g(other, "pull", "-q", "--rebase", "origin", "main")
    write_commit_push(
        other, PRD_FILE, PRD_BODY.replace("한 줄로.", "셋."), "spec(EXMP-PRD-001): 밖에서"
    )
    await pipeline.trash_document("EXMP-RFQ-001", author, confirm=True)
    assert "셋." in g(remote, "show", f"main:{PRD_FILE}")
    assert RFQ_FILE not in remote_files(proj["repos"])


async def test_change_status_commits_frontmatter_no_version(scoped: Session, proj) -> None:
    from app.core.errors import StatusBlocked

    await create(proj, DocType.RFQ, RFQ)
    r = await create(proj)
    svc = SpecService(scoped)
    user = proj["user"]
    # 완료로 — 상위 대조 없이, 다이얼로그 없이
    d = await pipeline.change_status("EXMP-PRD-001", "approved", user, "다 썼다")
    assert d.status == "approved" and d.current_version_no == 1
    assert (
        g(proj["repos"]["remote"], "log", "-1", "--format=%s", "main")
        == "status(EXMP-PRD-001): draft → approved"
    )
    row = scoped.execute(
        text("SELECT from_status, to_status, reason, commit_hash FROM status_changes")
    ).one()
    assert row[:3] == ("draft", "approved", "다 썼다") and row[3] == g(
        proj["repos"]["remote"], "rev-parse", "main"
    )
    assert (
        scoped.execute(
            text("SELECT count(*) FROM versions WHERE document_id=:d"), {"d": d.id}
        ).scalar()
        == 1
    )
    assert "status: approved" in svc.get_document("EXMP-PRD-001").body
    # 같은 상태로 다시 → 커밋 없음 (멱등)
    head = g(proj["repos"]["remote"], "rev-parse", "main")
    await pipeline.change_status("EXMP-PRD-001", "approved", user, None)
    assert g(proj["repos"]["remote"], "rev-parse", "main") == head
    # 초안으로 되돌리기 — 사유 없이. 막는 검사가 없다
    d2 = await pipeline.change_status("EXMP-PRD-001", "draft", user)
    assert d2.status == "draft" and "status: draft" in svc.get_document("EXMP-PRD-001").body
    # 미완성 경고가 있는 문서는 approved 불가 — 생성 직후부터 경고가 남는다 (MS-002 create 1단계)
    scn = await create(proj, DocType.SCN, "# 시나리오\n\n## 배경\n\n아직 항목이 없다.\n")
    assert "item.none" in scn.warnings
    assert "item.none" in svc.get_document(scn.doc_id).incomplete_warnings
    with pytest.raises(StatusBlocked) as ei:
        await pipeline.change_status(scn.doc_id, "approved", user, None)
    assert "item.none" in ei.value.extra["warnings"]
    # mcp 수정 저장에도 남는다 (MS-007 8단계, 모든 경로)
    body = svc.get_document(scn.doc_id).body + "\n한 줄 더.\n"
    r3 = await update(proj, scn.doc_id, body, 1)
    assert "item.none" in r3.warnings
    assert "item.none" in svc.get_document(scn.doc_id).incomplete_warnings
    with pytest.raises(StatusBlocked):
        await pipeline.change_status(scn.doc_id, "approved", user, None)
    assert r.doc_id == "EXMP-PRD-001"


async def test_convention_error_document_cannot_be_completed(scoped: Session, proj) -> None:
    """규약 오류 문서는 완료로 못 올린다 — 게이트는 혼자 써도 남는다 (MS-007 change_status 2a)."""
    from app.core.errors import StatusBlocked

    await create(proj, DocType.RFQ, RFQ)
    await create(proj)
    scoped.execute(
        text(
            "UPDATE documents SET has_convention_error=true,"
            " convention_error_detail='author.unknown: x' WHERE doc_id='EXMP-PRD-001'"
        )
    )
    with pytest.raises(StatusBlocked) as ei:
        await pipeline.change_status("EXMP-PRD-001", "approved", proj["user"], None)
    assert ei.value.extra["convention_error_detail"] == "author.unknown: x"
    assert SpecService(scoped).get_document("EXMP-PRD-001").status == "draft"


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
    # P1을 가리키던 참조가 미존재로 (카드 V — 플래그가 아니라 참조 행 자신)
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 1
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
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 1
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
    """RFQ v1 · PRD v1(→Q1) · PRD v2 · status 커밋(approved) — 저장소에만. DB는 비어 있다."""
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
        PRD_BODY.replace("한 줄로.", "두 줄로.").replace("status: draft", "status: approved"),
        "status(EXMP-PRD-001): draft → approved",
    )
    return g(remote, "rev-parse", "main")


async def test_rebuild_restores_versions_references_and_survives_rerun(
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
    assert (prd.current_version_no, prd.status, "두 줄로." in prd.body) == (2, "approved", True)
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
    # 다시 돌려도 같다 — 버전은 다시 4, 문서는 2
    r2 = await pipeline.rebuild("EXMP")
    assert r2.versions == 4
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
    user = proj["user"]
    st = (await ps.repo_status(user))[0]
    assert (st.code, st.last_processed_commit, st.behind_by) == ("EXMP", None, None)
    head = _push_history(other, remote)
    r = await ps.rebuild_index("EXMP", user)
    assert r.docs == 3
    # 재구축은 README를 먼저 새 판으로 커밋한다 — head가 그만큼 앞선다 (카드 AB)
    assert r.readme_updated is True
    new_head = g(remote, "rev-parse", "main")
    assert new_head != head
    st = (await ps.repo_status(user))[0]
    assert (st.last_processed_commit, st.behind_by) == (new_head, 0) and st.synced_at is not None
    # 앱이 README를 밀었으니 밖의 클론은 뒤처져 있다 — 받아 와야 push된다 (카드 AB)
    g(other, "pull", "-q", "--rebase", "origin", "main")
    write_commit_push(other, RFQ_FILE, RFQ + "\n", "spec: 하나 더")
    # repo_status는 DB만 읽는다(MS-001). 폴링이 재기 전까지는 밖의 push를 모른다
    assert (await ps.repo_status(user))[0].behind_by == 0
    with pytest.raises(NotFound):
        await ps.rebuild_index("NOPE", user)
    # 남의 프로젝트 — 없는 것과 같다. 관리 표에도 안 뜬다 (카드 W)
    stranger = make_user(scoped, login="stranger")
    with pytest.raises(NotFound) as ei:
        await ps.rebuild_index("EXMP", stranger)
    assert ei.value.extra == {"resource": "project", "id": "EXMP"}
    assert await ps.repo_status(stranger) == []


async def test_revert_can_restore_a_deleted_item(scoped: Session, proj) -> None:
    """#48 — 항목을 지운 뒤에도 그 이전 버전으로 되돌릴 수 있어야 한다."""
    from app.core.spec.service import SpecService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)
    await pipeline.rebuild("EXMP")
    svc = SpecService(scoped)
    d = svc.get_document("EXMP-RFQ-001")
    before = d.current_version_no
    assert [i.item_id for i in d.items] == ["Q1", "Q2"]

    # Q2를 지운다 (하위 참조가 있어 확인이 필요하다)
    body = d.body[: d.body.index("#### Q2")]
    await pipeline.save_pipeline(
        Entry.mcp,
        "EXMP-RFQ-001",
        None,
        body,
        before,
        None,
        proj["author"],
        "spec(EXMP-RFQ-001): Q2를 뺀다",
        changed_items=[],
        confirm_item_deletion=True,
    )
    assert [i.item_id for i in svc.get_document("EXMP-RFQ-001").items] == ["Q1"]

    # 지우기 전으로 되돌린다 — 예전에는 item.reused 로 영영 막혔다
    r = await pipeline.revert("EXMP-RFQ-001", before, proj["user"])

    assert r.version_no == before + 2
    assert [i.item_id for i in svc.get_document("EXMP-RFQ-001").items] == ["Q1", "Q2"]


async def test_agent_still_cannot_reuse_a_deleted_item_id(scoped: Session, proj) -> None:
    """#48 — 면제는 되돌리기 경로만이다. MCP 저장은 그대로 막힌다."""
    from app.core.errors import ConventionViolation
    from app.core.spec.service import SpecService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)
    await pipeline.rebuild("EXMP")
    svc = SpecService(scoped)
    d = svc.get_document("EXMP-RFQ-001")
    body = d.body[: d.body.index("#### Q2")]
    await pipeline.save_pipeline(
        Entry.mcp,
        "EXMP-RFQ-001",
        None,
        body,
        d.current_version_no,
        None,
        proj["author"],
        "spec(EXMP-RFQ-001): Q2를 뺀다",
        changed_items=[],
        confirm_item_deletion=True,
    )
    d2 = svc.get_document("EXMP-RFQ-001")

    with pytest.raises(ConventionViolation) as e:
        await pipeline.save_pipeline(
            Entry.mcp,
            "EXMP-RFQ-001",
            None,
            d2.body + "#### Q2 다른 뜻으로 재사용\n",
            d2.current_version_no,
            None,
            proj["author"],
            "spec(EXMP-RFQ-001): Q2 재사용",
            changed_items=[],
        )
    assert any(v["rule"] == "item.reused" for v in e.value.to_dict()["violations"])


async def test_editing_an_approved_doc_keeps_frontmatter_and_db_in_step(
    scoped: Session, proj
) -> None:
    """#47 — 자동 강등이 저장소에도 써져야 에이전트가 그 문서를 계속 고칠 수 있다."""
    from app.core.spec.service import SpecService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)
    await pipeline.rebuild("EXMP")
    svc = SpecService(scoped)
    # 승인 게이트(미완성 경고)를 우회해 상태만 만든다 — 여기서 보려는 것은 강등 경로다
    d0 = svc.get_document("EXMP-RFQ-001")
    approved_body = re.sub(
        r"^status: .*$", f"status: {DocStatus.approved}", d0.body, count=1, flags=re.M
    )
    await pipeline.save_pipeline(
        Entry.web_status,
        "EXMP-RFQ-001",
        None,
        approved_body,
        d0.current_version_no,
        None,
        proj["author"],
        "status(EXMP-RFQ-001): draft → approved",
        reason=None,
    )
    assert svc.get_document("EXMP-RFQ-001").status == DocStatus.approved

    d = svc.get_document("EXMP-RFQ-001")
    r = await pipeline.save_pipeline(
        Entry.mcp,
        "EXMP-RFQ-001",
        None,
        d.body + "\n<!-- 한 줄 -->\n",
        d.current_version_no,
        None,
        proj["author"],
        "spec(EXMP-RFQ-001): 한 줄",
        changed_items=[],
    )

    assert r.status == DocStatus.draft  # 자동 강등 (SEQ-1 6a)
    d2 = svc.get_document("EXMP-RFQ-001")
    assert d2.status == DocStatus.draft
    # **본문의 frontmatter도 같이 내려가야 한다** — 저장소가 진실이다 (STD-001 1.2)
    assert "status: draft" in d2.body and "status: approved" not in d2.body
    assert "status: draft" in g(remote, "show", "HEAD:docs/specs/01-RFQ/EXMP-RFQ-001.md")

    # 그래서 받은 본문을 그대로 되돌려줘도 막히지 않는다 (막히면 그 문서는 영영 못 고친다)
    r2 = await pipeline.save_pipeline(
        Entry.mcp,
        "EXMP-RFQ-001",
        None,
        d2.body + "<!-- 또 한 줄 -->\n",
        d2.current_version_no,
        None,
        proj["author"],
        "spec(EXMP-RFQ-001): 또",
        changed_items=[],
    )
    assert r2.version_no == d2.current_version_no + 1


async def test_github_edit_of_approved_doc_pushes_the_demotion(scoped: Session, proj) -> None:
    """#58 — #47이 고친 것은 mcp·되돌리기뿐이다. github는 커밋이 이미 저장소에 있어
    본문만 고쳐서는 저장소가 안 바뀌므로 6a에서 아예 빠져 있었고, 그래서 남이 승인 문서를
    push로 고치면 **DB=초안 · 저장소=approved**로 갈렸다. 이제 status 커밋을 하나 더 민다.

    그 해시를 StatusChange에 적는 것도 같이 본다 — 안 적으면 다음 폴링이 3a에서
    앱 커밋을 못 걸러 앱이 민 커밋을 남의 편집으로 다시 저장한다.
    """
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    svc = SpecService(scoped)
    await create(proj, DocType.RFQ, RFQ)
    # 승인 게이트(미완성 경고)를 우회해 상태만 만든다 — 여기서 보려는 것은 강등 경로다
    d0 = svc.get_document("EXMP-RFQ-001")
    await pipeline.save_pipeline(
        Entry.web_status,
        "EXMP-RFQ-001",
        None,
        re.sub(r"^status: .*$", f"status: {DocStatus.approved}", d0.body, count=1, flags=re.M),
        d0.current_version_no,
        None,
        proj["author"],
        "status(EXMP-RFQ-001): draft → approved",
        reason=None,
    )
    assert svc.get_document("EXMP-RFQ-001").status == DocStatus.approved
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()

    # 남이 저장소에서 직접 고쳐 push한다
    g(other, "pull", "-q", "--rebase")
    body = (other / RFQ_FILE).read_text(encoding="utf-8")
    assert "status: approved" in body
    head = write_commit_push(
        other, RFQ_FILE, body + "\n<!-- 밖에서 한 줄 -->\n", "spec(EXMP-RFQ-001): 밖에서 한 줄"
    )

    results = await pipeline.process_commit(repo, head)

    assert [(r.doc_id, r.status) for r in results] == [("EXMP-RFQ-001", DocStatus.draft)]
    d = svc.get_document("EXMP-RFQ-001")
    in_repo = g(remote, "show", f"main:{RFQ_FILE}")
    assert d.status == DocStatus.draft
    assert "status: draft" in in_repo, f"갈렸다 — DB={d.status} 저장소=approved"
    status_head = g(remote, "rev-parse", "main")
    assert g(remote, "log", "-1", "--format=%s", status_head) == (
        "status(EXMP-RFQ-001): approved → draft"
    )
    # 그 커밋이 StatusChange에 적혀 있어야 다음 폴링이 3a에서 걸러낸다
    rows = scoped.execute(
        text("SELECT reason, commit_hash FROM status_changes WHERE to_status='draft'")
    ).all()
    assert [(r.reason, r.commit_hash) for r in rows] == [("본문 수정으로 자동 강등", status_head)]
    assert await pipeline.process_commit(repo, status_head) == []
    assert svc.get_document("EXMP-RFQ-001").current_version_no == d.current_version_no


async def test_github_author_lowering_status_themselves_is_not_overridden(
    scoped: Session, proj
) -> None:
    """#58 — 같은 커밋에서 작성자가 frontmatter를 스스로 내렸으면 그게 원본의 진실이다.
    자동 강등이 status 커밋을 하나 더 밀면 안 된다 — 같은 값이어도 이력이 는다."""
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = _repo_row(proj)
    scoped.flush()
    svc = SpecService(scoped)
    await create(proj, DocType.RFQ, RFQ)
    d0 = svc.get_document("EXMP-RFQ-001")
    await pipeline.save_pipeline(
        Entry.web_status,
        "EXMP-RFQ-001",
        None,
        re.sub(r"^status: .*$", f"status: {DocStatus.approved}", d0.body, count=1, flags=re.M),
        d0.current_version_no,
        None,
        proj["author"],
        "status(EXMP-RFQ-001): draft → approved",
        reason=None,
    )
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()

    g(other, "pull", "-q", "--rebase")
    body = (other / RFQ_FILE).read_text(encoding="utf-8")
    head = write_commit_push(
        other,
        RFQ_FILE,
        re.sub(r"^status: .*$", "status: draft", body, count=1, flags=re.M) + "\n<!-- 한 줄 -->\n",
        "spec(EXMP-RFQ-001): 초안으로 되돌리며 수정",
    )

    await pipeline.process_commit(repo, head)

    assert svc.get_document("EXMP-RFQ-001").status == DocStatus.draft
    assert g(remote, "rev-parse", "main") == head  # status 커밋을 만들지 않는다


async def test_catch_up_records_fetch_error_and_a_good_round_clears_it(
    scoped: Session, proj
) -> None:
    """#46 — 폴링 실패를 로그로만 남기면 그 프로젝트는 조용히 멈춘다."""
    import shutil
    from pathlib import Path

    from app import scheduler
    from app.core.project.service import ProjectService

    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)
    repo = _repo_row(proj)
    good_workdir = repo.workdir_path

    # 작업 사본을 치워 fetch가 실패하게 한다 (원인은 무엇이든 좋다)
    broken = Path(good_workdir).parent / "gone"
    repo.workdir_path = str(broken)
    scoped.flush()
    scoped.commit()

    await scheduler.catch_up()  # 예외로 죽지 않는다

    scoped.expire_all()
    assert _repo_row(proj).fetch_error, "실패 사유가 DB에 남아야 한다"
    # 화면에도 올라간다. 여기서는 백업 읽기도 같은 이유로 실패해 그쪽 문구가 이긴다
    # (MS-001 — 둘 다 "이 저장소를 지금 못 보고 있다"는 같은 말이라 한 칸에 모은다)
    st = (await ProjectService(scoped).repo_status(proj["user"]))[0]
    assert st.error and "gone" in st.error

    # 고치면 다음 주기가 지운다
    shutil.rmtree(broken, ignore_errors=True)
    r = _repo_row(proj)
    r.workdir_path = good_workdir
    scoped.flush()
    scoped.commit()

    await scheduler.catch_up()

    scoped.expire_all()
    assert _repo_row(proj).fetch_error is None
    assert (await ProjectService(scoped).repo_status(proj["user"]))[0].error is None


async def test_process_commit_skips_commits_the_app_pushed_itself(scoped: Session, proj) -> None:
    """mcp 저장·상태 변경 커밋은 이미 기록돼 있다 — 폴링이 다시 저장하면 안 된다."""
    remote = proj["repos"]["remote"]
    repo = _repo_row(proj)
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    await create(proj, DocType.RFQ, RFQ)
    r = await create(proj)
    await pipeline.change_status("EXMP-PRD-001", "approved", proj["user"], "완료")
    head = g(remote, "rev-parse", "main")
    assert await pipeline.process_commit(repo, head) == []
    d = SpecService(scoped).get_document("EXMP-PRD-001")
    assert (d.current_version_no, d.status) == (1, "approved")
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
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 0
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


# ── #35 끊어진 참조가 완료를 막는다 (읽을 때 계산) ──
async def test_missing_ref_blocks_approve_and_clears_when_target_arrives(
    scoped: Session, proj
) -> None:
    """미존재 참조는 컬럼이 아니라 읽을 때 센다.

    그래서 상대 문서가 들어오면 이 문서를 다시 저장하지 않아도 완료된다 (#35).
    """
    from app.core import queries
    from app.core.errors import StatusBlocked

    user = proj["user"]
    svc = SpecService(scoped)
    # RFQ 없이 PRD만 — R1이 EXMP-RFQ-001#Q1을 가리키는데 아직 없다
    await create(proj)
    assert svc.get_document("EXMP-PRD-001").incomplete_warnings == []  # 컬럼에는 안 들어간다
    assert "EXMP-RFQ-001#Q1" in (await queries.document_view("EXMP-PRD-001", user)).missing_refs
    with pytest.raises(StatusBlocked) as ei:
        await pipeline.change_status("EXMP-PRD-001", "approved", user, None)
    assert "ref.missing: EXMP-RFQ-001#Q1" in ei.value.extra["warnings"]
    # 초안은 막히지 않는다 — 저장은 됐고 완료만 막힌다
    await pipeline.change_status("EXMP-PRD-001", "draft", user, None)
    assert svc.get_document("EXMP-PRD-001").status == "draft"
    # 상대 문서가 들어오면 resolve_missing이 풀고, PRD를 다시 저장하지 않아도 완료된다
    await create(proj, DocType.RFQ, RFQ)
    assert (await queries.document_view("EXMP-PRD-001", user)).missing_refs == []
    await pipeline.change_status("EXMP-PRD-001", "approved", user, None)
    assert svc.get_document("EXMP-PRD-001").status == "approved"


async def test_rebuild_twice_does_not_duplicate_status_changes(scoped: Session, proj) -> None:
    """status( 커밋이 있는 저장소를 두 번 재구축해도 상태 변경이 안 쌓인다 (#38)."""
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    _push_history(other, remote)  # 마지막이 status(EXMP-PRD-001): draft → approved
    await pipeline.rebuild("EXMP")
    once = scoped.execute(text("SELECT count(*) FROM status_changes")).scalar()
    assert once == 1
    await pipeline.rebuild("EXMP")
    assert scoped.execute(text("SELECT count(*) FROM status_changes")).scalar() == once


# ── 카드 R — 휴지통 (MS-007 trash·restore·purge_document) ──
async def test_trash_restore_purge_document(scoped: Session, proj) -> None:
    from app.core.errors import (
        DocumentDeletionNeedsConfirm,
        DocumentHasHistory,
        DocumentNotTrashed,
        DocumentTrashed,
    )

    remote = proj["repos"]["remote"]
    await create(proj, DocType.RFQ, RFQ)
    await create(proj)  # PRD R1 → RFQ#Q1
    a = proj["author"]
    svc = SpecService(scoped)
    # confirm 없이 → 끊어질 것을 담아 되묻는다. 막지 않는다
    with pytest.raises(DocumentDeletionNeedsConfirm) as ex:
        await pipeline.trash_document("EXMP-RFQ-001", a, confirm=False)
    assert ex.value.extra["inbound_refs"] == ["EXMP-PRD-001", "EXMP-PRD-001#R1"]
    assert (ex.value.extra["title"], ex.value.extra["version_count"]) == ("요구", 1)
    assert "docs/specs/01-RFQ/EXMP-RFQ-001.md" in remote_files(proj["repos"])
    # 남이 가리켜도 confirm이면 들어간다 — 하위 R1에 끊어진 참조
    before = g(remote, "rev-parse", "main")
    r = await pipeline.trash_document("EXMP-RFQ-001", a, confirm=True)
    assert r.broken_refs == 1 and "휴지통" in r.next_step
    assert g(remote, "log", "-1", "--format=%s", "main") == "spec(EXMP-RFQ-001): 휴지통"
    assert "docs/specs/01-RFQ/EXMP-RFQ-001.md" not in remote_files(proj["repos"])
    rfq = svc.get_document("EXMP-RFQ-001")
    assert rfq.trashed_at is not None and rfq.status == "draft" and rfq.items == []
    assert not rfq.has_convention_error  # 규약 오류가 아니라 휴지통
    assert (
        scoped.execute(
            text("SELECT count(*) FROM versions WHERE document_id=:d"), {"d": rfq.id}
        ).scalar()
        == 1
    )
    # 하위 R1의 참조가 미존재로 — raw_target은 남는다 (MS-003 mark_missing)
    assert scoped.execute(
        text('SELECT raw_target FROM "references" WHERE is_missing ORDER BY raw_target')
    ).scalars().all() == ["EXMP-RFQ-001#Q1"]  # 문서 단위 참조는 행이 남아 있어 그대로
    # 목록·단계에서 빠진다. 문서 조회는 된다
    assert [d.doc_id for d in svc.list_by_project(proj["project"].id)] == ["EXMP-PRD-001"]
    assert [d.doc_id for d in svc.list_trashed(proj["project"].id)] == ["EXMP-RFQ-001"]
    # 휴지통 문서는 다시 못 넣고, 저장·상태 변경이 막힌다
    with pytest.raises(DocumentTrashed):
        await pipeline.trash_document("EXMP-RFQ-001", a, confirm=True)
    with pytest.raises(DocumentTrashed):
        await update(proj, "EXMP-RFQ-001", RFQ, 1, changed_items=[])
    with pytest.raises(DocumentTrashed):
        await pipeline.change_status("EXMP-RFQ-001", DocStatus.approved, proj["user"], None)
    # 폴링은 휴지통 커밋의 D를 건너뛰고 나아간다
    repo = _repo_row(proj)
    repo.last_processed_commit = before
    scoped.flush()
    assert await pipeline.process_commit(repo, r.commit_hash) == []
    assert (
        scoped.execute(text("SELECT last_processed_commit FROM repositories")).scalar()
        == r.commit_hash
    )
    # 완전 삭제는 남이 가리키는 동안 막힌다 — 그런데 방금 미존재가 된 참조는 to_*가 비어
    # inbound에 안 잡힌다. 문서 단위 참조([[EXMP-RFQ-001]])는 to_document_id가 남아 잡힌다
    with pytest.raises(DocumentHasHistory) as ex2:
        await pipeline.purge_document("EXMP-RFQ-001", a)
    assert ex2.value.extra["inbound_refs"] == ["EXMP-PRD-001"]
    assert "flags" not in ex2.value.extra and "comments" not in ex2.value.extra
    # 되살리기 — 직전 본문으로 새 버전, 항목 복구, 미존재 참조가 다시 이어진다 (10a)
    r2 = await pipeline.restore_document("EXMP-RFQ-001", a)
    assert r2.version_no == 2
    rfq = svc.get_document("EXMP-RFQ-001")
    assert rfq.trashed_at is None and {i.item_id for i in rfq.items} == {"Q1", "Q2"}
    assert rfq.body.strip() == RFQ.strip()
    assert "docs/specs/01-RFQ/EXMP-RFQ-001.md" in remote_files(proj["repos"])
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 0
    assert [d.doc_id for d in svc.list_by_project(proj["project"].id)] == [
        "EXMP-RFQ-001",
        "EXMP-PRD-001",
    ]
    with pytest.raises(DocumentNotTrashed):
        await pipeline.restore_document("EXMP-RFQ-001", a)
    with pytest.raises(DocumentNotTrashed):
        await pipeline.purge_document("EXMP-RFQ-001", a)
    # 아무도 안 가리키는 PRD — 넣고, 완전히 지운다
    prd = svc.get_document("EXMP-PRD-001")
    await pipeline.trash_document("EXMP-PRD-001", a, confirm=True)
    await pipeline.purge_document("EXMP-PRD-001", a)
    for t in ("documents", "items", "versions", "status_changes", '"references"'):
        col = "id" if t == "documents" else ("from_document_id" if "ref" in t else "document_id")
        n = scoped.execute(text(f"SELECT count(*) FROM {t} WHERE {col}=:d"), {"d": prd.id}).scalar()
        assert n == 0, t
    assert (
        svc.issue_doc_id(proj["project"].id, "EXMP", DocType.PRD) == "EXMP-PRD-001"
    )  # 번호 재발급


# ── 저장이 끊어진 참조를 정리한다 (#70 — 카드 V에서 플래그 대신 참조 행 자신) ──
async def test_saving_a_fixed_reference_clears_the_missing_ref(scoped: Session, proj) -> None:
    await create(proj, DocType.RFQ, RFQ)
    await create(proj)  # PRD R1 → RFQ#Q1
    no_q1 = RFQ.replace("#### Q1 첫 요구\n내용\n", "")
    await update(proj, "EXMP-RFQ-001", no_q1, 1, confirm_item_deletion=True)

    def missing():
        return (
            scoped.execute(text('SELECT raw_target FROM "references" WHERE is_missing'))
            .scalars()
            .all()
        )

    assert missing() == ["EXMP-RFQ-001#Q1"]
    prd = SpecService(scoped).get_document("EXMP-PRD-001").body
    assert "[[EXMP-RFQ-001#Q1]]" in prd
    # 참조를 둔 채 다른 곳만 고치면 남는다
    await update(
        proj, "EXMP-PRD-001", prd.replace("한 줄로.", "한 줄로 정리."), 1, changed_items=[]
    )
    assert missing() == ["EXMP-RFQ-001#Q1"]
    # 참조를 지워 저장하면 참조 행이 사라진다 — extract가 없어진 참조를 지운다
    fixed = prd.replace("한 줄로.", "한 줄로 정리.").replace(
        "[[EXMP-RFQ-001#Q1]]", "요구 Q1(삭제됨)"
    )
    await update(proj, "EXMP-PRD-001", fixed, 2, changed_items=["R1"])
    assert missing() == []


# ── 카드 W — 소유 (MS-007 1단계 · get_owned) ──
async def test_human_paths_hide_someone_elses_project_but_github_path_does_not(
    scoped: Session, proj
) -> None:
    from app import scheduler

    await create(proj, DocType.RFQ, RFQ)
    await create(proj)
    stranger = make_user(scoped, login="stranger")
    s_author = Author(kind=AuthorKind.agent, user=stranger, instructed_by=stranger, via=Entry.mcp)
    # mcp 저장 — 없는 것과 같다. get의 없음과 같은 필드라 존재가 새지 않는다
    with pytest.raises(NotFound) as ei:
        await pipeline.save_pipeline(
            Entry.mcp, "EXMP-PRD-001", None, PRD_BODY + "\n", 1, None, s_author, "spec: 남"
        )
    assert ei.value.extra == {"resource": "project", "id": "EXMP"}
    for coro in (
        pipeline.change_status("EXMP-PRD-001", "approved", stranger, None),
        pipeline.revert("EXMP-PRD-001", 1, stranger),
        pipeline.trash_document("EXMP-PRD-001", s_author, confirm=True),
        pipeline.restore_document("EXMP-PRD-001", s_author),
        pipeline.purge_document("EXMP-PRD-001", s_author),
    ):
        with pytest.raises(NotFound):
            await coro
    assert SpecService(scoped).get_document("EXMP-PRD-001").current_version_no == 1
    # github 경로는 사람이 없는 배치 — 소유와 무관하게 들어온다
    other = proj["repos"]["other"]
    g(other, "pull", "-q", "origin", "main")
    head = write_commit_push(
        other, "docs/specs/02-PRD/EXMP-PRD-001.md", PRD_BODY + "\n", "spec: 밖에서"
    )
    await scheduler.catch_up()
    assert SpecService(scoped).get_document("EXMP-PRD-001").commit_hash == head
