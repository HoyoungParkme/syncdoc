"""카드 L9 — 상태·되돌리기·휴지통 (SYNC-SCN-001 S2·S4): 웹 `POST …/status`·`…/revert`·`DELETE /api/docs/{id}`·
`…/restore`·`…/purge`와 MCP `change_status`·`delete_document`·`restore_document`.

차례대로 상태를 쌓으며 응답 바이트를 파이썬 판의 것(스냅숏 `write_closed`)과 비교한다. 커밋 해시와 시각만 가린다.
코드는 두 판 차이 시험의 단어와 겹치지 않게 쓴다.
"""

from __future__ import annotations

import json
import re

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L9")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")

HASH = re.compile(r"\b[0-9a-f]{40}\b")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")


def masked(reply) -> dict:
    """비교할 꼴 — 커밋 해시와 시각은 판마다 다르다"""
    c = reply.contract()
    c["body"] = STAMP.sub("T", HASH.sub("H", c["body"]))
    return c


def mcp(server, name: str, args: dict):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        ensure_ascii=False,
    ).encode()
    hs = [("Authorization", f"Bearer {token_for(server)}"), ACCEPT, JSON]
    return request(server.port, "POST", "/mcp", hs, body)


def text(reply) -> dict:
    data = json.loads(reply.body.decode().split("data: ", 1)[1])
    return json.loads(data["result"]["content"][0]["text"])


PRD = (
    "# 쓰기 시험\n\n## 1. 목표\n\n#### G1 목표\n한 줄.\n\n## 2. 비목표\n\n## 3. 요구사항\n\n"
    "#### R1 첫 기능\n설명.\n\n#### R2 둘째 기능\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n"
)
SCN = (
    "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LWB-PRD-001]\n---\n# 시나리오\n\n"
    "## 1. 페르소나\n\n#### P1 사람\n누구.\n\n## 2. 시나리오\n\n#### S1 첫 흐름\n근거: [[LWB-PRD-001#R1]] · [[LWB-PRD-001#R2]] · [[LWB-PRD-009#R1]]\n\n"
    "## 3. 대응표\n"
)


def prd_v1() -> str:
    return "---\ndoc_id: LWB-PRD-001\ntype: PRD\ntitle: 쓰기 시험\nstatus: draft\n---\n" + PRD


def rest(method: str, path: str, body=None):
    raw = (
        b""
        if body is None
        else (body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode())
    )
    return (method, path, [JSON] if body is not None else [], raw)


CASES = [
    ("init", "mcp", ("init_project", {"storage": "server", "code": "LWB", "name": "쓰기 시험"})),
    (
        "prd",
        "mcp",
        (
            "create_document",
            {"project_code": "LWB", "doc_type": "PRD", "body": PRD, "message": "PRD"},
        ),
    ),
    (
        "scn",
        "mcp",
        (
            "create_document",
            {"project_code": "LWB", "doc_type": "SCN", "body": SCN, "message": "SCN"},
        ),
    ),
    # 상태
    ("status_no_body", "rest", rest("POST", "/api/docs/LWB-PRD-001/status")),
    ("status_empty", "rest", rest("POST", "/api/docs/LWB-PRD-001/status", {})),
    ("status_bad_to", "rest", rest("POST", "/api/docs/LWB-PRD-001/status", {"to": "review"})),
    ("status_not_json", "rest", rest("POST", "/api/docs/LWB-PRD-001/status", b"{x")),
    (
        "status_approve",
        "rest",
        rest("POST", "/api/docs/LWB-PRD-001/status", {"to": "approved", "reason": "다 읽음"}),
    ),
    ("status_again", "rest", rest("POST", "/api/docs/LWB-PRD-001/status", {"to": "approved"})),
    (
        "status_missing_doc",
        "rest",
        rest("POST", "/api/docs/LWB-PRD-404/status", {"to": "approved"}),
    ),
    (
        "status_other_project",
        "rest",
        rest("POST", "/api/docs/NOPE-PRD-001/status", {"to": "approved"}),
    ),
    ("mcp_status_blocked", "mcp", ("change_status", {"doc_id": "LWB-SCN-001", "to": "approved"})),
    ("mcp_status_bad_to", "mcp", ("change_status", {"doc_id": "LWB-SCN-001", "to": "x"})),
    (
        "mcp_status_draft",
        "mcp",
        ("change_status", {"doc_id": "LWB-PRD-001", "to": "draft", "reason": "다시 볼 것"}),
    ),
    ("doc_after_status", "rest", rest("GET", "/api/docs/LWB-PRD-001")),
    ("versions_after_status", "rest", rest("GET", "/api/docs/LWB-PRD-001/versions")),
    # 되돌리기
    (
        "edit_v2",
        "mcp",
        (
            "update_document",
            {
                "doc_id": "LWB-PRD-001",
                "body": prd_v1().replace("설명.", "고친 설명.", 1),
                "expected_version": 1,
                "message": "고침",
                "changed_items": [],
            },
        ),
    ),
    ("revert_v1", "rest", rest("POST", "/api/docs/LWB-PRD-001/revert", {"to_version": 1})),
    ("revert_current", "rest", rest("POST", "/api/docs/LWB-PRD-001/revert", {"to_version": 3})),
    ("revert_zero", "rest", rest("POST", "/api/docs/LWB-PRD-001/revert", {"to_version": 0})),
    ("revert_missing", "rest", rest("POST", "/api/docs/LWB-PRD-001/revert", {"to_version": 9})),
    ("revert_huge", "rest", rest("POST", "/api/docs/LWB-PRD-001/revert", {"to_version": 10**12})),
    ("revert_no_body", "rest", rest("POST", "/api/docs/LWB-PRD-001/revert")),
    ("revert_missing_doc", "rest", rest("POST", "/api/docs/LWB-PRD-404/revert", {"to_version": 1})),
    ("diff_after_revert", "rest", rest("GET", "/api/docs/LWB-PRD-001/diff?from=2&to=3")),
    # 휴지통
    ("mcp_trash_ask", "mcp", ("delete_document", {"doc_id": "LWB-PRD-001"})),
    ("rest_trash_ask", "rest", rest("DELETE", "/api/docs/LWB-PRD-001")),
    ("rest_trash_bad_confirm", "rest", rest("DELETE", "/api/docs/LWB-PRD-001?confirm=maybe")),
    ("rest_trash", "rest", rest("DELETE", "/api/docs/LWB-PRD-001?confirm=true")),
    ("rest_trash_again", "rest", rest("DELETE", "/api/docs/LWB-PRD-001?confirm=1")),
    ("trash_list", "rest", rest("GET", "/api/projects/LWB/trash")),
    ("scn_broken", "rest", rest("GET", "/api/docs/LWB-SCN-001")),
    (
        "update_trashed",
        "mcp",
        (
            "update_document",
            {
                "doc_id": "LWB-PRD-001",
                "body": prd_v1(),
                "expected_version": 3,
                "message": "m",
                "changed_items": [],
            },
        ),
    ),
    ("status_trashed", "rest", rest("POST", "/api/docs/LWB-PRD-001/status", {"to": "approved"})),
    ("purge_has_history", "rest", rest("POST", "/api/docs/LWB-PRD-001/purge")),
    ("restore", "rest", rest("POST", "/api/docs/LWB-PRD-001/restore")),
    ("mcp_restore_again", "mcp", ("restore_document", {"doc_id": "LWB-PRD-001"})),
    ("scn_restored", "rest", rest("GET", "/api/docs/LWB-SCN-001")),
    ("purge_not_trashed", "rest", rest("POST", "/api/docs/LWB-PRD-001/purge")),
    ("mcp_trash_scn", "mcp", ("delete_document", {"doc_id": "LWB-SCN-001", "confirm": True})),
    ("purge_scn", "rest", rest("POST", "/api/docs/LWB-SCN-001/purge")),
    ("docs_after_purge", "rest", rest("GET", "/api/projects/LWB/docs")),
    (
        "scn_again",
        "mcp",
        (
            "create_document",
            {"project_code": "LWB", "doc_type": "SCN", "body": SCN, "message": "SCN 다시"},
        ),
    ),
    ("mcp_restore_missing", "mcp", ("restore_document", {"doc_id": "LWB-PRD-404"})),
    ("mcp_trash_missing", "mcp", ("delete_document", {"doc_id": "LWB-PRD-404", "confirm": True})),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_write_paths(server, case):
    name, kind, arg = case
    if kind == "mcp":
        tool, args = arg
        reply = mcp(server, tool, args)
    else:
        method, path, headers, body = arg
        reply = request(server.port, method, path, headers, body)
    check("write_closed", name, masked(reply), server.target)


def test_status_toggle_writes_frontmatter_only(server):
    """S2 — 완료로 올린 문서는 판이 그대로고 본문의 status 줄만 바뀐다"""
    d = text(mcp(server, "get_document", {"doc_id": "LWB-PRD-001"}))
    before = d["version_no"]
    mcp(server, "change_status", {"doc_id": "LWB-PRD-001", "to": "approved"})
    after = text(mcp(server, "get_document", {"doc_id": "LWB-PRD-001"}))
    assert after["status"] == "approved" and after["version_no"] == before
    assert after["body"] == d["body"].replace("status: draft", "status: approved", 1)
