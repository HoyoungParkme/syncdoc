"""카드 L25·L26 — 흐름 보기 (SYNC-SCN-001 S12, UC-H24·UC-A11 · UI-19): 흐름 고정 저장소
(`local/crates/codegraph/tests/flow_fixture`)와 그 graph.json(정답 파일의 `flow_raw` — 파이썬 판 graphify 원형)을
두 판에 push하고, 클래스 명세의 층 표를 더해 `GET /api/projects/{code}/flow`(L25)와 MCP `get_flow`(L26)의 응답
바이트(흐름 키·층 표·대조·층)를 파이썬 판의 것(스냅숏 `flow`)과 비교한다. graph.json이 있으니 두 판이 같은
원형으로 그래프를 만든다 — 흐름 키는 두 판의 흐름 엔진이 같아야 같다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from snapshots import check
from test_l12_code import PRD, clone, masked, mcp, push, rest, wait_graph, write

pytestmark = pytest.mark.card("L25")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "local" / "crates" / "codegraph" / "tests" / "flow_fixture"
GOLDEN = ROOT / "local" / "crates" / "codegraph" / "tests" / "golden" / "codegraph.json"
CODE = "LFW"

MS = (
    "---\ndoc_id: {code}-MS-001\ntype: MS\ntitle: MINISPEC — items\nstatus: draft\nupstream: [{code}-DOM-001]\n---\n\n"
    "# MINISPEC\n\n## 1. 함수 목록\n\n## 2. 함수\n\n"
    "#### items.make 만들기\n\n근거: [[{code}-PRD-001#R1]]\n\n**호출하는 것** —\n\n"
    "## 3. 미결사항\n"
)
DOM = (
    "---\ndoc_id: {code}-DOM-001\ntype: DOM\ntitle: 클래스 명세 — 흐름 시험\nstatus: draft\nupstream: []\n---\n"
    "# 클래스 명세\n\n## 1. 폴더 구조\n\n| 경로 | 층 | 명세 |\n|---|---|---|\n"
    "| `backend/app/api/**` | 라우터 | [[{code}-MS-001]] · API |\n"
    "| `backend/app/core/**` | 서비스 | [[{code}-MS-001]] 2장 |\n"
    "| `frontend/**` | 화면 | [[{code}-PRD-001]] |\n| `server/*.ts` | 노드 서버 | 없음 |\n\n## 2. 클래스\n"
)


def fixture(work: Path) -> None:
    for f in sorted(FIXTURE.rglob("*")):
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            # 파일 끝 함수에 항목 docstring — 뒤에 다른 함수가 없어 graph.json의 줄이 그대로다
            text = text.replace("def make(payload: dict):\n", f'def make(payload: dict):\n    """{CODE}-MS-001#items.make"""\n')
            write(work, f.relative_to(FIXTURE).as_posix(), text)
    raw = json.loads(GOLDEN.read_text(encoding="utf-8"))["flow_raw"]
    write(work, "graphify-out/graph.json", json.dumps(raw, ensure_ascii=False, indent=1) + "\n")
    write(work, f"docs/specs/02-PRD/{CODE}-PRD-001.md", PRD.replace("LCG-", f"{CODE}-"))
    write(work, f"docs/specs/10-MS/{CODE}-MS-001.md", MS.format(code=CODE))
    write(work, f"docs/specs/06-DOM/{CODE}-DOM-001.md", DOM.format(code=CODE))


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    done: dict[str, dict] = {}

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        tmp = tmp_path_factory.mktemp(f"l25-{server.target}")
        (tmp / "client-gitconfig").write_text("")
        mcp(server, "init_project", {"storage": "server", "code": CODE, "name": "흐름 시험"})
        got["flow_none"] = rest(server, "GET", f"/api/projects/{CODE}/flow")
        got["mcp_none"] = mcp(server, "get_flow", {"project_code": CODE, "function": "x.py:1"})
        work = clone(server, tmp, CODE)
        fixture(work)
        head = push(server, CODE, work, "흐름 고정 저장소")
        wait_graph(server, CODE, lambda g: g["commit_hash"] == head and g["source"] == "repo")
        got["flow"] = rest(server, "GET", f"/api/projects/{CODE}/flow")
        got["flow_other_project"] = rest(server, "GET", "/api/projects/NOPE/flow")
        fns = json.loads(got["flow"].body)["functions"]
        read = next(f["key"] for f in fns if f["name"] == "read")
        got["mcp_key"] = mcp(server, "get_flow", {"project_code": CODE, "function": read})
        got["mcp_item"] = mcp(
            server, "get_flow", {"project_code": CODE, "function": f"{CODE}-MS-001#items.make"}
        )
        got["mcp_missing"] = mcp(server, "get_flow", {"project_code": CODE, "function": "nope.py:9"})
        done[server.target] = got
        return got

    return run


@pytest.mark.parametrize("key", ["flow_none", "flow", "flow_other_project"])
def test_flow_replies(server, flow, key):
    check("flow", key, masked(flow(server)[key]), server.target)


@pytest.mark.card("L26")
@pytest.mark.parametrize("key", ["mcp_none", "mcp_key", "mcp_item", "mcp_missing"])
def test_get_flow_replies(server, flow, key):
    check("flow", key, masked(flow(server)[key]), server.target)


def test_flow_keys_are_there(server, flow):
    """흐름 키 — 라우트·호출 순서·화면 요청·장비·실행 단위가 그래프에서 온다"""
    v = json.loads(flow(server)["flow"].body)
    assert {"files", "functions", "calls", "http", "infra", "units", "layers", "communities"} <= set(v)
    assert any(f["route"] for f in v["functions"]) and any(f["steps"] for f in v["functions"])
    assert v["http"] and v["units"] and v["infra"]["nodes"]
    assert [r["doc"] for r in v["layers"]] == [f"{CODE}-DOM-001"] * 4
