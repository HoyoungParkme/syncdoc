"""SYNC-MS-011 enrich 2i~2l — Java·Go 보강(카드 CM). graph.py의 enrich가 부른다.

graphify의 Java 추출은 끝 줄·항목·파일 사이 호출을 주지 않고, Go 추출은 함수에 `_callable`이
없어 reduce가 다 버린다 — 정의·끝 줄·항목 ID·호출을 tree-sitter로 채운다.
Rust 판(`crates/codegraph/src/java.rs`·`go.rs`)이 같은 결과를 낸다.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

_LANGS: dict[str, object] = {}

_JAVA_TYPES = frozenset({"class_declaration", "interface_declaration", "enum_declaration",
                         "record_declaration"})  # fmt: skip
_JAVA_COMMENTS = ("line_comment", "block_comment")
_JAVA_FNS = frozenset({"method_declaration", "constructor_declaration"})
_GO_MODULE = re.compile(r"^module\s+(\S+)", re.M)


def _parse(lang: str, src: bytes):
    import tree_sitter as ts

    if lang not in _LANGS:
        if lang == "java":
            import tree_sitter_java as tsl
        else:
            import tree_sitter_go as tsl
        _LANGS[lang] = ts.Language(tsl.language())
    return ts.Parser(_LANGS[lang]).parse(src).root_node


def _text(n, src: bytes) -> str:
    return src[n.start_byte : n.end_byte].decode("utf-8", errors="replace")


def _comment_first(text: str) -> str | None:
    """주석 하나의 첫 내용 줄 — 블록 주석은 기호와 줄 앞 `*`를 떼고, `//`는 그 뒤."""
    if text.startswith("/*"):
        body = text[2:]
        if body.endswith("*/"):
            body = body[:-2]
        if body.startswith("*"):
            body = body[1:]
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("*"):
                line = line[1:].strip()
            if line:
                return line
        return None
    line = text[2:].strip()
    return line or None


def _doc(node, src: bytes, kinds: tuple[str, ...]) -> str | None:
    """선언 바로 앞의 주석(빈 줄 없이 붙은 것) — 블록 주석 하나 또는 줄 주석 묶음의 첫 내용 줄."""
    run = []
    top = node.start_point[0]
    p = node.prev_sibling
    while p is not None and p.type in kinds and p.end_point[0] >= top - 1:
        text = _text(p, src)
        run.append(text)
        if text.startswith("/*"):
            break
        top = p.start_point[0]
        p = p.prev_sibling
    for text in reversed(run):
        first = _comment_first(text)
        if first:
            return first
    return None


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


# ---------------------------------------------------------------- Java


def _jtype(n, src: bytes) -> str | None:
    """타입 노드 → 단순 이름. 제네릭은 뗀다(`List<T>` → List) · `a.b.T` → T."""
    while n is not None:
        if n.type == "type_identifier":
            return _text(n, src)
        if n.type == "generic_type":
            n = n.named_children[0] if n.named_children else None
        elif n.type == "scoped_type_identifier":
            ids = [c for c in n.named_children if c.type == "type_identifier"]
            return _text(ids[-1], src) if ids else None
        else:
            return None
    return None


class _JavaFile:
    def __init__(self, file: str, src: bytes) -> None:
        self.file, self.src = file, src
        self.root = _parse("java", src)
        # (타입, 이름, 선언 첫 줄(애노테이션 포함), 끝 줄, 선언 노드, 문서 첫 줄)
        self.defs: list[tuple[str, str, int, int, object, str | None]] = []
        self.types: list[str] = []
        self.fields: dict[str, dict[str, str]] = {}  # 타입 → 필드 → 타입
        self._types(self.root)

    def _types(self, node) -> None:
        for c in node.named_children:
            if c.type in _JAVA_TYPES:
                self._type(c)

    def _type(self, decl) -> None:
        name_node = decl.child_by_field_name("name")
        body = decl.child_by_field_name("body")
        if name_node is None or body is None:
            return
        owner = _text(name_node, self.src)
        self.types.append(owner)
        fields = self.fields.setdefault(owner, {})
        members = list(body.named_children)
        for m in body.named_children:
            if m.type == "enum_body_declarations":
                members.extend(m.named_children)
        for m in members:
            if m.type in _JAVA_FNS and m.child_by_field_name("body") is not None:
                n = m.child_by_field_name("name")
                if n is None:
                    continue
                self.defs.append((owner, _text(n, self.src), m.start_point[0] + 1,
                                  m.end_point[0] + 1, m,
                                  _doc(m, self.src, _JAVA_COMMENTS)))  # fmt: skip
            elif m.type == "field_declaration":
                t = _jtype(m.child_by_field_name("type"), self.src)
                for d in m.named_children:
                    if d.type == "variable_declarator" and t:
                        dn = d.child_by_field_name("name")
                        if dn is not None:
                            fields[_text(dn, self.src)] = t
            elif m.type in _JAVA_TYPES:
                self._type(m)


def _java_locals(fn, src: bytes) -> dict[str, str]:
    """매개변수·지역 변수의 타입 — `T x`, `var x = new T(…)`."""
    out: dict[str, str] = {}
    params = fn.child_by_field_name("parameters")
    for p in params.named_children if params is not None else []:
        if p.type in ("formal_parameter", "spread_parameter"):
            t = _jtype(p.child_by_field_name("type"), src)
            n = p.child_by_field_name("name")
            if n is None:
                n = next((c for c in p.named_children if c.type == "variable_declarator"), None)
                n = n.child_by_field_name("name") if n is not None else None
            if t and n is not None:
                out[_text(n, src)] = t
    body = fn.child_by_field_name("body")
    for n in _walk(body):
        if n.type != "local_variable_declaration":
            continue
        tnode = n.child_by_field_name("type")
        t = _jtype(tnode, src)
        for d in n.named_children:
            if d.type != "variable_declarator":
                continue
            dn = d.child_by_field_name("name")
            v = d.child_by_field_name("value")
            vt = t
            if tnode is not None and _text(tnode, src) == "var":
                vt = (
                    _jtype(v.child_by_field_name("type"), src)
                    if v is not None and v.type == "object_creation_expression"
                    else None
                )
            if vt and dn is not None:
                out[_text(dn, src)] = vt
    return out


def enrich_java(src_dir: Path, graph: dict, seen_files: list[str], is_test, item_of) -> None:
    """MS-011 enrich 2i·2j — Java 메서드·생성자의 끝 줄·qual·항목, 빠진 정의, 호출 선."""
    funcs: list[dict] = graph["functions"]
    by_loc = {(f["file"], f["line"]): f for f in funcs}
    files = sorted({f["file"] for f in funcs if f["file"].endswith(".java")} | set(seen_files))
    parsed: list[_JavaFile] = []
    for file in files:
        if is_test(file):
            continue
        try:
            parsed.append(_JavaFile(file, (src_dir / file).read_bytes()))
        except (OSError, ValueError):
            continue
    count: dict[str, int] = {}
    for jf in parsed:
        for t in set(jf.types):
            count[t] = count.get(t, 0) + 1
    methods: dict[str, dict[str, list[str]]] = {}  # 타입 → 이름 → key들
    for jf in parsed:
        for owner, name, line, end, _node, doc in jf.defs:
            f = by_loc.get((jf.file, line))
            if f is None:
                f = {"key": f"{jf.file}:{line}", "name": name, "qual": "", "file": jf.file,
                     "line": line, "end": None, "item": None, "ms": None}  # fmt: skip
                funcs.append(f)
                by_loc[(jf.file, line)] = f
            f["name"] = name
            f["end"] = end
            f["qual"] = f"{owner}.{name}"
            if doc:
                it, m = item_of(doc)
                if it:
                    f["item"], f["ms"] = it, m
            if count.get(owner) == 1:
                keys = methods.setdefault(owner, {}).setdefault(name, [])
                if f["key"] not in keys:
                    keys.append(f["key"])
    have = {(c[0], c[1]) for c in graph["calls"]}
    for jf in parsed:
        for owner, _name, line, _end, node, _doc in jf.defs:
            key = f"{jf.file}:{line}"
            local = _java_locals(node, jf.src)
            fields = jf.fields.get(owner, {})
            dsts: set[str] = set()
            for n in _walk(node.child_by_field_name("body")):
                t = m = None
                if n.type == "method_invocation":
                    m = _text(n.child_by_field_name("name"), jf.src)
                    obj = n.child_by_field_name("object")
                    if obj is None or obj.type == "this":
                        t = owner
                    elif obj.type == "identifier":
                        x = _text(obj, jf.src)
                        t = local.get(x) or fields.get(x) or (x if x in methods else None)
                    elif (
                        obj.type == "field_access"
                        and (o := obj.child_by_field_name("object")) is not None
                        and o.type == "this"
                    ):
                        f_ = obj.child_by_field_name("field")
                        t = fields.get(_text(f_, jf.src)) if f_ is not None else None
                elif n.type == "object_creation_expression":
                    t = _jtype(n.child_by_field_name("type"), jf.src)
                    m = t
                if t and m:
                    dsts.update(methods.get(t, {}).get(m, []))
            for dst in sorted(dsts):
                if dst != key and (key, dst) not in have:
                    have.add((key, dst))
                    graph["calls"].append([key, dst, "enrich"])


# ---------------------------------------------------------------- Go


def _gotype(n, src: bytes) -> str | None:
    """타입 노드 → 이름. 포인터·제네릭을 뗀다(`*T`·`T[K]` → T)."""
    while n is not None:
        if n.type == "type_identifier":
            return _text(n, src)
        if n.type in ("pointer_type", "generic_type", "parenthesized_type"):
            n = n.named_children[0] if n.named_children else None
        else:
            return None
    return None


class _GoFile:
    def __init__(self, file: str, src: bytes) -> None:
        self.file, self.src = file, src
        self.dir = str(PurePosixPath(file).parent)
        self.root = _parse("go", src)
        self.package = ""
        # (타입 | None, 이름, func 줄, 끝 줄, 선언 노드, 받는 쪽 이름, 문서 첫 줄)
        self.defs: list[tuple[str | None, str, int, int, object, str | None, str | None]] = []
        self.imports: dict[str, str] = {}  # 이름 → import 경로
        for c in self.root.named_children:
            if c.type == "package_clause":
                pid = next((x for x in c.named_children if x.type == "package_identifier"), None)
                self.package = _text(pid, src) if pid is not None else ""
            elif c.type == "import_declaration":
                for spec in _walk(c):
                    if spec.type != "import_spec":
                        continue
                    path_node = spec.child_by_field_name("path")
                    if path_node is None:
                        continue
                    path = _text(path_node, src).strip('"`')
                    alias = spec.child_by_field_name("name")
                    name = _text(alias, src) if alias is not None else path.rsplit("/", 1)[-1]
                    if name not in ("_", "."):
                        self.imports[name] = path
            elif c.type in ("function_declaration", "method_declaration"):
                n = c.child_by_field_name("name")
                if n is None or c.child_by_field_name("body") is None:
                    continue
                owner = recv = None
                if c.type == "method_declaration":
                    r = c.child_by_field_name("receiver")
                    p = (
                        next(
                            (x for x in r.named_children if x.type == "parameter_declaration"), None
                        )
                        if r is not None
                        else None
                    )
                    if p is not None:
                        owner = _gotype(p.child_by_field_name("type"), src)
                        rn = p.child_by_field_name("name")
                        recv = _text(rn, src) if rn is not None else None
                    if owner is None:
                        continue
                self.defs.append((owner, _text(n, src), c.start_point[0] + 1, c.end_point[0] + 1,
                                  c, recv, _doc(c, src, ("comment",))))  # fmt: skip


def _go_locals(fn, src: bytes, owner: str | None, recv: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if owner and recv:
        out[recv] = owner
    params = fn.child_by_field_name("parameters")
    for p in params.named_children if params is not None else []:
        if p.type != "parameter_declaration":
            continue
        t = _gotype(p.child_by_field_name("type"), src)
        for nm in p.named_children:
            if nm.type == "identifier" and t:
                out[_text(nm, src)] = t
    for n in _walk(fn.child_by_field_name("body")):
        if n.type == "short_var_declaration":
            left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
            if left is None or right is None:
                continue
            names = [c for c in left.named_children if c.type == "identifier"]
            vals = list(right.named_children)
            for nm, v in zip(names, vals, strict=False):
                if v.type == "unary_expression":
                    v = v.child_by_field_name("operand") or v
                if v.type == "composite_literal":
                    t = _gotype(v.child_by_field_name("type"), src)
                    if t:
                        out[_text(nm, src)] = t
        elif n.type == "var_spec":
            t = _gotype(n.child_by_field_name("type"), src)
            for nm in n.named_children:
                if nm.type == "identifier" and t:
                    out[_text(nm, src)] = t
    return out


def _go_modules(src_dir: Path, dirs: set[str]) -> list[tuple[str, str]]:
    """go.mod 모듈 경로 → 그 폴더 — 패키지 폴더에서 위로 찾은 것들, 경로 바이트 순."""
    found: dict[str, str] = {}
    for d in sorted(dirs, key=lambda x: x.encode()):
        cur = PurePosixPath(d)
        while True:
            mod = src_dir / cur / "go.mod" if str(cur) != "." else src_dir / "go.mod"
            try:
                text = mod.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = None
            if text is not None:
                m = _GO_MODULE.search(text)
                if m:
                    found[m.group(1)] = "" if str(cur) == "." else str(cur)
                break
            if str(cur) in (".", ""):
                break
            cur = cur.parent
    return sorted(found.items(), key=lambda kv: kv[0].encode())


def enrich_go(src_dir: Path, graph: dict, seen_files: list[str], is_test, item_of) -> None:
    """MS-011 enrich 2k·2l — Go 함수·메서드의 정의·끝 줄·qual·항목과 호출 선."""
    funcs: list[dict] = graph["functions"]
    by_loc = {(f["file"], f["line"]): f for f in funcs}
    files = sorted({f["file"] for f in funcs if f["file"].endswith(".go")} | set(seen_files))
    parsed: list[_GoFile] = []
    for file in files:
        if is_test(file):
            continue
        try:
            parsed.append(_GoFile(file, (src_dir / file).read_bytes()))
        except (OSError, ValueError):
            continue
    fns: dict[str, dict[str, str]] = {}  # 폴더 → 함수 이름 → key
    meths: dict[str, dict[str, dict[str, str]]] = {}  # 폴더 → 타입 → 메서드 → key
    for gf in parsed:
        for owner, name, line, end, _node, _recv, doc in gf.defs:
            f = by_loc.get((gf.file, line))
            if f is None:
                f = {"key": f"{gf.file}:{line}", "name": name, "qual": "", "file": gf.file,
                     "line": line, "end": None, "item": None, "ms": None}  # fmt: skip
                funcs.append(f)
                by_loc[(gf.file, line)] = f
            f["name"] = name
            f["end"] = end
            f["qual"] = f"{owner}.{name}" if owner else f"{gf.package}.{name}"
            if doc:
                it, m = item_of(doc)
                if it:
                    f["item"], f["ms"] = it, m
            if owner:
                meths.setdefault(gf.dir, {}).setdefault(owner, {}).setdefault(name, f["key"])
            else:
                fns.setdefault(gf.dir, {}).setdefault(name, f["key"])
    modules = _go_modules(src_dir, {gf.dir for gf in parsed})

    def dir_of(path: str) -> str | None:
        for mod, d in modules:
            if path == mod or path.startswith(mod + "/"):
                rest = path[len(mod) :].lstrip("/")
                return str(PurePosixPath(d) / rest) if d and rest else (rest or d or ".")
        return None

    have = {(c[0], c[1]) for c in graph["calls"]}
    for gf in parsed:
        for owner, _name, line, _end, node, recv, _doc in gf.defs:
            key = f"{gf.file}:{line}"
            local = _go_locals(node, gf.src, owner, recv)
            dsts: set[str] = set()
            for n in _walk(node.child_by_field_name("body")):
                if n.type != "call_expression":
                    continue
                fn = n.child_by_field_name("function")
                if fn is None:
                    continue
                if fn.type == "identifier":
                    hit = fns.get(gf.dir, {}).get(_text(fn, gf.src))
                    if hit:
                        dsts.add(hit)
                elif fn.type == "selector_expression":
                    op, field = fn.child_by_field_name("operand"), fn.child_by_field_name("field")
                    if op is None or field is None or op.type != "identifier":
                        continue
                    x, m = _text(op, gf.src), _text(field, gf.src)
                    if x in local:
                        hit = meths.get(gf.dir, {}).get(local[x], {}).get(m)
                    elif x in gf.imports and (d := dir_of(gf.imports[x])) is not None:
                        hit = fns.get(d, {}).get(m)
                    else:
                        hit = None
                    if hit:
                        dsts.add(hit)
            for dst in sorted(dsts):
                if dst != key and (key, dst) not in have:
                    have.add((key, dst))
                    graph["calls"].append([key, dst, "enrich"])
