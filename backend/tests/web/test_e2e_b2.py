"""CODE-001 B2 E2E — SYNC-SCN-001#S2·S5 흐름 그대로 (카드 V 뒤: 댓글·상위 대조 없음).

소유자(호영)가 웹에서 로그인 → 프로젝트 목록 → 문서 뷰 → 완료로 올림(토글) → 토큰 발급 → 그 토큰으로 MCP get_document.
카드 W 뒤: 프로젝트는 등록한 사람의 것이라 다른 계정(민준)에게는 보이지 않는다(R12).
GitHub OAuth는 모킹, 저장소는 임시 bare, MCP는 Bearer로 HTTP(/mcp) 초기화까지 + 인프로세스 도구 호출.
"""

import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from mcp import Client
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


async def test_s2_owner_reads_completes_and_connects_mcp(
    client: TestClient, scoped: Session, proj, mock_github
) -> None:
    # 에이전트(호영)가 미리 쌓아 둔 RFQ·PRD (B1 파이프라인)
    await create(proj, DocType.RFQ, RFQ)
    await create(proj, DocType.PRD, PRD_BODY)

    # 1. 소유자 호영이 GitHub로 로그인한다 (SEQ-8). 같은 GitHub 계정이라 User 행이 합쳐진다
    mock_github(github_ok(proj["user"].github_user_id, "hoyoung", "박호영"))
    r = client.get(
        "/auth/github", params={"next": "/p/EXMP/d/EXMP-PRD-001"}, follow_redirects=False
    )
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get(
        "/auth/github/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert r.status_code == 302 and r.headers["location"] == "/p/EXMP/d/EXMP-PRD-001"
    assert client.get("/api/me").json()["github_login"] == "hoyoung"

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

    # 4. 읽고 완료로 올린다 — 토글 하나, 다이얼로그 없음 (UC-H8). frontmatter 커밋은 소유자 이름으로
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert g(proj["repos"]["remote"], "log", "-1", "--format=%s%n%an", "main").split("\n") == [
        "status(EXMP-PRD-001): draft → approved",
        "박호영",
    ]
    # 5. 토글은 되돌아온다 — 완료 문서를 다시 초안으로
    assert (
        client.post("/api/docs/EXMP-PRD-001/status", json={"to": "draft"}).json()["status"]
        == "draft"
    )
    assert client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"}).status_code == 200

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
    assert user is not None and user.github_login == "hoyoung"
    ctx = tools.current_user_id.set(user.id)
    try:
        async with Client(tools.server) as mcp_client:
            r = await mcp_client.call_tool("get_document", {"doc_id": "EXMP-PRD-001"})
    finally:
        tools.current_user_id.reset(ctx)
    got = json.loads(r.content[0].text)
    assert (
        not r.is_error and got["status"] == "approved" and got["version_no"] == 1
    )  # 상태 변경은 Version을 안 만든다
    assert got["items"][1]["item_id"] == "R1"
