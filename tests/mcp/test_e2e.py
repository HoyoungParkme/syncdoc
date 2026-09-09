"""CODE-001 B1 E2E — SYNC-SCN-001#S1 흐름 그대로.

에이전트가 init_project → create_document → get_document → update_document(버전 충돌·규약 위반·삭제 확인 세 갈래)
→ 저장소에 커밋이 있고 참조가 추출됨. GitHub 대신 임시 bare 저장소, MCP는 인프로세스 Client.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import git as g
from tests.core.reference.test_service import RFQ
from tests.core.spec.test_service import PRD
from tests.mcp.test_tools import call

PRD_BODY = PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1")


async def test_s1_agent_builds_specs_over_mcp(
    scoped: Session, as_user, tmp_path, monkeypatch
) -> None:
    from syncdoc.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    bare = tmp_path / "remote.git"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    g(tmp_path, "clone", "-q", str(bare), str(seed))
    g(seed, "checkout", "-q", "-b", "main")
    (seed / "README.md").write_text("새 프로젝트", encoding="utf-8")
    g(seed, "add", "README.md")
    g(seed, "commit", "-q", "-m", "init")
    g(seed, "push", "-q", "origin", "HEAD:main")

    # 1. "이 저장소로 싱크독 시작해줘" → 11단계 디렉터리·템플릿 커밋
    err, r = await call("init_project", remote_url=str(bare), code="EXMP", name="예시")
    assert not err and all(s["status"] is None for s in r["stages"])
    assert g(bare, "log", "-1", "--format=%s", "main") == "chore(EXMP): init syncdoc"

    # 3. "RFQ 써줘" → 규약대로 frontmatter 채워지고 초안 v1 커밋
    err, rfq = await call(
        "create_document",
        project_code="EXMP",
        doc_type="RFQ",
        body=RFQ.replace("doc_id: EXMP-RFQ-001", "doc_id: "),
        message="spec(RFQ): 첫 요구",
    )
    assert not err and (rfq["doc_id"], rfq["version_no"], rfq["status"]) == (
        "EXMP-RFQ-001",
        1,
        "draft",
    )
    assert rfq["pending_decision_version_id"] is None and "section.missing: 요구" in rfq["warnings"]

    # 4. PRD — RFQ를 읽고 [[EXMP-RFQ-001#Q1]] 참조
    err, doc = await call("get_document", doc_id="EXMP-RFQ-001")
    assert (
        not err and doc["body"].startswith("---\ndoc_id: EXMP-RFQ-001") and doc["version_no"] == 1
    )
    err, prd = await call(
        "create_document",
        project_code="EXMP",
        doc_type="PRD",
        body=PRD_BODY,
        message="spec(PRD): 목표·요구",
    )
    assert not err and prd["doc_id"] == "EXMP-PRD-001" and prd["warnings"] == []
    err, doc = await call("get_document", doc_id="EXMP-PRD-001")
    assert not err and [i["item_id"] for i in doc["items"]] == ["G1", "R1", "N1"]
    assert doc["last_author"] == {
        "kind": "agent",
        "user": "hoyoung",
        "instructed_by": "hoyoung",
        "via": "mcp",
    }

    # 수정 — 정상
    body2 = PRD_BODY.replace("한 줄로.", "한 줄로 정리.")
    err, r2 = await call(
        "update_document",
        doc_id="EXMP-PRD-001",
        body=body2,
        expected_version=1,
        message="spec(EXMP-PRD-001): G1 다듬기",
        changed_items=["G1"],
    )
    assert not err and r2["version_no"] == 2 and r2["status"] == "draft"

    # 갈래 1 — 버전 충돌: 현재 버전·본문이 담긴다
    err, p = await call(
        "update_document",
        doc_id="EXMP-PRD-001",
        body=body2 + "\n",
        expected_version=1,
        message="m",
        changed_items=[],
    )
    assert (
        err
        and p["type"] == "urn:syncdoc:version-conflict"
        and p["current_version"] == 2
        and p["current_body"] == body2
    )

    # 갈래 2 — 규약 위반: 저장 안 됨
    err, p = await call(
        "update_document",
        doc_id="EXMP-PRD-001",
        body=body2.replace("#### N1 성능", "#### N01 성능"),
        expected_version=2,
        message="m",
        changed_items=["N1"],
    )
    assert (
        err
        and p["type"] == "urn:syncdoc:convention-violation"
        and p["violations"][0]["rule"] == "item.padding"
    )

    # 갈래 3 — 항목 삭제 확인: RFQ의 Q1을 지우면 PRD R1이 참조 중
    no_q1 = RFQ.replace("#### Q1 첫 요구\n내용\n", "")
    err, p = await call(
        "update_document",
        doc_id="EXMP-RFQ-001",
        body=no_q1,
        expected_version=1,
        message="spec(EXMP-RFQ-001): Q1 삭제",
        changed_items=["Q1"],
    )
    assert (
        err
        and p["type"] == "urn:syncdoc:item-deletion-needs-confirm"
        and p["deleted_items"][0]["item_id"] == "Q1"
    )
    err, r3 = await call(
        "update_document",
        doc_id="EXMP-RFQ-001",
        body=no_q1,
        expected_version=1,
        message="spec(EXMP-RFQ-001): Q1 삭제",
        changed_items=["Q1"],
        confirm_item_deletion=True,
    )
    assert not err and r3["version_no"] == 2
    err, doc = await call("get_document", doc_id="EXMP-PRD-001")
    assert not err and {i["item_id"]: i["flags"] for i in doc["items"]}["R1"] == [
        "broken_ref"
    ]  # 끊어진 참조

    # 저장소에 커밋이 있고 참조가 추출됨
    subjects = g(bare, "log", "--format=%s", "main").split("\n")
    assert subjects[:5] == [
        "spec(EXMP-RFQ-001): Q1 삭제",
        "spec(EXMP-PRD-001): G1 다듬기",
        "spec(PRD): 목표·요구",
        "spec(RFQ): 첫 요구",
        "chore(EXMP): init syncdoc",
    ]
    tree = g(bare, "ls-tree", "-r", "--name-only", "main")
    assert (
        "docs/specs/02-PRD/EXMP-PRD-001.md" in tree and "docs/specs/01-RFQ/EXMP-RFQ-001.md" in tree
    )
    assert (
        g(bare, "log", "-1", "--format=%an <%ae>", "main")
        == "hoyoung <hoyoung@users.noreply.github.com>"
    )
    refs = scoped.execute(
        text('SELECT raw_target, is_missing FROM "references" ORDER BY raw_target')
    ).all()
    # 참조 행은 PRD를 다시 저장할 때까지 그대로(MS-003 6단계). 끊어짐은 broken_ref 플래그가 알린다
    assert ("EXMP-RFQ-001", False) in refs and ("EXMP-RFQ-001#Q1", False) in refs
    assert scoped.execute(text("SELECT is_deleted FROM items WHERE item_id='Q1'")).scalar() is True
    assert scoped.execute(text("SELECT count(*) FROM versions")).scalar() == 4
    err, lst = await call("list_documents", project_code="EXMP")
    assert not err and {s["doc_type"]: s["doc_count"] for s in lst["stages"] if s["doc_count"]} == {
        "RFQ": 1,
        "PRD": 1,
    }
