"""카드 L3 몫(틀만) — 토큰을 발급해 MCP로 붙는다. Rust 판은 L3가 끝나야 돈다.

SYNC-API-001#POST/api/me/tokens · SYNC-API-002 · SYNC-SCN-001#S5.
"""

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

pytestmark = pytest.mark.card("L3")


def test_mcp_without_token_is_401(server):
    r = server.client().post("/mcp", json={})
    assert r.status_code == 401
    assert r.json()["type"] == "urn:syncdoc:unauthorized"


async def test_issued_token_opens_mcp(server):
    issued = server.client().post("/api/me/tokens", json={"label": "contract"})
    assert issued.status_code == 201
    token = issued.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as hc:
        async with streamable_http_client(f"{server.url}/mcp", http_client=hc) as (read, write):
            async with ClientSession(read, write) as s:
                init = await s.initialize()
                assert init.server_info.name == "syncdoc_local"
                tools = await s.list_tools()
                assert len(tools.tools) == 13
