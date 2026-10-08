"""카드 L3 — `/mcp` 사례 표. 파이썬 판의 답(스냅숏)과 상태·계약 안 머리·본문 바이트가 같아야 한다.

SYNC-API-002 1장 · SYNC-SEQ-001#SEQ-C2 · SYNC-INFRA-001 9.8. 스냅숏은 `contract/snapshots/mcp_closed.json` —
파이썬 판에서 `uv run pytest --target python --update-snapshots`로 다시 뜬다. 어떤 입력에도 같다는 것은
두 판 차이 시험(`test_l3_diff.py`)이 지킨다. 여기는 에이전트가 실제로 쓰는 흐름과 갈림길마다 한 번씩.
"""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import token_for
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L3")

TOKEN = "{token}"
ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")
AUTH = ("Authorization", f"Bearer {TOKEN}")
STD = [AUTH, ACCEPT, JSON]


def rpc(method: str, params=None, id_=1, **extra) -> bytes:
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    msg.update(extra)
    return json.dumps(msg, ensure_ascii=False).encode()


def note(method: str, params=None) -> bytes:
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg).encode()


INIT = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}

# (이름, 메서드, 머리, 본문[, 카드]) — 카드가 L3가 아니면 그 도구를 만드는 카드까지 Rust는 건너뛴다
CASES: list[tuple] = [
    # 인증
    ("auth_none", "POST", [ACCEPT, JSON], rpc("ping")),
    ("auth_wrong", "POST", [("Authorization", "Bearer nope"), ACCEPT, JSON], rpc("ping")),
    ("auth_lowercase", "POST", [("Authorization", f"bearer {TOKEN}"), ACCEPT, JSON], rpc("ping")),
    ("auth_padded", "POST", [("Authorization", f"Bearer  \t{TOKEN} "), ACCEPT, JSON], rpc("ping")),
    ("auth_last_wins", "POST", [("Authorization", "Bearer nope"), AUTH, ACCEPT, JSON], rpc("ping")),
    ("auth_first_ok_last_bad", "POST", [AUTH, ("Authorization", "Bearer nope"), ACCEPT, JSON], rpc("ping")),
    ("auth_get", "GET", [ACCEPT], b""),
    ("method_put", "PUT", STD, rpc("ping")),
    # 전송 — Content-Type·Accept·본문
    ("ct_missing", "POST", [AUTH, ACCEPT], rpc("ping")),
    ("ct_text", "POST", [AUTH, ACCEPT, ("Content-Type", "text/plain")], rpc("ping")),
    ("ct_upper", "POST", [AUTH, ACCEPT, ("Content-Type", "APPLICATION/JSON")], rpc("ping")),
    ("ct_charset", "POST", [AUTH, ACCEPT, ("Content-Type", "application/json; charset=utf-8")], rpc("ping")),
    ("ct_list", "POST", [AUTH, ACCEPT, ("Content-Type", "application/json, text/plain")], rpc("ping")),
    ("ct_suffix", "POST", [AUTH, ACCEPT, ("Content-Type", "application/jsonx")], rpc("ping")),
    ("accept_json_only", "POST", [AUTH, ("Accept", "application/json"), JSON], rpc("ping")),
    ("accept_sse_only", "POST", [AUTH, ("Accept", "text/event-stream"), JSON], rpc("ping")),
    ("accept_star", "POST", [AUTH, ("Accept", "*/*"), JSON], rpc("ping")),
    ("accept_wild_q", "POST", [AUTH, ("Accept", "application/*;q=0.9, text/* ; q=0.1"), JSON], rpc("ping")),
    ("accept_missing", "POST", [AUTH, JSON], rpc("ping")),
    ("body_empty", "POST", STD, b""),
    ("body_broken", "POST", STD, b'{"jsonrpc":'),
    ("body_trailing", "POST", STD, rpc("ping") + b" x"),
    ("body_nan", "POST", STD, b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}'),
    ("body_not_object", "POST", STD, b'"ping"'),
    ("body_batch", "POST", STD, b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]'),
    ("body_too_big_declared", "POST", [*STD, ("Content-Length", str(5 * 1024 * 1024))], b"{}"),
    ("delete", "DELETE", [AUTH], b""),
    ("get_no_sse", "GET", [AUTH, ("Accept", "application/json")], b""),
    ("get_last_event_id", "GET", [AUTH, ("Accept", "text/event-stream"), ("Last-Event-ID", "7")], b""),
    # 봉투
    ("env_bad_version", "POST", STD, b'{"jsonrpc":"1.0","id":1,"method":"ping"}'),
    ("env_id_float", "POST", STD, b'{"jsonrpc":"2.0","id":1.5,"method":"ping"}'),
    ("env_id_bool", "POST", STD, b'{"jsonrpc":"2.0","id":true,"method":"ping"}'),
    ("env_id_null", "POST", STD, b'{"jsonrpc":"2.0","id":null,"method":"ping"}'),
    ("env_id_big", "POST", STD, rpc("ping", id_=123456789012345678901234567890)),
    ("env_id_text", "POST", STD, rpc("ping", id_='a"\\\n\u0001é ')),
    ("env_method_int", "POST", STD, b'{"jsonrpc":"2.0","id":1,"method":3}'),
    ("env_params_list", "POST", STD, b'{"jsonrpc":"2.0","id":1,"method":"ping","params":[1]}'),
    ("env_nothing", "POST", STD, b'{"a":1}'),
    ("env_long_values", "POST", STD, json.dumps({"jsonrpc": "2" * 80, "id": [1] * 40, "method": "x" * 60}).encode()),
    ("note_initialized", "POST", STD, note("notifications/initialized")),
    ("note_unknown", "POST", STD, note("notifications/whatever", {"a": 1})),
    ("msg_response", "POST", STD, b'{"jsonrpc":"2.0","id":1,"result":{}}'),
    ("msg_error", "POST", STD, b'{"jsonrpc":"2.0","id":null,"error":{"code":1,"message":"m"}}'),
    # 메서드
    ("initialize", "POST", STD, rpc("initialize", INIT)),
    ("initialize_2024", "POST", STD, rpc("initialize", {**INIT, "protocolVersion": "2024-11-05"})),
    ("initialize_future", "POST", STD, rpc("initialize", {**INIT, "protocolVersion": "2030-01-01"})),
    ("initialize_no_params", "POST", STD, rpc("initialize")),
    ("initialize_bad", "POST", STD, rpc("initialize", {"protocolVersion": 1})),
    ("ping", "POST", STD, rpc("ping")),
    ("ping_meta_bad", "POST", STD, rpc("ping", {"_meta": 5})),
    ("tools_list", "POST", STD, rpc("tools/list")),
    ("tools_list_2024", "POST", [*STD, ("MCP-Protocol-Version", "2024-11-05")], rpc("tools/list")),
    ("tools_list_2025_11", "POST", [*STD, ("MCP-Protocol-Version", "2025-11-25")], rpc("tools/list")),
    ("tools_list_bad_cursor", "POST", STD, rpc("tools/list", {"cursor": 5})),
    ("resources_list", "POST", STD, rpc("resources/list")),
    ("resources_templates", "POST", STD, rpc("resources/templates/list")),
    ("resources_read", "POST", STD, rpc("resources/read", {"uri": "file:///x"})),
    ("resources_read_no_uri", "POST", STD, rpc("resources/read", {})),
    ("resources_subscribe", "POST", STD, rpc("resources/subscribe", {"uri": "x"})),
    ("prompts_list", "POST", STD, rpc("prompts/list")),
    ("prompts_get", "POST", STD, rpc("prompts/get", {"name": "p"})),
    ("prompts_get_bad_args", "POST", STD, rpc("prompts/get", {"name": "p", "arguments": {"a": 1}})),
    ("complete", "POST", STD, rpc("completion/complete", {"ref": {"type": "ref/prompt", "name": "x"}, "argument": {"name": "a", "value": "b"}})),
    ("complete_bad", "POST", STD, rpc("completion/complete", {})),
    ("set_level", "POST", STD, rpc("logging/setLevel", {"level": "info"})),
    ("discover", "POST", STD, rpc("server/discover")),
    ("listen", "POST", STD, rpc("subscriptions/listen")),
    ("method_unknown", "POST", STD, rpc("nope/x")),
    # 도구
    ("call_no_params", "POST", STD, rpc("tools/call")),
    ("call_unknown_tool", "POST", STD, rpc("tools/call", {"name": "nope", "arguments": {}})),
    ("call_missing_args", "POST", STD, rpc("tools/call", {"name": "get_document"})),
    ("call_bad_types", "POST", STD, rpc("tools/call", {"name": "list_documents", "arguments": {"project_code": 1, "stage": "x", "status": [1]}})),
    ("call_pre_parse", "POST", STD, rpc("tools/call", {"name": "update_document", "arguments": {"doc_id": "a", "body": "b", "expected_version": "3", "message": "m", "changed_items": '["x", 1]'}})),
    ("call_upload_bad", "POST", STD, rpc("tools/call", {"name": "upload_code", "arguments": {"project_code": "X", "files": [{"path": 1}], "message": "m"}})),
    ("call_literal_bad", "POST", STD, rpc("tools/call", {"name": "change_status", "arguments": {"doc_id": "a", "to": "done"}})),
    ("call_init_bad", "POST", STD, rpc("tools/call", {"name": "init_project", "arguments": {"storage": "s3", "code": "X"}})),
    # 도구 인자를 미리 읽는 파이썬 json의 C 재귀 한도 — 이 경로에서 9987겹까지
    ("call_arg_depth_ok", "POST", STD, rpc("tools/call", {"name": "update_document", "arguments": {"doc_id": "a", "body": "b", "expected_version": 1, "message": "m", "changed_items": "[" * 9987 + "]" * 9987}})),
    ("call_arg_depth_over", "POST", STD, rpc("tools/call", {"name": "update_document", "arguments": {"doc_id": "a", "body": "b", "expected_version": 1, "message": "m", "changed_items": "[" * 9988 + "]" * 9988}})),
    ("call_get_document", "POST", STD, rpc("tools/call", {"name": "get_document", "arguments": {"doc_id": "X-PRD-001"}}), "L7"),
]


@pytest.mark.parametrize(
    "case",
    [pytest.param(c, id=c[0], marks=[pytest.mark.card(c[4])] if len(c) > 4 else []) for c in CASES],
)
def test_mcp_case(server, case):
    name, method, headers, body = case[:4]
    tok = token_for(server)
    hs = [(k, v.replace(TOKEN, tok)) for k, v in headers]
    reply = request(server.port, method, "/mcp", hs, body)
    check("mcp_closed", name, reply.contract(), server.target)


def test_get_stream_stays_open(server):
    """GET은 끝나지 않는 SSE — 보낼 것이 없어 15초마다 ping뿐이다. 머리만 보고 1초 뒤 끊는다"""
    reply = request(server.port, "GET", "/mcp", [("Authorization", f"Bearer {token_for(server)}"), ACCEPT], read_for=1.0)
    assert reply.timed_out
    got = reply.contract()
    assert (got["status"], got["body"]) == (200, "")
    check("mcp_closed", "get_stream_headers", {"status": got["status"], "headers": got["headers"]}, server.target)


async def test_real_client_connects(server):
    """실제 MCP 클라이언트(파이썬 SDK)로 — 서버 이름 `syncdoc_local`, 도구 13개"""
    headers = {"Authorization": f"Bearer {token_for(server)}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as hc:
        async with streamable_http_client(f"{server.url}/mcp", http_client=hc) as (read, write):
            async with ClientSession(read, write) as s:
                init = await s.initialize()
                assert init.server_info.name == "syncdoc_local"
                tools = await s.list_tools()
                assert len(tools.tools) == 13
