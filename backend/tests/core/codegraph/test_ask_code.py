"""SYNC-MS-008 테스트 관점 — ask_tool의 code_graph · read_code(카드 AZ)."""

import json

from sqlalchemy.orm import Session

from app.core import queries
from app.core.codegraph import service as cg_service
from app.infra.git import GitError
from tests.core.codegraph.test_queries import _seed
from tests.core.spec.test_service import owner

FILE = "\n".join(f"line {i}" for i in range(1, 21))


def _fake_git(monkeypatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []

    async def fake_read(workdir, path, ref="HEAD"):
        seen.append((path, ref))
        if path != "a.py":
            raise GitError(["git", "show"], "없음")
        return FILE

    monkeypatch.setattr(cg_service.git, "read", fake_read)
    return seen


async def test_code_graph_tool(scoped: Session) -> None:
    _seed(scoped)
    r = await queries.ask_tool(
        "code_graph",
        {"doc_id": "EXMP-MS-001", "item_id": "svc.save", "reason": "대조"},
        "EXMP",
        owner(scoped),
        0,
    )
    data = json.loads(r.text)
    assert r.target == "코드:EXMP-MS-001#svc.save"
    assert data["graph"]["commit"] == "c" * 7 and data["function"]["file"] == "a.py"
    assert [(c["id"].split("#")[1], c["status"]) for c in data["function"]["calls"]] == [
        ("svc.write", "code_only"),
        ("svc.gone", "spec_only"),
        ("svc.check", "same"),
    ]


async def test_code_graph_tool_without_graph(scoped: Session) -> None:
    _seed(scoped, graph=None)
    r = await queries.ask_tool(
        "code_graph",
        {"doc_id": "EXMP-MS-001", "item_id": "svc.save", "reason": "대조"},
        "EXMP",
        owner(scoped),
        0,
    )
    assert json.loads(r.text)["error"] == "코드 그래프 없음" and r.target is None


async def test_read_code_three_forms_numbered_and_denied(scoped: Session, monkeypatch) -> None:
    _seed(scoped)
    seen = _fake_git(monkeypatch)
    u = owner(scoped)

    async def read(target: str) -> tuple[str | None, dict]:
        r = await queries.ask_tool("read_code", {"target": target, "reason": "본문"}, "EXMP", u, 0)
        return r.target, json.loads(r.text)

    t, d = await read("EXMP-MS-001#svc.check")  # 항목 ID
    assert t == "코드:a.py:5-8" and d["text"] == "5: line 5\n6: line 6\n7: line 7\n8: line 8"
    t2, d2 = await read("svc.check")  # 함수 이름 — 같은 줄
    assert (t2, d2["text"]) == (t, d["text"])
    t3, d3 = await read("a.py:2-3")  # 경로:시작-끝
    assert t3 == "코드:a.py:2-3" and d3["text"] == "2: line 2\n3: line 3"
    assert all(ref == "c" * 40 for _, ref in seen)  # 그래프 커밋에서
    for bad in (".env", "없는.py", "EXMP-MS-001#svc.gone"):
        tb, db = await read(bad)
        assert tb is None and db["error"] == "없음" and "code_graph" in db["hint"], bad
