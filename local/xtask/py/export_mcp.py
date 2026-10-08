"""cargo xtask mcp-tools — 파이썬 판 MCP 서버(폐쇄망판 설정)에서 Rust 판이 쓸 선언을 뽑는다.

SYNC-STD-004#DEV-7 · SYNC-DOM-004 1장(mcp/·compat/). 손으로 고치지 않는다 — 이 스크립트가 다시 만든다.
뽑는 것: 서버 이름·안내문·능력, 판마다 고정 결과(initialize·tools/list·빈 목록들)의 바이트,
pydantic core schema(봉투·메서드 표면·처리기 인자·도구 인자)와 검증기 제목, 판 목록.
`uv run --project backend python local/xtask/py/export_mcp.py OUT` — 작업 자리는 `.env`가 없는 곳이어야 한다.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import re
import sys

os.environ.update(
    {
        "EDITION": "closed",
        "SECRET_KEY": "export-only",
        "DATABASE_URL": "postgresql+psycopg://x:x@127.0.0.1:1/x",
        "LOCAL_LOGIN": "local",
        "LLM_API_URL": "",
        "LLM_API_KEY": "",
    }
)

import mcp  # noqa: E402, F401
import mcp_types  # noqa: E402
import pydantic  # noqa: E402
import pydantic_core  # noqa: E402
from mcp_types import DEFAULT_NEGOTIATED_VERSION, jsonrpc, methods  # noqa: E402
from mcp_types.version import (  # noqa: E402
    HANDSHAKE_PROTOCOL_VERSIONS,
    KNOWN_PROTOCOL_VERSIONS,
    LATEST_HANDSHAKE_VERSION,
    MODERN_PROTOCOL_VERSIONS,
)
from pydantic import TypeAdapter  # noqa: E402

from app.mcp.tools import server  # noqa: E402

LOW = server._lowlevel_server  # noqa: SLF001
FN_OK = {"_BaseUrl.__get_pydantic_core_schema__.<locals>.wrap_val"}


def clean(x):
    """core schema → JSON. 클래스는 이름, 함수는 {"<fn>": qualname}, ref의 메모리 번호는 뺀다."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k == "cls":
                out[k] = v.__name__
                continue
            if k in ("metadata", "serialization", "ref_cls", "generic_origin"):
                continue
            if k in ("post_init",) and v is None:
                continue
            if k == "config":
                out[k] = {kk: vv for kk, vv in v.items() if not callable(vv)}
                continue
            if k in ("ref", "schema_ref") and isinstance(v, str):
                out[k] = re.sub(r":\d+$", "", v)
                continue
            out[k] = clean(v)
        return out
    if isinstance(x, (list, tuple)):
        return [clean(y) for y in x]
    if callable(x) and not isinstance(x, type):
        name = getattr(x, "__qualname__", str(x))
        return {"<fn>": name}
    if isinstance(x, type):
        return x.__qualname__
    return x


def schema_of(model_or_adapter, title=None):
    if isinstance(model_or_adapter, TypeAdapter):
        return {"title": model_or_adapter.validator.title, "schema": clean(model_or_adapter.core_schema)}
    return {
        "title": model_or_adapter.__pydantic_validator__.title,
        "schema": clean(model_or_adapter.__pydantic_core_schema__),
    }


def check_functions(node, where):
    if isinstance(node, dict):
        f = node.get("function")
        if isinstance(f, dict) and "<fn>" in str(f) and node.get("type", "").startswith("function"):
            name = f.get("function", {}).get("<fn>") if isinstance(f.get("function"), dict) else None
            if name not in FN_OK:
                raise SystemExit(f"{where}: 옮기지 않은 함수 검증기 {name}")
        for v in node.values():
            check_functions(v, where)
    elif isinstance(node, list):
        for v in node:
            check_functions(v, where)


async def results():
    """처리기가 내는 고정 결과 — 판마다 `_serialize`를 거친 사전을 JSON으로."""
    from mcp.server.runner import ServerRunner

    class _Conn:
        protocol_version = None

    out = {}
    for v in HANDSHAKE_PROTOCOL_VERSIONS:
        r = ServerRunner.__new__(ServerRunner)
        r.server = LOW
        r.init_options = None
        r.connection = _Conn()
        init = r._handle_initialize({"protocolVersion": v, "capabilities": {}, "clientInfo": {"name": "x", "version": "0"}})  # noqa: SLF001
        per = {"initialize": r._serialize("initialize", v, init)}  # noqa: SLF001
        for m in ("tools/list", "resources/list", "resources/templates/list", "prompts/list"):
            entry = LOW.get_request_handler(m)
            res = await entry.handler(None, entry.params_type.model_validate({}))
            per[m] = r._serialize(m, v, res)  # noqa: SLF001
        out[v] = {k: pydantic_core.to_json(val).decode() for k, val in per.items()}
    return out


def main(path: str) -> None:
    tools = server._tool_manager._tools  # noqa: SLF001
    tool_args = {}
    for name, t in tools.items():
        model = t.fn_metadata.arg_model
        entry = schema_of(model)
        entry["str_fields"] = [n for n, f in model.model_fields.items() if f.annotation is str]
        entry["aliases"] = {n: f.alias for n, f in model.model_fields.items() if f.alias}
        tool_args[name] = entry

    surface = {}
    for (m, v), cls in methods.CLIENT_REQUESTS.items():
        if v == LATEST_HANDSHAKE_VERSION:
            surface[m] = schema_of(cls)
    handshake_methods = {
        v: sorted(m for (m, vv) in methods.CLIENT_REQUESTS if vv == v) for v in KNOWN_PROTOCOL_VERSIONS
    }
    handlers = {}
    for m in sorted(LOW._request_handlers):  # noqa: SLF001
        handlers[m] = schema_of(LOW._request_handlers[m].params_type)  # noqa: SLF001

    out = {
        "_": "생성물 — cargo xtask mcp-tools. 손으로 고치지 않는다 (SYNC-STD-004#DEV-7)",
        "versions": {
            "mcp": importlib.metadata.version("mcp"),
            "pydantic": pydantic.VERSION,
            "pydantic_core": pydantic_core.__version__,
        },
        "server_name": LOW.name,
        "pydantic_url_prefix": f"https://errors.pydantic.dev/{'.'.join(pydantic.VERSION.split('.')[:2])}/v/",
        "protocol": {
            "known": list(KNOWN_PROTOCOL_VERSIONS),
            "handshake": list(HANDSHAKE_PROTOCOL_VERSIONS),
            "modern": list(MODERN_PROTOCOL_VERSIONS),
            "latest_handshake": LATEST_HANDSHAKE_VERSION,
            "default_negotiated": DEFAULT_NEGOTIATED_VERSION,
        },
        "spec_client_methods": sorted(methods.SPEC_CLIENT_METHODS),
        "methods_by_version": handshake_methods,
        "handled_methods": sorted(LOW._request_handlers),  # noqa: SLF001
        # RequestStateBoundary(미들웨어, 검증 전) — 이 메서드에 requestState가 오면 늘 거절(키가 프로세스마다 새것)
        "input_required_methods": sorted(methods.INPUT_REQUIRED_METHODS),
        "results": asyncio.run(results()),
        "schemas": {
            "envelope": schema_of(TypeAdapter(jsonrpc.JSONRPCMessage)),
            "surface": surface,
            "handlers": handlers,
            "initialize_params": schema_of(mcp_types.InitializeRequestParams),
            "tool_args": tool_args,
        },
    }
    check_functions(out["schemas"], "schemas")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
