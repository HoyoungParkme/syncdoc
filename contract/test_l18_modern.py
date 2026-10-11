"""카드 L18 — MCP 2026-07-28: 핸드셰이크 없는 요청 하나짜리 봉투 (SYNC-API-002 1장, mcp 2.2.0 `_streamable_http_modern`).

`MCP-Protocol-Version` 머리가 핸드셰이크 판이 아니면(모르는 값까지) 새 입구가 받는다. 사례 표는 갈림길마다 한 번 —
보안·메서드·Accept·본문·알림 202·봉투·머리 중복·분류 사다리(_meta·머리 줄·판)·메서드 문지기·표면 검증·처리기·
`server/discover`·목록들(캐시 힌트·serverInfo 도장)·`tools/call`(resultType)·`subscriptions/listen`(확인 프레임) —
을 파이썬 판의 것(스냅숏 `modern_closed`)과 바이트로 비교한다. 무작위 차이 시험이 그 사이를 메운다.
"""

from __future__ import annotations

import base64
import json
import random
import re

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L18")

V = "2026-07-28"
PV = "io.modelcontextprotocol/protocolVersion"
CC = "io.modelcontextprotocol/clientCapabilities"
CI = "io.modelcontextprotocol/clientInfo"
HASH = re.compile(r"\b[0-9a-f]{40}\b")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(\+00:00|Z)")


def meta(**kw) -> dict:
    m = {PV: V, CC: {}}
    m.update(kw)
    return m


def req(method: str, params: dict | None = None, rid=1, **extra) -> dict:
    body = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        body["params"] = params
    body.update(extra)
    return body


def send(server, body, *, set_headers=None, extra_headers=(), raw: bytes | None = None, method="POST", read_for=None):
    """새 프로토콜 요청 — 판·메서드·이름 머리는 본문을 따라 붙인다. `set_headers`의 None은 뺀다"""
    hs = {
        "Authorization": f"Bearer {token_for(server)}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": V,
    }
    if isinstance(body, dict) and isinstance(body.get("method"), str):
        hs["Mcp-Method"] = body["method"]
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        for key in ("name", "uri"):
            if isinstance(params.get(key), str):
                hs["Mcp-Name"] = params[key]
    for k, v in (set_headers or {}).items():
        if v is None:
            hs.pop(k, None)
        else:
            hs[k] = v
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    pairs = [(k, header_value(k, v)) for k, v in [*hs.items(), *extra_headers]]
    return request(server.port, method, "/mcp", pairs, data, read_for=read_for)


def header_value(name: str, value: str) -> str:
    """머리에 실을 수 있게 — `Mcp-Name`은 클라이언트처럼 base64 표지로(`encode_header_value`), 그 밖은 latin-1로 못 쓰면 `?`"""
    if name.lower() == "mcp-name" and not (value.isascii() and value.isprintable() and value == value.strip()):
        return "=?base64?" + base64.b64encode(value.encode()).decode() + "?="
    return value.encode("latin-1", "replace").decode("latin-1")


def masked(reply) -> dict:
    c = reply.contract()
    c["body"] = STAMP.sub("T", HASH.sub("H", c["body"]))
    return c


CASES = [
    # 입구 — 보안·메서드·Accept·본문
    ("discover", req("server/discover", {"_meta": meta()}), {}),
    ("get", None, {"method": "GET"}),
    ("delete", None, {"method": "DELETE"}),
    ("no_content_type", req("server/discover", {"_meta": meta()}), {"set_headers": {"Content-Type": None}}),
    ("text_plain", req("server/discover", {"_meta": meta()}), {"set_headers": {"Content-Type": "text/plain"}}),
    ("accept_json_only", req("server/discover", {"_meta": meta()}), {"set_headers": {"Accept": "application/json"}}),
    ("accept_sse_only", req("server/discover", {"_meta": meta()}), {"set_headers": {"Accept": "text/event-stream"}}),
    ("accept_wild", req("server/discover", {"_meta": meta()}), {"set_headers": {"Accept": "*/*"}}),
    ("parse", None, {"raw": b"{bad"}),
    ("parse_empty", None, {"raw": b""}),
    ("batch", None, {"raw": b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]'}),
    ("scalar", None, {"raw": b"5"}),
    ("nan_id", None, {"raw": b'{"jsonrpc":"2.0","id":NaN,"method":"server/discover"}'}),
    # 알림 — 받고 버린다(판만 본다)
    ("notification", {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}, {}),
    ("notification_bad_version", {"jsonrpc": "2.0", "method": "notifications/x"}, {"set_headers": {"MCP-Protocol-Version": "2099"}}),
    ("notification_malformed", {"jsonrpc": "2.0", "method": 5}, {"set_headers": {"Mcp-Method": "5"}}),
    ("response_posted", {"jsonrpc": "2.0", "id": 1, "result": {}}, {}),
    # 봉투
    ("id_null", req("server/discover", {"_meta": meta()}, rid=None), {}),
    ("id_string", req("server/discover", {"_meta": meta()}, rid="문자 id"), {}),
    ("id_float", req("server/discover", {"_meta": meta()}, rid=1.0), {}),
    ("id_bool", req("server/discover", {"_meta": meta()}, rid=True), {}),
    ("jsonrpc_wrong", {"jsonrpc": "1.0", "id": 1, "method": "server/discover", "params": {"_meta": meta()}}, {}),
    ("params_list", {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": [1]}, {}),
    # 머리 중복·분류 사다리
    ("dup_method", req("server/discover", {"_meta": meta()}), {"extra_headers": [("Mcp-Method", "server/discover")]}),
    ("dup_version", req("server/discover", {"_meta": meta()}), {"extra_headers": [("mcp-protocol-version", V)]}),
    ("no_meta", req("tools/list", {}), {}),
    ("no_params", req("tools/list"), {}),
    ("meta_list", req("tools/list", {"_meta": [1]}), {}),
    ("missing_caps", req("tools/list", {"_meta": {PV: V}}), {}),
    ("missing_both", req("tools/list", {"_meta": {}}), {}),
    ("method_header_missing", req("tools/list", {"_meta": meta()}), {"set_headers": {"Mcp-Method": None}}),
    ("method_header_wrong", req("tools/list", {"_meta": meta()}), {"set_headers": {"Mcp-Method": "tools/call"}}),
    ("version_header_other", req("tools/list", {"_meta": meta()}), {"set_headers": {"MCP-Protocol-Version": "garbage"}}),
    ("version_body_other", req("tools/list", {"_meta": meta(**{PV: "2099-01-01"})}), {"set_headers": {"MCP-Protocol-Version": "2099-01-01"}}),
    ("version_body_int", req("tools/list", {"_meta": meta(**{PV: 5})}), {"set_headers": {"MCP-Protocol-Version": "5"}}),
    ("name_mismatch", req("tools/call", {"name": "list_documents", "arguments": {}, "_meta": meta()}), {"set_headers": {"Mcp-Name": "other"}}),
    ("name_missing", req("tools/call", {"name": "list_documents", "arguments": {}, "_meta": meta()}), {"set_headers": {"Mcp-Name": None}}),
    ("name_base64", req("tools/call", {"name": "list_documents", "arguments": {}, "_meta": meta()}), {"set_headers": {"Mcp-Name": "=?base64?bGlzdF9kb2N1bWVudHM=?="}}),
    ("name_bad_base64", req("tools/call", {"name": "list_documents", "arguments": {}, "_meta": meta()}), {"set_headers": {"Mcp-Name": "=?base64?bGlzd?="}}),
    ("uri_mismatch", req("resources/read", {"uri": "x://y", "_meta": meta()}), {"set_headers": {"Mcp-Name": "x://z"}}),
    ("client_info", req("tools/list", {"_meta": meta(**{CI: {"name": "c", "version": "1"}})}), {}),
    ("caps_wrong_type", req("tools/list", {"_meta": meta(**{CC: 5})}), {}),
    # 메서드 문지기·표면 검증·처리기
    ("ping", req("ping", {"_meta": meta()}), {}),
    ("initialize", req("initialize", {"_meta": meta(), "protocolVersion": V, "capabilities": {}, "clientInfo": {"name": "x", "version": "1"}}), {}),
    ("unknown_method", req("nope/x", {"_meta": meta()}), {}),
    ("complete", req("completion/complete", {"_meta": meta(), "ref": {"type": "ref/prompt", "name": "p"}, "argument": {"name": "a", "value": "b"}}), {}),
    ("set_level", req("logging/setLevel", {"_meta": meta(), "level": "info"}), {}),
    ("tools_list", req("tools/list", {"_meta": meta()}), {}),
    ("tools_list_cursor", req("tools/list", {"_meta": meta(), "cursor": "abc"}), {}),
    ("resources_list", req("resources/list", {"_meta": meta()}), {}),
    ("templates_list", req("resources/templates/list", {"_meta": meta()}), {}),
    ("prompts_list", req("prompts/list", {"_meta": meta()}), {}),
    ("resources_read", req("resources/read", {"uri": "x://가", "_meta": meta()}), {"set_headers": {"Mcp-Name": "=?base64?eDovL+qwgA==?="}}),
    ("prompts_get", req("prompts/get", {"name": "p", "_meta": meta()}), {}),
    ("discover_extra", req("server/discover", {"_meta": meta(), "x": 1}), {}),
    ("call_no_name", req("tools/call", {"_meta": meta()}), {}),
    ("call_args_list", req("tools/call", {"name": "get_document", "arguments": [1], "_meta": meta()}), {}),
    ("call_unknown_tool", req("tools/call", {"name": "nope", "arguments": {}, "_meta": meta()}), {}),
    ("call_bad_args", req("tools/call", {"name": "get_document", "arguments": {}, "_meta": meta()}), {}),
    ("call_init", req("tools/call", {"name": "init_project", "arguments": {"storage": "server", "code": "LMA", "name": "새 프로토콜"}, "_meta": meta()}), {}),
    ("call_template", req("tools/call", {"name": "get_template", "arguments": {"project_code": "LMA", "doc_type": "PRD"}, "_meta": meta()}), {}),
    ("call_list_docs", req("tools/call", {"name": "list_documents", "arguments": {"project_code": "LMA"}, "_meta": meta()}), {}),
    ("call_missing_doc", req("tools/call", {"name": "get_document", "arguments": {"doc_id": "LMA-PRD-009"}, "_meta": meta()}), {}),
    ("request_state", req("tools/call", {"name": "nope", "requestState": "x", "_meta": meta()}), {}),
    # 듣기 — 응답이 곧 알림 흐름(확인 프레임 뒤 ping)
    ("listen_no_filter", req("subscriptions/listen", {"_meta": meta()}), {}),
    ("listen_empty", req("subscriptions/listen", {"_meta": meta(), "notifications": {}}, rid="L1"), {"read_for": 1.5}),
    (
        "listen_filter",
        req(
            "subscriptions/listen",
            {"_meta": meta(), "notifications": {"toolsListChanged": True, "promptsListChanged": False, "resourcesListChanged": "true", "resourceSubscriptions": ["a://가"], "x": 1}},
            rid=7,
        ),
        {"read_for": 1.5},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_modern_cases(server, case):
    key, body, kw = case
    reply = send(server, body, **kw)
    if kw.get("read_for"):
        assert reply.timed_out, "듣기는 끝나지 않는다"
    check("modern_closed", key, masked(reply), server.target)


def test_json_depth_limit_alike(both):
    """`json.loads`의 C 재귀 한도 — 파이썬 판은 경계가 한 겹쯤 흔들린다(같은 프로세스에서도). 두 판의 경계가 한 겹 안이고,
    경계에서 셋 떨어진 깊이에서는 바이트로 같다"""
    py, rs = both

    def boundary(server) -> int:
        lo, hi = 9000, 11000
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if b"Parse error" in send(server, None, raw=b"[" * mid + b"]" * mid).body:
                hi = mid
            else:
                lo = mid
        return hi

    b_py, b_rs = boundary(py), boundary(rs)
    assert abs(b_py - b_rs) <= 1, f"경계 — 파이썬 {b_py}, Rust {b_rs}"
    for depth in (b_py - 3, b_py + 3):
        body = b"[" * depth + b"]" * depth
        assert masked(send(py, None, raw=body)) == masked(send(rs, None, raw=body)), depth


METHODS = [
    "server/discover",
    "tools/list",
    "tools/call",
    "resources/list",
    "resources/templates/list",
    "resources/read",
    "prompts/list",
    "prompts/get",
    "completion/complete",
    "logging/setLevel",
    "ping",
    "initialize",
    "notifications/cancelled",
    "nope/x",
    "",
]
WORDS = ["", "a", "2.0", "1", "x://y", "가", "list_documents", "get_document", "get_template", V, "2099-01-01", None, True, 0, 1.5, [], {}]


def rand_value(r: random.Random, depth: int = 0):
    k = r.random()
    if depth > 2 or k < 0.6:
        return r.choice(WORDS)
    if k < 0.8:
        return [rand_value(r, depth + 1) for _ in range(r.randint(0, 3))]
    return {r.choice(["name", "uri", "cursor", "arguments", "x", "_meta", "notifications"]): rand_value(r, depth + 1) for _ in range(r.randint(0, 3))}


def rand_meta(r: random.Random):
    k = r.random()
    if k < 0.75:
        m = meta()
        if r.random() < 0.2:
            m[CI] = r.choice([{"name": "c", "version": "1"}, rand_value(r)])
        if r.random() < 0.1:
            m[r.choice([PV, CC])] = rand_value(r)
        if r.random() < 0.05:
            del m[r.choice([PV, CC])]
        return m
    return rand_value(r)


def rand_params(r: random.Random, method: str):
    if r.random() < 0.06:
        return rand_value(r)
    p: dict = {}
    if r.random() < 0.92:
        p["_meta"] = rand_meta(r)
    if method == "tools/call":
        if r.random() < 0.9:
            p["name"] = r.choice(["list_documents", "get_document", "get_template", "get_item", "nope", 5])
        if r.random() < 0.85:
            p["arguments"] = r.choice([{}, {"project_code": r.choice(["LMA", "NOPE", 5])}, {"doc_id": "LMA-PRD-001"}, {"project_code": "LMA", "doc_type": r.choice(["PRD", "XYZ"])}, rand_value(r)])
    elif method in ("resources/read", "prompts/get"):
        if r.random() < 0.9:
            p["uri" if method == "resources/read" else "name"] = r.choice(["x://y", "p", 5])
    elif r.random() < 0.3:
        p[r.choice(["cursor", "x", "level", "ref"])] = rand_value(r)
    return p


def rand_case(r: random.Random) -> tuple[dict | None, dict]:
    method = r.choice(METHODS) if r.random() < 0.95 else rand_value(r)
    body: dict = {"jsonrpc": "2.0" if r.random() < 0.95 else r.choice(["1.0", 2])}
    is_note = isinstance(method, str) and method.startswith("notifications/")
    if not is_note and r.random() < 0.95:
        body["id"] = r.choice([1, "a", 0, -1, 2**40]) if r.random() < 0.9 else rand_value(r)
    body["method"] = method
    if r.random() < 0.9:
        body["params"] = rand_params(r, method if isinstance(method, str) else "")
    kw: dict = {}
    headers: dict = {}
    k = r.random()
    if k < 0.1:
        headers["Mcp-Method"] = r.choice(["tools/list", "", "x"])
    elif k < 0.15:
        headers["Mcp-Method"] = None
    k = r.random()
    if k < 0.08:
        headers["Mcp-Name"] = r.choice(["other", "=?base64?bGlzdF9kb2N1bWVudHM=?=", "=?base64?!!?="])
    elif k < 0.12:
        headers["Mcp-Name"] = None
    if r.random() < 0.06:
        headers["MCP-Protocol-Version"] = r.choice(["2099-01-01", "x", " 2026-07-28"])
    if r.random() < 0.04:
        headers["Accept"] = r.choice(["application/json", "text/event-stream", "*/*"])
    if r.random() < 0.03:
        headers["Content-Type"] = r.choice(["text/plain", "application/json; charset=utf-8"])
    kw["set_headers"] = headers
    if r.random() < 0.03:
        kw["extra_headers"] = [("Mcp-Method", str(method))]
    return body, kw


def test_modern_both_editions_answer_alike(both, request_count):
    py, rs = both
    count, seed = request_count
    r = random.Random(seed + 18)
    diffs = []
    for i in range(max(count // 2, 50)):
        body, kw = rand_case(r)
        a = masked(send(py, body, **kw))
        b = masked(send(rs, body, **kw))
        if a != b:
            diffs.append((i, body, kw, a, b))
    detail = "\n".join(f"#{i} {kw} {json.dumps(body, ensure_ascii=False)[:300]}\n  파이썬 {a}\n  Rust   {b}" for i, body, kw, a, b in diffs[:5])
    assert not diffs, f"{len(diffs)}개가 다르다:\n{detail}"


@pytest.fixture
def request_count(request) -> tuple[int, int]:
    return request.config.getoption("--diff-count"), request.config.getoption("--diff-seed")
