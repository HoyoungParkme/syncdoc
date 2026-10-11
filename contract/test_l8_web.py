"""카드 L8 — 웹 읽기 (SYNC-SCN-001 S2·S3·S4·S6): 프로젝트 상세·문서 목록·문제 목록·관계도·첨부, 문서·이력·diff·추적표·
항목·참조·체인의 GET 경로.

MCP로 문서를 쌓고(파이썬 판과 같은 차례) REST로 읽어 응답 바이트를 파이썬 판의 것(스냅숏 `web_closed`)과 비교한다.
커밋 해시와 시각만 가린다 — 판마다 다르다. 코드는 두 판 차이 시험의 단어와 겹치지 않게 쓴다.
"""

from __future__ import annotations

import json
import re

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L8")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")

HASH = re.compile(r"\b[0-9a-f]{40}\b")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")


def masked(reply) -> dict:
    """비교할 꼴 — 커밋 해시와 시각은 판마다 다르다"""
    c = reply.contract()
    c["body"] = STAMP.sub("T", HASH.sub("H", c["body"]))
    return c


def chain_sorted(c: dict) -> dict:
    """체인 행 안의 차례는 파이썬 `set` 순회 차례 — 항목 pk 값에 매여 앞선 시험의 이력(판마다 다르다)에 따라 바뀐다.
    계약은 행 안을 정렬해 보고, 차례 자체는 core 단위 시험(`pycompat::pyset`, 파이썬에서 뜬 정답)이 본다"""
    if c["status"] != 200:
        return c
    data = json.loads(c["body"])
    for row in data["rows"]:
        row["items"].sort(
            key=lambda i: (i["ref"]["doc_id"] or "", i["ref"]["item_id"] or "", i["role"])
        )
    return {**c, "body": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}


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
    reply = request(server.port, "POST", "/mcp", hs, body)
    data = json.loads(reply.body.decode().split("data: ", 1)[1])
    return json.loads(data["result"]["content"][0]["text"])


PRD = (
    "# 웹 시험\n\n## 1. 목표\n\n#### G1 첫 목표\n한 줄.\n\n## 2. 비목표\n\n## 3. 요구사항\n\n"
    "#### R1 첫 기능\n설명.\n\n#### R2 둘째 기능\n설명.\n\n#### R3 외톨이\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n"
)
SCN = (
    "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LWA-PRD-001]\n---\n# 시나리오\n\n"
    "## 1. 페르소나\n\n#### P1 사람\n누구.\n\n## 2. 시나리오\n\n#### S1 첫 흐름\n근거: [[LWA-PRD-001#R1]] · [[LWA-PRD-001#R2]] · [[LWA-PRD-009#R1]]\n\n"
    "#### S2 둘째 흐름\n근거: [[LWA-PRD-001#R1]] · [[#P1]]\n\n## 3. 대응표\n\n표에서 [[LWA-PRD-001#R1]] · [[LWA-PRD-001]]\n"
)
UC = (
    "# 유스케이스\n\n## 1. 액터\n\n## 2. 사용자 목표 수준 유스케이스\n\n#### UC-A1 첫 일\n근거 [[LWA-SCN-001#S1]] · [[LWA-SCN-001#S2]]\n\n"
    "#### UC-A2 둘째 일\n근거 [[LWA-SCN-001#S1]]\n\n## 3. 하위기능 수준 유스케이스\n\n## 4. 대응표\n"
)


@pytest.fixture(scope="module")
def seeded(_servers):
    """두 판에 같은 프로젝트를 같은 차례로 — 만들고 고친 판까지(이력·diff가 쓴다)"""
    done = {}

    def seed(server):
        if server.target in done:
            return
        mcp(server, "init_project", {"storage": "server", "code": "LWA", "name": "웹 시험"})
        mcp(
            server,
            "create_document",
            {"project_code": "LWA", "doc_type": "PRD", "body": PRD, "message": "PRD"},
        )
        mcp(
            server,
            "create_document",
            {"project_code": "LWA", "doc_type": "SCN", "body": SCN, "message": "SCN"},
        )
        mcp(
            server,
            "create_document",
            {"project_code": "LWA", "doc_type": "UC", "body": UC, "message": "UC"},
        )
        body = mcp(server, "get_document", {"doc_id": "LWA-PRD-001"})["body"]
        edited = body.replace("#### R1 첫 기능\n설명.", "#### R1 첫 기능\n고친 설명.").replace(
            "## 5. 미결사항\n", "## 5. 미결사항\n\n#### R4 새것\n새.\n"
        )
        mcp(
            server,
            "update_document",
            {
                "doc_id": "LWA-PRD-001",
                "body": edited,
                "expected_version": 1,
                "message": "R1 고침",
                "changed_items": ["R1"],
            },
        )
        done[server.target] = True

    return seed


CASES = [
    ("detail", "/api/projects/LWA"),
    ("detail_missing", "/api/projects/NOPE"),
    ("docs", "/api/projects/LWA/docs"),
    ("docs_stage2", "/api/projects/LWA/docs?stage=2"),
    ("docs_stage_last_wins", "/api/projects/LWA/docs?stage=2&stage=3"),
    ("docs_stage0", "/api/projects/LWA/docs?stage=0"),
    ("docs_stage12", "/api/projects/LWA/docs?stage=12"),
    ("docs_stage_text", "/api/projects/LWA/docs?stage=abc"),
    ("docs_stage_empty", "/api/projects/LWA/docs?stage="),
    ("docs_status", "/api/projects/LWA/docs?status=draft"),
    ("docs_status_bad", "/api/projects/LWA/docs?status=review"),
    ("docs_two_errors", "/api/projects/LWA/docs?stage=99&status=x"),
    ("docs_plus_space", "/api/projects/LWA/docs?status=dr+aft"),
    ("docs_missing", "/api/projects/NOPE/docs"),
    ("flags_broken", "/api/projects/LWA/flags?kind=broken_ref"),
    ("flags_errors", "/api/projects/LWA/flags?kind=convention_errors"),
    ("flags_incomplete", "/api/projects/LWA/flags?kind=incomplete"),
    ("flags_no_kind", "/api/projects/LWA/flags"),
    ("flags_bad_kind", "/api/projects/LWA/flags?kind=x"),
    ("flags_missing", "/api/projects/NOPE/flags?kind=incomplete"),
    ("graph", "/api/projects/LWA/graph"),
    ("graph_approved", "/api/projects/LWA/graph?scope=approved"),
    ("graph_bad_scope", "/api/projects/LWA/graph?scope=APPROVED"),
    ("graph_missing", "/api/projects/NOPE/graph"),
    ("file_none", "/api/projects/LWA/files/assets/x.png"),
    ("file_outside", "/api/projects/LWA/files/../../../../etc/passwd.png"),
    ("file_outside_encoded", "/api/projects/LWA/files/..%2F..%2Fx.png"),
    ("file_markdown", "/api/projects/LWA/files/02-PRD/LWA-PRD-001.md"),
    ("file_readme", "/api/projects/LWA/files/README.md"),
    ("file_empty", "/api/projects/LWA/files/"),
    ("file_other_project", "/api/projects/NOPE/files/assets/x.png"),
    ("doc_prd", "/api/docs/LWA-PRD-001"),
    ("doc_scn", "/api/docs/LWA-SCN-001"),
    ("doc_missing", "/api/docs/LWA-PRD-404"),
    ("doc_other_project", "/api/docs/NOPE-PRD-001"),
    ("versions_prd", "/api/docs/LWA-PRD-001/versions"),
    ("versions_missing", "/api/docs/LWA-PRD-404/versions"),
    ("diff", "/api/docs/LWA-PRD-001/diff?from=1&to=2"),
    ("diff_back", "/api/docs/LWA-PRD-001/diff?from=2&to=1"),
    ("diff_same", "/api/docs/LWA-PRD-001/diff?from=2&to=2"),
    ("diff_no_query", "/api/docs/LWA-PRD-001/diff"),
    ("diff_zero", "/api/docs/LWA-PRD-001/diff?from=0&to=1"),
    ("diff_text", "/api/docs/LWA-PRD-001/diff?from=1&to=x"),
    ("diff_missing_version", "/api/docs/LWA-PRD-001/diff?from=1&to=9"),
    ("diff_huge_from", "/api/docs/LWA-PRD-001/diff?from=1000000000000&to=1"),
    ("diff_huge_to", "/api/docs/LWA-PRD-001/diff?from=1&to=1000000000000"),
    ("diff_missing_doc", "/api/docs/LWA-PRD-404/diff?from=1&to=2"),
    ("downstream_prd", "/api/docs/LWA-PRD-001/downstream"),
    ("downstream_scn", "/api/docs/LWA-SCN-001/downstream"),
    ("downstream_uc", "/api/docs/LWA-UC-001/downstream"),
    ("item_r1", "/api/docs/LWA-PRD-001/items/R1"),
    ("item_tilde", "/api/docs/LWA-PRD-001/items/R~1"),
    ("item_missing", "/api/docs/LWA-PRD-001/items/R9"),
    ("refs_r1", "/api/docs/LWA-PRD-001/items/R1/references"),
    ("refs_s1", "/api/docs/LWA-SCN-001/items/S1/references"),
    ("refs_missing", "/api/docs/LWA-SCN-001/items/S9/references"),
    ("chain_s1", "/api/docs/LWA-SCN-001/items/S1/chain"),
    ("chain_r1", "/api/docs/LWA-PRD-001/items/R1/chain"),
    ("chain_uc", "/api/docs/LWA-UC-001/items/UC-A1/chain"),
    ("chain_missing", "/api/docs/LWA-UC-001/items/UC-A9/chain"),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_web_reads(server, seeded, case):
    seeded(server)
    name, path = case
    got = masked(request(server.port, "GET", path))
    if name.startswith("chain_"):
        got = chain_sorted(got)
    check("web_closed", name, got, server.target)


def test_approved_scope_after_approval_reads_only_approved(server, seeded):
    """S6 — 완료로 올린 문서만 관계도 범위에 든다(완료는 웹 L9 — 여기서는 화면이 읽는 꼴만)"""
    seeded(server)
    g = json.loads(request(server.port, "GET", "/api/projects/LWA/graph?scope=approved").body)
    assert g["nodes"] == [] and g["edges"] == [] and g["project_name"] == "웹 시험"
    full = json.loads(request(server.port, "GET", "/api/projects/LWA/graph").body)
    assert any(n["isolated"] for n in full["nodes"]) and any(e["to"] is None for e in full["edges"])
