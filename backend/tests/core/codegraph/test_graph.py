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


def test_reduce_lists_code_files_without_functions_too() -> None:
    """#282 — 함수 없는 코드 파일도 files에(테스트 파일은 뺀다). enrich가 쓰고 지운다."""
    raw = {
        "nodes": [
            *RAW["nodes"],
            {"id": "f_api", "label": "api.ts", "file_type": "code", "source_file": "web/api.ts"},
            {
                "id": "f_t",
                "label": "test_x.py",
                "file_type": "code",
                "source_file": "tests/test_x.py",
            },
            {"id": "d_doc", "label": "notes", "file_type": "document", "source_file": "notes.md"},
        ],
        "links": RAW["links"],
    }
    files = cg.reduce(raw)["files"]
    assert "web/api.ts" in files and "tests/test_x.py" not in files and "notes.md" not in files


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


def test_reduce_drops_test_files() -> None:
    """MS-011 reduce 1 — 테스트 파일의 노드는 함수가 아니다. `test`가 들어도 꼴이 아니면 남는다."""
    files = {
        "tests/x.py": True,
        "app/test/y.py": True,
        "web/src/__tests__/b.ts": True,
        "app/test_a.py": True,
        "app/a_test.py": True,
        "web/a.test.tsx": True,
        "web/a.spec.ts": True,
        "conftest.py": True,
        "app/sub/conftest.py": True,
        "app/testing.py": False,
        "app/contest.py": False,
        "web/spec.ts": False,
    }
    raw = {
        "nodes": [
            {"id": f, "label": "f()", "_callable": True, "source_file": f, "source_location": "L1"}
            for f in files
        ],
        "links": [],
    }
    kept = {f["file"] for f in cg.reduce(raw)["functions"]}
    assert kept == {f for f, is_test in files.items() if not is_test}


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
        {
            "key": "app/b.py:30",
            "name": "g3",
            "qual": "b.g3",
            "file": "app/b.py",
            "line": 30,
            "end": None,
            "ms": None,
        }  # fmt: skip
    )
    out = cg.communities(RAW2, graph)
    assert out is graph
    by = {f["name"]: f["community"] for f in graph["functions"]}
    assert by["f1"] == by["f2"] and by["g1"] == by["g2"] == by["g3"] and by["f1"] != by["g1"]
    assert all(c is not None for c in by.values())
    comms = graph["communities"]
    assert [c["size"] for c in comms] == [3, 2]  # 함수 수 내림차순 · 테스트·문서만 든 군집은 없다
    assert {c["id"] for c in comms} == {by["g1"], by["f1"]}
    assert by["g1"] == 0  # 노드가 가장 많은 군집(fb·g1·g2·d1)이 0 (#253) — t1은 안 든다(#306)
    assert all(c["label"] and not c["label"].endswith("()") for c in comms)
    assert "노트" not in [c["label"] for c in comms]  # 문서 허브는 라벨이 못 된다 (#255)
    again = cg.communities(RAW2, cg.reduce(RAW2))
    assert [f["community"] for f in again["functions"]] == [
        f["community"] for f in graph["functions"] if f["name"] != "g3"
    ]


# 테스트 여덟이 c.py의 두 함수를 넷씩 나눠 부른다 — 테스트까지 묶으면 h1·h2가 두 커뮤니티로 갈리고
# 하나의 라벨이 test_c.py였다 (#306)
RAW3 = {
    "nodes": [
        {"id": "fa", "label": "a.py", "source_file": "app/a.py", "source_location": "L1"},
        {"id": "f1", "label": "f1()", "_callable": True, "source_file": "app/a.py",
         "source_location": "L2"},
        {"id": "f2", "label": "f2()", "_callable": True, "source_file": "app/a.py",
         "source_location": "L5"},
        {"id": "fc", "label": "c.py", "source_file": "app/c.py", "source_location": "L1"},
        {"id": "h1", "label": "h1()", "_callable": True, "source_file": "app/c.py",
         "source_location": "L2"},
        {"id": "h2", "label": "h2()", "_callable": True, "source_file": "app/c.py",
         "source_location": "L9"},
        {"id": "ft", "label": "test_c.py", "source_file": "tests/test_c.py",
         "source_location": "L1"},
        *[{"id": f"t{i}", "label": f"test_{i}()", "_callable": True,
           "source_file": "tests/test_c.py", "source_location": f"L{10 * i}"} for i in range(1, 9)],
    ],
    "links": [
        {"source": "fa", "target": "f1", "relation": "contains"},
        {"source": "fa", "target": "f2", "relation": "contains"},
        {"source": "f1", "target": "f2", "relation": "calls"},
        {"source": "fc", "target": "h1", "relation": "contains"},
        {"source": "fc", "target": "h2", "relation": "contains"},
        {"source": "f2", "target": "h1", "relation": "calls"},
        *[{"source": "ft", "target": f"t{i}", "relation": "contains"} for i in range(1, 9)],
        *[{"source": f"t{i}", "target": "h1" if i <= 4 else "h2", "relation": "calls"}
          for i in range(1, 9)],
    ],
}  # fmt: skip


def test_communities_leave_tests_out() -> None:
    """#306 — 테스트 노드·선은 군집에 안 든다. 같은 파일의 함수가 한 커뮤니티, 라벨은 테스트가 아니다."""
    out = cg.communities(RAW3, cg.reduce(RAW3))
    by = {f["name"]: f["community"] for f in out["functions"]}
    assert by["h1"] == by["h2"] and by["f1"] == by["f2"] and by["h1"] != by["f1"]
    assert not any(c["label"].startswith("test_") for c in out["communities"])
    tests = {n["id"] for n in RAW3["nodes"] if n["source_file"].startswith("tests/")}
    bare = {
        "nodes": [n for n in RAW3["nodes"] if n["id"] not in tests],
        "links": [e for e in RAW3["links"] if not {e["source"], e["target"]} & tests],
    }
    same = cg.communities(bare, cg.reduce(bare))  # 테스트 노드를 뺀 raw와 같은 결과
    assert same["communities"] == out["communities"] and same["functions"] == out["functions"]


# 메서드 없는 타입 클래스(User — 함수 넷이 타입으로 가리킴)와 의존성 파일(package.json — 의존성 다섯을
# import)이 각 군집의 차수 최고 — 옛 라벨은 User·package.json이었다 (#308)
RAW4 = {
    "nodes": [
        {"id": "fs", "label": "svc.py", "source_file": "app/svc.py", "source_location": "L1"},
        *[{"id": f"s{i}", "label": f"f{i}()", "_callable": True, "source_file": "app/svc.py",
           "source_location": f"L{10 * i}"} for i in range(1, 5)],
        {"id": "fm", "label": "models.py", "source_file": "app/models.py", "source_location": "L1"},
        {"id": "cu", "label": "User", "_callable": True, "_callable_class": True,
         "source_file": "app/models.py", "source_location": "L5"},
        {"id": "fp", "label": "package.json", "source_file": "web/package.json",
         "source_location": "L1"},
        *[{"id": f"k{i}", "label": f"dep{i}", "file_type": "concept",
           "source_file": "web/package.json"} for i in range(1, 6)],
        {"id": "fv", "label": "vite.config.ts", "source_file": "web/vite.config.ts",
         "source_location": "L1"},
        {"id": "pd", "label": "pkgDir()", "_callable": True, "source_file": "web/vite.config.ts",
         "source_location": "L3"},
    ],
    "links": [
        *[{"source": "fs", "target": f"s{i}", "relation": "contains"} for i in range(1, 5)],
        {"source": "s1", "target": "s2", "relation": "calls"},
        {"source": "fm", "target": "cu", "relation": "contains"},
        *[{"source": f"s{i}", "target": "cu", "relation": "references"} for i in range(1, 5)],
        *[{"source": "fp", "target": f"k{i}", "relation": "imports"} for i in range(1, 6)],
        *[{"source": "fv", "target": f"k{i}", "relation": "imports"} for i in range(1, 4)],
        {"source": "fv", "target": "pd", "relation": "contains"},
    ],
}  # fmt: skip


def test_communities_label_owns_a_function() -> None:
    """#308 — 라벨은 그 커뮤니티의 함수를 품은 노드. 메서드 없는 클래스·함수 없는 파일은 못 된다."""
    out = cg.communities(RAW4, cg.reduce(RAW4))
    by = {f["name"]: f["community"] for f in out["functions"]}
    labels = {c["id"]: c["label"] for c in out["communities"]}
    assert labels[by["f1"]] == "svc.py"  # User(차수 5)가 아니라 함수 넷이 든 파일
    assert labels[by["pkgDir"]] == "vite.config.ts"  # package.json(차수 5)이 아니라 함수가 든 파일


def test_communities_class_with_methods_labels_and_no_owner_falls_back() -> None:
    """#308 — 메서드가 그 커뮤니티에 든 클래스는 라벨이 된다 · 후보가 없으면 코드 노드 중 허브."""
    raw = {
        "nodes": [
            {"id": "fc", "label": "c.py", "source_file": "app/c.py", "source_location": "L1"},
            {"id": "cc", "label": "Repo", "_callable": True, "_callable_class": True,
             "source_file": "app/c.py", "source_location": "L3"},
            *[{"id": f"m{i}", "label": f".m{i}()", "_callable": True, "source_file": "app/c.py",
               "source_location": f"L{10 * i}"} for i in range(1, 4)],
        ],
        "links": [
            {"source": "fc", "target": "cc", "relation": "contains"},
            *[{"source": "cc", "target": f"m{i}", "relation": "method"} for i in range(1, 4)],
            {"source": "m1", "target": "m2", "relation": "calls"},
        ],
    }  # fmt: skip
    out = cg.communities(raw, cg.reduce(raw))
    assert {f["qual"] for f in out["functions"]} == {"Repo.m1", "Repo.m2", "Repo.m3"}
    labels = {c["id"]: c["label"] for c in out["communities"]}
    by = {f["qual"]: f["community"] for f in out["functions"]}
    assert labels[by["Repo.m3"]] == "Repo"  # 그 커뮤니티에 메서드가 든 클래스
    # 메서드 없는 클래스 하나뿐 + 보강이 더한 같은 파일 함수 — 함수를 품은 노드가 없다
    lone = {"nodes": [{"id": "cx", "label": "X", "_callable": True, "_callable_class": True,
                       "source_file": "app/x.py", "source_location": "L1"}], "links": []}  # fmt: skip
    graph = {"functions": [{"key": "app/x.py:5", "name": "f", "qual": "x.f", "file": "app/x.py",
                            "line": 5, "end": None, "ms": None}], "calls": []}  # fmt: skip
    assert [c["label"] for c in cg.communities(lone, graph)["communities"]] == ["X"]


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
    assert (by["pipe.by_tuple"]["item"], by["pipe.by_tuple"]["ms"]) == (
        "EXMP-API-001#POST/api/x/{id}",
        None,
    )
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
    (tmp_path / "a.go").write_text("package a\nfunc F() {}\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    g = {"functions": [_fn("a.go", 2, "F"), _fn("bad.py", 1, "x")], "calls": []}
    cg.enrich(tmp_path, g)
    assert [f["qual"] for f in g["functions"]] == ["", ""]  # Go·깨진 파이썬은 손대지 않는다
    assert [f["end"] for f in g["functions"]] == [None, None]
    assert [f["item"] for f in g["functions"]] == [None, None]  # 화면 ID 없는 파일은 그대로


# ── enrich — TS/JS (MS-011 enrich 2a~2d, 카드 BL) ──
PAGE_TSX = """/** UI-1 화면 — X-UI-002#UI-1 */
import { useState } from 'react'
import { api as client, helper } from '../lib/api'
import Badge from '../lib/Badge'
import * as md from '../lib/md'

const short = (s: string) =>
  s.slice(1)

export function Page() {
  const [v, setV] = useState(0)
  const onClick = () => {
    client.get('/x')
    helper(short('ab'))
  }
  return <div onClick={onClick}><Badge />{md.render('x')}</div>
}

export default function Main() {
  return <Page />
}

class Store {
  load() {
    return short('a')
  }
}
"""
API_TS = """export const api = {
  get: <T,>(url: string) => fetch(url) as T,
  post(url: string) {
    return fetch(url)
  },
}

export function helper(x: string) {
  return x
}
"""
BADGE_TSX = "export default function Badge() {\n  return <span />\n}\n"
MD_TS = "export function render(s: string): string {\n  return s\n}\n"


def _ts_src(tmp_path: Path) -> Path:
    for rel, body in (("pages/Page.tsx", PAGE_TSX), ("lib/api.ts", API_TS),
                      ("lib/Badge.tsx", BADGE_TSX), ("lib/md/index.ts", MD_TS)):  # fmt: skip
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    (tmp_path / "lib" / "broken.ts").write_bytes(b"\xff\xfe(((")
    return tmp_path


def test_enrich_ts_reads_files_graphify_saw_without_functions(tmp_path: Path) -> None:
    """#282 — graphify가 함수를 0개 찾은 api.ts도 files로 읽어 api.get·api.post와 선을 더한다."""
    src = _ts_src(tmp_path)
    g = {
        "functions": [_fn("pages/Page.tsx", 10, "Page")],
        "calls": [],
        "files": ["lib/api.ts", "pages/Page.tsx", "README.md"],
    }
    cg.enrich(src, g)
    by = {f["key"]: f for f in g["functions"]}
    assert by["lib/api.ts:2"]["qual"] == "api.get" and by["lib/api.ts:3"]["qual"] == "api.post"
    assert ["pages/Page.tsx:10", "lib/api.ts:2", "enrich"] in g["calls"]
    assert "files" not in g  # 저장 모양에는 없다


def test_enrich_ts_ends_quals_missing_defs_nested_and_calls(tmp_path: Path) -> None:
    src = _ts_src(tmp_path)
    # graphify가 잡은 것처럼 — 맨 위 몇 개(끝 줄 없음)와 중첩 핸들러 하나, 선 하나. api.get/post는 놓쳤다
    g = {
        "functions": [
            _fn("pages/Page.tsx", 7, "short"), _fn("pages/Page.tsx", 10, "Page"),
            _fn("pages/Page.tsx", 12, "onClick"),  # 중첩 — 끝 줄만 채운다
            _fn("pages/Page.tsx", 19, "Main"), _fn("lib/api.ts", 8, "helper"),
            _fn("lib/Badge.tsx", 1, "Badge"), _fn("lib/md/index.ts", 1, "render"),
            _fn("lib/broken.ts", 1, "x"),
        ],
        "calls": [["pages/Page.tsx:19", "pages/Page.tsx:10", "graphify"]],
    }  # fmt: skip
    cg.enrich(src, g)
    by = {f["key"]: f for f in g["functions"]}
    # 2b — 맨 위 함수의 끝 줄·qual (const 화살표는 선언문 끝, index.ts는 폴더 이름)
    assert (by["pages/Page.tsx:7"]["end"], by["pages/Page.tsx:7"]["qual"]) == (8, "Page.short")
    assert (by["pages/Page.tsx:10"]["end"], by["pages/Page.tsx:19"]["end"]) == (17, 21)
    assert by["lib/md/index.ts:1"]["qual"] == "md.render"
    # 2a — 놓친 정의를 더한다: 객체 리터럴의 화살표·메서드, 클래스 메서드
    assert by["lib/api.ts:2"]["qual"] == "api.get" and by["lib/api.ts:3"]["qual"] == "api.post"
    assert by["lib/api.ts:3"]["end"] == 5
    assert by["pages/Page.tsx:24"]["qual"] == "Store.load" and by["pages/Page.tsx:24"]["end"] == 26
    # 2c — 중첩 함수는 지우지 않고 끝 줄만
    assert by["pages/Page.tsx:12"]["end"] == 15 and by["pages/Page.tsx:12"]["qual"] == ""
    # 깨진 파일은 건너뛴다
    assert by["lib/broken.ts:1"]["end"] is None
    # 3 — 더한 TS 함수도 파일 첫 주석의 화면 ID를 받는다
    assert by["pages/Page.tsx:24"]["item"] == "X-UI-002#UI-1" and by["lib/api.ts:2"]["item"] is None
    # 2d — 호출: 같은 파일 · 별칭 import의 객체 메서드 · named import · default import(JSX) ·
    # 이름공간 import · 클래스 메서드에서 같은 파일. 패키지(useState)는 안 잇는다
    enriched = {(a, b) for a, b, via in g["calls"] if via == "enrich"}
    page = "pages/Page.tsx:10"
    assert {(page, "pages/Page.tsx:7"), (page, "lib/api.ts:2"), (page, "lib/api.ts:8"),
            (page, "lib/Badge.tsx:1"), (page, "lib/md/index.ts:1"),
            ("pages/Page.tsx:24", "pages/Page.tsx:7")} <= enriched  # fmt: skip
    assert ("pages/Page.tsx:19", "pages/Page.tsx:10") not in enriched  # graphify 선과 안 겹친다
    assert all(not b.startswith("react") for _, b in enriched)


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
    no_stem = {
        "functions": [f for f in SCREEN["functions"] if f["qual"] != "Page.Page"],
        "calls": [],
    }
    assert (
        cg.item_function(no_stem, "X-UI-002#UI-1")["qual"] == "Page.helper"
    )  # (파일, 줄) 순 첫 함수
    assert cg.item_function(SCREEN, "X-UI-002#UI-9") is None
    assert (
        cg.item_function(cg.reduce(RAW), "EXMP-MS-007#pipeline.save_pipeline")["name"]
        == "save_pipeline"
    )
    old = {
        "functions": [{k: v for k, v in f.items() if k != "item"} for f in SCREEN["functions"]],
        "calls": [],
    }
    assert cg.item_function(old, "X-API-001#GET/api/code") is None  # item 없는 옛 그래프


def test_item_neighbors_skips_helpers_and_same_item_both_ways() -> None:
    fwd, back = cg.item_neighbors(SCREEN, "r.py:1")
    assert fwd == ["q.py:1"]  # 라우터 → queries.view (항목 있는 함수에서 멈춘다)
    # UI-1 둘(helper·panes.Left)은 하나로 접힌다(먼저 닿은 것) · 사이클(_help → 라우터)로 queries.view도 — 항목 ID 순
    assert back == ["q.py:1", "pages/Page.tsx:3"]
    fwd, back = cg.item_neighbors(SCREEN, "pages/Page.tsx:10")
    assert fwd == ["r.py:1"] and back == []  # 같은 항목의 helper를 건너 라우터까지
    fwd, back = cg.item_neighbors(SCREEN, "q.py:1")
    assert fwd == [
        "r.py:1",
        "q.py:20",
    ]  # 도우미(_help)를 건너 get · 사이클로 라우터 — deep은 get 너머. 항목 ID 순
    assert back == ["r.py:1"]
    assert cg.item_neighbors(SCREEN, "없음:1") == ([], [])
    old = {
        "functions": [{**f, "item": None} for f in SCREEN["functions"]],
        "calls": SCREEN["calls"],
    }
    assert cg.item_neighbors(old, "r.py:1") == ([], [])  # item 없는 옛 그래프


# ── layer_table · layers (MS-011, 카드 BM) ──
CLASS_DOC = """---
doc_id: X-DOM-002
type: DOM
title: 클래스 명세 — X
status: draft
---
## 0. 이 문서가 다루는 것

| 경로 | 층 | 명세 |
|---|---|---|
| `a/*.py` | 다른 절 | [[X-STD-001]] |

## 1. 폴더 구조

```
| 경로 | 층 | 명세 |
| `fenced/*.py` | 코드블록 | [[X-STD-001]] |
```

| 이름 | 뜻 |
|---|---|
| `x` | 머리가 다른 표 |

**층**

| 경로 | 층 | 명세 |
|---|---|---|
| `app/core/*/repository.py` | 리포지토리 | [[X-DOM-002]] 4장 · [[X-DOM-003]] |
| `app/alembic/**` · `app/db.py` | 마이그레이션·설정 | [[X-STD-004#DEV-7]] · 글자만 |
| `tools/special.py` | 특별 도구 | [[X-STD-002]] |
| `tools/*.py` | 도구 | [[X-STD-004#DEV-14]] |
| `gone/**` | 지운 폴더 | [[X-DOM-003]] |

## 2. 엔티티
"""


def test_layer_table_reads_only_the_folder_section_table() -> None:
    rows = cg.layer_table(CLASS_DOC)
    assert [r["name"] for r in rows] == [
        "리포지토리",
        "마이그레이션·설정",
        "특별 도구",
        "도구",
        "지운 폴더",
    ]
    assert rows[1]["patterns"] == ["app/alembic/**", "app/db.py"]  # 꼴 여럿
    assert rows[0]["specs"] == [
        {"ref": "X-DOM-002", "note": "4장"},
        {"ref": "X-DOM-003", "note": ""},
    ]
    assert rows[1]["specs"][1] == {"ref": None, "note": "글자만"}  # 링크 없는 조각
    assert CLASS_DOC.split("\n")[rows[0]["line"] - 1].startswith("| `app/core/*/repository.py`")
    assert cg.layer_table(CLASS_DOC.replace("## 1. 폴더 구조", "## 1. 구조")) == []  # 절이 없으면
    assert (
        cg.layer_table("## 폴더 구조\n| 경로 | 층 | 명세 |\n|-|-|-|\n| `x/*` | 층 | |\n")[0]["name"]
        == "층"
    )  # 번호 없는 절도


def test_layers_item_first_then_helper_then_first_row() -> None:
    rows = cg.layer_table(CLASS_DOC)

    def fn(key: str, item: str | None = None, ms: str | None = None) -> dict:
        file, line = key.rsplit(":", 1)
        return {"key": key, "name": "f", "qual": "m.f", "file": file, "line": int(line),
                "end": None, "item": item, "ms": ms}  # fmt: skip

    g = {
        "functions": [
            fn("app/core/spec/repository.py:3"),
            fn("app/core/spec/service.py:5", item="X-MS-002#SpecService.save"),
            fn("app/core/spec/service.py:9"),  # 같은 파일에 항목 → 도우미
            fn("app/core/spec/sub/repository.py:1"),  # `*`는 한 단만 — 안 맞는다
            fn("app/alembic/versions/0001.py:2"),  # `**`는 여러 단
            fn("tools/special.py:1"),  # 위 줄이 이긴다
            fn("tools/check.py:1"),
            fn("tools/old.py:4", ms="X-MS-009#old.run"),  # 옛 그래프 — ms만 있어도 항목
        ],
        "calls": [],
    }
    layer_of, unmatched = cg.layers(g, rows)
    assert layer_of["app/core/spec/repository.py:3"]["name"] == "리포지토리"
    assert layer_of["app/core/spec/repository.py:3"]["specs"][0] == {
        "ref": "X-DOM-002",
        "note": "4장",
    }
    assert "app/core/spec/service.py:5" not in layer_of  # 항목이 먼저
    assert layer_of["app/core/spec/service.py:9"] == {"name": "도우미", "specs": []}
    assert "app/core/spec/sub/repository.py:1" not in layer_of  # 층 없음
    assert layer_of["app/alembic/versions/0001.py:2"]["name"] == "마이그레이션·설정"
    assert layer_of["tools/special.py:1"]["name"] == "특별 도구"
    assert layer_of["tools/check.py:1"]["name"] == "도구"
    assert "tools/old.py:4" not in layer_of
    assert [r["name"] for r in unmatched] == ["지운 폴더"]  # 어느 함수에도 안 맞는 줄
    only_helpers, _ = cg.layers(g, [])
    assert set(only_helpers) == {"app/core/spec/service.py:9"}  # 표가 없으면 도우미만


def test_enrich_resolves_self_attribute_set_in_init(tmp_path: Path) -> None:
    """MS-011 enrich 4·5 — `__init__`의 self.repo = Repo(…) 뒤 self.repo.get(…) → Repo.get (카드 BM)."""
    (tmp_path / "repo.py").write_text(
        "class Repo:\n    def __init__(self, s):\n        self.s = s\n\n"
        "    def get(self, k):\n        return k\n",
        encoding="utf-8",
    )
    (tmp_path / "svc.py").write_text(
        "from repo import Repo\n\n\nclass Svc:\n    def __init__(self, s):\n"
        "        self.repo = Repo(s)\n        self.other: Repo = make()\n        self.n = 3\n\n"
        "    def run(self, k):\n        return self.repo.get(k)\n\n"
        "    def run2(self, k):\n        return self.other.get(k) + self.n.bit_length()\n",
        encoding="utf-8",
    )
    g = {"functions": [_fn("repo.py", 5, "get"), _fn("svc.py", 10, "run"), _fn("svc.py", 13, "run2")],
         "calls": []}  # fmt: skip
    cg.enrich(tmp_path, g)
    k = {f["qual"]: f["key"] for f in g["functions"]}
    enriched = {(a, b) for a, b, via in g["calls"] if via == "enrich"}
    assert (k["Svc.run"], k["Repo.get"]) in enriched  # 대입한 속성
    assert (k["Svc.run2"], k["Repo.get"]) in enriched  # 주석 단 속성


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
