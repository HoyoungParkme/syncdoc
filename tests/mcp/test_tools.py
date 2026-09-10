"""SYNC-API-002 — MCP 도구 (B1 다섯). 인프로세스 Client(server). 인증은 test_auth, 여기서는 user 컨텍스트만."""

import json

from mcp import Client
from sqlalchemy.orm import Session

from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import DocType
from syncdoc.mcp import tools
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import make_project


async def call(tool: str, **args):
    async with Client(tools.server) as c:
        r = await c.call_tool(tool, args)
    return r.is_error, json.loads(r.content[0].text)


def _seed(scoped: Session, a):
    svc, ref, tr = SpecService(scoped), ReferenceService(scoped), TrackingService(scoped)
    p = make_project(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    tr.raise_broken(q1)
    return p


async def test_tools_listed_with_descriptions() -> None:
    async with Client(tools.server) as c:
        names = {t.name: t.description for t in (await c.list_tools()).tools}
    assert set(names) == {
        "init_project",
        "list_documents",
        "get_document",
        "get_item",
        "get_template",
        "get_references",
        "create_document",
        "update_document",
    }
    assert names["get_template"].startswith("문서 타입의 템플릿과 작성 규약")


async def test_get_document_and_get_item(scoped: Session, as_user) -> None:
    _seed(scoped, as_user)
    err, d = await call("get_document", doc_id="EXMP-PRD-001")
    assert not err
    assert (d["doc_id"], d["doc_type"], d["stage"], d["status"], d["version_no"]) == (
        "EXMP-PRD-001",
        "PRD",
        2,
        "draft",
        1,
    )
    assert d["commit_hash"] == "h1" and d["body"] == PRD and d["has_convention_error"] is False
    assert d["last_author"] == {
        "kind": "agent",
        "user": "hoyoung",
        "instructed_by": "hoyoung",
        "via": "mcp",
    }
    assert d["items"] == [
        {"item_id": "G1", "display_name": "목표", "flags": ["broken_ref"]},
        {"item_id": "R1", "display_name": "기능", "flags": []},
    ]
    assert d["prev_doc_id"] == "EXMP-RFQ-001" and d["next_doc_id"] is None
    err, it = await call("get_item", doc_id="EXMP-PRD-001", item_id="G1")
    assert not err and it["body"].startswith("#### G1 목표") and it["flags"] == ["broken_ref"]
    assert (it["doc_status"], it["doc_version_no"]) == ("draft", 1)


async def test_errors_are_problem_json(scoped: Session, as_user) -> None:
    _seed(scoped, as_user)
    err, p = await call("get_document", doc_id="EXMP-PRD-404")
    assert err and p["type"] == "urn:syncdoc:not-found" and p["status"] == 404
    err, p = await call("get_item", doc_id="EXMP-PRD-001", item_id="R9")
    assert err and p["type"] == "urn:syncdoc:not-found" and p["available_items"] == ["G1", "R1"]
    scoped.execute(
        __import__("sqlalchemy").text(
            "UPDATE items SET is_deleted=true, deleted_at=now() WHERE item_id='R1'"
        )
    )
    err, p = await call("get_item", doc_id="EXMP-PRD-001", item_id="R1")
    assert err and p["type"] == "urn:syncdoc:item-deleted" and p["deleted_at"]


async def test_unauthenticated_context_is_unauthorized(scoped: Session) -> None:
    err, p = await call("get_document", doc_id="X-PRD-001")
    assert err and p["type"] == "urn:syncdoc:unauthorized"


async def test_list_documents_grouped_by_stage(scoped: Session, as_user) -> None:
    _seed(scoped, as_user)
    err, r = await call("list_documents", project_code="EXMP")
    assert not err and r["project_code"] == "EXMP" and len(r["stages"]) == 11
    by = {s["doc_type"]: s for s in r["stages"]}
    assert by["RFQ"]["doc_count"] == 1 and by["RFQ"]["docs"][0]["doc_id"] == "EXMP-RFQ-001"
    assert by["PRD"]["docs"][0]["counts"] == {
        "needs_check": 0,
        "broken_ref": 1,
        "unresolved_comments": 0,
    }
    assert by["UI"] == {"stage": 7, "doc_type": "UI", "status": None, "doc_count": 0, "docs": []}
    err, r = await call("list_documents", project_code="EXMP", stage=2)
    assert not err and [s["doc_type"] for s in r["stages"]] == ["PRD"]
    err, p = await call("list_documents", project_code="NOPE")
    assert err and p["type"] == "urn:syncdoc:not-found"


async def test_get_template_rules_template_example(scoped: Session, as_user) -> None:
    make_project(scoped, "SYNC")  # workdir /w 는 없음 → 앱 내장 사본으로
    err, t = await call("get_template", project_code="SYNC", doc_type="PRD")
    assert not err and t["doc_type"] == "PRD"
    assert t["type_rules"]["item_patterns"] == ["G\\d+", "R\\d+", "N\\d+"]
    assert t["type_rules"]["required_sections"] == [
        "목표",
        "비목표",
        "요구사항",
        "성공지표",
        "미결사항",
    ]
    assert "인수기준" in t["type_rules"]["block_structure"]
    assert t["template"].startswith("---\ndoc_id:") and "type: PRD" in t["template"]
    assert (
        t["common_rules"].startswith("## 1. 공통 규약")
        and "표 행은 항목이 아니다" in t["common_rules"]
    )
    assert t["example"].startswith("## 5. 예시") and "EXMP-PRD-001" in t["example"]
    err, p = await call("get_template", project_code="SYNC", doc_type="NOPE")
    assert err and p["type"] == "urn:syncdoc:not-found"


async def test_init_project_tool(scoped: Session, as_user, repos, tmp_path, monkeypatch) -> None:
    from syncdoc.config import settings
    from tests.conftest import git as g

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    bare = tmp_path / "empty.git"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    g(tmp_path, "clone", "-q", str(bare), str(seed))
    g(seed, "checkout", "-q", "-b", "main")
    (seed / "README.md").write_text("x", encoding="utf-8")
    g(seed, "add", "README.md")
    g(seed, "commit", "-q", "-m", "init")
    g(seed, "push", "-q", "origin", "HEAD:main")
    err, r = await call("init_project", remote_url=str(bare), code="NEW", name="새")
    assert not err and r["code"] == "NEW" and len(r["stages"]) == 11
    assert all(s["status"] is None and s["doc_count"] == 0 for s in r["stages"])
    assert "docs/specs/_templates/RFQ.md" in g(bare, "ls-tree", "-r", "--name-only", "main")
    err, p = await call("init_project", remote_url=str(bare), code="NEW", name="새")
    assert err and p["type"] == "urn:syncdoc:project-code-conflict"
    err, p = await call("init_project", remote_url=str(repos["remote"]), code="EXST", name="n")
    assert err and p["type"] == "urn:syncdoc:existing-specs" and p["doc_count"] == 1
    err, p = await call(
        "init_project", remote_url=str(repos["remote"]), code="EXST", name="n", import_existing=True
    )
    assert not err and p["code"] == "EXST"
    assert next(s for s in p["stages"] if s["doc_type"] == "PRD")["doc_count"] == 1


async def test_get_references_splits_upstream_downstream_and_flags(
    scoped: Session, as_user
) -> None:
    _seed(scoped, as_user)
    err, r = await call("get_references", doc_id="EXMP-PRD-001", item_id="G1")
    assert not err and (r["doc_id"], r["item_id"]) == ("EXMP-PRD-001", "G1")
    assert sorted((u["doc_id"], u["item_id"], u["is_missing"]) for u in r["upstream"]) == [
        ("EXMP-PRD-001", "R1", False),
        ("EXMP-RFQ-001", "Q1", False),
    ]
    assert r["downstream"] == []
    assert [(f["kind"], f["cause"], f["cause_version_no"]) for f in r["flags"]] == [
        ("broken_ref", "EXMP-RFQ-001#Q1", None)
    ]
    err, r = await call("get_references", doc_id="EXMP-PRD-001", item_id="R1")
    assert not err and [(u["raw_target"], u["is_missing"]) for u in r["upstream"]] == [
        ("EXMP-RFQ-001#Q9", True)
    ]
    assert [(x["doc_id"], x["item_id"]) for x in r["downstream"]] == [("EXMP-PRD-001", "G1")]
    err, p = await call("get_references", doc_id="EXMP-PRD-001", item_id="R9")
    assert err and p["type"] == "urn:syncdoc:not-found"
