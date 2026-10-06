"""SYNC-API-002 — MCP 도구 (B1 다섯). 인프로세스 Client(server). 인증은 test_auth, 여기서는 user 컨텍스트만."""

import json

from mcp import Client
from sqlalchemy.orm import Session

from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.types import DocType
from app.mcp import tools
from tests.core.account.test_service import make_user
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import PRD as PRD_BODY
from tests.core.spec.test_service import make_project


async def call(tool: str, **args):
    async with Client(tools.server) as c:
        r = await c.call_tool(tool, args)
    return r.is_error, json.loads(r.content[0].text)


def _seed(scoped: Session, a):
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    p.owner_user_id = a.user.id  # R12 — 도구를 부르는 사람이 소유자
    scoped.flush()
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
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
        "delete_document",
        "restore_document",
        "get_code_graph",  # 카드 AZ
        "upload_code",  # 카드 BB
        "change_status",  # 카드 BE
    }
    assert (
        "status-blocked" in names["change_status"] and "update_document" in names["change_status"]
    )
    assert "docs/specs/" in names["upload_code"] and "upload-too-large" in names["upload_code"]
    assert "호출하는 것" in names["get_code_graph"] and "graphify" in names["get_code_graph"]
    assert "document-deletion-needs-confirm" in names["delete_document"]
    assert (
        "휴지통" in names["delete_document"] and "document-not-trashed" in names["restore_document"]
    )
    assert names["get_template"].startswith("문서 타입의 템플릿과 작성 규약")
    # STD-001 1.8·2.6 — 도구 설명이 멈춤과 DOM 순서를 말한다
    assert (
        "next_step" in names["create_document"] and "precondition-unmet" in names["create_document"]
    )
    assert "next_step" in names["update_document"]


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
    # 항목마다 대상이 없는 참조의 raw_target (API-002 get_document). R1 → Q9는 아직 없다
    assert d["items"] == [
        {"item_id": "G1", "display_name": "목표", "missing_refs": []},
        {"item_id": "R1", "display_name": "기능", "missing_refs": ["EXMP-RFQ-001#Q9"]},
    ]
    assert d["prev_doc_id"] == "EXMP-RFQ-001" and d["next_doc_id"] is None
    err, it = await call("get_item", doc_id="EXMP-PRD-001", item_id="G1")
    assert not err and it["body"].startswith("#### G1 목표") and "flags" not in it
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
    assert by["PRD"]["docs"][0]["counts"] == {"broken_ref": 1}  # R1 → Q9 미존재
    assert by["UI"] == {"stage": 7, "doc_type": "UI", "status": None, "doc_count": 0, "docs": []}
    err, r = await call("list_documents", project_code="EXMP", stage=2)
    assert not err and [s["doc_type"] for s in r["stages"]] == ["PRD"]
    err, p = await call("list_documents", project_code="NOPE")
    assert err and p["type"] == "urn:syncdoc:not-found"


async def test_get_template_reads_the_project_own_std_document(
    scoped: Session, as_user, monkeypatch
) -> None:
    """#8 — 규약 문서 이름에도 프로젝트 코드가 들어간다 (STD-001 1.1)."""
    _seed(scoped, as_user)
    asked: list[str] = []

    async def spy(workdir, path):  # noqa: ANN001
        asked.append(path)
        raise tools.git.GitError(["git", "show"], "does not exist")

    monkeypatch.setattr(tools.git, "read", spy)
    err, t = await call("get_template", project_code="EXMP", doc_type="PRD")

    assert not err
    assert "docs/specs/STD/EXMP-STD-001.md" in asked
    assert "docs/specs/STD/SYNC-STD-001.md" not in asked
    # 템플릿은 저장소를 묻지 않는다 — 내장된 최신 것이 먼저다 (#94, 카드 X)
    assert "docs/specs/_templates/PRD.md" not in asked
    # 저장소에 없으면 싱크독 내장 사본으로 떨어진다 (STD-001 2.12)
    assert t["common_rules"] and t["template"]


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


async def test_get_template_by_subtype_gives_that_subtypes_rules(scoped: Session, as_user) -> None:
    """#114 — 서브타입을 주면 그 서브타입의 필수 절·항목 패턴·항목 블록·뼈대가 온다 (카드 AG).

    전에는 서브타입을 받을 자리가 없어 DOM의 필수 절이 늘 빈 배열이었고, 템플릿은 도메인
    모델 골격 하나라 그대로 쓴 클래스 명세·ERD가 반드시 미완성이 됐다.
    """
    make_project(scoped, "SYNC")
    err, t = await call("get_template", project_code="SYNC", doc_type="DOM", subtype="클래스")
    assert not err and t["subtype"] == "클래스"
    assert t["type_rules"]["required_sections"] == [
        "폴더 구조",
        "엔티티",
        "의존 관계",
        "설계 클래스",
        "미결사항",
    ]
    assert t["type_rules"]["item_patterns"] == ["[A-Z][A-Za-z]+"]
    assert "classDiagram" in t["type_rules"]["block_structure"]
    assert "## 1. 폴더 구조" in t["template"] and "title: 클래스 명세" in t["template"]

    err, t = await call("get_template", project_code="SYNC", doc_type="DOM", subtype="ERD")
    assert not err and t["type_rules"]["item_patterns"] == ["[a-z][a-z0-9_]+"]
    assert "컬럼 표" in t["type_rules"]["block_structure"]
    assert "#### documents" in t["template"]

    err, t = await call("get_template", project_code="SYNC", doc_type="API", subtype="MCP")
    assert not err
    assert t["type_rules"]["required_sections"] == ["규칙", "도구", "에이전트 순서", "미결사항"]
    assert "inputSchema" in t["type_rules"]["block_structure"]
    assert "## 3. 에이전트 순서" in t["template"]

    # UI는 두 서브타입의 필수 절이 같아 뼈대가 하나다 — 서브타입을 줘도 UI.md
    err, t = await call("get_template", project_code="SYNC", doc_type="UI", subtype="와이어프레임")
    assert not err and "### 배치" in t["template"]


async def test_get_template_without_subtype_lists_choices(scoped: Session, as_user) -> None:
    make_project(scoped, "SYNC")
    err, t = await call("get_template", project_code="SYNC", doc_type="DOM")
    assert not err and t["type_rules"]["required_sections"] == []
    assert t["subtypes"] == ["도메인", "클래스", "ERD"]
    assert "셋 중 하나를 고른다" in t["template"]  # 뼈대가 아니라 고르는 안내
    # 서브타입이 없는 타입은 subtypes가 없다
    err, t = await call("get_template", project_code="SYNC", doc_type="PRD")
    assert not err and "subtypes" not in t
    # 그 타입의 서브타입이 아니면 doc_type이 틀렸을 때와 같은 답
    err, p = await call("get_template", project_code="SYNC", doc_type="DOM", subtype="REST")
    assert err and p["type"] == "urn:syncdoc:not-found"


async def test_init_project_tool(scoped: Session, as_user, repos, tmp_path, monkeypatch) -> None:
    from app.config import settings
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
    gh = {"storage": "github"}
    err, r = await call("init_project", **gh, remote_url=str(bare), code="NEW", name="새")
    assert not err and r["code"] == "NEW" and len(r["stages"]) == 11
    assert r["storage"] == "github" and r["remote_url"] == str(bare)
    assert all(s["status"] is None and s["doc_count"] == 0 for s in r["stages"])
    # 규약·템플릿 사본은 안 넣는다 — README가 링크로 가리킨다 (카드 AB)
    tree = g(bare, "ls-tree", "-r", "--name-only", "main")
    assert "docs/specs/README.md" in tree and "_templates" not in tree
    err, p = await call("init_project", **gh, remote_url=str(bare), code="NEW", name="새")
    assert err and p["type"] == "urn:syncdoc:project-code-conflict"
    err, p = await call(
        "init_project", **gh, remote_url=str(repos["remote"]), code="EXST", name="n"
    )
    assert err and p["type"] == "urn:syncdoc:existing-specs" and p["doc_count"] == 1
    err, p = await call(
        "init_project",
        **gh,
        remote_url=str(repos["remote"]),
        code="EXST",
        name="n",
        import_existing=True,
    )
    assert not err and p["code"] == "EXST"
    assert next(s for s in p["stages"] if s["doc_type"] == "PRD")["doc_count"] == 1


async def test_init_project_tool_passes_visibility(
    scoped: Session, as_user, tmp_path, monkeypatch
) -> None:
    """카드 BS — private를 넘긴다. 빼면 서버 기본값(GITHUB_REPO_PRIVATE)."""
    from app.config import settings
    from app.infra import github
    from tests.conftest import git as g

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    seen: list[bool] = []

    async def fake_create(token, owner, name, private):
        seen.append(private)
        g(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / f"{name}.git"))
        return str(tmp_path / f"{name}.git")

    monkeypatch.setattr(github, "create_repo", fake_create)
    for code, extra in (("PUB", {"private": False}), ("DEF", {})):
        err, r = await call(
            "init_project",
            storage="github",
            remote_url=str(tmp_path / f"{code.lower()}.git"),
            code=code,
            name="x",
            create_repo=True,
            **extra,
        )
        assert not err, r
    assert seen == [False, True]


async def test_init_project_server_storage_and_storage_is_required(
    scoped: Session, as_user, tmp_path, monkeypatch
) -> None:
    """카드 BA — storage는 기본값이 없다. 서버 저장은 주소 없이 만들고 결과에도 주소가 없다."""
    from app.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    async with Client(tools.server) as c:  # storage 없음 → 도구 인자 검증에서 막힌다(JSON 아님)
        missing = await c.call_tool("init_project", {"code": "SRV", "name": "서버"})
    assert missing.is_error and "storage" in missing.content[0].text
    err, r = await call("init_project", storage="server", code="SRV", name="서버")
    assert not err and r["storage"] == "server" and r["remote_url"] is None
    monkeypatch.setattr(settings, "STORAGE_MODES", "github")
    err, p = await call("init_project", storage="server", code="SRVB", name="x")
    assert err and p["type"] == "urn:syncdoc:storage-unavailable" and p["enabled"] == ["github"]


def test_init_description_asks_first_only_when_both_modes_are_on() -> None:
    """API-002 init_project — 설명 끝 문장이 서버가 켠 방식으로 정해진다(RFQ Q7의 확인 절차)."""
    both = tools.init_description(["github", "server"])
    assert "사람에게 어느 쪽으로 할지 묻고" in both
    only = tools.init_description(["server"])
    assert "서버 저장만 쓴다" in only and 'storage="server"' in only and "묻지 않는다" in only
    assert "GitHub 저장만" in tools.storage_sentence(["github"])
    assert "저장 방식을 고른다" in (tools.server.instructions or "")
    assert "공개 여부는 private로 고르고, 빼면 비공개" in both  # 카드 BS


async def test_get_references_splits_upstream_downstream(scoped: Session, as_user) -> None:
    _seed(scoped, as_user)
    err, r = await call("get_references", doc_id="EXMP-PRD-001", item_id="G1")
    assert not err and (r["doc_id"], r["item_id"]) == ("EXMP-PRD-001", "G1")
    assert sorted((u["doc_id"], u["item_id"], u["is_missing"]) for u in r["upstream"]) == [
        ("EXMP-PRD-001", "R1", False),
        ("EXMP-RFQ-001", "Q1", False),
    ]
    assert r["downstream"] == [] and "flags" not in r
    err, r = await call("get_references", doc_id="EXMP-PRD-001", item_id="R1")
    assert not err and [(u["raw_target"], u["is_missing"]) for u in r["upstream"]] == [
        ("EXMP-RFQ-001#Q9", True)
    ]
    assert [(x["doc_id"], x["item_id"]) for x in r["downstream"]] == [("EXMP-PRD-001", "G1")]
    err, p = await call("get_references", doc_id="EXMP-PRD-001", item_id="R9")
    assert err and p["type"] == "urn:syncdoc:not-found"


async def test_other_owner_project_is_not_found(scoped: Session, as_user) -> None:
    """R12 — 발급자가 소유하지 않은 프로젝트는 도구 어디서나 not-found(project)다."""
    _seed(scoped, as_user)
    other = make_user(scoped, login="minjun")
    tok = tools.current_user_id.set(other.id)
    try:
        for tool, args in [
            ("list_documents", {"project_code": "EXMP"}),
            ("get_document", {"doc_id": "EXMP-PRD-001"}),
            ("get_item", {"doc_id": "EXMP-PRD-001", "item_id": "R1"}),
            ("get_references", {"doc_id": "EXMP-PRD-001", "item_id": "R1"}),
            ("get_template", {"project_code": "EXMP", "doc_type": "SCN"}),
            (
                "create_document",
                {"project_code": "EXMP", "doc_type": "SCN", "body": PRD_BODY, "message": "x"},
            ),
            ("delete_document", {"doc_id": "EXMP-PRD-001"}),
        ]:
            err, p = await call(tool, **args)
            assert err and p["type"] == "urn:syncdoc:not-found", tool
            assert (p["resource"], p["id"]) == ("project", "EXMP"), tool
    finally:
        tools.current_user_id.reset(tok)
    # 소유자에게는 그대로
    err, _ = await call("get_document", doc_id="EXMP-PRD-001")
    assert not err


async def test_get_code_graph(scoped: Session, as_user) -> None:
    """SYNC-API-002 get_code_graph — 코드 탭과 같은 대조(카드 AZ)."""
    from app.core.codegraph.service import CodeGraphService
    from tests.core.codegraph.test_queries import GRAPH, MS

    p = _seed(scoped, as_user)
    SpecService(scoped).create(p.id, "EXMP-MS-001", DocType.MS, MS, "h2", as_user, "spec: 테스트")
    err, v = await call("get_code_graph", doc_id="EXMP-MS-001", item_id="svc.save")
    assert not err and v["graph"] is None  # 아직 그래프가 없다
    CodeGraphService(scoped).save(p.id, "c" * 40, "server", GRAPH)
    err, v = await call("get_code_graph", doc_id="EXMP-MS-001", item_id="svc.save")
    assert not err and v["function"]["qual"] == "svc.save"
    assert [c["status"] for c in v["function"]["calls"]] == ["code_only", "spec_only", "same"]
    err, v = await call("get_code_graph", doc_id="NOPE-MS-001")
    assert err and v["type"] == "urn:syncdoc:not-found"


async def test_upload_code_tool_puts_code_in_a_server_project(
    scoped: Session, as_user, tmp_path, monkeypatch
) -> None:
    """카드 BB — 서버 저장 프로젝트에 코드를 커밋 하나로. GitHub 저장 프로젝트는 storage-mismatch."""
    from app.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    err, _ = await call("init_project", storage="server", code="UPT", name="올리기")
    assert not err
    err, r = await call(
        "upload_code",
        project_code="UPT",
        files=[{"path": "app/x.py", "content": "X = 1\n"}],
        message="code: x",
    )
    assert not err and r["changed"] and r["files"] == 1 and r["deleted"] == 0
    err, p = await call(
        "upload_code",
        project_code="UPT",
        files=[{"path": "docs/specs/01-RFQ/UPT-RFQ-001.md", "content": "x"}],
        message="m",
    )
    assert err and p["type"] == "urn:syncdoc:upload-path-refused"
