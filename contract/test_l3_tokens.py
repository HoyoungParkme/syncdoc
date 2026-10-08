"""카드 L3 — 토큰 세 경로(SYNC-API-001 `/api/me/tokens`)와 MCP 인증의 흔적.

성공 응답은 모양과 값(시각·원문 꼴)을, 실패 응답은 파이썬 판의 바이트(스냅숏 `tokens_closed`)를 본다.
"""

from __future__ import annotations

import re

import pytest
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L3")

ISO = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{6})?Z"
KEYS = ["id", "label", "issued_at", "expires_at", "revoked_at", "last_used_at"]
JSON = ("Content-Type", "application/json")


def issue(server, label="t"):
    r = server.client().post("/api/me/tokens", json={"label": label})
    assert r.status_code == 201, r.text
    return r.json()


def test_issue_list_revoke(server):
    t = issue(server, "노트북 · 집")
    assert list(t) == [*KEYS, "token"]
    assert re.fullmatch(r"syncdoc_pat_[A-Za-z0-9_-]{43}", t["token"])
    assert re.fullmatch(ISO, t["issued_at"])
    assert (t["label"], t["expires_at"], t["revoked_at"], t["last_used_at"]) == ("노트북 · 집", None, None, None)
    listed = server.client().get("/api/me/tokens")
    assert listed.status_code == 200 and listed.headers["content-type"] == "application/json"
    first = listed.json()[0]
    assert list(first) == KEYS
    assert first == {k: t[k] for k in KEYS}
    r = server.client().delete(f"/api/me/tokens/{t['id']}")
    assert (r.status_code, r.content, r.headers.get("content-type")) == (204, b"", None)
    again = [x for x in server.client().get("/api/me/tokens").json() if x["id"] == t["id"]][0]
    assert re.fullmatch(ISO, again["revoked_at"])


def test_mcp_use_leaves_a_trace_and_revoked_token_is_refused(server):
    t = issue(server, "trace")
    hs = [("Authorization", f"Bearer {t['token']}"), ("Accept", "application/json, text/event-stream"), JSON]
    ping = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    assert request(server.port, "POST", "/mcp", hs, ping).status == 200
    used = [x for x in server.client().get("/api/me/tokens").json() if x["id"] == t["id"]][0]
    assert re.fullmatch(ISO, used["last_used_at"])
    assert server.client().delete(f"/api/me/tokens/{t['id']}").status_code == 204
    r = request(server.port, "POST", "/mcp", hs, ping)
    assert r.status == 401


def test_empty_label_is_allowed(server):
    assert issue(server, "")["label"] == ""


ERRORS = [
    ("label_too_long", "POST", "/api/me/tokens", [JSON], b'{"label":"' + b"x" * 51 + b'"}'),
    ("label_missing", "POST", "/api/me/tokens", [JSON], b"{}"),
    ("label_not_str", "POST", "/api/me/tokens", [JSON], b'{"label":5}'),
    ("label_surrogate", "POST", "/api/me/tokens", [JSON], b'{"label":"\\ud800"}'),
    ("body_list", "POST", "/api/me/tokens", [JSON], b"[]"),
    ("body_null", "POST", "/api/me/tokens", [JSON], b"null"),
    ("body_empty", "POST", "/api/me/tokens", [JSON], b""),
    ("body_broken", "POST", "/api/me/tokens", [JSON], b'{"label": "x",}'),
    ("body_not_utf8", "POST", "/api/me/tokens", [JSON], b"\xff"),
    ("body_no_content_type", "POST", "/api/me/tokens", [], b'{"label":"x"}'),
    ("body_text_plain", "POST", "/api/me/tokens", [("Content-Type", "text/plain")], b'{"label":"x"}'),
    ("body_int_too_long", "POST", "/api/me/tokens", [JSON], b'{"label":' + b"1" * 4301 + b"}"),
    ("revoke_text", "DELETE", "/api/me/tokens/abc", [], b""),
    ("revoke_fraction", "DELETE", "/api/me/tokens/1.5", [], b""),
    ("revoke_missing", "DELETE", "/api/me/tokens/999999", [], b""),
    ("revoke_huge", "DELETE", "/api/me/tokens/99999999999999999999999", [], b""),
    ("revoke_i32_over", "DELETE", "/api/me/tokens/2147483648", [], b""),
    ("revoke_i64_max", "DELETE", "/api/me/tokens/9223372036854775807", [], b""),
    ("revoke_i64_over", "DELETE", "/api/me/tokens/9223372036854775808", [], b""),
    ("revoke_i64_min", "DELETE", "/api/me/tokens/-9223372036854775808", [], b""),
    ("revoke_i64_under", "DELETE", "/api/me/tokens/-9223372036854775809", [], b""),
    ("tokens_put", "PUT", "/api/me/tokens", [JSON], b"{}"),
    # 파이썬 json의 C 재귀 한도 — 이 경로에서 9986겹까지 읽는다(넘으면 400)
    ("body_depth_ok", "POST", "/api/me/tokens", [JSON], b"[" * 9986 + b"]" * 9986),
    ("body_depth_over", "POST", "/api/me/tokens", [JSON], b"[" * 9987 + b"]" * 9987),
    ("path_encoded", "GET", "/api/m%65/tokens%2Fx", [], b""),
]


@pytest.mark.parametrize("case", [c for c in ERRORS if c[1]], ids=lambda c: c[0])
def test_error_bytes(server, case):
    name, method, path, headers, body = case
    reply = request(server.port, method, path, headers, body)
    check("tokens_closed", name, reply.contract(), server.target)
