"""카드 L13 — 코드 그래프 노드 (SYNC-SCN-001 S9, UC-H20 · UI-17): L12의 고정 저장소(`tests/l12`)와 그 graph.json을
두 판에 push하고, 클래스 명세의 층 표와 graph.json에 없는 파일(보강이 더한 함수 — 커뮤니티 없음)을 더해
`GET /api/projects/{code}/code-graph`의 응답 바이트(커뮤니티 번호·라벨·대조 상태·층)를 파이썬 판의 것(스냅숏
`nodes_closed`)과 비교한다. graph.json이 없는 프로젝트는 원형을 판마다 뽑아 커뮤니티가 다를 수 있어 꼴만 본다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from snapshots import check
from test_l12_code import (
    FIXTURE,
    MS,
    PRD,
    clone,
    masked,
    mcp,
    push,
    rest,
    wait_graph,
    write,
)

pytestmark = pytest.mark.card("L13")

CODE = "LCN"
BARE = "LCM"

DOM = (
    "---\ndoc_id: {code}-DOM-001\ntype: DOM\ntitle: 클래스 명세 — 계약 시험\nstatus: draft\nupstream: []\n---\n"
    "# 클래스 명세\n\n## 1. 폴더 구조\n\n| 경로 | 층 | 명세 |\n|---|---|---|\n"
    "| `app/tool.py` | 도구 | [[{code}-MS-001]] 2장 · 손으로 고친다 |\n"
    "| `web/*.ts` | 화면 | [[{code}-PRD-001]] |\n| `nowhere/**` | 빈 층 | 없음 |\n\n## 2. 클래스\n"
)
TOOL = "def tidy(x):\n    return x.strip()\n\n\ndef again(x):\n    return tidy(tidy(x))\n"


def fixture(work: Path, code: str, with_graph: bool) -> None:
    """고정 저장소를 그 프로젝트의 항목 ID로 — graph.json 안의 docstring 노드까지"""
    for f in sorted(FIXTURE.rglob("*")):
        rel = f.relative_to(FIXTURE)
        if f.is_dir() or (not with_graph and rel.parts[0] == "graphify-out"):
            continue
        write(work, rel.as_posix(), f.read_text(encoding="utf-8").replace("LCG-", f"{code}-"))


def specs(work: Path, code: str) -> None:
    write(work, f"docs/specs/02-PRD/{code}-PRD-001.md", PRD.replace("LCG-", f"{code}-"))
    ms = MS.format(code=code).replace("upstream: []", f"upstream: [{code}-DOM-001]")
    write(work, f"docs/specs/10-MS/{code}-MS-001.md", ms)
    write(work, f"docs/specs/06-DOM/{code}-DOM-001.md", DOM.format(code=code))
    write(work, "app/tool.py", TOOL)


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    done: dict[str, dict] = {}

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        tmp = tmp_path_factory.mktemp(f"l13-{server.target}")
        (tmp / "client-gitconfig").write_text("")
        mcp(server, "init_project", {"storage": "server", "code": CODE, "name": "노드 시험"})
        got["graph_none"] = rest(server, "GET", f"/api/projects/{CODE}/code-graph")
        work = clone(server, tmp, CODE)
        fixture(work, CODE, with_graph=True)
        specs(work, CODE)
        head = push(server, CODE, work, "명세·코드·graph.json")
        wait_graph(server, CODE, lambda g: g["commit_hash"] == head and g["source"] == "repo")
        got["nodes"] = rest(server, "GET", f"/api/projects/{CODE}/code-graph")
        got["nodes_other_project"] = rest(server, "GET", "/api/projects/NOPE/code-graph")
        got["item_get"] = rest(server, "GET", f"/api/docs/{CODE}-MS-001/items/svc.get/code")
        got["calls"] = rest(server, "GET", f"/api/projects/{CODE}/code-calls")
        # graph.json 없는 프로젝트 — 판마다 뽑는다
        mcp(server, "init_project", {"storage": "server", "code": BARE, "name": "노드 뽑기"})
        bare = clone(server, tmp, BARE)
        fixture(bare, BARE, with_graph=False)
        specs(bare, BARE)
        head = push(server, BARE, bare, "코드만")
        wait_graph(server, BARE, lambda g: g["commit_hash"] == head)
        got["bare"] = json.loads(rest(server, "GET", f"/api/projects/{BARE}/code-graph").body)
        done[server.target] = got
        return got

    return run


KEYS = ["graph_none", "nodes", "nodes_other_project", "item_get", "calls"]


@pytest.mark.parametrize("key", KEYS)
def test_nodes_replies(server, flow, key):
    check("nodes_closed", key, masked(flow(server)[key]), server.target)


def test_extracted_nodes_have_the_same_shape(server, flow):
    """graph.json이 없으면 커뮤니티는 판마다 다를 수 있다 — 꼴과 대조·층은 같다"""
    v = flow(server)["bare"]
    assert v["graph"]["source"] == "server" and v["graph"]["error"] is None
    sizes = {c["id"]: c["size"] for c in v["communities"]}
    assert sizes and all(isinstance(c["label"], str) and c["label"] for c in v["communities"])
    counted: dict[int, int] = {}
    for f in v["functions"]:
        if f["community"] is not None:
            counted[f["community"]] = counted.get(f["community"], 0) + 1
    assert counted == sizes
    by_name = {f["name"]: f for f in v["functions"]}
    assert (by_name["main"]["ms"], by_name["main"]["status"]) == (
        f"{BARE}-MS-001#svc.main",
        "spec_only",
    )
    assert by_name["tidy"]["layer"] == {
        "name": "도구",
        "specs": [{"ref": f"{BARE}-MS-001", "note": "2장"}, {"ref": None, "note": "손으로 고친다"}],
    }
    assert by_name["extra"]["layer"] == {"name": "도우미", "specs": []}
