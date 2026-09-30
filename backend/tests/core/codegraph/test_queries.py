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
            "line": int(line), "end": end, "ms": ms}  # fmt: skip


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
