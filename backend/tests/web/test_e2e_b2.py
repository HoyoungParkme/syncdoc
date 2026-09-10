"""CODE-001 B2 E2E — SYNC-SCN-001#S2·S5 흐름 그대로.

민준이 웹에서 로그인 → 프로젝트 목록 → 문서 뷰 → 댓글 → 승인(상위 대조 포함) → 토큰 발급 → 그 토큰으로 MCP get_document.
GitHub OAuth는 모킹, 저장소는 임시 bare, MCP는 Bearer로 HTTP(/mcp) 초기화까지 + 인프로세스 도구 호출.
"""

import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from mcp import Client
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.account.service import AccountService
from app.core.types import DocType
from app.mcp import tools
from tests.conftest import git as g
from tests.conftest import github_ok
from tests.core.reference.test_service import RFQ
from tests.core.spec.test_service import PRD
from tests.core.test_pipeline import create

PRD_BODY = PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1")


async def test_s2_minjun_reads_comments_approves_and_connects_mcp(
    client: TestClient, scoped: Session, proj, mock_github
) -> None:
    # 에이전트(호영)가 미리 쌓아 둔 RFQ·PRD (B1 파이프라인)
    await create(proj, DocType.RFQ, RFQ)
    await create(proj, DocType.PRD, PRD_BODY)

    # 1. 민준이 GitHub로 로그인한다 (SEQ-8)
    mock_github(github_ok(77, "minjun", "김민준"))
    r = client.get(
        "/auth/github", params={"next": "/p/EXMP/d/EXMP-PRD-001"}, follow_redirects=False
    )
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get(
        "/auth/github/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert r.status_code == 302 and r.headers["location"] == "/p/EXMP/d/EXMP-PRD-001"
    assert client.get("/api/me").json()["github_login"] == "minjun"

    # 2. 프로젝트 목록 → 상세 문서 목록 (UI-2 → UI-4)
    projects = client.get("/api/projects").json()
    assert [p["code"] for p in projects] == ["EXMP"]
    prd_stage = next(s for s in projects[0]["stages"] if s["doc_type"] == "PRD")
    assert (prd_stage["status"], prd_stage["doc_count"]) == ("draft", 1)
    docs = client.get("/api/projects/EXMP/docs").json()
    assert [d["doc_id"] for d in docs] == ["EXMP-RFQ-001", "EXMP-PRD-001"]

    # 3. 문서 뷰 — 참조가 링크로, 항목 참조 패널 (UI-5, UC-H2·H3)
    doc = client.get("/api/docs/EXMP-PRD-001").json()
    assert doc["items"][1]["item_id"] == "R1" and doc["prev_doc_id"] == "EXMP-RFQ-001"
    refs = client.get("/api/docs/EXMP-PRD-001/items/R1/references").json()
    assert [(u["doc_id"], u["item_id"]) for u in refs["upstream"]] == [("EXMP-RFQ-001", "Q1")]

    # 4. 애매한 줄에 댓글 → 해결됨 (UC-H9)
    line_no = PRD_BODY.split("\n").index("#### R1 첫 기능") + 2
    c = client.post(
        "/api/docs/EXMP-PRD-001/comments", json={"line_no": line_no, "body": "이 줄이 애매하다"}
    ).json()
    assert c["author"]["github_login"] == "minjun"
    assert (
        next(
            d for d in client.get("/api/projects/EXMP/docs").json() if d["doc_id"] == "EXMP-PRD-001"
        )["counts"]["unresolved_comments"]
        == 1
    )
    assert client.post(f"/api/comments/{c['id']}/resolve").json()["is_resolved"] is True

    # 5. 승인 — 상위 대조를 거친다 (UC-H8 3). 상위 Q1이 어긋났다고 표시
    up = client.get("/api/docs/EXMP-PRD-001/upstream").json()
    assert ("EXMP-RFQ-001", "Q1") in [(u["target"]["doc_id"], u["target"]["item_id"]) for u in up]
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"})
    assert r.status_code == 422  # upstream_reviewed 없이는 못 간다
    r = client.post(
        "/api/docs/EXMP-PRD-001/status",
        json={
            "to": "approved",
            "upstream_reviewed": True,
            "upstream_mismatch": ["EXMP-RFQ-001#Q1"],
        },
    )
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert g(proj["repos"]["remote"], "log", "-1", "--format=%s%n%an", "main").split("\n") == [
        "status(EXMP-PRD-001): draft → approved",
        "김민준",
    ]
    flags = scoped.execute(text("SELECT kind, assignee_user_id FROM flags")).all()
    assert flags == [("upstream_impact", proj["user"].id)]  # 상위 담당 = RFQ 최근 작성자(호영)
    q1_refs = client.get("/api/docs/EXMP-RFQ-001/items/Q1/references").json()
    assert [(f["kind"], f["cause_version_no"]) for f in q1_refs["flags"]] == [
        ("upstream_impact", 1)
    ]

    # 6. 토큰 발급 → 7. 그 토큰으로 MCP (SEQ-C2). HTTP 인증 + 인프로세스 도구
    tok = client.post("/api/me/tokens", json={"label": "Codex"}).json()
    assert tok["token"].startswith("syncdoc_pat_")
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "codex", "version": "0"},
        },
    }
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    assert client.post("/mcp", json=init, headers=hdr).status_code == 401
    assert (
        client.post(
            "/mcp", json=init, headers={**hdr, "Authorization": f"Bearer {tok['token']}"}
        ).status_code
        == 200
    )
    user = AccountService(scoped).authenticate_token(tok["token"])
    assert user is not None and user.github_login == "minjun"
    ctx = tools.current_user_id.set(user.id)
    try:
        async with Client(tools.server) as mcp_client:
            r = await mcp_client.call_tool("get_document", {"doc_id": "EXMP-PRD-001"})
    finally:
        tools.current_user_id.reset(ctx)
    got = json.loads(r.content[0].text)
    assert (
        not r.is_error and got["status"] == "approved" and got["version_no"] == 1
    )  # 승인은 Version을 안 만든다
    assert got["items"][1]["item_id"] == "R1"
