"""카드 L12 — 코드 그래프 (SYNC-SCN-001 S9, UC-S8·H20): 두 판에 같은 코드와 같은 `graphify-out/graph.json`
(`tests/l12` — 파이썬 판 graphify가 뽑은 원형)을 진짜 `git push`로 넣고, 그래프 만들기가 끝나기를 기다린 뒤
코드 탭·코드 보기·관계도 코드 호출·코드 그래프의 코드·MCP `get_code_graph`의 응답 바이트를 파이썬 판의 것
(스냅숏 `code_closed`)과 비교한다. 커밋 해시(40자, 그래프 실패 이유의 앞 7자)와 시각만 가린다.

graph.json이 없는 프로젝트는 원형을 각 판이 뽑는다(파이썬 graphify · Rust tree-sitter) — 호출 선이 다를 수 있어
꼴만 본다(SYNC-MS-022 0장).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L12")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")
HASH = re.compile(r"\b[0-9a-f]{40}\b")
SHORT = re.compile(r"(\"error\\?\":\s?\\?\")[0-9a-f]{7}:")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")
FIXTURE = Path(__file__).parent / "tests" / "l12"
CODE = "LCG"
BARE = "LCH"


def masked(reply) -> dict:
    """비교할 꼴 — 커밋 해시와 시각은 판마다 다르다"""
    c = reply.contract()
    c["body"] = STAMP.sub("T", SHORT.sub(r"\1h:", HASH.sub("H", c["body"])))
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


def rest(server, method: str, path: str):
    return request(server.port, method, path)


def git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(cwd.parent / "client-gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    r = subprocess.run(
        ["git", "-c", "user.name=밖", "-c", "user.email=out@example.com", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def processed(server, code: str) -> str | None:
    rows = json.loads(rest(server, "GET", "/api/admin/repos").body)
    return next(r["last_processed_commit"] for r in rows if r["code"] == code)


def graph_of(server, code: str) -> dict | None:
    return json.loads(rest(server, "GET", f"/api/projects/{code}/code-calls").body)["graph"]


def push(server, code: str, work: Path, message: str) -> str:
    """민 뒤 처리가 끝나고 그 커밋의 그래프 행(성공이든 실패든)이 생기기를 기다린다"""
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", message)
    git(work, "push", "-q", "origin", "HEAD:main")
    head = git(work, "rev-parse", "HEAD")
    end = time.monotonic() + 30
    while time.monotonic() < end and processed(server, code) != head:
        time.sleep(0.2)
    return head


def wait_graph(server, code: str, ok) -> dict:
    end = time.monotonic() + 60
    while time.monotonic() < end:
        g = graph_of(server, code)
        if g is not None and ok(g):
            return g
        time.sleep(0.2)
    raise AssertionError(f"{code} 그래프가 만들어지지 않았다")


PRD = (
    "---\ndoc_id: LCG-PRD-001\ntype: PRD\ntitle: 코드 대조\nstatus: draft\n---\n# 코드 대조\n\n## 1. 목표\n\n"
    "## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 숫자를 글로\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n"
)
MS = (
    "---\ndoc_id: {code}-MS-001\ntype: MS\ntitle: MINISPEC — svc\nstatus: draft\nupstream: []\n---\n\n"
    "# MINISPEC\n\n## 1. 함수 목록\n\n## 2. 함수\n\n"
    "#### svc.main 진입\n\n근거: [[{code}-PRD-001#R1]]\n\n**호출하는 것** [[#svc.helper]] · [[#svc.other]]\n\n"
    "#### svc.helper 도우미\n\n**호출하는 것** —\n\n"
    "#### svc.get 꺼내기\n\n**호출하는 것** `svc.helper`\n\n"
    "#### svc.other 코드에 없다\n\n**호출하는 것** —\n\n"
    "#### svc.rs_entry Rust 입구\n\n**호출하는 것** [[#svc.helper]]\n\n"
    "## 3. 미결사항\n"
)


def write(work: Path, path: str, text: str) -> None:
    f = work / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def clone(server, tmp: Path, code: str) -> Path:
    url = f"http://x:{token_for(server)}@127.0.0.1:{server.port}/git/{code}.git"
    work = tmp / f"w-{code}"
    git(tmp, "clone", "-q", url, str(work))
    return work


def copy_fixture(work: Path, code: str) -> None:
    """시험 코드를 작업 사본에 — 항목 ID는 그 프로젝트 것으로. graph.json은 고정 코드(LCG)에만"""
    for f in sorted(FIXTURE.rglob("*")):
        rel = f.relative_to(FIXTURE)
        if f.is_dir() or (code != CODE and rel.parts[0] == "graphify-out"):
            continue
        write(work, rel.as_posix(), f.read_text(encoding="utf-8").replace(f"{CODE}-", f"{code}-"))


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    """두 판에 같은 차례로 — 프로젝트 → 그래프 없음 → 명세·코드·graph.json push → 그래프 → 읽기 → 깨진 graph.json"""
    done: dict[str, dict] = {}

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        tmp = tmp_path_factory.mktemp(f"l12-{server.target}")
        (tmp / "client-gitconfig").write_text("")
        mcp(server, "init_project", {"storage": "server", "code": CODE, "name": "코드 대조 시험"})
        # 1. 그래프가 아직 없다
        got["calls_none"] = rest(server, "GET", f"/api/projects/{CODE}/code-calls")
        got["text_none"] = rest(
            server, "GET", f"/api/projects/{CODE}/code/source?file=app/svc.py&line=6"
        )
        work = clone(server, tmp, CODE)
        write(work, "docs/specs/02-PRD/LCG-PRD-001.md", PRD)
        write(work, "docs/specs/10-MS/LCG-MS-001.md", MS.format(code=CODE))
        copy_fixture(work, CODE)
        head = push(server, CODE, work, "명세와 코드")
        wait_graph(server, CODE, lambda g: g["commit_hash"] == head and g["source"] == "repo")
        # 2. 코드 탭 — MINISPEC 문서·항목, 다른 문서의 항목, 없는 것
        for key, path in [
            ("doc_ms", "/api/docs/LCG-MS-001/code"),
            ("item_main", "/api/docs/LCG-MS-001/items/svc.main/code"),
            ("item_get", "/api/docs/LCG-MS-001/items/svc.get/code"),
            ("item_other", "/api/docs/LCG-MS-001/items/svc.other/code"),
            ("item_rs", "/api/docs/LCG-MS-001/items/svc.rs_entry/code"),
            ("doc_prd", "/api/docs/LCG-PRD-001/code"),
            ("item_prd", "/api/docs/LCG-PRD-001/items/R1/code"),
            ("item_nope", "/api/docs/LCG-MS-001/items/nope/code"),
            ("doc_nope", "/api/docs/LCG-MS-999/code"),
            ("doc_other_project", "/api/docs/NOPE-MS-001/code"),
        ]:
            got[key] = rest(server, "GET", path)
        # 3. 코드 보기 — 그 함수의 줄(끝 줄 없으면 다음 함수 앞, 그것도 없으면 +59)
        for key, item in [
            ("source_helper", "LCG-MS-001/items/svc.helper"),
            ("source_get", "LCG-MS-001/items/svc.get"),
            ("source_rs", "LCG-MS-001/items/svc.rs_entry"),
            ("source_other", "LCG-MS-001/items/svc.other"),
            ("source_r1", "LCG-PRD-001/items/R1"),
            ("source_nope", "LCG-MS-001/items/nope"),
        ]:
            got[key] = rest(server, "GET", f"/api/docs/{item}/code/source")
        # 4. 관계도 코드 호출 · 코드 그래프의 코드
        got["calls"] = rest(server, "GET", f"/api/projects/{CODE}/code-calls")
        for key, q in [
            ("text_main", "file=app/svc.py&line=6"),
            ("text_ts", "file=web/app.ts&line=2"),
            ("text_ts_helper", "file=web/app.ts&line=6"),
            ("text_rs", "file=crates/x/src/lib.rs&line=2"),
            ("text_no_fn", "file=app/svc.py&line=7"),
            ("text_no_query", ""),
            ("text_line_zero", "file=app/svc.py&line=0"),
            ("text_file_empty", "file=&line=6"),
            ("text_line_word", "file=app/svc.py&line=abc"),
            ("text_line_huge", "file=app/svc.py&line=99999999999999999999999"),
            ("text_no_file", "line=6"),
        ]:
            got[key] = rest(server, "GET", f"/api/projects/{CODE}/code/source?{q}")
        got["text_other_project"] = rest(
            server, "GET", "/api/projects/NOPE/code/source?file=a.py&line=1"
        )
        got["calls_other_project"] = rest(server, "GET", "/api/projects/NOPE/code-calls")
        # 5. MCP get_code_graph
        for key, args in [
            ("mcp_doc", {"doc_id": "LCG-MS-001"}),
            ("mcp_item", {"doc_id": "LCG-MS-001", "item_id": "svc.main"}),
            ("mcp_item_empty", {"doc_id": "LCG-MS-001", "item_id": ""}),
            ("mcp_item_null", {"doc_id": "LCG-MS-001", "item_id": None}),
            ("mcp_missing", {"doc_id": "LCG-MS-001", "item_id": "svc.other"}),
            ("mcp_prd", {"doc_id": "LCG-PRD-001", "item_id": "R1"}),
            ("mcp_nope", {"doc_id": "LCG-MS-999"}),
            ("mcp_no_args", {}),
            ("mcp_bad_type", {"doc_id": 3}),
        ]:
            got[key] = mcp(server, "get_code_graph", args)
        # 6. 깨진 graph.json → 옛 그래프를 두고 이유만
        write(work, "graphify-out/graph.json", "{깨짐")
        write(work, "app/util.py", "def fmt(x):\n    return repr(x)\n")
        push(server, CODE, work, "깨진 그래프")
        wait_graph(server, CODE, lambda g: g["error"] is not None)
        got["broken_calls"] = rest(server, "GET", f"/api/projects/{CODE}/code-calls")
        got["broken_source"] = rest(
            server, "GET", "/api/docs/LCG-MS-001/items/svc.helper/code/source"
        )
        # 7. graph.json 없는 프로젝트 — 각 판이 뽑는다
        mcp(server, "init_project", {"storage": "server", "code": BARE, "name": "뽑기 시험"})
        bare = clone(server, tmp, BARE)
        write(bare, f"docs/specs/10-MS/{BARE}-MS-001.md", MS.format(code=BARE))
        copy_fixture(bare, BARE)
        head = push(server, BARE, bare, "코드만")
        wait_graph(server, BARE, lambda g: g["commit_hash"] == head)
        got["bare_main"] = json.loads(
            rest(server, "GET", f"/api/docs/{BARE}-MS-001/items/svc.main/code").body
        )
        done[server.target] = got
        return got

    return run


FLOW_KEYS = [
    "calls_none",
    "text_none",
    "doc_ms",
    "item_main",
    "item_get",
    "item_other",
    "item_rs",
    "doc_prd",
    "item_prd",
    "item_nope",
    "doc_nope",
    "doc_other_project",
    "source_helper",
    "source_get",
    "source_rs",
    "source_other",
    "source_r1",
    "source_nope",
    "calls",
    "text_main",
    "text_ts",
    "text_ts_helper",
    "text_rs",
    "text_no_fn",
    "text_no_query",
    "text_line_zero",
    "text_file_empty",
    "text_line_word",
    "text_line_huge",
    "text_no_file",
    "text_other_project",
    "calls_other_project",
    "mcp_doc",
    "mcp_item",
    "mcp_item_empty",
    "mcp_item_null",
    "mcp_missing",
    "mcp_prd",
    "mcp_nope",
    "mcp_no_args",
    "mcp_bad_type",
    "broken_calls",
    "broken_source",
]


@pytest.mark.parametrize("key", FLOW_KEYS)
def test_code_replies(server, flow, key):
    check("code_closed", key, masked(flow(server)[key]), server.target)


def test_extracted_graph_has_the_same_shape(server, flow):
    """graph.json이 없으면 판마다 뽑는다 — 출처 server, 항목의 함수·자리·같음 호출은 같다"""
    v = flow(server)["bare_main"]
    assert v["graph"]["source"] == "server"
    assert v["graph"]["error"] is None
    f = v["function"]
    assert (f["qual"], f["file"], f["line"], f["end"]) == ("svc.main", "app/svc.py", 6, 8)
    calls = {(c["ms_id"], c["status"]) for c in f["calls"]}
    assert (f"{BARE}-MS-001#svc.helper", "same") in calls
    assert (f"{BARE}-MS-001#svc.other", "spec_only") in calls
    assert [b["ms_id"].split("#")[1] for b in v["functions"]] == [
        "svc.main",
        "svc.helper",
        "svc.get",
        "svc.other",
        "svc.rs_entry",
    ]
