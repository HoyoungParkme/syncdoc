"""SYNC-MS-008 테스트 관점 — queries.code_view · code_calls · code_source(카드 AY)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import queries
from app.core.codegraph import service as cg_service
from app.core.codegraph.service import CodeGraphService
from app.core.errors import NotFound
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.types import DocType
from tests.core.account.test_service import make_user
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import author, make_project, owner

MS = """---
doc_id: EXMP-MS-001
type: MS
title: 예시 MINISPEC
status: draft
upstream: [EXMP-PRD-001]
---
# MINISPEC

## 2. 함수

#### svc.save 저장
근거 [[EXMP-PRD-001#R1]]

**호출하는 것** [[#svc.check]] · [[#svc.gone]]

#### svc.check 검사

#### svc.gone 코드에 없는 것

#### svc.write 쓰기
"""


def _fn(key: str, qual: str, ms: str | None, end: int | None = None) -> dict:
    file, line = key.split(":")
    return {"key": key, "name": qual.split(".")[-1], "qual": qual, "file": file,
            "line": int(line), "end": end, "ms": ms}  # fmt: skip  — 옛 그래프 꼴(item 없음)


GRAPH = {
    "functions": [
        _fn("a.py:1", "svc.save", "EXMP-MS-001#svc.save", 4),
        _fn("a.py:5", "svc.check", "EXMP-MS-001#svc.check", 8),
        _fn("a.py:9", "svc.write", "EXMP-MS-001#svc.write", 12),
        _fn("a.py:13", "svc._help", None, 15),
    ],
    "calls": [
        ["a.py:1", "a.py:13", "graphify"],  # save → 도우미 → check (같음)
        ["a.py:13", "a.py:5", "enrich"],
        ["a.py:1", "a.py:9", "graphify"],  # save → write (코드만)
        ["a.py:9", "a.py:1", "graphify"],  # write → save (불리는 곳)
    ],
}


API = """---
doc_id: EXMP-API-001
type: API
title: 예시 API
status: draft
upstream: [EXMP-PRD-001]
---
# API

## 3. 엔드포인트

#### GET/api/code 코드 탭
근거 [[EXMP-PRD-001#R1]]
"""
UI = """---
doc_id: EXMP-UI-002
type: UI
title: 예시 화면
status: draft
upstream: [EXMP-PRD-001]
---
# 와이어프레임

## 1. 화면

#### UI-1 로그인
근거 [[EXMP-PRD-001#R1]]
"""
# item 있는 그래프(카드 BK) — GRAPH + 라우터(a.py:17, API 항목) + 화면 파일(함수 둘, 같은 UI 항목)
GRAPH_ITEMS = {
    "functions": [dict(f, item=f["ms"]) for f in GRAPH["functions"]]
    + [
        dict(_fn("a.py:17", "routers.get_code", None, 20), item="EXMP-API-001#GET/api/code"),
        dict(_fn("Page.tsx:3", "Page.helper", None), item="EXMP-UI-002#UI-1"),
        dict(_fn("Page.tsx:10", "Page.Page", None), item="EXMP-UI-002#UI-1"),
    ],
    "calls": GRAPH["calls"]
    + [
        ["a.py:17", "a.py:1", "graphify"],  # 라우터 → svc.save
        ["Page.tsx:10", "Page.tsx:3", "graphify"],  # 컴포넌트 → 같은 항목의 도우미
        ["Page.tsx:3", "a.py:17", "graphify"],  # 도우미 → 라우터
    ],
}  # fmt: skip


def _seed(scoped: Session, graph: dict | None = GRAPH):
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-MS-001", DocType.MS, MS, "h2", a, "spec: 테스트")
    d = svc.get_document("EXMP-MS-001")
    ref.extract(d.id, v.id, d.body, {i.item_id: i.pk for i in d.items}, ["EXMP-PRD-001"])
    if graph is not None:
        CodeGraphService(scoped).save(p.id, "c" * 40, "server", graph)
    return p


def _seed_items(scoped: Session, graph: dict | None = GRAPH_ITEMS):
    """_seed + API·UI 문서 — API·UI 항목의 함수(카드 BK)."""
    p = _seed(scoped, graph)
    svc, a = SpecService(scoped), author(scoped)
    svc.create(p.id, "EXMP-API-001", DocType.API, API, "h3", a, "spec: 테스트")
    svc.create(p.id, "EXMP-UI-002", DocType.UI, UI, "h4", a, "spec: 테스트")
    return p


async def test_code_view_ms_item_calls_in_order_and_callers(scoped: Session) -> None:
    _seed(scoped)
    v = await queries.code_view("EXMP-MS-001", "svc.save", owner(scoped))
    assert v.is_ms and not v.missing and v.graph.commit_hash == "c" * 40
    f = v.function
    assert (f.qual, f.file, f.line, f.end) == ("svc.save", "a.py", 1, 4)
    # 코드만 → 명세만 → 같음 순. 도우미를 건너 닿은 check는 같음
    assert [(c.ms_id.split("#")[1], c.status) for c in f.calls] == [
        ("svc.write", "code_only"),
        ("svc.gone", "spec_only"),
        ("svc.check", "same"),
    ]
    assert f.calls[1].qual is None  # 코드에 없는 명세 호출
    assert [c.ms_id for c in f.callers] == ["EXMP-MS-001#svc.write"]


async def test_code_view_missing_function_and_doc_level(scoped: Session) -> None:
    _seed(scoped)
    gone = await queries.code_view("EXMP-MS-001", "svc.gone", owner(scoped))
    assert gone.missing and gone.function is None
    doc = await queries.code_view("EXMP-MS-001", None, owner(scoped))
    assert [b.ms_id.split("#")[1] for b in doc.functions] == [
        "svc.save",
        "svc.check",
        "svc.gone",
        "svc.write",
    ]  # fmt: skip  블록 순서
    save = doc.functions[0]
    assert (save.same, save.code_only, save.spec_only) == (1, 1, 1)


async def test_code_view_non_ms_item_lists_downstream_chain_functions(scoped: Session) -> None:
    _seed(scoped)
    v = await queries.code_view("EXMP-PRD-001", "R1", owner(scoped))
    assert not v.is_ms and v.function is None
    assert [b.ms_id for b in v.functions] == ["EXMP-MS-001#svc.save"]  # R1을 근거로 삼는 함수
    none = await queries.code_view("EXMP-PRD-001", None, owner(scoped))
    assert none.functions == []  # 항목을 안 골랐으면 화면이 「항목을 고르세요」


async def test_code_view_api_and_ui_items_show_their_function_without_compare(scoped: Session) -> None:
    """MS-008 code_view 3a — API·UI 항목도 그 항목의 함수, 이웃은 항목 있는 함수까지, status None (카드 BK)."""
    _seed_items(scoped)
    v = await queries.code_view("EXMP-API-001", "GET/api/code", owner(scoped))
    assert not v.is_ms and not v.missing
    f = v.function
    assert (f.ms_id, f.qual, f.file, f.line, f.end) == ("EXMP-API-001#GET/api/code", "routers.get_code", "a.py", 17, 20)
    assert [(c.ms_id, c.qual, c.status) for c in f.calls] == [("EXMP-MS-001#svc.save", "svc.save", None)]
    assert [(c.ms_id, c.qual) for c in f.callers] == [("EXMP-UI-002#UI-1", "Page.helper")]
    assert v.functions == []  # 하위 체인은 그대로 — API 항목을 근거로 삼은 MINISPEC이 없다
    u = await queries.code_view("EXMP-UI-002", "UI-1", owner(scoped))
    assert u.function.qual == "Page.Page" and u.function.line == 10  # 파일 이름과 같은 컴포넌트
    assert [c.ms_id for c in u.function.calls] == ["EXMP-API-001#GET/api/code"]  # 같은 항목의 helper를 건너
    ms = await queries.code_view("EXMP-MS-001", "svc.save", owner(scoped))  # MINISPEC 회귀 — 대조 그대로
    assert [c.status for c in ms.function.calls] == ["code_only", "spec_only", "same"]
    assert [c.ms_id for c in ms.function.callers] == ["EXMP-MS-001#svc.write"]


async def test_code_view_api_item_on_old_graph_has_no_function(scoped: Session) -> None:
    _seed_items(scoped, GRAPH)  # item 없는 옛 그래프
    v = await queries.code_view("EXMP-API-001", "GET/api/code", owner(scoped))
    assert v.function is None and not v.missing and v.functions == []


async def test_code_view_without_graph_and_not_owned(scoped: Session) -> None:
    _seed(scoped, graph=None)
    v = await queries.code_view("EXMP-MS-001", "svc.save", owner(scoped))
    assert v.graph is None and v.function is None
    with pytest.raises(NotFound):
        await queries.code_view("EXMP-MS-001", "svc.save", owner(scoped, "minjun"))


async def test_spec_change_reflects_without_rebuilding_graph(scoped: Session) -> None:
    """대조는 읽을 때 계산한다 — 「호출하는 것」만 바꾸면 그래프를 안 바꿔도 결과가 바뀐다."""
    _seed(scoped)
    body = MS.replace("[[#svc.check]] · [[#svc.gone]]", "[[#svc.check]] · [[#svc.write]]")
    scoped.execute(
        text("UPDATE documents SET current_body = :b WHERE doc_id = 'EXMP-MS-001'"), {"b": body}
    )
    v = await queries.code_view("EXMP-MS-001", "svc.save", owner(scoped))
    assert [c.status for c in v.function.calls] == ["same", "same"]


async def test_code_calls_three_kinds(scoped: Session) -> None:
    _seed(scoped)
    calls = await queries.code_calls("EXMP", owner(scoped))
    got = {(e.from_.split("#")[1], e.to.split("#")[1], e.status) for e in calls.edges}
    assert got == {
        ("svc.save", "svc.check", "same"),
        ("svc.save", "svc.write", "code_only"),
        ("svc.save", "svc.gone", "spec_only"),
        ("svc.write", "svc.save", "code_only"),
    }
    assert calls.graph.function_count == 4


async def test_code_nodes_lists_everything_with_status_and_communities(scoped: Session) -> None:
    graph = {
        "functions": [dict(f, item=f["ms"], community=0 if f["file"] == "a.py" else None)
                      for f in GRAPH["functions"]]
        + [dict(_fn("r.py:1", "routers.get_code", None, 3), item="EXMP-API-001#GET/api/code")],
        "calls": GRAPH["calls"],
        "communities": [{"id": 0, "label": "svc", "size": 4}],
    }  # fmt: skip
    _seed(scoped, graph)
    nodes = await queries.code_nodes("EXMP", owner(scoped))
    assert nodes.graph.function_count == 5 and [c.label for c in nodes.communities] == ["svc"]
    by = {f.qual: f for f in nodes.functions}
    # 코드만이 하나라도 있으면 code_only > 명세만 > 같음 · 도우미는 항목 없음
    assert (by["svc.save"].ms, by["svc.save"].status) == ("EXMP-MS-001#svc.save", "code_only")
    assert by["svc.save"].item == "EXMP-MS-001#svc.save"
    assert (by["svc.write"].ms, by["svc.write"].status) == ("EXMP-MS-001#svc.write", "code_only")
    assert by["svc.check"].status == "same" and by["svc._help"].ms is None and by["svc._help"].item is None
    # API 항목 함수 — item만, 대조는 없다 (카드 BJ)
    r = by["routers.get_code"]
    assert (r.item, r.ms, r.status) == ("EXMP-API-001#GET/api/code", None, None)
    assert all(f.community == (0 if f.file == "a.py" else None) for f in nodes.functions)
    assert nodes.calls == [[a, b] for a, b, _ in GRAPH["calls"]]  # via는 싣지 않는다


async def test_code_nodes_old_graph_no_graph_and_not_owned(scoped: Session) -> None:
    _seed(scoped)  # GRAPH 그대로 — 커뮤니티·item을 모르는 옛 그래프
    nodes = await queries.code_nodes("EXMP", owner(scoped))
    assert nodes.communities == [] and all(f.community is None for f in nodes.functions)
    assert all(f.item == f.ms for f in nodes.functions)  # item이 없으면 ms로 (카드 BJ)
    with pytest.raises(NotFound):
        await queries.code_nodes("EXMP", make_user(scoped, login="stranger"))
    scoped.execute(text("DELETE FROM code_graphs"))
    assert (await queries.code_nodes("EXMP", owner(scoped))).graph is None


async def test_code_source_reads_function_range_from_graph_commit(
    scoped: Session, monkeypatch
) -> None:
    _seed(scoped)
    seen = []

    async def fake_read(workdir, path, ref="HEAD"):
        seen.append((path, ref))
        return "\n".join(f"line {i}" for i in range(1, 21))

    monkeypatch.setattr(cg_service.git, "read", fake_read)
    t = await queries.code_source("EXMP-MS-001", "svc.check", owner(scoped))
    assert (t.path, t.start, t.end, t.text) == ("a.py", 5, 8, "line 5\nline 6\nline 7\nline 8")
    assert seen == [("a.py", "c" * 40)]  # 그래프 커밋에서
    with pytest.raises(NotFound):  # 코드에 없는 함수
        await queries.code_source("EXMP-MS-001", "svc.gone", owner(scoped))


async def test_code_source_reads_api_item_function_by_item(scoped: Session, monkeypatch) -> None:
    """MS-008 code_source 2 — compare로 못 찾으면 item으로 (카드 BK)."""
    _seed_items(scoped)

    async def fake_read(workdir, path, ref="HEAD"):
        return "\n".join(f"line {i}" for i in range(1, 21))

    monkeypatch.setattr(cg_service.git, "read", fake_read)
    t = await queries.code_source("EXMP-API-001", "GET/api/code", owner(scoped))
    assert (t.path, t.start, t.end) == ("a.py", 17, 20)


async def test_code_text_reads_any_function_by_file_and_line(scoped: Session, monkeypatch) -> None:
    """MS-008 code_text — 항목 없는 함수도 파일·줄로 (카드 BF)."""
    _seed(scoped)
    seen = []

    async def fake_read(workdir, path, ref="HEAD"):
        seen.append((path, ref))
        return "\n".join(f"line {i}" for i in range(1, 21))

    monkeypatch.setattr(cg_service.git, "read", fake_read)
    t = await queries.code_text("EXMP", "a.py", 13, owner(scoped))  # svc._help — 항목 없음
    assert (t.path, t.start, t.end, t.text) == ("a.py", 13, 15, "line 13\nline 14\nline 15")
    assert seen == [("a.py", "c" * 40)]  # 그래프 커밋에서
    # end 없는 함수는 같은 파일 다음 함수 앞 줄까지, 마지막이면 +59 (code_source와 같은 규칙)
    g = {**GRAPH, "functions": [dict(f, end=None) for f in GRAPH["functions"]]}
    CodeGraphService(scoped).save(_project_id(scoped), "d" * 40, "server", g)
    t = await queries.code_text("EXMP", "a.py", 1, owner(scoped))
    assert (t.start, t.end) == (1, 4)
    t = await queries.code_text("EXMP", "a.py", 13, owner(scoped))
    assert (t.start, t.end) == (13, 20)  # 파일이 20줄이라 read가 자른다
    with pytest.raises(NotFound) as ei:  # 그 자리에 함수 없음
        await queries.code_text("EXMP", "a.py", 2, owner(scoped))
    assert ei.value.extra["resource"] == "function"
    with pytest.raises(NotFound):  # 남의 것
        await queries.code_text("EXMP", "a.py", 1, make_user(scoped, "minjun"))


def _project_id(scoped: Session) -> int:
    return scoped.execute(text("SELECT id FROM projects WHERE code='EXMP'")).scalar_one()
