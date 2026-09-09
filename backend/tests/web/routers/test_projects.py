"""SYNC-API-001 3.3 — GET /api/projects · POST · GET /api/projects/{code} · GET /api/projects/{code}/docs."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.spec.service import SpecService
from app.core.types import DocType
from tests.conftest import git as g
from tests.core.spec.test_service import PRD, author, make_project
from tests.web.conftest import login


def test_projects_requires_session(client: TestClient) -> None:
    assert client.get("/api/projects").status_code == 401


def test_list_and_docs(client: TestClient, scoped: Session) -> None:
    login(client, scoped, "minjun")
    p = make_project(scoped, "EXMP")
    a = author(scoped)
    SpecService(scoped).create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    lst = client.get("/api/projects").json()
    assert [x["code"] for x in lst] == ["EXMP"] and len(lst[0]["stages"]) == 11
    prd = next(s for s in lst[0]["stages"] if s["doc_type"] == "PRD")
    assert (prd["status"], prd["doc_count"], prd["gate_warning"]) == ("draft", 1, False)
    assert lst[0]["counts"]["convention_errors"] == 0
    docs = client.get("/api/projects/EXMP/docs").json()
    assert [d["doc_id"] for d in docs] == ["EXMP-PRD-001"]
    assert docs[0]["counts"] == {"needs_check": 0, "broken_ref": 0, "unresolved_comments": 0}
    assert (
        docs[0]["last_author"]["user"]["github_login"] == "hoyoung"
        and docs[0]["last_author"]["via"] == "mcp"
    )
    assert client.get("/api/projects/EXMP/docs", params={"stage": 3}).json() == []
    assert client.get("/api/projects/EXMP/docs", params={"status": "bogus"}).status_code == 422
    r = client.get("/api/projects/NOPE/docs")
    assert r.status_code == 404 and r.json()["type"] == "urn:syncdoc:not-found"
    # 상세 (UI-4): 요약 + 문서 목록 + 최근 변경
    d = SpecService(scoped).get_document("EXMP-PRD-001")
    SpecService(scoped).apply_status(
        d, d.body.replace("status: draft", "status: review"), "c1", a.user, "검토"
    )
    det = client.get("/api/projects/EXMP").json()
    assert det["code"] == "EXMP" and [x["doc_id"] for x in det["docs"]] == ["EXMP-PRD-001"]
    assert [
        (v["doc_id"], v["version_no"], v["message"], v["author"]["kind"], v["author"]["via"])
        for v in det["recent_changes"]
    ] == [
        ("EXMP-PRD-001", None, "status(EXMP-PRD-001): draft → review", "human", "web"),
        ("EXMP-PRD-001", 1, "spec: 테스트", "agent", "mcp"),
    ]
    assert det["recent_changes"][0]["author"]["user"]["github_login"] == "hoyoung"
    assert client.get("/api/projects/NOPE").status_code == 404


def test_init_project_web_path(
    client: TestClient, scoped: Session, tmp_path, monkeypatch, repos
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    login(client, scoped)
    bare = tmp_path / "empty.git"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    g(tmp_path, "clone", "-q", str(bare), str(seed))
    g(seed, "checkout", "-q", "-b", "main")
    (seed / "README.md").write_text("x", encoding="utf-8")
    g(seed, "add", "README.md")
    g(seed, "commit", "-q", "-m", "init")
    g(seed, "push", "-q", "origin", "HEAD:main")
    r = client.post("/api/projects", json={"remote_url": str(bare), "code": "NEW", "name": "새"})
    assert r.status_code == 201 and r.json()["code"] == "NEW"
    assert all(s["status"] is None and s["doc_count"] == 0 for s in r.json()["stages"])
    assert (
        client.post(
            "/api/projects", json={"remote_url": str(bare), "code": "new", "name": "x"}
        ).status_code
        == 422
    )
    r = client.post("/api/projects", json={"remote_url": str(bare), "code": "NEW", "name": "x"})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:project-code-conflict"
    r = client.post(
        "/api/projects", json={"remote_url": str(repos["remote"]), "code": "EXST", "name": "x"}
    )
    assert (
        r.status_code == 409
        and r.json()["type"] == "urn:syncdoc:existing-specs"
        and r.json()["doc_count"] == 1
    )
    r = client.post(
        "/api/projects",
        json={
            "remote_url": str(repos["remote"]),
            "code": "EXST",
            "name": "x",
            "import_existing": True,
        },
    )
    assert (
        r.status_code == 201 and r.json()["code"] == "EXST"
    )  # import_existing → 재구축으로 가져온다
    prd = next(s for s in r.json()["stages"] if s["doc_type"] == "PRD")
    assert (
        prd["doc_count"] == 1 and r.json()["counts"]["convention_errors"] == 1
    )  # 시드 PRD는 frontmatter 미완
