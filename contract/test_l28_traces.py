"""카드 L28 — 실행 기록 (SYNC-SCN-001 S13, UC-H25·UC-S9 · SEQ-36): 흐름 고정 저장소를 두 판에 push하고 기록 도구가
부르는 두 경로(trace-spans·기록 올리기 — 개인 토큰)와 화면의 목록·하나·커버리지·지우기의 응답 바이트를 파이썬 판의
것(스냅숏 `traces`)과 비교한다. 꼴이 틀린 기록·4MB 넘는 본문·남의 프로젝트·없는 기록도.
"""

from __future__ import annotations

import json

import pytest

from conftest import token_for
from snapshots import check
from test_l12_code import clone, masked, mcp, push, rest, wait_graph
from test_l25_flow import fixture
from wire import request

pytestmark = pytest.mark.card("L28")

CODE = "LTR"
JSON = ("Content-Type", "application/json")


def record(key: str, **over) -> dict:
    r = {
        "version": 1, "id": key, "kind": "back", "method": "GET", "path": "/v1/items/3", "status": 200,
        "error": None, "startedAt": "2026-10-17T10:02:03.25+09:00", "ms": 12, "commit": None,
        "truncated": False,
        "events": [
            {"i": 0, "parent": -1, "fn": "backend/app/api/items.py:14", "name": "read", "t0": 0, "t1": 9,
             "args": {"item_id": "3"}, "ret": "{'id': 3}"},
            {"i": 1, "parent": 0, "fn": "@infra", "t0": 1, "t1": 2,
             "infra": {"kind": "db", "target": "db:5432", "op": "SELECT 1"}},
            {"i": 2, "parent": 0, "fn": "backend/app/core/service.py:4", "t0": 3},
        ],
    }  # fmt: skip
    r.update(over)
    return r


def post(server, path: str, body: bytes, token: str | None):
    hs = [JSON] + ([("Authorization", f"Bearer {token}")] if token else [])
    return request(server.port, "POST", path, hs, body)


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    done: dict[str, dict] = {}

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        tmp = tmp_path_factory.mktemp(f"l28-{server.target}")
        (tmp / "client-gitconfig").write_text("")
        mcp(server, "init_project", {"storage": "server", "code": CODE, "name": "기록 시험"})
        token = token_for(server)
        base = f"/api/projects/{CODE}"
        auth = [("Authorization", f"Bearer {token}")]
        got["spans_none"] = request(server.port, "GET", f"{base}/trace-spans", auth)
        work = clone(server, tmp, CODE)
        fixture(work)
        head = push(server, CODE, work, "흐름 고정 저장소")
        wait_graph(server, CODE, lambda g: g["commit_hash"] == head)
        got["spans_token"] = request(server.port, "GET", f"{base}/trace-spans", auth)
        got["spans_local"] = rest(server, "GET", f"{base}/trace-spans")
        got["spans_bad_token"] = request(
            server.port, "GET", f"{base}/trace-spans", [("Authorization", "Bearer nope")]
        )
        got["spans_other"] = request(server.port, "GET", "/api/projects/NOPE/trace-spans", auth)
        one = json.dumps(record("k1"), ensure_ascii=False).encode()
        got["upload"] = post(server, f"{base}/traces", one, token)
        got["upload_again"] = post(server, f"{base}/traces", one, token)
        got["upload_local"] = post(server, f"{base}/traces", json.dumps(record("k2", kind="job", method="JOB")).encode(), None)
        got["upload_bad_token"] = post(server, f"{base}/traces", one, "nope")
        got["upload_orphan"] = post(server, f"{base}/traces", json.dumps(record("k3", events=[
            {"i": 0, "parent": 7, "fn": "a", "t0": 0}])).encode(), token)  # fmt: skip
        got["upload_time"] = post(server, f"{base}/traces", json.dumps(record("k4", startedAt="2026-02-30T00:00:00")).encode(), token)
        got["upload_shape"] = post(server, f"{base}/traces", json.dumps(record("k5", kind="other", ms=-1)).encode(), token)
        got["upload_not_json"] = post(server, f"{base}/traces", b"{nope", token)
        big = record("k6")
        big["events"][0]["ret"] = "x" * (4 * 1024 * 1024)
        got["upload_big"] = post(server, f"{base}/traces", json.dumps(big).encode(), token)
        got["upload_other"] = post(server, "/api/projects/NOPE/traces", one, token)
        got["list"] = rest(server, "GET", f"{base}/traces")
        ids = [t["id"] for t in json.loads(got["list"].body)]
        got["one"] = rest(server, "GET", f"{base}/traces/{ids[-1]}")
        got["one_missing"] = rest(server, "GET", f"{base}/traces/999999")
        got["one_huge"] = rest(server, "GET", f"{base}/traces/99999999999999999999999")
        got["one_text"] = rest(server, "GET", f"{base}/traces/abc")
        got["coverage"] = rest(server, "GET", f"{base}/traces/coverage")
        got["delete_one"] = rest(server, "DELETE", f"{base}/traces/{ids[-1]}")
        got["delete_one_again"] = rest(server, "DELETE", f"{base}/traces/{ids[-1]}")
        got["delete_all"] = rest(server, "DELETE", f"{base}/traces")
        got["list_empty"] = rest(server, "GET", f"{base}/traces")
        got["list_other"] = rest(server, "GET", "/api/projects/NOPE/traces")
        done[server.target] = got
        return got

    return run


KEYS = [
    "spans_none", "spans_token", "spans_local", "spans_bad_token", "spans_other", "upload",
    "upload_again", "upload_local", "upload_bad_token", "upload_orphan", "upload_time",
    "upload_shape", "upload_not_json", "upload_big", "upload_other", "list", "one", "one_missing",
    "one_huge", "one_text", "coverage", "delete_one", "delete_one_again", "delete_all",
    "list_empty", "list_other",
]  # fmt: skip


@pytest.mark.parametrize("key", KEYS)
def test_trace_replies(server, flow, key):
    check("traces", key, masked(flow(server)[key]), server.target)


def test_trace_flow_is_sane(server, flow):
    """올린 기록이 목록·커버리지로 돌아온다 — 바이트 비교와 따로 뜻을 본다"""
    got = flow(server)
    assert got["upload"].status == 201 and got["upload_again"].status == 200
    assert got["upload_big"].status == 413 and got["spans_bad_token"].status == 401
    lst = json.loads(got["list"].body)
    assert [t["trace_key"] for t in lst] == ["k2", "k1"] and lst[0]["method"] is None
    cov = json.loads(got["coverage"].body)
    assert cov["keys"] == ["backend/app/api/items.py:14", "backend/app/core/service.py:4"]
    spans = json.loads(got["spans_token"].body)
    assert spans["spans"] and all(s["end"] >= s["line"] for s in spans["spans"])
