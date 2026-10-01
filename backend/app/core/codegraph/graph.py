"""SYNC-MS-011 — core/codegraph/graph.py. 코드 호출 그래프 — 추출·줄이기·보강·대조(카드 AX).

DB를 모른다. 서버(pipeline.build_code_graph)와 검사기(tools/check_calls.py)가 같은 함수를 불러
같은 결과를 낸다 — 사람·모델·에이전트·검사기가 한 대조를 본다([[SYNC-PRD-001#R13]]).

그래프 모양 `{functions: [{key, name, qual, file, line, end, ms, community}],
calls: [[from, to, via]], communities: [{id, label, size}]}` — key는 `파일:줄`, via는
`graphify`(graphify가 찾은 선) 또는 `enrich`(싱크독이 보강한 선), community는 graphify 군집
번호(카드 BD — 2026-10-01 이전 그래프에는 없다).
"""

from __future__ import annotations

import ast
import json
import logging
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from app.core.errors import CodeGraphFailed
from app.core.types import CallDiff
from app.infra import graphify

log = logging.getLogger(__name__)

# graphify가 읽는 코드 파일 — 이것이 바뀐 커밋만 그래프를 다시 만든다 (UC-S8 1a)
CODE_EXTS = frozenset(
    ".py .ts .tsx .js .jsx .mjs .go .rs .java .kt .scala .rb .php .cs .c .h .cpp .hpp"
    " .swift .lua .ex .exs .jl .sh .sql .vue .svelte".split()
)
_MS_ID = re.compile(r"^([A-Z][A-Z0-9]*-MS-\d+#[\w.]+)")
# 모듈 이름 대신 폴더 이름을 쓰는 파일 — core/codegraph/service.py의 함수는 codegraph.x
_PKG_STEMS = frozenset({"service", "__init__", "index"})
_REF = re.compile(r"\[\[([^\]]+)\]\]")
_TICK = re.compile(r"`([A-Za-z_][\w.]*)")
_CALLS_LINE = "**호출하는 것**"


def touches_code(paths: list[str]) -> bool:
    """SYNC-MS-011#codegraph.touches_code"""
    for p in paths:
        if p.startswith("docs/specs/") or p.startswith("graphify-out/") or "/graphify-out/" in p:
            continue  # 명세·graphify 결과는 코드가 아니다
        if PurePosixPath(p).suffix.lower() in CODE_EXTS:
            return True
    return False


async def load(src_dir: Path) -> tuple[str, dict]:
    """SYNC-MS-011#codegraph.load

    저장소에 커밋된 graphify-out/graph.json이 있으면 그것(`repo`), 없으면 서버가 추출(`server`).
    """
    committed = src_dir / "graphify-out" / "graph.json"
    if committed.is_file():
        try:
            return "repo", json.loads(committed.read_text(encoding="utf-8"))
        except ValueError as e:
            raise CodeGraphFailed("graph.json 형식") from e
    return "server", await graphify.extract(src_dir)


_TEST_FILE = re.compile(
    r"(^|/)(tests?|__tests__)/|(^|/)(test_[^/]*|[^/]*_test)\.py$|\.(test|spec)\.[jt]sx?$|(^|/)conftest\.py$"
)


def _is_test(file: str) -> bool:
    """테스트 코드는 구현이 아니다 — 대조에서 뺀다."""
    return bool(_TEST_FILE.search(file))


def _clean(label: str) -> str:
    return label.strip().lstrip(".").removesuffix("()")


def _module(file: str) -> str:
    p = PurePosixPath(file)
    return p.parent.name if p.stem in _PKG_STEMS and p.parent.name else p.stem


def _node_key(n: dict) -> tuple[str, int] | None:
    """raw 노드의 (파일, 줄) — `source_file` + `source_location`의 `L` 뒤 숫자. 없으면 None.

    reduce의 함수 key 규칙이다. communities도 같은 규칙으로 노드와 함수를 잇는다.
    """
    file = n.get("source_file")
    loc = str(n.get("source_location") or "")
    if not file or not loc.startswith("L") or not loc[1:].isdigit():
        return None
    return file, int(loc[1:])


def reduce(raw: dict) -> dict:
    """SYNC-MS-011#codegraph.reduce

    함수·메서드와 그 사이 호출 선만 남긴다. import·포함·문서·docstring·개념 노드는 버린다.
    """
    nodes = {n["id"]: n for n in raw.get("nodes", [])}
    links = raw.get("links") or raw.get("edges") or []
    owner: dict[str, str] = {}  # 메서드 노드 → 클래스 이름 (method 선은 클래스 → 메서드)
    ms: dict[str, str] = {}  # 함수 노드 → docstring 첫 줄의 항목 ID
    for e in links:
        rel = e.get("relation")
        if rel == "method" and e.get("source") in nodes:
            owner[e["target"]] = _clean(nodes[e["source"]].get("label", ""))
        elif rel == "rationale_for" and e.get("source") in nodes:
            m = _MS_ID.match(str(nodes[e["source"]].get("label", "")).strip())
            if m:
                ms[e["target"]] = m.group(1)
    key_of: dict[str, str] = {}
    functions: list[dict] = []
    keys: set[str] = set()
    for nid, n in nodes.items():
        if not n.get("_callable") or n.get("_callable_class"):
            continue
        fl = _node_key(n)
        if fl is None or _is_test(fl[0]):
            continue
        file, line = fl
        key = f"{file}:{line}"
        key_of[nid] = key
        if key in keys:
            continue  # 같은 자리 둘 — 하나로 접는다
        keys.add(key)
        name = _clean(str(n.get("label", "")))
        cls = owner.get(nid)
        functions.append(
            {
                "key": key,
                "name": name,
                "qual": f"{cls}.{name}" if cls else f"{_module(file)}.{name}",
                "file": file,
                "line": line,
                "end": None,
                "ms": ms.get(nid),
            }
        )
    seen: set[tuple[str, str]] = set()
    calls: list[list[str]] = []
    for e in links:
        if e.get("relation") not in ("calls", "indirect_call"):
            continue
        if e.get("confidence") == "INFERRED":
            continue  # 이름만 보고 추측한 선 — 테스트의 같은 이름 함수로 잘못 잇기도 한다
        a, b = key_of.get(e.get("source", "")), key_of.get(e.get("target", ""))
        if a and b and a != b and (a, b) not in seen:
            seen.add((a, b))
            calls.append([a, b, "graphify"])
    return {"functions": functions, "calls": calls}


def _defs(tree: ast.Module):
    """모듈 맨 위 함수와 클래스의 메서드 — (클래스 이름 | None, 정의)."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield None, node
        elif isinstance(node, ast.ClassDef):
            for b in node.body:
                if isinstance(b, ast.FunctionDef | ast.AsyncFunctionDef):
                    yield node.name, b


def _ann_name(ann: ast.expr | None) -> str | None:
    """인자 주석에서 클래스 이름 — `Cls` · `mod.Cls` · `"Cls"` · `Cls | None`."""
    if isinstance(ann, ast.Name):
        return ann.id
    if isinstance(ann, ast.Attribute):
        return ann.attr
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        return ann.value.split("|")[0].strip().split(".")[-1] or None
    if isinstance(ann, ast.BinOp):
        return _ann_name(ann.left) or _ann_name(ann.right)
    return None


def _bind(target: ast.expr, value: ast.expr, env: dict[str, str], classes: dict) -> None:
    """`x = Cls(…)` · `a, b = A(…), B(…)` — 타입을 아는 변수로 적는다."""
    pairs: list[tuple[ast.expr, ast.expr]] = []
    if isinstance(target, ast.Name):
        pairs = [(target, value)]
    elif isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple):
        pairs = list(zip(target.elts, value.elts, strict=False))
    for t, v in pairs:
        if (
            isinstance(t, ast.Name)
            and isinstance(v, ast.Call)
            and isinstance(v.func, ast.Name)
            and v.func.id in classes
        ):
            env[t.id] = v.func.id


class _Ctx:
    """보강에 쓰는 이름표 — 클래스의 메서드, 파일의 맨 위 함수, 점 이름 → 파일."""

    def __init__(self) -> None:
        self.classes: dict[str, dict[str, str]] = defaultdict(dict)  # 클래스 → 메서드 → key
        self.module_funcs: dict[str, dict[str, str]] = defaultdict(dict)  # 파일 → 함수 → key
        self.modules: dict[str, str] = {}  # 점 이름 꼬리(`app.infra.git`·`git`) → 파일

    def index_modules(self, files: list[str]) -> None:
        dup: set[str] = set()
        for f in files:
            parts = PurePosixPath(f).with_suffix("").parts
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                name = ".".join(parts[i:])
                if name in self.modules and self.modules[name] != f:
                    dup.add(name)
                self.modules[name] = f
        for d in dup:  # 겹치는 꼬리는 모호하다
            self.modules.pop(d, None)


def _imports(
    nodes: list[ast.stmt] | list[ast.AST], file: str, ctx: _Ctx
) -> tuple[dict[str, str], dict[str, str]]:
    """import 문 → (모듈 별칭 → 파일, 가져온 함수 이름 → key). 상대 import도 푼다."""
    mods: dict[str, str] = {}
    names: dict[str, str] = {}
    pkg = list(PurePosixPath(file).parent.parts)
    for node in nodes:
        if isinstance(node, ast.Import):
            for al in node.names:
                if al.asname and al.name in ctx.modules:
                    mods[al.asname] = ctx.modules[al.name]
                elif al.name in ctx.modules and "." not in al.name:
                    mods[al.name] = ctx.modules[al.name]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                base = ".".join([*up, *([base] if base else [])])
            for al in node.names:
                alias = al.asname or al.name
                sub = f"{base}.{al.name}" if base else al.name
                if sub in ctx.modules:  # `from app.infra import git` — 모듈을 가져왔다
                    mods[alias] = ctx.modules[sub]
                elif base in ctx.modules:  # `from app.core.x import f` — 함수를 가져왔다
                    key = ctx.module_funcs.get(ctx.modules[base], {}).get(al.name)
                    if key:
                        names[alias] = key
    return mods, names


def _resolve(
    cls: str | None,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    ctx: _Ctx,
    file_mods: dict[str, str],
    file_names: dict[str, str],
) -> set[str]:
    """함수 몸통의 호출과 넘기는 참조 → 그래프 안 함수의 key.

    `x.m` · `Cls(…).m` · `self.m`(타입을 아는 객체의 메서드) · `mod.f`(가져온 모듈의 함수) ·
    `f(…)`(가져온 함수). 호출이 아니라 인자로 넘겨도(`closure(pk, refs.upstream)`) 센다.
    """
    classes = ctx.classes
    env: dict[str, str] = {}
    a = fn.args
    for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
        t = _ann_name(arg.annotation)
        if t in classes:
            env[arg.arg] = t
    # 두 번 훑는다 — ast.walk는 너비 우선이라 대입보다 호출을 먼저 볼 수 있다.
    # 대입을 다 모은 뒤 푼다. 함수 안 import는 부르는 쪽이 file_mods·file_names에 합쳐 준다
    nodes = list(ast.walk(fn))
    for node in nodes:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            _bind(node.targets[0], node.value, env, classes)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            t = _ann_name(node.annotation)
            if isinstance(node.target, ast.Name) and t in classes:
                env[node.target.id] = t
            else:
                _bind(node.target, node.value, env, classes)
    mods, names = file_mods, file_names
    out: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            base, attr = node.value, node.attr
            c: str | None = None
            if (
                isinstance(base, ast.Call)
                and isinstance(base.func, ast.Name)
                and base.func.id in classes
            ):
                c = base.func.id
            elif isinstance(base, ast.Name) and base.id in env:
                c = env[base.id]
            elif isinstance(base, ast.Name) and base.id == "self" and cls:
                c = cls
            if c and attr in classes.get(c, {}):
                out.add(classes[c][attr])
            elif isinstance(base, ast.Name) and base.id in mods:
                key = ctx.module_funcs.get(mods[base.id], {}).get(attr)
                if key:
                    out.add(key)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in names:
                out.add(names[node.func.id])
    return out


def enrich(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-011#codegraph.enrich

    파이썬 파일을 AST로 다시 읽어 끝 줄·이름·항목 ID를 바로잡고, graphify가 놓친 호출을 더한다 —
    변수에 담은 객체의 메서드, 가져온 모듈·함수, 인자로 넘기는 메서드. 다른 언어는 손대지 않는다.
    """
    funcs: list[dict] = graph["functions"]
    by_loc = {(f["file"], f["line"]): f for f in funcs}
    ctx = _Ctx()
    trees: dict[str, ast.Module] = {}
    found: list[tuple[str, dict, str | None, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    files = sorted({f["file"] for f in funcs if f["file"].endswith(".py")})
    ctx.index_modules(files)
    for file in files:
        try:
            tree = ast.parse((src_dir / file).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        trees[file] = tree
        for cls, fn in _defs(tree):
            heads = [fn.lineno, *(d.lineno for d in fn.decorator_list)]
            f = next((by_loc[(file, ln)] for ln in heads if (file, ln) in by_loc), None)
            if f is None:  # graphify가 놓친 정의 — 더한다
                f = {"key": f"{file}:{fn.lineno}", "name": fn.name, "qual": "", "file": file,
                     "line": fn.lineno, "end": None, "ms": None}  # fmt: skip
                funcs.append(f)
                by_loc[(file, fn.lineno)] = f
            f["end"] = fn.end_lineno
            f["qual"] = f"{cls}.{fn.name}" if cls else f"{_module(file)}.{fn.name}"
            doc = ast.get_docstring(fn)
            if doc:
                m = _MS_ID.match(doc.strip().splitlines()[0].strip())
                if m:
                    f["ms"] = m.group(1)
            if cls:
                ctx.classes[cls][fn.name] = f["key"]
            else:
                ctx.module_funcs[file][fn.name] = f["key"]
            found.append((file, f, cls, fn))
    file_imports = {file: _imports(tree.body, file, ctx) for file, tree in trees.items()}
    have = {(c[0], c[1]) for c in graph["calls"]}
    for file, f, cls, fn in found:
        mods, names = file_imports[file]
        inner = [n for n in ast.walk(fn) if isinstance(n, ast.Import | ast.ImportFrom)]
        local = _imports(
            inner, file, ctx
        )  # 순환을 피한 함수 안 import (`from app.core import pipeline`)
        for dst in sorted(_resolve(cls, fn, ctx, {**mods, **local[0]}, {**names, **local[1]})):
            if dst != f["key"] and (f["key"], dst) not in have:
                have.add((f["key"], dst))
                graph["calls"].append([f["key"], dst, "enrich"])
    return graph


def _short_names(ids: set[str]) -> dict[str, str]:
    """항목 ID의 `#` 뒤 → 항목 ID. 겹치는 이름은 모호하니 뺀다."""
    names: dict[str, str] = {}
    dup: set[str] = set()
    for i in ids:
        n = i.split("#", 1)[1]
        if n in names:
            dup.add(n)
        names[n] = i
    for n in dup:
        names.pop(n, None)
    return names


def _louvain(g, resolution: float = 1.0) -> dict[int, list[str]]:
    """Louvain 군집(seed 42) — MS-011 communities 2. graphify cluster의 재쪼개기 없이 (#253).

    Louvain은 노드·선 순서에 민감하다 — 노드와 양 끝을 정렬한 선으로 다시 만들어 넣는다.
    번호는 크기 내림차순(같으면 정렬한 노드 튜플) — 0이 가장 큰 군집.
    """
    import networkx as nx

    u = nx.Graph()
    u.add_nodes_from(sorted(g.nodes(), key=str))
    u.add_edges_from(sorted(tuple(sorted((str(a), str(b)))) for a, b in g.edges()))
    if u.number_of_edges() == 0:
        comms = [{n} for n in u.nodes()]
    else:
        comms = nx.community.louvain_communities(u, resolution=resolution, seed=42)
    ordered = sorted(comms, key=lambda c: (-len(c), tuple(sorted(c))))
    return {i: sorted(c) for i, c in enumerate(ordered)}


def communities(raw: dict, graph: dict) -> dict:
    """SYNC-MS-011#codegraph.communities

    raw 그래프(파일·클래스·호출 선이 다 든 것)를 networkx Louvain으로 군집해 함수마다 커뮤니티
    번호를 붙이고 `communities`를 더한다. enrich 뒤에 — 보강이 더한 함수는 파일의 커뮤니티를
    받는다. 모델·네트워크 없이 결정적(seed 42). graphify `cluster`는 안 쓴다 — 응집도 재쪼개기가
    싱크독을 100개 넘는 군집으로 터뜨린다(#253). 라벨만 graphify의 허브 라벨 — 후보는 코드
    노드만(#255). 군집이 실패해도 그래프는 남는다.
    """
    functions: list[dict] = graph["functions"]
    by_key: dict[str, int] = {}
    file_votes: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    labels: dict[int, str] = {}
    nodes = {n["id"]: n for n in raw.get("nodes", []) if "id" in n}
    if nodes:
        try:
            from graphify.cluster import label_communities_by_hub
            from graphify.paths import load_node_link_graph

            g = load_node_link_graph(raw)
            found = _louvain(g)
            # 라벨 허브는 코드 노드만 — 문서·절 노드가 허브면 「SEQUENCE: 싱크독」 같은
            # 이름이 된다 (#255)
            code_only = {
                cid: [n for n in members if nodes.get(n, {}).get("source_file")]
                for cid, members in found.items()
            }
            named = label_communities_by_hub(g, code_only)
            labels = {cid: _clean(str(lab)) for cid, lab in named.items()}
            for cid, members in found.items():
                for nid in members:
                    n = nodes.get(nid)
                    fl = _node_key(n) if n else None
                    if fl is None:
                        continue
                    by_key[f"{fl[0]}:{fl[1]}"] = cid
                    file_votes[fl[0]][cid] += 1
        except Exception as e:  # noqa: BLE001 — 군집은 덤이다. 그래프 만들기를 깨지 않는다
            log.warning("code graph 군집 실패 — 커뮤니티 없이 둔다: %s", e)
            by_key, file_votes, labels = {}, defaultdict(lambda: defaultdict(int)), {}
    by_file = {f: min(v.items(), key=lambda kv: (-kv[1], kv[0]))[0] for f, v in file_votes.items()}
    sizes: dict[int, int] = defaultdict(int)
    for f in functions:
        cid = by_key.get(f["key"], by_file.get(f["file"]))
        f["community"] = cid
        if cid is not None:
            sizes[cid] += 1
    graph["communities"] = [
        {"id": cid, "label": labels.get(cid, str(cid)), "size": size}
        for cid, size in sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return graph


def spec_calls(items: list[tuple[str, str]]) -> dict[str, set[str]]:
    """SYNC-MS-011#codegraph.spec_calls

    항목마다 「호출하는 것」 줄의 `[[…]]`와 백틱 이름 중 MINISPEC 항목인 것만.
    """
    ids = {i for i, _ in items}
    names = _short_names(ids)
    out: dict[str, set[str]] = {}
    for ms_id, body in items:
        doc = ms_id.split("#", 1)[0]
        found: set[str] = set()
        line = next((ln for ln in body.splitlines() if ln.startswith(_CALLS_LINE)), None)
        if line:
            for r in _REF.findall(line):
                r = r.strip()
                rid = f"{doc}{r}" if r.startswith("#") else r
                if rid in ids:
                    found.add(rid)
            for t in _TICK.findall(line):
                if t in names:
                    found.add(names[t])
        found.discard(ms_id)
        out[ms_id] = found
    return out


def compare(graph: dict, spec: dict[str, set[str]]) -> list[CallDiff]:
    """SYNC-MS-011#codegraph.compare

    코드 호출은 항목이 없는 함수(도우미)를 건너 항목이 있는 함수에 닿을 때까지 따라간다.
    """
    names = _short_names(set(spec))
    fn_ms: dict[str, str] = {}  # 함수 key → 항목 ID
    ms_fn: dict[str, str] = {}  # 항목 ID → 함수 key (docstring이 이름보다 먼저)
    by_name: dict[str, list[str]] = defaultdict(list)
    for f in graph.get("functions", []):
        if f.get("ms"):
            fn_ms[f["key"]] = f["ms"]
            ms_fn.setdefault(f["ms"], f["key"])
        elif f.get("qual") in names:
            by_name[names[f["qual"]]].append(f["key"])
    for mid, keys in by_name.items():
        if mid not in ms_fn and len(keys) == 1:  # 이름이 겹치면 잇지 않는다
            ms_fn[mid] = keys[0]
            fn_ms[keys[0]] = mid
    adj: dict[str, list[str]] = defaultdict(list)
    for c in graph.get("calls", []):
        adj[c[0]].append(c[1])
    out: list[CallDiff] = []
    for mid in sorted(spec):
        key = ms_fn.get(mid)
        want = spec[mid]
        if key is None:
            out.append(CallDiff(mid, None, [], [], sorted(want)))
            continue
        code: set[str] = set()
        seen = {key}
        stack = [key]
        while stack:
            for v in adj.get(stack.pop(), ()):
                if v in seen:
                    continue
                seen.add(v)
                if v in fn_ms:
                    code.add(fn_ms[v])  # 항목이 있는 함수 — 여기서 멈춘다
                else:
                    stack.append(v)  # 도우미 — 건너 계속
        code.discard(mid)
        out.append(
            CallDiff(mid, key, sorted(want & code), sorted(code - want), sorted(want - code))
        )
    return out
