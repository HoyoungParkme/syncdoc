"""카드 L6 — 서버 저장 프로젝트 (SYNC-SCN-001 S5·S10 1~5): MCP `init_project`·`get_template`, REST 만들기·목록·지우기.

응답 바이트를 파이썬 판의 것(스냅숏 `projects_closed`)과 비교한다. 보관 시각(`archived_at`)만 가린다.
코드는 두 판 차이 시험의 단어(SYNC·PRD·DOM·MCP)와 겹치지 않게 쓴다 — 같은 세션에서 판마다 상태가 같아야 한다.
"""

from __future__ import annotations

import json
import re

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L6")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")


def masked(reply) -> dict:
    """비교할 꼴 — 보관 시각은 판마다 다르다"""
    c = reply.contract()
    c["body"] = re.sub(r'(\\?"archived_at\\?": ?\\?")[^"\\]+', r"\1T", c["body"])
    return c


def mcp(server, name: str, args: dict):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}},
        ensure_ascii=False,
    ).encode()
    hs = [("Authorization", f"Bearer {token_for(server)}"), ACCEPT, JSON]
    return request(server.port, "POST", "/mcp", hs, body)


def result(reply) -> dict:
    """SSE 한 사건의 CallToolResult"""
    data = json.loads(reply.body.decode().split("data: ", 1)[1])
    return data["result"]


MCP_CASES = [
    ("init_ok", "init_project", {"storage": "server", "code": "LSA", "name": "엘에스에이"}),
    ("init_dup", "init_project", {"storage": "server", "code": "LSA", "name": "다시"}),
    ("init_lower", "init_project", {"storage": "server", "code": "lsa", "name": "x"}),
    ("init_five", "init_project", {"storage": "server", "code": "LSABC", "name": "x"}),
    ("init_github", "init_project", {"storage": "github", "code": "LSB", "name": "x", "remote_url": "https://github.com/a/b"}),
    ("init_import_new", "init_project", {"storage": "server", "code": "LSC", "name": "가져오기", "import_existing": True}),
    ("tmpl_dom", "get_template", {"project_code": "LSA", "doc_type": "DOM"}),
    ("tmpl_dom_class", "get_template", {"project_code": "LSA", "doc_type": "DOM", "subtype": "클래스"}),
    ("tmpl_dom_erd", "get_template", {"project_code": "LSA", "doc_type": "DOM", "subtype": "ERD"}),
    ("tmpl_api_mcp", "get_template", {"project_code": "LSA", "doc_type": "API", "subtype": "MCP"}),
    ("tmpl_api_rest", "get_template", {"project_code": "LSA", "doc_type": "API", "subtype": "REST"}),
    ("tmpl_ui_wire", "get_template", {"project_code": "LSA", "doc_type": "UI", "subtype": "와이어프레임"}),
    ("tmpl_bad_type", "get_template", {"project_code": "LSA", "doc_type": "XYZ"}),
    ("tmpl_bad_subtype", "get_template", {"project_code": "LSA", "doc_type": "DOM", "subtype": "없음"}),
    ("tmpl_type_before_project", "get_template", {"project_code": "NOPE", "doc_type": "XYZ"}),
    ("tmpl_no_project", "get_template", {"project_code": "NOPE", "doc_type": "PRD"}),
] + [
    (f"tmpl_{t.lower()}", "get_template", {"project_code": "LSA", "doc_type": t})
    for t in ["RFQ", "PRD", "SCN", "UC", "INFRA", "UI", "API", "SEQ", "MS", "CODE", "STD"]
]


@pytest.mark.parametrize("case", MCP_CASES, ids=lambda c: c[0])
def test_mcp_tools(server, case):
    name, tool, args = case
    check("projects_closed", name, masked(mcp(server, tool, args)), server.target)


def test_init_project_made_a_server_repo(server):
    """S5 — 만든 프로젝트는 서버 저장, 11단계가 비어 있다(요약의 꼴)"""
    out = json.loads(result(mcp(server, "init_project", {"storage": "server", "code": "LSD", "name": "넷"}))["content"][0]["text"])
    assert (out["code"], out["storage"], out["remote_url"], out["updated_at"]) == ("LSD", "server", None, None)
    assert [s["doc_type"] for s in out["stages"]][:3] == ["RFQ", "PRD", "SCN"] and len(out["stages"]) == 11
    assert all(s["status"] is None and s["doc_count"] == 0 for s in out["stages"])


REST_CASES = [
    ("rest_create", "POST", "/api/projects", [JSON], {"storage": "server", "code": "LSR", "name": "레스트"}),
    ("rest_dup", "POST", "/api/projects", [JSON], {"storage": "server", "code": "LSR", "name": "다시"}),
    ("rest_bad_code", "POST", "/api/projects", [JSON], {"storage": "server", "code": "x1", "name": "x"}),
    ("rest_long_name", "POST", "/api/projects", [JSON], {"storage": "server", "code": "LSE", "name": "가" * 101}),
    ("rest_github", "POST", "/api/projects", [JSON], {"storage": "github", "code": "LSF", "name": "x"}),
    ("rest_no_storage", "POST", "/api/projects", [JSON], {"code": "LSG", "name": "x"}),
    ("rest_bad_storage", "POST", "/api/projects", [JSON], {"storage": "s3", "code": "LSG", "name": "x"}),
    ("rest_delete_missing", "DELETE", "/api/projects/NOPE", [], None),
    ("rest_delete", "DELETE", "/api/projects/LSR", [], None),
    ("rest_recreate_archived", "POST", "/api/projects", [JSON], {"storage": "server", "code": "LSR", "name": "다시"}),
    ("rest_template_after_delete", None, None, None, None),
]


@pytest.mark.parametrize("case", REST_CASES, ids=lambda c: c[0])
def test_rest(server, case):
    name, method, path, headers, body = case
    if method is None:  # 지운 프로젝트의 템플릿 — 없는 것과 같다
        reply = mcp(server, "get_template", {"project_code": "LSR", "doc_type": "PRD"})
    else:
        raw = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        reply = request(server.port, method, path, headers, raw)
    check("projects_closed", name, masked(reply), server.target)


def test_list_has_my_projects_in_summary_shape(server):
    listed = server.client().get("/api/projects")
    assert listed.status_code == 200 and listed.headers["content-type"] == "application/json"
    codes = [p["code"] for p in listed.json()]
    assert "LSA" in codes and "LSR" not in codes
    first = next(p for p in listed.json() if p["code"] == "LSA")
    assert list(first) == ["code", "name", "storage", "remote_url", "stages", "std_docs", "counts", "updated_at"]


@pytest.mark.card("L11")
def test_import_restores_archived_repo(server):
    """S10 6 — 보관본을 가져오기로 되살리고 재구축한다(파이썬 판). Rust는 카드 L11"""
    raw = json.dumps({"storage": "server", "code": "LSR", "name": "되살림", "import_existing": True}, ensure_ascii=False).encode()
    reply = request(server.port, "POST", "/api/projects", [JSON], raw)
    assert reply.status == 201, reply.body
