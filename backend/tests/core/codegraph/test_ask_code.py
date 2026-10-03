"""SYNC-MS-008 테스트 관점 — ask_tool의 code_graph · read_code(카드 AZ)."""

import json

from sqlalchemy.orm import Session

from app.core import queries
from app.core.codegraph import service as cg_service
from app.infra.git import GitError
from tests.core.codegraph.test_queries import GRAPH, _fn, _seed, _seed_items
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


async def test_read_code_takes_what_the_context_shows(scoped: Session, monkeypatch) -> None:
    """#286 — 맥락·code_graph가 보인 꼴(file:줄·en dash 범위·맨 이름)도 같은 줄을 읽는다."""
    _seed(scoped)
    _fake_git(monkeypatch)
    u = owner(scoped)

    async def read(target: str) -> tuple[str | None, dict]:
        r = await queries.ask_tool("read_code", {"target": target, "reason": "본문"}, "EXMP", u, 0)
        return r.target, json.loads(r.text)

    want = await read("EXMP-MS-001#svc.check")  # a.py 5–8
    for same in ("a.py:5", "a.py:6", "check", "a.py:5–8"):  # 시작 줄·안쪽 줄·맨 이름·en dash
        assert await read(same) == want, same
    t, d = await read("a.py:17")  # 함수 밖 줄 — 그 줄부터 파일 끝까지
    assert t == "코드:a.py:17-20" and d["text"].split("\n")[0] == "17: line 17"


async def test_read_code_ambiguous_name_gives_candidates(scoped: Session, monkeypatch) -> None:
    """#286 — 이름이 여럿이면 「없음」에 후보(`file:줄 qual`)를 싣는다."""
    _seed(
        scoped,
        graph=dict(GRAPH, functions=[*GRAPH["functions"], _fn("b.py:1", "other.check", None, 3)]),
    )
    _fake_git(monkeypatch)
    r = await queries.ask_tool(
        "read_code", {"target": "check", "reason": "본문"}, "EXMP", owner(scoped), 0
    )
    d = json.loads(r.text)
    assert r.target is None and d["error"] == "없음" and "code_graph" in d["hint"]
    assert d["candidates"] == ["a.py:5 svc.check", "b.py:1 other.check"]


async def test_code_graph_and_read_code_take_api_item(scoped: Session, monkeypatch) -> None:
    """카드 BK — API 항목의 함수를 code_graph가 대조 없이 보이고, read_code가 항목 ID로 읽는다."""
    _seed_items(scoped)
    seen = _fake_git(monkeypatch)
    u = owner(scoped)
    r = await queries.ask_tool(
        "code_graph",
        {"doc_id": "EXMP-API-001", "item_id": "GET/api/code", "reason": "라우터"},
        "EXMP",
        u,
        0,
    )
    data = json.loads(r.text)
    assert data["is_ms"] is False and data["function"]["qual"] == "routers.get_code"
    assert data["function"]["calls"] == [
        {
            "id": "EXMP-MS-001#svc.save",
            "status": None,
            "qual": "svc.save",
            "file": "a.py",
            "line": 1,
        }
    ]
    r2 = await queries.ask_tool(
        "read_code", {"target": "EXMP-API-001#GET/api/code", "reason": "본문"}, "EXMP", u, 0
    )
    d2 = json.loads(r2.text)
    assert r2.target == "코드:a.py:17-20" and d2["text"].startswith("17: line 17\n18: line 18")
    assert seen == [("a.py", "c" * 40)]


async def _find(scoped: Session, query: str) -> tuple[str | None, dict]:
    r = await queries.ask_tool(
        "find_code", {"query": query, "reason": "찾기"}, "EXMP", owner(scoped), 0
    )
    return r.target, json.loads(r.text)


async def test_find_code_names_and_callers(scoped: Session, monkeypatch) -> None:
    """#302 — 이름 일부로 함수와 불리는 곳. 똑같은 이름이 먼저, 나머지는 파일·줄 순. 항목을 싣는다."""
    _seed_items(scoped)
    t, d = await _find(scoped, "check")
    assert t == "코드검색:check" and d["total"] == 1 and d["more"] == 0
    f = d["functions"][0]
    assert (f["qual"], f["file"], f["line"], f["item"]) == (
        "svc.check",
        "a.py",
        5,
        "EXMP-MS-001#svc.check",
    )
    assert (
        f["callers"] == [{"qual": "svc._help", "file": "a.py", "line": 13}]
        and f["more_callers"] == 0
    )
    _, d2 = await _find(scoped, "svc.")
    assert [x["qual"] for x in d2["functions"]] == [
        "svc.save",
        "svc.check",
        "svc.write",
        "svc._help",
    ]
    _, d3 = await _find(scoped, "write")
    assert d3["functions"][0]["qual"] == "svc.write"
    monkeypatch.setattr(queries, "_FIND_FUNCTIONS", 2)
    monkeypatch.setattr(queries, "_FIND_CALLERS", 0)
    _, d4 = await _find(scoped, "a.py")
    assert len(d4["functions"]) == 2 and d4["total"] >= 4 and d4["more"] == d4["total"] - 2
    assert all(x["callers"] == [] for x in d4["functions"])
    assert d4["functions"][0]["more_callers"] >= 1  # svc.save ← svc.write … — 상한 0이라 전부 넘친 수


async def test_find_code_exact_name_first_none_and_no_graph(scoped: Session) -> None:
    """#302 — 똑같은 이름이 먼저 · 맞는 것 없음은 빈 목록과 hint · 그래프 없음은 error."""
    _seed(
        scoped,
        graph=dict(GRAPH, functions=[*GRAPH["functions"], _fn("0.py:1", "x.save_all", None, 3)]),
    )
    _, d = await _find(scoped, "save")
    assert [x["qual"] for x in d["functions"]] == ["svc.save", "x.save_all"]
    _, none = await _find(scoped, "zzz")
    assert none["functions"] == [] and none["total"] == 0 and "더 짧은" in none["hint"]


async def test_find_code_without_graph(scoped: Session) -> None:
    _seed(scoped, graph=None)
    t, d = await _find(scoped, "svc")
    assert t is None and d["error"] == "코드 그래프 없음"
