"""SYNC-MS-024 — core/codegraph/routes.py. 라우트와 화면 요청(카드 CD).

순수 함수다 — DB를 모른다. 라우트는 함수마다 `route = {method, path}`, 화면 요청은 그래프의
`http = [{from, to, inferred}]`. 경로 매개변수는 `{이름}` 꼴로 맞춘다.
Rust 판(MS-026)이 같은 결과를 낸다.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from app.core.codegraph.steps import _BOM, _rs_root, _text, _ts_root, _unparen, _walk

VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
_PY_ROUTERS = {"APIRouter": "prefix", "FastAPI": "prefix", "Blueprint": "url_prefix",
               "Flask": None}  # fmt: skip
_TS_VERBS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "delete": "DELETE",
             "all": "ANY"}  # fmt: skip
_TS_ROUTER_CALLS = frozenset({"express", "express.Router", "Router", "fastify", "Fastify"})
_TS_ROUTER_NEWS = frozenset({"Hono", "Router", "KoaRouter"})
_NEST = {"Get": "GET", "Post": "POST", "Put": "PUT", "Patch": "PATCH", "Delete": "DELETE",
         "Head": "HEAD", "Options": "OPTIONS", "All": "ANY"}  # fmt: skip
_RS_VERBS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "delete": "DELETE",
             "head": "HEAD", "options": "OPTIONS", "any": "ANY"}  # fmt: skip
_NEXT_ROUTE = re.compile(r"(^|/)app/(.*/)?route\.(ts|js)$")
_FLASK_PARAM = re.compile(r"<(?:[^<>:]+:)?([^<>]+)>")
_EXPRESS_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_SPRING = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
           "PatchMapping": "PATCH", "DeleteMapping": "DELETE", "RequestMapping": None}  # fmt: skip
_SPRING_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*):[^{}]*\}")
_GO_VERBS = {"GET": "GET", "POST": "POST", "PUT": "PUT", "PATCH": "PATCH", "DELETE": "DELETE",
             "Get": "GET", "Post": "POST", "Put": "PUT", "Patch": "PATCH", "Delete": "DELETE",
             "HandleFunc": "ANY", "Handle": "ANY", "Any": "ANY"}  # fmt: skip
_GO_PATTERN = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/.*)$", re.A)
_GIN_PARAM = re.compile(r"[:*]([A-Za-z_][A-Za-z0-9_]*)")
_GO_REST = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\.\.\.\}")
_REQ_NAMES = frozenset({"fetch", "get", "post", "put", "patch", "delete", "del", "head", "request"})


def norm(path: str) -> str:
    """앞에 `/`, 끝 `/`는 뗀다(`/`만 남으면 `/`)."""
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return path


def _join(prefix: str, path: str) -> str:
    return norm(prefix.rstrip("/") + "/" + path.lstrip("/")) if prefix else norm(path)


def _read(src_dir: Path, file: str) -> bytes | None:
    try:
        src = (src_dir / file).read_bytes()
    except OSError:
        return None
    if src.startswith(_BOM):
        src = src[len(_BOM) :]
    try:
        src.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return src


# ---------------------------------------------------------------- 파이썬


def _const_str(n: ast.AST | None) -> str | None:
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


def _kw(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _last_name(n: ast.expr) -> str | None:
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        return n.attr
    return None


def _py_tables(tree: ast.Module) -> dict[str, str]:
    """맨 위 `X = APIRouter(prefix=…)` → {X: 접두어}."""
    out: dict[str, str] = {}
    for st in tree.body:
        if not (isinstance(st, ast.Assign) and isinstance(st.value, ast.Call)):
            continue
        kind = _last_name(st.value.func)
        if kind not in _PY_ROUTERS:
            continue
        key = _PY_ROUTERS[kind]
        prefix = (_const_str(_kw(st.value, key)) if key else None) or ""
        for t in st.targets:
            if isinstance(t, ast.Name):
                out[t.id] = prefix
    return out


def _py_dotted(file: str) -> str:
    p = PurePosixPath(file).with_suffix("")
    parts = list(p.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _py_include_prefixes(trees: dict[str, ast.Module]) -> dict[tuple[str, str], str]:
    """`app.include_router(Z, prefix="…")` → {(파일, 라우터 이름): 접두어} — 한 단만."""
    dotted = {_py_dotted(f): f for f in trees}

    def file_of(mod: str) -> str | None:
        hits = [f for d, f in dotted.items() if d == mod or d.endswith("." + mod)]
        return hits[0] if len(hits) == 1 else None

    out: dict[tuple[str, str], str] = {}
    for tree in trees.values():
        names: dict[str, tuple[str, str]] = {}  # 이름 → (모듈, 원래 이름 | "")
        for st in ast.walk(tree):
            if isinstance(st, ast.ImportFrom) and st.module and not st.level:
                for a in st.names:
                    names[a.asname or a.name] = (st.module, a.name)
            elif isinstance(st, ast.Import):
                for a in st.names:
                    names[a.asname or a.name.split(".")[0]] = (a.name, "")
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            if n.func.attr != "include_router" or not n.args:
                continue
            prefix = _const_str(_kw(n, "prefix"))
            if not prefix:
                continue
            arg = n.args[0]
            target: tuple[str | None, str] | None = None
            if isinstance(arg, ast.Name) and arg.id in names:
                mod, orig = names[arg.id]
                target = (file_of(mod), orig) if orig else None
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                base = names.get(arg.value.id)
                if base is not None:
                    mod = f"{base[0]}.{base[1]}" if base[1] else base[0]
                    target = (file_of(mod), arg.attr)
            if target and target[0]:
                out.setdefault((target[0], target[1]), prefix)
    return out


def _flask(path: str) -> str:
    return _FLASK_PARAM.sub(lambda m: "{" + m.group(1) + "}", path)


def _py_routes(trees: dict[str, ast.Module]) -> dict[tuple[str, int], dict]:
    """(파일, 줄) → route. 줄은 def 줄과 첫 데코레이터 줄 둘 다."""
    includes = _py_include_prefixes(trees)
    out: dict[tuple[str, int], dict] = {}
    for file, tree in trees.items():
        table = _py_tables(tree)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route = None
            for deco in fn.decorator_list:
                if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                    continue
                owner = deco.func.value
                if not isinstance(owner, ast.Name):
                    continue
                verb = deco.func.attr
                path = _const_str(deco.args[0]) if deco.args else None
                if path is None:
                    continue
                if verb in VERBS:
                    method = verb.upper()
                elif verb in ("route", "api_route"):
                    methods = _kw(deco, "methods")
                    first = None
                    if isinstance(methods, (ast.List, ast.Tuple)) and methods.elts:
                        first = _const_str(methods.elts[0])
                    method = (first or "GET").upper()
                else:
                    continue
                prefix = table.get(owner.id, "")
                inc = includes.get((file, owner.id), "")
                route = {"method": method, "path": _join(inc + prefix, _flask(path))}
                break
            if route is None:
                continue
            lines = {fn.lineno}
            if fn.decorator_list:
                lines.add(fn.decorator_list[0].lineno)
            for ln in lines:
                out.setdefault((file, ln), route)
    return out


# ---------------------------------------------------------------- TS/JS


def _str_value(n, src: bytes) -> str | None:
    """글자 상수의 값(따옴표 안). 템플릿은 `${…}`를 `*` 칸으로."""
    if n is None:
        return None
    if n.type == "string":
        return "".join(_text(c, src) for c in n.named_children if c.type == "string_fragment")
    if n.type == "template_string":
        out = []
        for c in n.named_children:
            if c.type == "string_fragment":
                out.append(_text(c, src))
            elif c.type == "template_substitution":
                out.append("*")
        return "".join(out)
    return None


def _args(call):
    a = call.child_by_field_name("arguments")
    return [] if a is None else [c for c in a.named_children if c.type != "comment"]


def _ts_router_names(root, src: bytes) -> set[str]:
    out: set[str] = set()
    for n in _walk(root):
        if n.type != "variable_declarator":
            continue
        name, val = n.child_by_field_name("name"), n.child_by_field_name("value")
        if name is None or val is None or name.type != "identifier":
            continue
        if val.type == "call_expression":
            f = val.child_by_field_name("function")
            if f is not None and _text(f, src) in _TS_ROUTER_CALLS:
                out.add(_text(name, src))
        elif val.type == "new_expression":
            c = val.child_by_field_name("constructor")
            if c is not None and _text(c, src) in _TS_ROUTER_NEWS:
                out.add(_text(name, src))
    return out


def _express(path: str) -> str:
    return _EXPRESS_PARAM.sub(lambda m: "{" + m.group(1) + "}", path)


def _next_path(file: str) -> str:
    parts = file.split("/")
    i = len(parts) - 1 - parts[::-1].index("app")
    segs = []
    for p in parts[i + 1 : -1]:
        if p.startswith("(") and p.endswith(")"):
            continue
        m = re.fullmatch(r"\[\[?(?:\.\.\.)?([^\]]+)\]?\]", p)
        segs.append("{" + m.group(1) + "}" if m else p)
    return norm("/".join(segs))


def _ts_routes(file: str, src: bytes, ts_names: dict, here: dict) -> list[tuple[dict, dict]]:
    """[(그래프 함수, route)] — 등록 차례. 핸들러 이름은 이 파일, 없으면 TS/JS에서 하나뿐인 것."""
    root = _ts_root(file, src)
    out: list[tuple[dict, dict]] = []
    routers = _ts_router_names(root, src)
    for n in _walk(root):
        if n.type == "call_expression":
            f = n.child_by_field_name("function")
            if f is None or f.type != "member_expression":
                continue
            obj, prop = f.child_by_field_name("object"), f.child_by_field_name("property")
            if obj is None or prop is None or _text(obj, src) not in routers:
                continue
            verb = _TS_VERBS.get(_text(prop, src))
            args = _args(n)
            path = _str_value(args[0], src) if args else None
            if verb is None or path is None or len(args) < 2:
                continue
            route = {"method": verb, "path": _express(norm(path))}
            h = args[-1]
            if h.type in ("arrow_function", "function_expression"):
                f_ = here.get(h.start_point[0] + 1)
                if f_ is not None:
                    out.append((f_, route))
            else:
                nm = _text(h, src).rsplit(".", 1)[-1]
                cands = [k for k in here.values() if k["name"] == nm] or ts_names.get(nm, [])
                if len(cands) == 1:
                    out.append((cands[0], route))
        elif n.type == "class_declaration":
            _nest(n, src, here, out)
    if _NEXT_ROUTE.search(file):
        for st in root.children:
            if st.type != "export_statement":
                continue
            for c in st.named_children:
                names = []
                if c.type == "function_declaration":
                    names.append((c.child_by_field_name("name"), c))
                elif c.type in ("lexical_declaration", "variable_declaration"):
                    for d in c.named_children:
                        if d.type == "variable_declarator":
                            names.append((d.child_by_field_name("name"), d))
                for nm, node in names:
                    if nm is None:
                        continue
                    verb = _text(nm, src)
                    if verb in _NEST.values() and verb != "ANY":
                        f_ = here.get(st.start_point[0] + 1) or here.get(node.start_point[0] + 1)
                        if f_ is not None:
                            out.append((f_, {"method": verb, "path": _next_path(file)}))
    return out


def _deco_call(d, src: bytes) -> tuple[str, str | None] | None:
    """`@Name('x')` → (Name, 'x' | None)."""
    call = next((c for c in d.named_children if c.type == "call_expression"), None)
    if call is None:
        return None
    f = call.child_by_field_name("function")
    if f is None:
        return None
    args = _args(call)
    return _text(f, src), (_str_value(args[0], src) if args else None)


def _nest(cls, src: bytes, here: dict, out: list) -> None:
    prefix = None
    # `export class`의 데코레이터는 export_statement의 자식이다
    owners = (
        [cls.parent] if cls.parent is not None and cls.parent.type == "export_statement" else []
    )
    for c in [*(ch for o in owners for ch in o.children), *cls.children]:
        if c.type == "decorator":
            got = _deco_call(c, src)
            if got and got[0] == "Controller":
                prefix = got[1] or ""
    if prefix is None:
        return
    body = cls.child_by_field_name("body")
    if body is None:
        return
    pending: list = []
    for m in body.children:
        if m.type == "decorator":
            pending.append(m)
            continue
        if m.type == "method_definition":
            decos = pending + [c for c in m.children if c.type == "decorator"]
            for d in decos:
                got = _deco_call(d, src)
                if got and got[0] in _NEST:
                    f_ = here.get(m.start_point[0] + 1)
                    if f_ is not None:
                        path = _join(prefix, _express(got[1] or ""))
                        out.append((f_, {"method": _NEST[got[0]], "path": path}))
                    break
        pending = []


# ---------------------------------------------------------------- Rust


def _rs_handlers(arg, src: bytes) -> list[tuple[str, str]]:
    """`get(h).post(g)` → [(GET, h), (POST, g)]."""
    out: list[tuple[str, str]] = []
    n = arg
    while n is not None and n.type == "call_expression":
        f = n.child_by_field_name("function")
        args = _args(n)
        if f is None:
            break
        if f.type == "identifier" or f.type == "scoped_identifier":
            nm = _text(f, src).rsplit("::", 1)[-1]
            if nm in _RS_VERBS and args:
                out.append((_RS_VERBS[nm], _text(_unparen(args[0]), src).rsplit("::", 1)[-1]))
            break
        if f.type == "field_expression":
            field = f.child_by_field_name("field")
            nm = _text(field, src) if field is not None else ""
            if nm in _RS_VERBS and args:
                out.append((_RS_VERBS[nm], _text(_unparen(args[0]), src).rsplit("::", 1)[-1]))
            n = f.child_by_field_name("value")
            continue
        break
    return list(reversed(out))


def _rs_str(n, src: bytes) -> str | None:
    if n is None or n.type != "string_literal":
        return None
    return "".join(_text(c, src) for c in n.named_children if c.type == "string_content")


def _rs_routes(src: bytes) -> tuple[list[tuple[str, str, str]], dict[int, dict]]:
    """axum `.route("경로", get(h)…)` → [(방법, 경로, 핸들러)] · actix 속성 → {fn 줄: route}."""
    root = _rs_root(src)
    chains: list[tuple[str, str, str]] = []
    attrs: dict[int, dict] = {}
    for n in _walk(root):
        if n.type == "call_expression":
            f = n.child_by_field_name("function")
            if f is None or f.type != "field_expression":
                continue
            field = f.child_by_field_name("field")
            if field is None or _text(field, src) != "route":
                continue
            args = _args(n)
            path = _rs_str(args[0], src) if args else None
            if path is None or len(args) < 2:
                continue
            for method, h in _rs_handlers(args[1], src):
                chains.append((method, norm(path), h))
        elif n.type == "function_item":
            prev = n.prev_named_sibling
            while prev is not None and prev.type in ("attribute_item", "line_comment"):
                if prev.type == "attribute_item":
                    attr = next((c for c in prev.named_children if c.type == "attribute"), None)
                    if attr is not None:
                        name = attr.named_children[0] if attr.named_children else None
                        nm = _text(name, src) if name is not None else ""
                        targs = next((c for c in attr.named_children
                                      if c.type == "token_tree"), None)  # fmt: skip
                        if nm in _RS_VERBS and targs is not None:
                            lit = next((c for c in targs.named_children
                                        if c.type == "string_literal"), None)  # fmt: skip
                            path = _rs_str(lit, src)
                            if path is not None:
                                kw = next((c for c in n.children if c.type == "fn"), n)
                                attrs[kw.start_point[0] + 1] = {"method": _RS_VERBS[nm],
                                                                "path": norm(path)}  # fmt: skip
                prev = prev.prev_named_sibling
    return chains, attrs


# ---------------------------------------------------------------- Java·Go (카드 CN)


def _java_str(n, src: bytes) -> str | None:
    """Java 글자 상수의 내용 — `"…"`만(이어 붙이기·상수 이름은 모른다)."""
    if n is None or n.type != "string_literal":
        return None
    return "".join(_text(c, src) for c in n.named_children if c.type == "string_fragment")


def _java_annotations(decl, src: bytes) -> list[tuple[str, object]]:
    """선언의 어노테이션 — [(이름의 마지막 조각, 인자 목록 | None)] 적힌 차례."""
    mods = next((c for c in decl.children if c.type == "modifiers"), None)
    out: list[tuple[str, object]] = []
    for a in mods.named_children if mods is not None else []:
        if a.type not in ("annotation", "marker_annotation"):
            continue
        name = a.child_by_field_name("name")
        if name is not None:
            out.append((_text(name, src).rsplit(".", 1)[-1], a.child_by_field_name("arguments")))
    return out


def _java_path(args, src: bytes) -> str | None:
    """`("/x")` · `(value = "/x")` · `(path = {"/x", "/y"})` → 첫 경로. 경로가 없으면 None."""
    if args is None:
        return None
    for c in args.named_children:
        val = c
        if c.type == "element_value_pair":
            key = c.child_by_field_name("key")
            if key is None or _text(key, src) not in ("value", "path"):
                continue
            val = c.child_by_field_name("value")
        if val is not None and val.type == "element_value_array_initializer":
            val = next((x for x in val.named_children if x.type == "string_literal"), None)
        got = _java_str(val, src)
        if got is not None:
            return got
    return None


def _java_method(args, src: bytes) -> str:
    """`@RequestMapping(method = RequestMethod.POST)` → POST, 없으면 ANY."""
    for c in args.named_children if args is not None else []:
        if c.type != "element_value_pair":
            continue
        key = c.child_by_field_name("key")
        if key is None or _text(key, src) != "method":
            continue
        val = c.child_by_field_name("value")
        if val is not None and val.type == "element_value_array_initializer":
            val = val.named_children[0] if val.named_children else None
        if val is not None:
            return _text(val, src).rsplit(".", 1)[-1].upper()
    return "ANY"


def _java_routes(src: bytes) -> dict[int, dict]:
    """Spring — 클래스 `@RequestMapping` 접두어 + 메서드 `@GetMapping`… → {선언 첫 줄: route}."""
    from app.core.codegraph.javago import _parse

    out: dict[int, dict] = {}
    for cls in _walk(_parse("java", src)):
        if cls.type != "class_declaration":
            continue
        prefix = ""
        for name, args in _java_annotations(cls, src):
            if name == "RequestMapping":
                prefix = _java_path(args, src) or ""
                break
        body = cls.child_by_field_name("body")
        for m in body.named_children if body is not None else []:
            if m.type != "method_declaration":
                continue
            for name, args in _java_annotations(m, src):
                if name not in _SPRING:
                    continue
                method = _SPRING[name] or _java_method(args, src)
                path = _SPRING_PARAM.sub(r"{\1}", _join(prefix, _java_path(args, src) or ""))
                out.setdefault(m.start_point[0] + 1, {"method": method, "path": path})
                break
    return out


def _go_routes(src: bytes) -> list[tuple[str, str, str]]:
    """Go — `X.HandleFunc("경로", h)`·gin·echo `X.GET`·chi `X.Get` → [(방법, 경로, 핸들러 이름)].
    `g := r.Group("/p")`의 접두어를 그 이름에 붙인다(같은 파일, 위에서부터)."""
    from app.core.codegraph.javago import _parse

    def lit(n) -> str | None:
        if n is None or n.type not in ("interpreted_string_literal", "raw_string_literal"):
            return None
        return "".join(_text(c, src) for c in n.named_children
                       if c.type in ("interpreted_string_literal_content",
                                     "raw_string_literal_content"))  # fmt: skip

    groups: dict[str, str] = {}
    out: list[tuple[str, str, str]] = []
    for n in _walk(_parse("go", src)):
        if n.type == "short_var_declaration":
            left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
            names = [c for c in left.named_children] if left is not None else []
            vals = [c for c in right.named_children] if right is not None else []
            if len(names) != 1 or len(vals) != 1 or vals[0].type != "call_expression":
                continue
            f = vals[0].child_by_field_name("function")
            args = _args(vals[0])
            if f is None or f.type != "selector_expression" or not args:
                continue
            op, field = f.child_by_field_name("operand"), f.child_by_field_name("field")
            p = lit(args[0])
            if field is not None and _text(field, src) == "Group" and p is not None:
                base = groups.get(_text(op, src), "") if op is not None else ""
                groups[_text(names[0], src)] = base + p
            continue
        if n.type != "call_expression":
            continue
        f = n.child_by_field_name("function")
        if f is None or f.type != "selector_expression":
            continue
        field = f.child_by_field_name("field")
        verb = _GO_VERBS.get(_text(field, src)) if field is not None else None
        args = _args(n)
        path = lit(args[0]) if args else None
        if verb is None or path is None or len(args) < 2:
            continue
        m = _GO_PATTERN.match(path)
        if m:
            verb, path = m.group(1), m.group(2)
        h = _unparen(args[-1])
        if h.type == "selector_expression":
            h = h.child_by_field_name("field")
        if h is None or h.type not in ("identifier", "field_identifier"):
            continue
        op = f.child_by_field_name("operand")
        prefix = groups.get(_text(op, src), "") if op is not None else ""
        path = _GO_REST.sub(r"{\1}", _GIN_PARAM.sub(r"{\1}", _join(prefix, path)))
        out.append((verb, path, _text(h, src)))
    return out


# ---------------------------------------------------------------- 묶기


def routes(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-024#routes.routes

    함수마다 받는 라우트 `{method, path}` 또는 null — FastAPI·Flask 데코레이터, Express·Fastify·Hono
    등록, NestJS 데코레이터, Next `app/**/route.ts`, axum `.route` 사슬, actix 속성,
    Spring 어노테이션, Go `HandleFunc`·gin·echo·chi 등록.
    """
    funcs = graph["functions"]
    for f in funcs:
        f["route"] = None
    by_file: dict[str, dict[int, dict]] = defaultdict(dict)
    by_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in funcs:
        by_file[f["file"]][f["line"]] = f
        by_name[(PurePosixPath(f["file"]).suffix, f["name"])].append(f)

    def give(f: dict, route: dict) -> None:
        if f["route"] is None:
            f["route"] = {"method": route["method"], "path": route["path"]}

    py_trees: dict[str, ast.Module] = {}
    py_files = {f for f in by_file if f.endswith(".py")}
    py_files |= {f["path"] for f in graph.get("files", []) if f["path"].endswith(".py")}
    for file in sorted(py_files, key=lambda x: x.encode("utf-8")):
        src = _read(src_dir, file)
        if src is None:
            continue
        try:
            py_trees[file] = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
    for (file, ln), route in sorted(_py_routes(py_trees).items()):
        f = by_file[file].get(ln)
        if f is not None:
            give(f, route)

    ts_names = defaultdict(list)
    for (suffix, name), fs in by_name.items():
        if suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            ts_names[name].extend(fs)
    for file in sorted(by_file):
        if not file.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
            continue
        src = _read(src_dir, file)
        if src is None:
            continue
        for f, route in _ts_routes(file, src, ts_names, by_file[file]):
            give(f, route)

    rs_names = {name: fs for (suffix, name), fs in by_name.items() if suffix == ".rs"}
    for file in sorted(by_file):
        if not file.endswith(".rs"):
            continue
        src = _read(src_dir, file)
        if src is None:
            continue
        chains, attrs = _rs_routes(src)
        here = by_file[file]
        for method, path, h in chains:
            cands = [f for f in here.values() if f["name"] == h] or rs_names.get(h, [])
            if len(cands) == 1:
                give(cands[0], {"method": method, "path": path})
        for ln, route in sorted(attrs.items()):
            if ln in here:
                give(here[ln], route)

    for file in sorted(by_file):
        if not file.endswith(".java"):
            continue
        src = _read(src_dir, file)
        if src is None:
            continue
        for ln, route in sorted(_java_routes(src).items()):
            if ln in by_file[file]:
                give(by_file[file][ln], route)

    go_names = {name: fs for (suffix, name), fs in by_name.items() if suffix == ".go"}
    for file in sorted(by_file):
        if not file.endswith(".go"):
            continue
        src = _read(src_dir, file)
        if src is None:
            continue
        folder = str(PurePosixPath(file).parent)
        for method, path, h in _go_routes(src):
            fs = go_names.get(h, [])
            cands = [f for f in fs if str(PurePosixPath(f["file"]).parent) == folder] or fs
            if len(cands) == 1:
                give(cands[0], {"method": method, "path": path})
    return graph


def _segs(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _match(req: list[str], route: list[str]) -> tuple[int, bool] | None:
    """칸마다 맞추기 → (글자-글자 맞은 수, 짐작인가) 또는 None."""
    if len(req) != len(route):
        return None
    score, guess = 0, False
    for a, b in zip(req, route, strict=True):
        param = b.startswith("{") and b.endswith("}")
        if a == "*":
            guess = guess or not param
        elif param:
            continue
        elif a == b:
            score += 1
        else:
            return None
    return score, guess


def _pick(req: list[str], method: str, routes_: list[tuple[str, list[str], str]],
          suffix: bool) -> list[tuple[str, bool]]:  # fmt: skip
    best: list[tuple[str, bool]] = []
    top = -1
    for key, segs, m in routes_:
        if m != method and m != "ANY":
            continue
        cand = segs[len(segs) - len(req) :] if suffix and len(segs) > len(req) else segs
        if suffix and len(segs) <= len(req):
            continue
        got = _match(req, cand)
        if got is None:
            continue
        score, guess = got
        if score > top:
            top, best = score, [(key, guess or suffix)]
        elif score == top:
            best.append((key, guess or suffix))
    if len(best) > 1:
        best = [(k, True) for k, _ in best]
    return best


def _is_front(file: str, web_dirs: list[str]) -> bool:
    if file.endswith((".tsx", ".jsx")):
        return True
    if not file.endswith((".ts", ".js", ".mjs")):
        return False
    return any(d == "" or file.startswith(d + "/") for d in web_dirs)


def http_links(src_dir: Path, graph: dict) -> list[dict]:
    """SYNC-MS-024#routes.http_links

    화면 파일 함수의 요청(`fetch`·`api.get(…)` — 첫 인자가 `/`로 시작하는 글자)을 라우트 함수에
    칸마다 맞춰 잇는다. 맞는 것이 없으면 끝맞춤. `[{from, to, inferred}]`, (from, to) 바이트 순.
    """
    from app.core.codegraph.steps import _ts_defs

    web_dirs = [u["dir"] for u in graph.get("units", []) if u.get("kind") == "web"]
    routes_ = [(f["key"], _segs(f["route"]["path"]), f["route"]["method"])
               for f in graph["functions"] if f.get("route")]  # fmt: skip
    if not routes_:
        return []
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in graph["functions"]:
        if _is_front(f["file"], web_dirs):
            by_file[f["file"]].append(f)
    found: dict[tuple[str, str], bool] = {}
    for file in sorted(by_file):
        src = _read(src_dir, file)
        if src is None:
            continue
        root = _ts_root(file, src)
        routers = _ts_router_names(root, src)
        defs = _ts_defs(root)
        for f in by_file[file]:
            node = defs.get(f["line"])
            body = node.child_by_field_name("body") if node is not None else None
            if body is None:
                continue
            for n in _walk(body):
                if n.type != "call_expression":
                    continue
                req = _request(n, src, routers)
                if req is None:
                    continue
                method, path = req
                segs = _segs(path.split("?", 1)[0])
                hits = _pick(segs, method, routes_, False) or _pick(segs, method, routes_, True)
                for to, inferred in hits:
                    found.setdefault((f["key"], to), inferred)
    pairs = sorted(found, key=lambda p: (p[0].encode("utf-8"), p[1].encode("utf-8")))
    return [{"from": a, "to": b, "inferred": found[(a, b)]} for a, b in pairs]


def _request(call, src: bytes, routers: set[str]) -> tuple[str, str] | None:
    f = call.child_by_field_name("function")
    if f is None:
        return None
    f = _unparen(f)
    if f.type == "identifier":
        name = _text(f, src)
    elif f.type == "member_expression":
        obj, prop = f.child_by_field_name("object"), f.child_by_field_name("property")
        if prop is None:
            return None
        if obj is not None and _text(obj, src) in routers:
            return None  # 서버의 라우트 등록 — 요청이 아니다
        name = _text(prop, src)
    else:
        return None
    if name not in _REQ_NAMES:
        return None
    args = _args(call)
    if not args:
        return None
    path = _str_value(args[0], src)
    if path is None or not path.startswith("/"):
        return None
    if name in ("fetch", "request"):
        method = "GET"
        if len(args) > 1 and args[1].type == "object":
            for p in args[1].named_children:
                if p.type != "pair":
                    continue
                k = p.child_by_field_name("key")
                if k is not None and _text(k, src).strip("'\"") == "method":
                    v = _str_value(p.child_by_field_name("value"), src)
                    if v:
                        method = v.upper()
    else:
        method = "DELETE" if name == "del" else name.upper()
    return method, path
