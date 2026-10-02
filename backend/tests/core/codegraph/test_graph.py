"""SYNC-MS-011 테스트 관점 — codegraph 순수 함수 여섯(카드 AX). DB를 안 쓴다."""

import json
from pathlib import Path

import pytest

from app.core.codegraph import graph as cg
from app.core.errors import CodeGraphFailed
from app.core.types import CallDiff


# ── touches_code ──
def test_touches_code_only_code_outside_specs() -> None:
    assert cg.touches_code(["docs/specs/02-PRD/X-PRD-001.md"]) is False
    assert cg.touches_code(["docs/specs/02-PRD/X-PRD-001.md", "backend/app/x.py"]) is True
    assert cg.touches_code(["docs/specs/assets/x.js"]) is False  # 명세 아래는 코드가 아니다
    assert cg.touches_code(["graphify-out/graph.json", "sub/graphify-out/cache.py"]) is False
    assert cg.touches_code(["frontend/src/App.tsx"]) is True


# ── reduce ──
RAW = {
    "nodes": [
        {"id": "f_mod", "label": "app/core/pipeline.py", "source_file": "app/core/pipeline.py",
         "source_location": "L1"},
        {"id": "c_svc", "label": "SpecService", "_callable": True, "_callable_class": True,
         "source_file": "app/core/spec/service.py", "source_location": "L10"},
        {"id": "m_get", "label": ".get_document()", "_callable": True,
         "source_file": "app/core/spec/service.py", "source_location": "L20"},
        {"id": "f_save", "label": "save_pipeline()", "_callable": True,
         "source_file": "app/core/pipeline.py", "source_location": "L30"},
        {"id": "f_help", "label": "_run()", "_callable": True,
         "source_file": "app/core/pipeline.py", "source_location": "L50"},
        {"id": "f_cg", "label": "load()", "_callable": True,
         "source_file": "app/core/codegraph/service.py", "source_location": "L5"},
        {"id": "r1", "label": "EXMP-MS-007#pipeline.save_pipeline 설명", "file_type": "rationale"},
        {"id": "r2", "label": "EXMP-API-001#GET/api/docs/{docId}/code — 코드 탭", "file_type": "rationale"},
    ],
    "links": [
        {"source": "c_svc", "target": "m_get", "relation": "method"},
        {"source": "r1", "target": "f_save", "relation": "rationale_for"},
        {"source": "r2", "target": "f_help", "relation": "rationale_for"},
        {"source": "f_save", "target": "f_help", "relation": "calls"},
        {"source": "f_save", "target": "f_help", "relation": "indirect_call"},
        {"source": "f_help", "target": "c_svc", "relation": "calls"},
        {"source": "f_mod", "target": "f_save", "relation": "contains"},
        {"source": "f_save", "target": "f_save", "relation": "calls"},
    ],
}  # fmt: skip


def test_reduce_keeps_functions_and_calls_only() -> None:
    g = cg.reduce(RAW)
    by = {f["name"]: f for f in g["functions"]}
    assert set(by) == {"get_document", "save_pipeline", "_run", "load"}  # 클래스·파일 노드는 빠진다
    assert by["get_document"]["qual"] == "SpecService.get_document"  # method 선으로 클래스
    assert by["save_pipeline"]["qual"] == "pipeline.save_pipeline"
    assert by["load"]["qual"] == "codegraph.load"  # service.py는 폴더 이름
    assert by["save_pipeline"]["ms"] == "EXMP-MS-007#pipeline.save_pipeline"
    assert by["save_pipeline"]["item"] == by["save_pipeline"]["ms"]  # MINISPEC ID는 item·ms 둘 다
    # API ID는 item에만 — `#` 뒤의 `/`·`{}`를 품고 ` — 설명`은 잘린다 (카드 BJ)
    assert by["_run"]["item"] == "EXMP-API-001#GET/api/docs/{docId}/code"
    assert by["_run"]["ms"] is None
    assert by["load"]["item"] is None and by["load"]["ms"] is None
    assert by["save_pipeline"]["key"] == "app/core/pipeline.py:30" and by["_run"]["line"] == 50
    # 같은 호출 둘은 하나, 자기 호출·클래스로 가는 선·포함 선은 없다
    assert g["calls"] == [["app/core/pipeline.py:30", "app/core/pipeline.py:50", "graphify"]]


# ── communities ──
RAW2 = {
    "nodes": [
        {"id": "fa", "label": "a.py", "source_file": "app/a.py", "source_location": "L1"},
        {"id": "f1", "label": "f1()", "_callable": True, "source_file": "app/a.py",
         "source_location": "L2"},
        {"id": "f2", "label": "f2()", "_callable": True, "source_file": "app/a.py",
         "source_location": "L5"},
        {"id": "fb", "label": "b.py", "source_file": "app/b.py", "source_location": "L1"},
        {"id": "g1", "label": "g1()", "_callable": True, "source_file": "app/b.py",
         "source_location": "L2"},
        {"id": "g2", "label": "g2()", "_callable": True, "source_file": "app/b.py",
         "source_location": "L9"},
        {"id": "t1", "label": "test_x()", "_callable": True, "source_file": "tests/test_x.py",
         "source_location": "L3"},
        {"id": "d1", "label": "노트", "file_type": "document", "node_kind": "heading",
         "source_file": "docs/n.md", "source_location": "L3"},  # 문서도 source_file이 있다
    ],
    "links": [
        {"source": "fa", "target": "f1", "relation": "contains"},
        {"source": "fa", "target": "f2", "relation": "contains"},
        {"source": "f1", "target": "f2", "relation": "calls"},
        {"source": "fb", "target": "g1", "relation": "contains"},
        {"source": "fb", "target": "g2", "relation": "contains"},
        {"source": "g1", "target": "g2", "relation": "calls"},
        {"source": "g1", "target": "g2", "relation": "calls"},
        {"source": "t1", "target": "g1", "relation": "calls"},
        # 문서 노드가 b.py 군집의 차수 최고 — 그래도 라벨은 코드 노드 이름 (#255)
        {"source": "d1", "target": "fb", "relation": "references"},
        {"source": "d1", "target": "g1", "relation": "references"},
        {"source": "d1", "target": "g2", "relation": "references"},
        {"source": "d1", "target": "t1", "relation": "references"},
    ],
}  # fmt: skip


def test_communities_groups_by_file_labels_by_hub_and_is_deterministic() -> None:
    graph = cg.reduce(RAW2)
    graph["functions"].append(  # enrich가 더한 정의 — 파일로 커뮤니티를 받는다
        {"key": "app/b.py:30", "name": "g3", "qual": "b.g3", "file": "app/b.py", "line": 30,
         "end": None, "ms": None}  # fmt: skip
    )
    out = cg.communities(RAW2, graph)
    assert out is graph
    by = {f["name"]: f["community"] for f in graph["functions"]}
    assert by["f1"] == by["f2"] and by["g1"] == by["g2"] == by["g3"] and by["f1"] != by["g1"]
    assert all(c is not None for c in by.values())
    comms = graph["communities"]
    assert [c["size"] for c in comms] == [3, 2]  # 함수 수 내림차순 · 테스트·문서만 든 군집은 없다
    assert {c["id"] for c in comms} == {by["g1"], by["f1"]}
    assert by["g1"] == 0  # 노드가 가장 많은 군집(fb·g1·g2·t1)이 0 (#253)
    assert all(c["label"] and not c["label"].endswith("()") for c in comms)
    assert "노트" not in [c["label"] for c in comms]  # 문서 허브는 라벨이 못 된다 (#255)
    again = cg.communities(RAW2, cg.reduce(RAW2))
    assert [f["community"] for f in again["functions"]] == [
        f["community"] for f in graph["functions"] if f["name"] != "g3"
    ]


def test_communities_without_nodes_leaves_none_and_empty() -> None:
    graph = cg.reduce(RAW)
    out = cg.communities({"nodes": [], "links": []}, graph)
    assert out["communities"] == [] and all(f["community"] is None for f in out["functions"])


# ── enrich ──
SVC = '''
class SpecService:
    def __init__(self, s):
        self.s = s

    def get_document(self, doc_id):
        """EXMP-MS-002#SpecService.get_document"""
        return self.item_blocks(doc_id)

    def item_blocks(self, doc_id):
        return []


class ReferenceService:
    def upstream(self, pk):
        return []
'''
PIPE = '''
from spec import SpecService, ReferenceService


def by_assign(s):
    """EXMP-MS-007#pipeline.by_assign"""
    spec = SpecService(s)
    return spec.get_document("x")


def by_tuple(s):
    """EXMP-API-001#POST/api/x/{id} — 라우터 (카드 BJ)"""
    spec, refs = SpecService(s), ReferenceService()
    return refs.upstream(1)


def by_inline(s):
    return SpecService(s).get_document("y")


def by_annotation(spec: SpecService, other: "ReferenceService | None" = None):
    other.upstream(2)
    return spec.get_document("z")


@decorate
def decorated(s):
    Unknown(s).get_document("n")  # 모르는 클래스는 잇지 않는다
    return SpecService(s).item_blocks("d")
'''


def _src(tmp_path: Path) -> Path:
    (tmp_path / "spec.py").write_text(SVC, encoding="utf-8")
    (tmp_path / "pipe.py").write_text(PIPE, encoding="utf-8")
    return tmp_path


def _fn(file: str, line: int, name: str) -> dict:
    return {"key": f"{file}:{line}", "name": name, "qual": "", "file": file, "line": line,
            "end": None, "item": None, "ms": None}  # fmt: skip


def test_enrich_resolves_five_forms_and_fixes_names(tmp_path: Path) -> None:
    src = _src(tmp_path)
    # graphify가 잡은 것처럼 — get_document과 by_assign 둘만, 선은 by_assign→get_document 하나
    g = {
        "functions": [_fn("spec.py", 6, "get_document"), _fn("pipe.py", 5, "by_assign")],
        "calls": [["pipe.py:5", "spec.py:6", "graphify"]],
    }
    cg.enrich(src, g)
    by = {f["qual"]: f for f in g["functions"]}
    assert by["SpecService.get_document"]["ms"] == "EXMP-MS-002#SpecService.get_document"
    assert by["pipe.by_assign"]["ms"] == "EXMP-MS-007#pipeline.by_assign"
    assert by["pipe.by_assign"]["item"] == by["pipe.by_assign"]["ms"]
    # API docstring은 item만 — 대조(ms) 대상이 아니다 (카드 BJ)
    assert (by["pipe.by_tuple"]["item"], by["pipe.by_tuple"]["ms"]) == ("EXMP-API-001#POST/api/x/{id}", None)
    assert by["pipe.by_inline"]["item"] is None
    assert by["SpecService.get_document"]["end"] == 8  # 끝 줄을 AST로
    assert "pipe.decorated" in by  # graphify가 놓친 정의는 더한다 (데코레이터가 있어도)
    k = {q: f["key"] for q, f in by.items()}
    enriched = {(a, b) for a, b, via in g["calls"] if via == "enrich"}
    assert (k["pipe.by_tuple"], k["ReferenceService.upstream"]) in enriched  # 튜플 대입
    assert (k["pipe.by_inline"], k["SpecService.get_document"]) in enriched  # 즉석 생성
    assert (k["pipe.by_annotation"], k["SpecService.get_document"]) in enriched  # 인자 주석
    assert (k["pipe.by_annotation"], k["ReferenceService.upstream"]) in enriched  # 문자열 주석
    assert (k["SpecService.get_document"], k["SpecService.item_blocks"]) in enriched  # self
    assert (k["pipe.decorated"], k["SpecService.item_blocks"]) in enriched
    # graphify가 이미 잡은 선(by_assign→get_document)은 겹치지 않는다
    pairs = [(a, b) for a, b, _ in g["calls"]]
    assert pairs.count((k["pipe.by_assign"], k["SpecService.get_document"])) == 1
    assert not any(b.startswith("Unknown") for _, b in pairs)


def test_enrich_skips_other_languages_and_broken_files(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("export function f() {}", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    g = {"functions": [_fn("a.ts", 1, "f"), _fn("bad.py", 1, "x")], "calls": []}
    cg.enrich(tmp_path, g)
    assert [f["qual"] for f in g["functions"]] == ["", ""]  # 손대지 않는다
    assert [f["item"] for f in g["functions"]] == [None, None]  # 화면 ID 없는 파일은 그대로


def test_enrich_gives_screen_id_of_file_head_comment_to_all_its_functions(tmp_path: Path) -> None:
    """MS-011 enrich 3 — 화면 코드는 파일 첫 주석의 화면 ID를 그 파일 함수 전부에 (카드 BJ)."""
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "CodeGraph.tsx").write_text(
        "/** UI-17 코드 그래프 — EXMP-UI-002#UI-17 (카드 BD).\n *  1 헤더 */\n"
        "import x from 'y'\nconst a = () => 1\nexport function CodeGraph() {}\n",
        encoding="utf-8",
    )
    (tmp_path / "pages" / "ui.tsx").write_text(
        "// 공용 부품 — 화면 ID 없음 (DEV-17 밖)\nexport function Badge() {}\n", encoding="utf-8"
    )
    (tmp_path / "pages" / "late.ts").write_text(
        "import z from 'z'\n// EXMP-UI-002#UI-5 는 첫 주석이 아니다\nexport function f() {}\n",
        encoding="utf-8",
    )
    own = dict(_fn("pages/CodeGraph.tsx", 4, "a"), item="EXMP-API-001#GET/x")  # 함수 ID가 우선
    g = {
        "functions": [own, _fn("pages/CodeGraph.tsx", 5, "CodeGraph"), _fn("pages/ui.tsx", 2, "Badge"),
                      _fn("pages/late.ts", 3, "f")],
        "calls": [],
    }  # fmt: skip
    cg.enrich(tmp_path, g)
    by = {f["name"]: f for f in g["functions"]}
    assert by["CodeGraph"]["item"] == "EXMP-UI-002#UI-17" and by["CodeGraph"]["ms"] is None
    assert by["a"]["item"] == "EXMP-API-001#GET/x"  # 이미 있는 item은 안 덮는다
    assert by["Badge"]["item"] is None and by["f"]["item"] is None


# ── spec_calls ──
def test_spec_calls_reads_only_the_calls_line() -> None:
    items = [
        ("X-MS-007#pipeline.save", "처리 `pipeline.other` 을 부른다\n"
         "**호출하는 것** [[#pipeline.other]] · [[X-MS-002#SpecService.get]] · `git.fetch` `exists`"),
        ("X-MS-007#pipeline.other", "**호출하는 것** 없음"),
        ("X-MS-002#SpecService.get", "처리만 있다"),
        ("X-MS-009#git.fetch", ""),
    ]  # fmt: skip
    got = cg.spec_calls(items)
    assert got["X-MS-007#pipeline.save"] == {
        "X-MS-007#pipeline.other",  # [[#…]]는 같은 문서
        "X-MS-002#SpecService.get",
        "X-MS-009#git.fetch",  # 백틱 이름이 항목이면 들어간다 — `exists`는 항목이 아니라 빠진다
    }
    assert got["X-MS-007#pipeline.other"] == set() and got["X-MS-002#SpecService.get"] == set()


def test_spec_calls_drops_ambiguous_short_names() -> None:
    items = [("A-MS-001#x.run", "**호출하는 것** `y.go`"), ("A-MS-002#y.go", ""),
             ("A-MS-003#y.go", "")]  # fmt: skip
    assert cg.spec_calls(items)["A-MS-001#x.run"] == set()  # 같은 이름 둘 — 모호하다


# ── compare ──
def _g(funcs: list[tuple[str, str | None, str]], calls: list[tuple[str, str]]) -> dict:
    return {
        "functions": [{"key": k, "name": q.split(".")[-1], "qual": q, "file": "f", "line": 1,
                       "end": None, "ms": m} for k, m, q in funcs],
        "calls": [[a, b, "graphify"] for a, b in calls],
    }  # fmt: skip


def test_compare_walks_helpers_and_splits_three_ways() -> None:
    g = _g(
        [
            ("a", "X#p.save", "p.save"),
            ("h", None, "p._run"),  # 도우미 — 건너 계속
            ("v", "X#S.validate", "S.validate"),
            ("w", "X#S.write", "S.write"),
            ("deep", "X#S.deep", "S.deep"),  # write 너머 — 안 간다
            ("n", None, "git.fetch"),  # docstring 없는 함수 — 이름으로 잇는다
        ],
        [("a", "h"), ("h", "v"), ("h", "a"), ("a", "w"), ("w", "deep"), ("a", "n")],
    )
    spec = {
        "X#p.save": {"X#S.validate", "X#S.gone"},
        "X#S.validate": set(),
        "X#S.write": {"X#S.deep"},
        "X#S.deep": set(),
        "X#git.fetch": set(),
        "X#S.gone": set(),
    }
    diffs = {d.ms_id: d for d in cg.compare(g, spec)}
    assert diffs["X#p.save"] == CallDiff(
        "X#p.save", "a", ["X#S.validate"], ["X#S.write", "X#git.fetch"], ["X#S.gone"]
    )
    assert diffs["X#S.write"].same == ["X#S.deep"] and not diffs["X#S.write"].code_only
    assert diffs["X#git.fetch"].function == "n"  # 이름으로 이어졌다
    assert diffs["X#S.gone"] == CallDiff("X#S.gone", None, [], [], [])  # 코드에 없음


# ── item_function · item_neighbors (카드 BK) ──
def _gi(funcs: list[tuple[str, str, str | None]], calls: list[tuple[str, str]]) -> dict:
    """(key=파일:줄, qual, item) — 이름은 qual의 끝, ms는 item이 MS일 때."""
    out = []
    for k, q, it in funcs:
        file, line = k.split(":")
        out.append({"key": k, "name": q.split(".")[-1], "qual": q, "file": file, "line": int(line),
                    "end": None, "item": it, "ms": it if it and "-MS-" in it else None})  # fmt: skip
    return {"functions": out, "calls": [[a, b, "graphify"] for a, b in calls]}


SCREEN = _gi(
    [
        ("pages/Page.tsx:3", "Page.helper", "X-UI-002#UI-1"),  # 같은 항목의 도우미
        ("pages/Page.tsx:10", "Page.Page", "X-UI-002#UI-1"),  # 파일 이름과 같은 컴포넌트
        ("pages/panes.tsx:2", "panes.Left", "X-UI-002#UI-1"),  # 같은 항목, 다른 파일
        ("r.py:1", "code.get_code", "X-API-001#GET/api/code"),  # 라우터
        ("q.py:1", "queries.view", "X-MS-008#queries.view"),
        ("q.py:9", "queries._help", None),  # 도우미
        ("q.py:20", "SpecService.get", "X-MS-002#SpecService.get"),
        ("q.py:30", "queries.deep", "X-MS-008#queries.deep"),  # get 너머 — 안 간다
    ],
    [
        ("pages/Page.tsx:10", "pages/Page.tsx:3"),
        ("pages/Page.tsx:3", "r.py:1"),
        ("pages/panes.tsx:2", "r.py:1"),
        ("r.py:1", "q.py:1"),
        ("q.py:1", "q.py:9"),
        ("q.py:9", "q.py:20"),
        ("q.py:20", "q.py:30"),
        ("q.py:9", "r.py:1"),  # 사이클
    ],
)


def test_item_function_prefers_file_stem_then_first() -> None:
    assert cg.item_function(SCREEN, "X-UI-002#UI-1")["qual"] == "Page.Page"  # 파일 이름과 같은 것
    assert cg.item_function(SCREEN, "X-API-001#GET/api/code")["key"] == "r.py:1"
    no_stem = {"functions": [f for f in SCREEN["functions"] if f["qual"] != "Page.Page"], "calls": []}
    assert cg.item_function(no_stem, "X-UI-002#UI-1")["qual"] == "Page.helper"  # (파일, 줄) 순 첫 함수
    assert cg.item_function(SCREEN, "X-UI-002#UI-9") is None
    assert cg.item_function(cg.reduce(RAW), "EXMP-MS-007#pipeline.save_pipeline")["name"] == "save_pipeline"
    old = {"functions": [{k: v for k, v in f.items() if k != "item"} for f in SCREEN["functions"]], "calls": []}
    assert cg.item_function(old, "X-API-001#GET/api/code") is None  # item 없는 옛 그래프


def test_item_neighbors_skips_helpers_and_same_item_both_ways() -> None:
    fwd, back = cg.item_neighbors(SCREEN, "r.py:1")
    assert fwd == ["q.py:1"]  # 라우터 → queries.view (항목 있는 함수에서 멈춘다)
    # UI-1 둘(helper·panes.Left)은 하나로 접힌다(먼저 닿은 것) · 사이클(_help → 라우터)로 queries.view도 — 항목 ID 순
    assert back == ["q.py:1", "pages/Page.tsx:3"]
    fwd, back = cg.item_neighbors(SCREEN, "pages/Page.tsx:10")
    assert fwd == ["r.py:1"] and back == []  # 같은 항목의 helper를 건너 라우터까지
    fwd, back = cg.item_neighbors(SCREEN, "q.py:1")
    assert fwd == ["r.py:1", "q.py:20"]  # 도우미(_help)를 건너 get · 사이클로 라우터 — deep은 get 너머. 항목 ID 순
    assert back == ["r.py:1"]
    assert cg.item_neighbors(SCREEN, "없음:1") == ([], [])
    old = {"functions": [{**f, "item": None} for f in SCREEN["functions"]], "calls": SCREEN["calls"]}
    assert cg.item_neighbors(old, "r.py:1") == ([], [])  # item 없는 옛 그래프


# ── load ──
async def test_load_prefers_committed_graph_json(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text(json.dumps(RAW), encoding="utf-8")

    async def boom(_):  # 저장소 것이 있으면 추출을 부르지 않는다
        raise AssertionError("extract를 불렀다")

    monkeypatch.setattr(cg.graphify, "extract", boom)
    assert await cg.load(tmp_path) == ("repo", RAW)
    (tmp_path / "graphify-out" / "graph.json").write_text("{깨짐", encoding="utf-8")
    with pytest.raises(CodeGraphFailed):
        await cg.load(tmp_path)


async def test_load_extracts_when_nothing_committed(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return g()\n\n\ndef g():\n    return 1\n")
    source, raw = await cg.load(tmp_path)
    g = cg.reduce(raw)
    assert source == "server"
    assert {f["qual"] for f in g["functions"]} >= {"a.f", "a.g"}
    assert ["a.py:1", "a.py:5", "graphify"] in g["calls"]
