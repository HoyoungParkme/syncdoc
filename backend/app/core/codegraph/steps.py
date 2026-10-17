"""SYNC-MS-024 — core/codegraph/steps.py. 호출 순서 — 함수마다 호출·반환·예외(카드 CC).

순수 함수다 — DB를 모른다. 차례는 사건이 끝나는 바이트 자리로 정한다(안쪽 호출이 먼저 끝난다).
파이썬 `ast`와 tree-sitter가 같은 바이트 자리를 주므로 Rust 판(MS-026)이 같은 결과를 낸다.
호출 대상은 그래프에 이미 있는 호출 선에서 이름으로 고른다 — 타입을 다시 풀지 않는다(MS-024 0장).
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

LABEL_MAX = 70
MAX_STEPS = 200
_WS = re.compile(r"\s+")
_BOM = b"\xef\xbb\xbf"

_PY = (".py",)
_TS = (".ts", ".tsx", ".js", ".jsx", ".mjs")
_RS = (".rs",)
_JAVA = (".java",)
_GO = (".go",)

_TS_FN = frozenset({"function_declaration", "generator_function_declaration", "method_definition",
                    "function_expression", "arrow_function"})  # fmt: skip
_TS_HOLDERS = frozenset({"pair", "public_field_definition"})


class _Ev:
    """사건 하나 — 차례 열쇠와 내용. `bare`는 맨 이름·경로 호출(짐작해도 되는 꼴)인가."""

    __slots__ = ("order", "k", "line", "label", "ident", "bare", "deferred", "awaited")

    def __init__(self, order: tuple, k: str, line: int, label: str, ident: tuple | None,
                 deferred: bool, awaited: bool) -> None:  # fmt: skip
        self.order, self.k, self.line, self.label = order, k, line, label
        self.ident, self.bare = (ident[0], ident[1]) if ident else (None, False)
        self.deferred, self.awaited = deferred, awaited


def _label(text: str) -> str:
    """공백 묶음을 한 칸으로 · 앞뒤 자르기 · `.` 앞뒤 한 칸을 지우고 · 70자 넘으면 69자 + `…`."""
    text = _WS.sub(" ", text).strip().replace(" .", ".").replace(". ", ".")
    return text if len(text) <= LABEL_MAX else text[: LABEL_MAX - 1] + "…"


def _lang(file: str) -> str | None:
    if file.endswith(_PY):
        return "py"
    if file.endswith(_TS):
        return "ts"
    if file.endswith(_RS):
        return "rs"
    if file.endswith(_JAVA):
        return "java"
    if file.endswith(_GO):
        return "go"
    return None


# ---------------------------------------------------------------- 파이썬 (ast)


class _PySrc:
    """파이썬 파일 — 줄 시작 바이트로 ast 자리를 파일 바이트 자리로."""

    def __init__(self, src: bytes) -> None:
        self.src = src
        self.starts = [0]
        for i, b in enumerate(src):
            if b == 0x0A:
                self.starts.append(i + 1)
        self.tree = ast.parse(src)

    def at(self, line: int, col: int) -> int:
        return self.starts[line - 1] + col

    def span(self, n: ast.AST) -> tuple[int, int]:
        return self.at(n.lineno, n.col_offset), self.at(n.end_lineno, n.end_col_offset)  # type: ignore[attr-defined]

    def text(self, n: ast.AST) -> str:
        a, b = self.span(n)
        return self.src[a:b].decode("utf-8", errors="replace")


def _py_defs(ps: _PySrc) -> dict[int, ast.AST]:
    """줄 → 함수 정의(중첩 포함) — `def` 줄과 첫 데코레이터 줄. 같은 줄이면 앞선 것."""
    found: list[tuple[int, int, ast.AST]] = []
    for n in ast.walk(ps.tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = ps.at(n.lineno, n.col_offset)
            lines = {n.lineno}
            if n.decorator_list:
                lines.add(n.decorator_list[0].lineno)
            for ln in lines:
                found.append((ln, start, n))
    out: dict[int, ast.AST] = {}
    for ln, _, n in sorted(found, key=lambda t: (t[0], t[1])):
        out.setdefault(ln, n)
    return out


def _py_ident(func: ast.expr) -> tuple | None:
    """호출의 마지막 이름과 맨 이름 호출인가."""
    if isinstance(func, ast.Name):
        return func.id, True
    if isinstance(func, ast.Attribute):
        return func.attr, False
    return None


def _is_depends(n: ast.AST) -> bool:
    if not isinstance(n, ast.Call):
        return False
    f = n.func
    return (isinstance(f, ast.Name) and f.id == "Depends") or (
        isinstance(f, ast.Attribute) and f.attr == "Depends"
    )


def _py_events(ps: _PySrc, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Ev]:
    out: list[_Ev] = []
    args = fn.args
    for d in [*args.defaults, *(x for x in args.kw_defaults if x is not None)]:
        if _is_depends(d) and d.args:  # type: ignore[attr-defined]
            arg = d.args[0]  # type: ignore[attr-defined]
            start, _ = ps.span(d)
            out.append(_Ev((0, start), "call", fn.lineno, _label(f"Depends({ps.text(arg)})"),
                           _py_ident(arg), False, False))  # fmt: skip

    def visit(n: ast.AST, deferred: bool, awaited: bool = False) -> None:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for c in n.body:
                visit(c, True)
            return
        if isinstance(n, ast.Lambda):
            visit(n.body, True)
            return
        if isinstance(n, ast.ClassDef):
            return
        if isinstance(n, ast.Await):
            visit(n.value, deferred, awaited=True)
            return
        if isinstance(n, ast.Call):
            start, end = ps.span(n)
            out.append(_Ev((1, end, -start), "call", n.lineno, _label(ps.text(n.func)),
                           _py_ident(n.func), deferred, awaited))  # fmt: skip
        elif isinstance(n, ast.Return) and not deferred:
            start, end = ps.span(n)
            label = "return" if n.value is None else f"return {ps.text(n.value)}"
            out.append(_Ev((1, end, -start), "return", n.lineno, _label(label), None, False, False))
        elif isinstance(n, ast.Raise) and not deferred:
            start, end = ps.span(n)
            label = "raise" if n.exc is None else f"raise {ps.text(n.exc)}"
            out.append(_Ev((1, end, -start), "raise", n.lineno, _label(label), None, False, False))
        for c in ast.iter_child_nodes(n):
            visit(c, deferred)

    for stmt in fn.body:
        visit(stmt, False)
    return out


# ---------------------------------------------------------------- TS/JS·Rust (tree-sitter)


def _ts_root(file: str, src: bytes):
    from app.core.codegraph.graph import _ts_parse

    return _ts_parse(file, src)


def _rs_root(src: bytes):
    from app.core.codegraph.graph import _rs_parse

    return _rs_parse(src)


def _text(n, src: bytes) -> str:
    return src[n.start_byte : n.end_byte].decode("utf-8", errors="replace")


def _unparen(n):
    """괄호로만 싼 식 → 안쪽 식 (MS-024 steps 6 — ast에는 괄호 노드가 없다)."""
    while n is not None and n.type == "parenthesized_expression":
        inner = [c for c in n.named_children if c.type != "comment"]
        if len(inner) != 1:
            break
        n = inner[0]
    return n


def _walk(root):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def _ts_defs(root) -> dict[int, object]:
    """줄 → 함수 정의 — 노드의 첫 줄, 그리고 그 값을 담은 선언문·export·키의 첫 줄."""
    found: list[tuple[int, int, object]] = []
    for n in _walk(root):
        if n.type not in _TS_FN:
            continue
        lines = {n.start_point[0] + 1}
        p = n.parent
        if p is not None and p.type == "variable_declarator":
            decl = p.parent
            if decl is not None and decl.type in ("lexical_declaration", "variable_declaration"):
                lines.add(decl.start_point[0] + 1)
                if decl.parent is not None and decl.parent.type == "export_statement":
                    lines.add(decl.parent.start_point[0] + 1)
        elif p is not None and p.type in _TS_HOLDERS:
            lines.add(p.start_point[0] + 1)
        elif p is not None and p.type == "export_statement":
            lines.add(p.start_point[0] + 1)
        for ln in lines:
            found.append((ln, n.start_byte, n))
    out: dict[int, object] = {}
    for ln, _, n in sorted(found, key=lambda t: (t[0], t[1])):
        out.setdefault(ln, n)
    return out


def _ts_ident(fn, src: bytes) -> tuple | None:
    fn = _unparen(fn)
    if fn is None:
        return None
    if fn.type == "identifier":
        return _text(fn, src), True
    if fn.type == "member_expression":
        prop = fn.child_by_field_name("property")
        return (_text(prop, src), False) if prop is not None else None
    return None


def _ts_events(fn, src: bytes) -> list[_Ev]:
    out: list[_Ev] = []
    body = fn.child_by_field_name("body")
    if body is None:
        return out

    def ev(n, k: str, label: str, ident: str | None, deferred: bool, awaited: bool) -> None:
        out.append(_Ev((1, n.end_byte, -n.start_byte), k, n.start_point[0] + 1, _label(label),
                       ident, deferred, awaited))  # fmt: skip

    def visit(n, deferred: bool, awaited: bool = False) -> None:
        t = n.type
        if t in _TS_FN:
            b = n.child_by_field_name("body")
            if b is not None:
                visit(b, True)
            return
        if t in ("class_declaration", "class"):
            return
        if t == "await_expression":
            for c in n.named_children:
                visit(c, deferred, awaited=True)
            return
        if t == "call_expression":
            f = n.child_by_field_name("function")
            if f is not None and f.type != "import":
                ev(n, "call", _text(_unparen(f), src), _ts_ident(f, src), deferred, awaited)
        elif t in ("jsx_opening_element", "jsx_self_closing_element"):
            name = n.child_by_field_name("name")
            if name is not None:
                nm = _text(name, src)
                if nm[:1].isupper():
                    ident = (nm.rsplit(".", 1)[-1], "." not in nm)
                    ev(n, "call", f"<{nm}>", ident, deferred, False)
        elif t == "return_statement" and not deferred:
            vals = [c for c in n.named_children if c.type != "comment"]
            label = "return" if not vals else f"return {_text(_unparen(vals[0]), src)}"
            ev(n, "return", label, None, False, False)
        elif t == "throw_statement" and not deferred:
            vals = [c for c in n.named_children if c.type != "comment"]
            label = "throw" if not vals else f"throw {_text(_unparen(vals[0]), src)}"
            ev(n, "raise", label, None, False, False)
        for c in n.children:
            visit(c, deferred)

    visit(body, False)
    return out


def _rs_defs(root) -> dict[int, object]:
    """줄 → `function_item` — `fn` 낱말이 든 줄."""
    found: list[tuple[int, int, object]] = []
    for n in _walk(root):
        if n.type != "function_item":
            continue
        kw = next((c for c in n.children if c.type == "fn"), None)
        ln = (kw if kw is not None else n).start_point[0] + 1
        found.append((ln, n.start_byte, n))
    out: dict[int, object] = {}
    for ln, _, n in sorted(found, key=lambda t: (t[0], t[1])):
        out.setdefault(ln, n)
    return out


def _rs_ident(fn, src: bytes) -> tuple | None:
    fn = _unparen(fn)
    if fn is None:
        return None
    if fn.type == "generic_function":
        return _rs_ident(fn.child_by_field_name("function"), src)
    if fn.type == "identifier":
        return _text(fn, src), True
    if fn.type == "field_expression":
        field = fn.child_by_field_name("field")
        return (_text(field, src), False) if field is not None else None
    if fn.type == "scoped_identifier":
        name = fn.child_by_field_name("name")
        return (_text(name, src), True) if name is not None else None
    return None


def _rs_events(fn, src: bytes) -> list[_Ev]:
    out: list[_Ev] = []
    body = fn.child_by_field_name("body")
    if body is None:
        return out

    def ev(n, k: str, label: str, ident: str | None, deferred: bool, awaited: bool) -> None:
        out.append(_Ev((1, n.end_byte, -n.start_byte), k, n.start_point[0] + 1, _label(label),
                       ident, deferred, awaited))  # fmt: skip

    def visit(n, deferred: bool, awaited: bool = False) -> None:
        t = n.type
        if t == "function_item":
            b = n.child_by_field_name("body")
            if b is not None:
                visit(b, True)
            return
        if t == "closure_expression":
            b = n.child_by_field_name("body")
            if b is not None:
                visit(b, True)
            return
        if t == "await_expression":
            for i, c in enumerate(n.named_children):
                visit(c, deferred, awaited=(i == 0))
            return
        if t == "call_expression":
            f = n.child_by_field_name("function")
            if f is not None:
                ev(n, "call", _text(_unparen(f), src), _rs_ident(f, src), deferred, awaited)
        elif t == "return_expression" and not deferred:
            vals = [c for c in n.named_children if c.type != "line_comment"]
            label = "return" if not vals else f"return {_text(_unparen(vals[0]), src)}"
            ev(n, "return", label, None, False, False)
        for c in n.children:
            visit(c, deferred)

    visit(body, False)
    return out


# ---------------------------------------------------------------- Java·Go (tree-sitter, 카드 CN)


def _jg_root(lang: str, src: bytes):
    from app.core.codegraph.javago import _parse

    return _parse(lang, src)


_JAVA_FN = frozenset({"method_declaration", "constructor_declaration"})
_GO_FN = frozenset({"function_declaration", "method_declaration"})


def _start_defs(root, kinds: frozenset) -> dict[int, object]:
    """줄 → 정의 — 선언의 첫 줄(Java는 어노테이션 줄부터, Go는 `func` 줄). 같은 줄이면 앞선 것."""
    out: dict[int, object] = {}
    for n in sorted((n for n in _walk(root) if n.type in kinds), key=lambda n: n.start_byte):
        out.setdefault(n.start_point[0] + 1, n)
    return out


def _java_ident(n, src: bytes) -> tuple | None:
    """`m()` → (m, 맨 이름) · `x.m()` → (m, 메서드)."""
    name = n.child_by_field_name("name")
    if name is None:
        return None
    return _text(name, src), n.child_by_field_name("object") is None


def _java_events(fn, src: bytes) -> list[_Ev]:
    out: list[_Ev] = []
    body = fn.child_by_field_name("body")
    if body is None:
        return out

    def ev(n, k: str, label: str, ident: tuple | None, deferred: bool) -> None:
        out.append(_Ev((1, n.end_byte, -n.start_byte), k, n.start_point[0] + 1, _label(label),
                       ident, deferred, False))  # fmt: skip

    def visit(n, deferred: bool) -> None:
        t = n.type
        if t == "lambda_expression":
            b = n.child_by_field_name("body")
            if b is not None:
                visit(b, True)
            return
        if t in ("class_body", "class_declaration", "interface_declaration", "enum_declaration",
                 "record_declaration"):  # fmt: skip
            return
        if t == "method_invocation":
            name = n.child_by_field_name("name")
            if name is not None:
                label = src[n.start_byte : name.end_byte].decode("utf-8", errors="replace")
                ev(n, "call", label, _java_ident(n, src), deferred)
        elif t == "object_creation_expression":
            ty = n.child_by_field_name("type")
            if ty is not None:
                from app.core.codegraph.javago import _jtype

                tn = _jtype(ty, src)
                ev(n, "call", f"new {_text(ty, src)}", (tn, True) if tn else None, deferred)
        elif t == "return_statement" and not deferred:
            vals = [c for c in n.named_children if c.type not in ("line_comment", "block_comment")]
            label = "return" if not vals else f"return {_text(_unparen(vals[0]), src)}"
            ev(n, "return", label, None, False)
        elif t == "throw_statement" and not deferred:
            vals = [c for c in n.named_children if c.type not in ("line_comment", "block_comment")]
            label = "throw" if not vals else f"throw {_text(_unparen(vals[0]), src)}"
            ev(n, "raise", label, None, False)
        for c in n.children:
            visit(c, deferred)

    visit(body, False)
    return out


def _go_ident(fn, src: bytes) -> tuple | None:
    fn = _unparen(fn)
    if fn is None:
        return None
    if fn.type == "identifier":
        return _text(fn, src), True
    if fn.type == "selector_expression":
        field = fn.child_by_field_name("field")
        return (_text(field, src), False) if field is not None else None
    return None


def _go_events(fn, src: bytes) -> list[_Ev]:
    out: list[_Ev] = []
    body = fn.child_by_field_name("body")
    if body is None:
        return out

    def ev(n, k: str, label: str, ident: tuple | None, deferred: bool) -> None:
        out.append(_Ev((1, n.end_byte, -n.start_byte), k, n.start_point[0] + 1, _label(label),
                       ident, deferred, False))  # fmt: skip

    def visit(n, deferred: bool) -> None:
        t = n.type
        if t == "func_literal":
            b = n.child_by_field_name("body")
            if b is not None:
                visit(b, True)
            return
        if t in ("go_statement", "defer_statement"):
            for c in n.children:
                visit(c, True)
            return
        if t == "call_expression":
            f = n.child_by_field_name("function")
            if f is not None:
                ev(n, "call", _text(_unparen(f), src), _go_ident(f, src), deferred)
        elif t == "return_statement" and not deferred:
            vals = [c for c in n.named_children if c.type != "comment"]
            label = "return" if not vals else f"return {_text(vals[0], src)}"
            ev(n, "return", label, None, False)
        for c in n.children:
            visit(c, deferred)

    visit(body, False)
    return out


# ---------------------------------------------------------------- 묶기


def _events_of(lang: str, file: str, src: bytes) -> dict[int, list[_Ev]]:
    """파일의 정의 줄 → 그 정의의 사건들. 못 읽으면 빈 사전."""
    if lang == "py":
        try:
            ps = _PySrc(src)
        except (SyntaxError, ValueError):
            return {}
        return {ln: _py_events(ps, n) for ln, n in _py_defs(ps).items()}  # type: ignore[arg-type]
    if lang == "ts":
        root = _ts_root(file, src)
        return {ln: _ts_events(n, src) for ln, n in _ts_defs(root).items()}
    if lang == "rs":
        root = _rs_root(src)
        return {ln: _rs_events(n, src) for ln, n in _rs_defs(root).items()}
    root = _jg_root(lang, src)
    if lang == "java":
        return {ln: _java_events(n, src) for ln, n in _start_defs(root, _JAVA_FN).items()}
    return {ln: _go_events(n, src) for ln, n in _start_defs(root, _GO_FN).items()}


def steps(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-024#steps.steps

    함수마다 `steps = [{k, line, label, to, inferred, deferred, awaited, infra}]` — 정의 몸통의
    호출·JSX·반환·예외를 끝 바이트 차례로. 대상은 이 함수에서 나가는 호출 선 중 이름이 하나뿐인 것,
    없으면 그래프 전체에서 하나뿐인 이름(`inferred`).
    """
    funcs = graph["functions"]
    by_name: dict[tuple, list[str]] = defaultdict(list)  # (언어, 이름) → 열쇠들
    for f in funcs:
        by_name[(_lang(f["file"]), f["name"])].append(f["key"])
    name_of = {f["key"]: f["name"] for f in funcs}
    out_edges: dict[str, list[str]] = defaultdict(list)
    for a, b, _ in graph["calls"]:
        if b not in out_edges[a]:
            out_edges[a].append(b)
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in funcs:
        f["steps"] = []
        by_file[f["file"]].append(f)
    # 호출마다 마지막 이름 — 장비 판정(infra.infra)이 쓰고 flow.extend가 지운다. 결과에 안 나간다
    idents: dict[str, list[str | None]] = {}
    graph["_idents"] = idents

    for file, fs in by_file.items():
        lang = _lang(file)
        if lang is None:
            continue
        try:
            src = (src_dir / file).read_bytes()
        except OSError:
            continue
        if src.startswith(_BOM):
            src = src[len(_BOM) :]
        try:
            src.decode("utf-8")
        except UnicodeDecodeError:
            continue
        events = _events_of(lang, file, src)
        for f in fs:
            evs = events.get(f["line"])
            if evs is None:
                continue
            evs = sorted(evs, key=lambda e: e.order)[:MAX_STEPS]
            f["steps"] = [_step(e, f["key"], lang, out_edges, by_name, name_of) for e in evs]
            idents[f["key"]] = [e.ident if e.k == "call" else None for e in evs]
    return graph


def _step(e: _Ev, key: str, lang: str, out_edges: dict, by_name: dict, name_of: dict) -> dict:
    """사건 → step. 기본값인 키(`to` 없음·거짓 표시)는 싣지 않는다 (MS-024 steps 10)."""
    to, inferred = None, False
    if e.k == "call" and e.ident:
        local = [b for b in out_edges.get(key, []) if name_of.get(b) == e.ident]
        if len(local) == 1:
            to = local[0]
        elif not local and e.bare:
            cands = by_name.get((lang, e.ident), [])
            if len(cands) == 1 and cands[0] != key:
                to, inferred = cands[0], True
    step: dict = {"k": e.k, "line": e.line, "label": e.label}
    if to is not None:
        step["to"] = to
    if inferred:
        step["inferred"] = True
    if e.deferred:
        step["deferred"] = True
    if e.awaited:
        step["awaited"] = True
    return step
