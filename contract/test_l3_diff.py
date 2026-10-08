"""카드 L3 — 두 판 차이 시험. 씨앗을 고정한 무작위 사례를 두 판에 보내 상태·계약 안 머리·본문을 바이트로 비교한다.

SYNC-INFRA-001 9.8 · SYNC-CODE-002 2장. 사례 표(`test_l3_mcp.py`)가 갈림길마다 한 번씩이라면 이것은 그 사이를 메운다 —
봉투·파라미터·도구 인자의 검증 문장(pydantic)과 JSON 읽기 오류까지. `--diff-count`·`--diff-seed`로 넓힌다.
Rust 판이 `not-implemented`로 답한 도구 부르기는 그 도구의 카드 전까지 비교하지 않는다(센다).
"""

from __future__ import annotations

import json
import random
import re
import urllib.parse

import pytest
from conftest import token_for
from wire import request

pytestmark = pytest.mark.card("L3")

HANDSHAKE = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
METHODS = [
    "initialize", "ping", "tools/list", "tools/call", "resources/list", "resources/templates/list",
    "resources/read", "resources/subscribe", "resources/unsubscribe", "prompts/list", "prompts/get",
    "completion/complete", "logging/setLevel", "server/discover", "subscriptions/listen",
    "notifications/initialized", "notifications/cancelled", "notifications/progress", "nope/x", "",
]
PARAM_KEYS = [
    "protocolVersion", "capabilities", "clientInfo", "_meta", "name", "arguments", "uri", "cursor",
    "level", "ref", "argument", "context", "task", "inputResponses", "requestState", "requestId",
    "reason", "progressToken", "progress", "total", "message", "x",
]
WORDS = [
    "", "a", "2.0", "1", " 1 ", "1_000", "1.0", "1.5", "1e3", "-0", "+1", "0x10", "true", "yes", "off",
    "null", "[1, 2]", '["x", 1]', '{"a": 1}', '[{"path": "a", "content": "b"}]', "한글 문장", "é \u0001",
    'quo"te', "it's", "\\", "😀", "file:///x", "http://example.com/a b", "ref/prompt", "ref/resource",
    "github", "server", "draft", "approved", "info", "debug", "SYNC", "X-PRD-001", "R1", "PRD", "DOM",
    "클래스", "MCP", "NaN", "inf", "\t", "x" * 60, "1" * 30, "ping", "tools/call",
]


def rand_scalar(r: random.Random):
    k = r.random()
    if k < 0.08:
        return None
    if k < 0.16:
        return r.choice([True, False])
    if k < 0.36:
        return r.choice([0, 1, -1, 2, 3, 42, 2**31, 2**63, 10**30, -(10**25), 7, 10])
    if k < 0.46:
        return r.choice([0.0, 1.0, 1.5, -2.5, 1e16, 1e-7, 3.14159, 2.0, 0.5, 1e300])
    return r.choice(WORDS)


def rand_value(r: random.Random, depth: int = 0):
    k = r.random()
    if depth > 2 or k < 0.6:
        return rand_scalar(r)
    if k < 0.8:
        return [rand_value(r, depth + 1) for _ in range(r.randint(0, 3))]
    return {r.choice(PARAM_KEYS + WORDS[:8]): rand_value(r, depth + 1) for _ in range(r.randint(0, 4))}


def rand_params(r: random.Random, method: str, tools: dict):
    k = r.random()
    if k < 0.08:
        return rand_value(r)
    if method == "tools/call" and tools:
        name = r.choice([*tools, "nope"]) if r.random() < 0.95 else rand_scalar(r)
        props = tools.get(name, {})
        args = {}
        for p, sch in props.items():
            if r.random() < 0.75:
                args[p] = rand_arg(r, sch)
        if r.random() < 0.2:
            args[r.choice(WORDS)] = rand_value(r)
        p = {"name": name}
        if r.random() < 0.9:
            p["arguments"] = args if r.random() < 0.95 else rand_value(r)
        return p
    if method == "initialize" and r.random() < 0.6:
        p = {
            "protocolVersion": r.choice([*HANDSHAKE, "2026-07-28", "1999-01-01", 5]),
            "capabilities": r.choice([{}, {"roots": {"listChanged": True}}, rand_value(r)]),
            "clientInfo": r.choice([{"name": "c", "version": "0"}, {"name": 1}, rand_value(r)]),
        }
        for key in list(p):
            if r.random() < 0.1:
                del p[key]
        return p
    return {r.choice(PARAM_KEYS): rand_value(r) for _ in range(r.randint(0, 3))}


def rand_arg(r: random.Random, sch: dict):
    """도구 인자 하나 — 스키마 꼴을 따르거나(대개) 어긋나게"""
    if r.random() < 0.3:
        return rand_value(r)
    t = sch.get("type")
    alts = [a.get("type") for a in sch.get("anyOf", [])]
    if "enum" in sch:
        return r.choice(sch["enum"] + ["other"])
    if t == "string" or "string" in alts:
        return r.choice(WORDS)
    if t == "integer" or "integer" in alts:
        return r.choice([0, 1, 3, -1, "3", "x", 1.0, 1.5, True, None])
    if t == "boolean" or "boolean" in alts:
        return r.choice([True, False, "true", "no", 1, 0, 2, None])
    if t == "array" or "array" in alts:
        return r.choice([[], ["a"], ["a", 1], [{"path": "a", "content": "b"}], [{"path": 1}], '["a"]', None])
    return rand_value(r)


def rand_body(r: random.Random, tools: dict) -> bytes:
    msg: dict = {}
    if r.random() < 0.95:
        msg["jsonrpc"] = "2.0" if r.random() < 0.9 else rand_scalar(r)
    method = r.choice(METHODS) if r.random() < 0.95 else rand_scalar(r)
    is_note = isinstance(method, str) and method.startswith("notifications/")
    if not is_note and r.random() < 0.92:
        msg["id"] = r.choice([1, 2, "a", "id-1", 0]) if r.random() < 0.8 else rand_scalar(r)
    msg["method"] = method
    if r.random() < 0.75:
        msg["params"] = rand_params(r, method if isinstance(method, str) else "", tools)
    if r.random() < 0.04:
        msg["result"] = rand_value(r)
    if r.random() < 0.04:
        msg["error"] = r.choice([{"code": 1, "message": "m"}, rand_value(r)])
    if r.random() < 0.03:
        del msg["method"]
    body = json.dumps(msg, ensure_ascii=r.random() < 0.3).encode()
    k = r.random()
    if k < 0.03:
        body = body[: r.randint(0, len(body))]
    elif k < 0.06:
        i = r.randint(0, len(body))
        body = body[:i] + r.choice([b"x", b",", b"}", b'"', b"\\", b"\x01", b" ", b"NaN"]) + body[i:]
    elif k < 0.07:
        body = b"[" + body + b"]"
    return body


def rand_headers(r: random.Random, tok: str) -> list[tuple[str, str]]:
    hs = [("Authorization", f"Bearer {tok}")]
    k = r.random()
    if k < 0.9:
        hs.append(("Accept", "application/json, text/event-stream"))
    elif k < 0.95:
        hs.append(("Accept", r.choice(["*/*", "application/json", "text/event-stream", "text/*, application/*"])))
    k = r.random()
    if k < 0.94:
        hs.append(("Content-Type", "application/json"))
    elif k < 0.97:
        hs.append(("Content-Type", r.choice(["application/json; charset=utf-8", "text/plain", "APPLICATION/JSON"])))
    if r.random() < 0.15:
        hs.append(("MCP-Protocol-Version", r.choice(HANDSHAKE)))
    return hs


def mask_tokens(body: str) -> str:
    """성공한 발급·목록의 값 — id·시각·원문은 판마다 다르다"""
    body = re.sub(r'"id":\d+', '"id":N', body)
    body = re.sub(r'"\d{4}-\d\d-\d\dT[\d:.]+Z"', '"T"', body)
    return re.sub(r'"syncdoc_pat_[A-Za-z0-9_-]{43}"', '"RAW"', body)


def _tool_props(server) -> dict:
    tok = token_for(server)
    hs = [("Authorization", f"Bearer {tok}"), ("Accept", "application/json, text/event-stream"), ("Content-Type", "application/json")]
    reply = request(server.port, "POST", "/mcp", hs, b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
    data = json.loads(reply.body.decode().split("data: ", 1)[1])
    return {t["name"]: t["inputSchema"].get("properties", {}) for t in data["result"]["tools"]}


def test_mcp_both_editions_answer_alike(both, request_count):
    py, rs = both
    count, seed = request_count
    r = random.Random(seed)
    tools = _tool_props(py)
    tok_py, tok_rs = token_for(py), token_for(rs)
    skipped, diffs = 0, []
    for i in range(count):
        method = "POST" if r.random() < 0.97 else r.choice(["DELETE", "GET"])
        body = rand_body(r, tools) if method == "POST" else b""
        hs = rand_headers(r, "{t}")
        if method == "GET":
            continue  # 끝나지 않는 SSE — 사례 표가 본다
        a = request(py.port, method, "/mcp", [(k, v.replace("{t}", tok_py)) for k, v in hs], body).contract()
        b = request(rs.port, method, "/mcp", [(k, v.replace("{t}", tok_rs)) for k, v in hs], body).contract()
        if "urn:syncdoc:not-implemented" in b["body"]:
            skipped += 1
            continue
        if a != b:
            diffs.append((i, hs, body, a, b))
    detail = "\n".join(
        f"#{i} {hs[1:]} {body[:300]!r}\n  파이썬 {a}\n  Rust   {b}" for i, hs, body, a, b in diffs[:5]
    )
    assert not diffs, f"{len(diffs)}/{count}개가 다르다(건너뜀 {skipped}):\n{detail}"


SEGMENTS = [
    "abc", "1.5", "1.0", "+7", "-0", "1_0", "%201", "%E2%80%8B1", "%FF", "１", "1e3", "0x1f", "-5",
    "2147483648", "-2147483649", "9" * 30, "%20", "nan", "true", "a%2Fb", "%2e%2e", "%25", "1%3F2",
]


def test_tokens_both_editions_answer_alike(both, request_count):
    py, rs = both
    count, seed = request_count
    r = random.Random(seed + 1)
    diffs = []
    for i in range(max(count // 4, 50)):
        if r.random() < 0.6:
            payload = {"label": r.choice(WORDS)} if r.random() < 0.7 else rand_value(r)
            body = json.dumps(payload, ensure_ascii=r.random() < 0.5).encode()
            k = r.random()
            if k < 0.08:
                body = body[: r.randint(0, len(body))]
            elif k < 0.12:
                body = b'{"label":"\\ud83d\\ude00\\ud800"}'
            ct = r.choice(["application/json"] * 6 + ["text/plain", "application/x+json", "", "application/json; charset=latin-1"])
            hs = [("Content-Type", ct)] if ct else []
            a = request(py.port, "POST", "/api/me/tokens", hs, body).contract()
            b = request(rs.port, "POST", "/api/me/tokens", hs, body).contract()
            a["body"], b["body"] = mask_tokens(a["body"]), mask_tokens(b["body"])
        else:
            seg = r.choice(SEGMENTS) if r.random() < 0.8 else urllib.parse.quote(str(rand_scalar(r)), safe="")
            if seg.isdigit() and len(seg) < 7:
                continue  # 있는 토큰일 수 있다 — 두 판의 번호가 다르다
            if not seg or urllib.parse.unquote(seg).endswith("/"):
                continue  # 끝 슬래시는 307 리다이렉트 — 계약 밖
            a = request(py.port, "DELETE", f"/api/me/tokens/{seg}").contract()
            b = request(rs.port, "DELETE", f"/api/me/tokens/{seg}").contract()
        if a != b:
            diffs.append((i, a, b))
    detail = "\n".join(f"#{i}\n  파이썬 {a}\n  Rust   {b}" for i, a, b in diffs[:5])
    assert not diffs, f"{len(diffs)}개가 다르다:\n{detail}"


@pytest.fixture
def request_count(request) -> tuple[int, int]:
    return request.config.getoption("--diff-count"), request.config.getoption("--diff-seed")
