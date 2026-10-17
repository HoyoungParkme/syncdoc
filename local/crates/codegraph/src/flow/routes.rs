//! 라우트와 화면 요청 (SYNC-MS-026 · MS-024 routes, 카드 L23).
//! 라우트는 함수마다 `route = {method, path}`, 화면 요청은 그래프의 `http = [{from, to, inferred}]`.
//! 경로 매개변수는 `{이름}` 꼴로 맞춘다. 파이썬 파일은 tree-sitter-python으로 `ast`의 뜻을 읽는다(MS-026 0장).

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;
use std::sync::LazyLock;

use regex::Regex;
use serde_json::{Value, json};
use tree_sitter::Node;

use super::{named_children, read, rs_parse, text, ts_parse, unparen, walk};
use crate::graph::suffix;
use crate::python;

const VERBS: [&str; 7] = ["get", "post", "put", "patch", "delete", "head", "options"];
const TS_EXTS: [&str; 5] = [".ts", ".tsx", ".js", ".jsx", ".mjs"];
const TS_ROUTER_CALLS: [&str; 5] = ["express", "express.Router", "Router", "fastify", "Fastify"];
const TS_ROUTER_NEWS: [&str; 3] = ["Hono", "Router", "KoaRouter"];
const REQ_NAMES: [&str; 9] = [
    "fetch", "get", "post", "put", "patch", "delete", "del", "head", "request",
];

static NEXT_ROUTE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(^|/)app/(.*/)?route\.(ts|js)$").expect("next"));
static NEXT_SEG: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\[\[?(?:\.\.\.)?([^\]]+)\]?\]$").expect("next seg"));
static FLASK_PARAM: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"<(?:[^<>:]+:)?([^<>]+)>").expect("flask"));
static EXPRESS_PARAM: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r":([A-Za-z_][A-Za-z0-9_]*)").expect("express"));
static SPRING_PARAM: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\{([A-Za-z_][A-Za-z0-9_]*):[^{}]*\}").expect("spring"));
static GO_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)[\t\n\x0B\x0C\r ]+(/.*)$")
        .expect("go pattern")
});
static GIN_PARAM: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[:*]([A-Za-z_][A-Za-z0-9_]*)").expect("gin"));
static GO_REST: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\{([A-Za-z_][A-Za-z0-9_]*)\.\.\.\}").expect("go rest"));

fn spring_verb(v: &str) -> Option<Option<&'static str>> {
    Some(match v {
        "GetMapping" => Some("GET"),
        "PostMapping" => Some("POST"),
        "PutMapping" => Some("PUT"),
        "PatchMapping" => Some("PATCH"),
        "DeleteMapping" => Some("DELETE"),
        "RequestMapping" => None,
        _ => return None,
    })
}

fn go_verb(v: &str) -> Option<&'static str> {
    Some(match v {
        "GET" | "Get" => "GET",
        "POST" | "Post" => "POST",
        "PUT" | "Put" => "PUT",
        "PATCH" | "Patch" => "PATCH",
        "DELETE" | "Delete" => "DELETE",
        "HandleFunc" | "Handle" | "Any" => "ANY",
        _ => return None,
    })
}

/// 파이썬 라우터 생성자 → 접두어 인자 이름 (`Flask`는 접두어가 없다)
fn py_router(kind: &str) -> Option<Option<&'static str>> {
    match kind {
        "APIRouter" | "FastAPI" => Some(Some("prefix")),
        "Blueprint" => Some(Some("url_prefix")),
        "Flask" => Some(None),
        _ => None,
    }
}

fn ts_verb(v: &str) -> Option<&'static str> {
    Some(match v {
        "get" => "GET",
        "post" => "POST",
        "put" => "PUT",
        "patch" => "PATCH",
        "delete" => "DELETE",
        "all" => "ANY",
        _ => return None,
    })
}

fn nest_verb(v: &str) -> Option<&'static str> {
    Some(match v {
        "Get" => "GET",
        "Post" => "POST",
        "Put" => "PUT",
        "Patch" => "PATCH",
        "Delete" => "DELETE",
        "Head" => "HEAD",
        "Options" => "OPTIONS",
        "All" => "ANY",
        _ => return None,
    })
}

fn rs_verb(v: &str) -> Option<&'static str> {
    Some(match v {
        "get" => "GET",
        "post" => "POST",
        "put" => "PUT",
        "patch" => "PATCH",
        "delete" => "DELETE",
        "head" => "HEAD",
        "options" => "OPTIONS",
        "any" => "ANY",
        _ => return None,
    })
}

/// 앞에 `/`, 끝 `/`는 뗀다(`/`만 남으면 `/`)
pub(crate) fn norm(path: &str) -> String {
    let mut p = if path.starts_with('/') {
        path.to_string()
    } else {
        format!("/{path}")
    };
    if p.len() > 1 {
        let t = p.trim_end_matches('/');
        p = if t.is_empty() { "/".into() } else { t.into() };
    }
    p
}

fn join(prefix: &str, path: &str) -> String {
    if prefix.is_empty() {
        norm(path)
    } else {
        norm(&format!(
            "{}/{}",
            prefix.trim_end_matches('/'),
            path.trim_start_matches('/')
        ))
    }
}

fn route(method: &str, path: String) -> Value {
    json!({"method": method, "path": path})
}

fn row(n: Node) -> i64 {
    n.start_position().row as i64 + 1
}

// ---------------------------------------------------------------- 파이썬

struct PyTree {
    file: String,
    pf: python::PyFile,
}

fn py_text(n: Node, src: &str) -> String {
    python::text(n, src).to_string()
}

/// 호출의 위치 인자 — `ast.Call.args`(이름 붙은 인자·`**` 뺀다)
fn py_args(call: Node) -> Vec<Node> {
    call.child_by_field_name("arguments")
        .filter(|a| a.kind() == "argument_list")
        .map(|a| {
            named_children(a)
                .into_iter()
                .filter(|c| {
                    !matches!(
                        c.kind(),
                        "keyword_argument" | "comment" | "dictionary_splat"
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

fn py_kw<'t>(call: Node<'t>, name: &str, src: &str) -> Option<Node<'t>> {
    let args = call.child_by_field_name("arguments")?;
    named_children(args)
        .into_iter()
        .filter(|c| c.kind() == "keyword_argument")
        .find(|k| {
            k.child_by_field_name("name")
                .is_some_and(|n| python::text(n, src) == name)
        })
        .and_then(|k| k.child_by_field_name("value"))
}

fn const_str(n: Option<Node>, src: &str) -> Option<String> {
    python::string_value(unparen(n?), src)
}

fn last_name(n: Node, src: &str) -> Option<String> {
    let n = unparen(n);
    match n.kind() {
        "identifier" => Some(py_text(n, src)),
        "attribute" => n.child_by_field_name("attribute").map(|a| py_text(a, src)),
        _ => None,
    }
}

/// 맨 위 `X = APIRouter(prefix=…)` → {X: 접두어}
fn py_tables(t: &PyTree) -> HashMap<String, String> {
    let src = &t.pf.src;
    let mut out = HashMap::new();
    for st in named_children(t.pf.tree.root_node()) {
        if st.kind() != "expression_statement" {
            continue;
        }
        let Some(a) = named_children(st).into_iter().next() else {
            continue;
        };
        if a.kind() != "assignment" || a.child_by_field_name("type").is_some() {
            continue;
        }
        // `a = b = X()` — 대상은 사슬의 왼쪽들, 값은 맨 끝
        let mut targets = Vec::new();
        let mut cur = a;
        let value = loop {
            if let Some(l) = cur.child_by_field_name("left") {
                targets.push(l);
            }
            match cur.child_by_field_name("right") {
                Some(r) if r.kind() == "assignment" && r.child_by_field_name("type").is_none() => {
                    cur = r
                }
                r => break r,
            }
        };
        let Some(value) = value.map(unparen) else {
            continue;
        };
        if value.kind() != "call" {
            continue;
        }
        let Some(kind) = value
            .child_by_field_name("function")
            .and_then(|f| last_name(f, src))
        else {
            continue;
        };
        let Some(key) = py_router(&kind) else {
            continue;
        };
        let prefix = key
            .and_then(|k| const_str(py_kw(value, k, src), src))
            .unwrap_or_default();
        for t in targets {
            if t.kind() == "identifier" {
                out.insert(py_text(t, src), prefix.clone());
            }
        }
    }
    out
}

fn py_dotted(file: &str) -> String {
    let stem = match suffix(file) {
        "" => file,
        s => &file[..file.len() - s.len()],
    };
    let mut parts: Vec<&str> = stem.split('/').filter(|p| !p.is_empty()).collect();
    if parts.last() == Some(&"__init__") {
        parts.pop();
    }
    parts.join(".")
}

/// `app.include_router(Z, prefix="…")` → {(파일, 라우터 이름): 접두어} — 한 단만
fn py_include_prefixes(trees: &[PyTree]) -> HashMap<(String, String), String> {
    let dotted: Vec<(String, &str)> = trees
        .iter()
        .map(|t| (py_dotted(&t.file), t.file.as_str()))
        .collect();
    let file_of = |m: &str| -> Option<String> {
        let suffix = format!(".{m}");
        let hits: Vec<&str> = dotted
            .iter()
            .filter(|(d, _)| d == m || d.ends_with(&suffix))
            .map(|(_, f)| *f)
            .collect();
        (hits.len() == 1).then(|| hits[0].to_string())
    };
    let mut out: HashMap<(String, String), String> = HashMap::new();
    for t in trees {
        let src = &t.pf.src;
        let nodes = python::walk(t.pf.tree.root_node());
        let mut names: HashMap<String, (String, String)> = HashMap::new();
        for st in &nodes {
            match st.kind() {
                "import_from_statement" => {
                    let (level, module) = python::from_module(*st, src);
                    if module.is_empty() || level > 0 {
                        continue;
                    }
                    let module_node = st.child_by_field_name("module_name");
                    for al in named_children(*st) {
                        if Some(al) == module_node {
                            continue;
                        }
                        let (name, asname) = match al.kind() {
                            "dotted_name" => (python::dotted(al, src), None),
                            "aliased_import" => (
                                al.child_by_field_name("name")
                                    .map(|x| python::dotted(x, src))
                                    .unwrap_or_default(),
                                al.child_by_field_name("alias").map(|x| py_text(x, src)),
                            ),
                            "wildcard_import" => ("*".to_string(), None),
                            _ => continue,
                        };
                        names.insert(
                            asname.unwrap_or_else(|| name.clone()),
                            (module.clone(), name),
                        );
                    }
                }
                "import_statement" => {
                    for al in named_children(*st) {
                        let (name, asname) = match al.kind() {
                            "dotted_name" => (python::dotted(al, src), None),
                            "aliased_import" => (
                                al.child_by_field_name("name")
                                    .map(|x| python::dotted(x, src))
                                    .unwrap_or_default(),
                                al.child_by_field_name("alias").map(|x| py_text(x, src)),
                            ),
                            _ => continue,
                        };
                        let key = asname
                            .unwrap_or_else(|| name.split('.').next().unwrap_or("").to_string());
                        names.insert(key, (name, String::new()));
                    }
                }
                _ => {}
            }
        }
        for n in &nodes {
            if n.kind() != "call" {
                continue;
            }
            let Some(f) = n.child_by_field_name("function").map(unparen) else {
                continue;
            };
            if f.kind() != "attribute"
                || f.child_by_field_name("attribute")
                    .map(|a| py_text(a, src))
                    .as_deref()
                    != Some("include_router")
            {
                continue;
            }
            let args = py_args(*n);
            let Some(arg) = args.first().map(|a| unparen(*a)) else {
                continue;
            };
            let prefix = const_str(py_kw(*n, "prefix", src), src).unwrap_or_default();
            if prefix.is_empty() {
                continue;
            }
            let mut target: Option<(Option<String>, String)> = None;
            if arg.kind() == "identifier" {
                if let Some((m, orig)) = names.get(&py_text(arg, src))
                    && !orig.is_empty()
                {
                    target = Some((file_of(m), orig.clone()));
                }
            } else if arg.kind() == "attribute"
                && let Some(obj) = arg.child_by_field_name("object").map(unparen)
                && obj.kind() == "identifier"
                && let Some(base) = names.get(&py_text(obj, src))
            {
                let m = if base.1.is_empty() {
                    base.0.clone()
                } else {
                    format!("{}.{}", base.0, base.1)
                };
                let attr = arg
                    .child_by_field_name("attribute")
                    .map(|a| py_text(a, src))
                    .unwrap_or_default();
                target = Some((file_of(&m), attr));
            }
            if let Some((Some(file), name)) = target {
                out.entry((file, name)).or_insert(prefix);
            }
        }
    }
    out
}

fn flask(path: &str) -> String {
    FLASK_PARAM.replace_all(path, "{$1}").into_owned()
}

/// (파일, 줄) → route. 줄은 def 줄과 첫 데코레이터 줄 둘 다
fn py_routes(trees: &[PyTree]) -> BTreeMap<(String, i64), Value> {
    let includes = py_include_prefixes(trees);
    let mut out = BTreeMap::new();
    for t in trees {
        let src = &t.pf.src;
        let table = py_tables(t);
        for fnode in python::walk(t.pf.tree.root_node()) {
            if fnode.kind() != "function_definition" {
                continue;
            }
            let decos: Vec<Node> = fnode
                .parent()
                .filter(|p| p.kind() == "decorated_definition")
                .map(|p| {
                    named_children(p)
                        .into_iter()
                        .filter(|c| c.kind() == "decorator")
                        .collect()
                })
                .unwrap_or_default();
            let mut found = None;
            for d in &decos {
                let Some(call) = named_children(*d)
                    .into_iter()
                    .find(|c| c.kind() != "comment")
                    .map(unparen)
                else {
                    continue;
                };
                if call.kind() != "call" {
                    continue;
                }
                let Some(f) = call.child_by_field_name("function").map(unparen) else {
                    continue;
                };
                if f.kind() != "attribute" {
                    continue;
                }
                let Some(owner) = f.child_by_field_name("object").map(unparen) else {
                    continue;
                };
                if owner.kind() != "identifier" {
                    continue;
                }
                let verb = f
                    .child_by_field_name("attribute")
                    .map(|a| py_text(a, src))
                    .unwrap_or_default();
                let Some(path) = const_str(py_args(call).first().copied(), src) else {
                    continue;
                };
                let method = if VERBS.contains(&verb.as_str()) {
                    verb.to_uppercase()
                } else if verb == "route" || verb == "api_route" {
                    let mut first = None;
                    if let Some(m) = py_kw(call, "methods", src).map(unparen)
                        && matches!(m.kind(), "list" | "tuple")
                    {
                        let elts: Vec<Node> = named_children(m)
                            .into_iter()
                            .filter(|c| c.kind() != "comment")
                            .collect();
                        if let Some(e) = elts.first() {
                            first = const_str(Some(*e), src);
                        }
                    }
                    first
                        .filter(|s| !s.is_empty())
                        .unwrap_or_else(|| "GET".into())
                        .to_uppercase()
                } else {
                    continue;
                };
                let owner_name = py_text(owner, src);
                let prefix = table.get(&owner_name).cloned().unwrap_or_default();
                let inc = includes
                    .get(&(t.file.clone(), owner_name))
                    .cloned()
                    .unwrap_or_default();
                found = Some(route(
                    &method,
                    join(&format!("{inc}{prefix}"), &flask(&path)),
                ));
                break;
            }
            let Some(r) = found else { continue };
            let mut lines = vec![row(fnode)];
            if let Some(d) = decos.first() {
                lines.push(row(*d));
            }
            for ln in lines {
                out.entry((t.file.clone(), ln)).or_insert_with(|| r.clone());
            }
        }
    }
    out
}

// ---------------------------------------------------------------- TS/JS

/// 글자 상수의 값(따옴표 안). 템플릿은 `${…}`를 `*` 칸으로
pub(crate) fn str_value(n: Option<Node>, src: &[u8]) -> Option<String> {
    let n = n?;
    match n.kind() {
        "string" => Some(
            named_children(n)
                .into_iter()
                .filter(|c| c.kind() == "string_fragment")
                .map(|c| text(c, src))
                .collect(),
        ),
        "template_string" => {
            let mut out = String::new();
            for c in named_children(n) {
                match c.kind() {
                    "string_fragment" => out.push_str(&text(c, src)),
                    "template_substitution" => out.push('*'),
                    _ => {}
                }
            }
            Some(out)
        }
        _ => None,
    }
}

pub(crate) fn args(call: Node) -> Vec<Node> {
    call.child_by_field_name("arguments")
        .map(|a| {
            named_children(a)
                .into_iter()
                .filter(|c| c.kind() != "comment")
                .collect()
        })
        .unwrap_or_default()
}

pub(crate) fn ts_router_names(root: Node, src: &[u8]) -> HashSet<String> {
    let mut out = HashSet::new();
    for n in walk(root) {
        if n.kind() != "variable_declarator" {
            continue;
        }
        let (Some(name), Some(val)) = (
            n.child_by_field_name("name"),
            n.child_by_field_name("value"),
        ) else {
            continue;
        };
        if name.kind() != "identifier" {
            continue;
        }
        if val.kind() == "call_expression" {
            if let Some(f) = val.child_by_field_name("function")
                && TS_ROUTER_CALLS.contains(&text(f, src).as_str())
            {
                out.insert(text(name, src));
            }
        } else if val.kind() == "new_expression"
            && let Some(c) = val.child_by_field_name("constructor")
            && TS_ROUTER_NEWS.contains(&text(c, src).as_str())
        {
            out.insert(text(name, src));
        }
    }
    out
}

fn express(path: &str) -> String {
    EXPRESS_PARAM.replace_all(path, "{$1}").into_owned()
}

fn next_path(file: &str) -> String {
    let parts: Vec<&str> = file.split('/').collect();
    let i = parts.iter().rposition(|p| *p == "app").unwrap_or(0);
    let mut segs: Vec<String> = Vec::new();
    for p in &parts[i + 1..parts.len() - 1] {
        if p.starts_with('(') && p.ends_with(')') {
            continue;
        }
        match NEXT_SEG.captures(p) {
            Some(m) => segs.push(format!("{{{}}}", &m[1])),
            None => segs.push(p.to_string()),
        }
    }
    norm(&segs.join("/"))
}

type Here = Vec<(i64, usize)>;

/// 줄 → 그래프 함수 번호 (파이썬 사전처럼 같은 줄이면 나중 것, 자리는 처음 것)
fn here_get(here: &Here, line: i64) -> Option<usize> {
    here.iter().find(|(l, _)| *l == line).map(|(_, i)| *i)
}

fn ts_routes(
    file: &str,
    src: &[u8],
    ts_names: &HashMap<String, Vec<usize>>,
    here: &Here,
    names: &[String],
) -> Vec<(usize, Value)> {
    let Some(tree) = ts_parse(file, src) else {
        return Vec::new();
    };
    let root = tree.root_node();
    let mut out = Vec::new();
    let routers = ts_router_names(root, src);
    for n in walk(root) {
        if n.kind() == "call_expression" {
            let Some(f) = n.child_by_field_name("function") else {
                continue;
            };
            if f.kind() != "member_expression" {
                continue;
            }
            let (Some(obj), Some(prop)) = (
                f.child_by_field_name("object"),
                f.child_by_field_name("property"),
            ) else {
                continue;
            };
            if !routers.contains(&text(obj, src)) {
                continue;
            }
            let verb = ts_verb(&text(prop, src));
            let a = args(n);
            let path = str_value(a.first().copied(), src);
            let (Some(verb), Some(path)) = (verb, path) else {
                continue;
            };
            if a.len() < 2 {
                continue;
            }
            let r = route(verb, express(&norm(&path)));
            let h = a[a.len() - 1];
            if matches!(h.kind(), "arrow_function" | "function_expression") {
                if let Some(i) = here_get(here, row(h)) {
                    out.push((i, r));
                }
            } else {
                let full = text(h, src);
                let nm = full.rsplit('.').next().unwrap_or("").to_string();
                let local: Vec<usize> = here
                    .iter()
                    .map(|(_, i)| *i)
                    .filter(|i| names[*i] == nm)
                    .collect();
                let cands = if local.is_empty() {
                    ts_names.get(&nm).cloned().unwrap_or_default()
                } else {
                    local
                };
                if cands.len() == 1 {
                    out.push((cands[0], r));
                }
            }
        } else if n.kind() == "class_declaration" {
            nest(n, src, here, &mut out);
        }
    }
    if NEXT_ROUTE.is_match(file) {
        let mut c = root.walk();
        for st in root.children(&mut c) {
            if st.kind() != "export_statement" {
                continue;
            }
            for ch in named_children(st) {
                let mut names: Vec<(Option<Node>, Node)> = Vec::new();
                if ch.kind() == "function_declaration" {
                    names.push((ch.child_by_field_name("name"), ch));
                } else if matches!(ch.kind(), "lexical_declaration" | "variable_declaration") {
                    for d in named_children(ch) {
                        if d.kind() == "variable_declarator" {
                            names.push((d.child_by_field_name("name"), d));
                        }
                    }
                }
                for (nm, node) in names {
                    let Some(nm) = nm else { continue };
                    let verb = text(nm, src);
                    if matches!(
                        verb.as_str(),
                        "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS"
                    ) && let Some(i) =
                        here_get(here, row(st)).or_else(|| here_get(here, row(node)))
                    {
                        out.push((i, route(&verb, next_path(file))));
                    }
                }
            }
        }
    }
    out
}

/// `@Name('x')` → (Name, 'x' | 없음)
fn deco_call(d: Node, src: &[u8]) -> Option<(String, Option<String>)> {
    let call = named_children(d)
        .into_iter()
        .find(|c| c.kind() == "call_expression")?;
    let f = call.child_by_field_name("function")?;
    let a = args(call);
    Some((text(f, src), str_value(a.first().copied(), src)))
}

fn nest(cls: Node, src: &[u8], here: &Here, out: &mut Vec<(usize, Value)>) {
    let mut prefix: Option<String> = None;
    // `export class`의 데코레이터는 export_statement의 자식이다
    let mut kids = Vec::new();
    if let Some(p) = cls.parent().filter(|p| p.kind() == "export_statement") {
        kids.extend(super::children(p));
    }
    kids.extend(super::children(cls));
    for c in kids {
        if c.kind() == "decorator"
            && let Some((name, arg)) = deco_call(c, src)
            && name == "Controller"
        {
            prefix = Some(arg.unwrap_or_default());
        }
    }
    let Some(prefix) = prefix else { return };
    let Some(body) = cls.child_by_field_name("body") else {
        return;
    };
    let mut pending: Vec<Node> = Vec::new();
    for m in super::children(body) {
        if m.kind() == "decorator" {
            pending.push(m);
            continue;
        }
        if m.kind() == "method_definition" {
            let mut decos = pending.clone();
            decos.extend(
                super::children(m)
                    .into_iter()
                    .filter(|c| c.kind() == "decorator"),
            );
            for d in decos {
                if let Some((name, arg)) = deco_call(d, src)
                    && let Some(verb) = nest_verb(&name)
                {
                    if let Some(i) = here_get(here, row(m)) {
                        let path = join(&prefix, &express(&arg.unwrap_or_default()));
                        out.push((i, route(verb, path)));
                    }
                    break;
                }
            }
        }
        pending.clear();
    }
}

// ---------------------------------------------------------------- Rust

fn last_path(s: &str) -> String {
    s.rsplit("::").next().unwrap_or("").to_string()
}

/// `get(h).post(g)` → [(GET, h), (POST, g)]
fn rs_handlers(arg: Node, src: &[u8]) -> Vec<(&'static str, String)> {
    let mut out = Vec::new();
    let mut n = Some(arg);
    while let Some(cur) = n.filter(|x| x.kind() == "call_expression") {
        let Some(f) = cur.child_by_field_name("function") else {
            break;
        };
        let a = args(cur);
        if matches!(f.kind(), "identifier" | "scoped_identifier") {
            let nm = last_path(&text(f, src));
            if let Some(v) = rs_verb(&nm)
                && let Some(first) = a.first()
            {
                out.push((v, last_path(&text(unparen(*first), src))));
            }
            break;
        }
        if f.kind() == "field_expression" {
            let nm = f
                .child_by_field_name("field")
                .map(|x| text(x, src))
                .unwrap_or_default();
            if let Some(v) = rs_verb(&nm)
                && let Some(first) = a.first()
            {
                out.push((v, last_path(&text(unparen(*first), src))));
            }
            n = f.child_by_field_name("value");
            continue;
        }
        break;
    }
    out.reverse();
    out
}

fn rs_str(n: Option<Node>, src: &[u8]) -> Option<String> {
    let n = n.filter(|n| n.kind() == "string_literal")?;
    Some(
        named_children(n)
            .into_iter()
            .filter(|c| c.kind() == "string_content")
            .map(|c| text(c, src))
            .collect(),
    )
}

type RsChain = (&'static str, String, String);

/// axum `.route("경로", get(h)…)` → [(방법, 경로, 핸들러)] · actix 속성 → {fn 줄: route}
fn rs_routes(src: &[u8]) -> (Vec<RsChain>, BTreeMap<i64, Value>) {
    let mut chains = Vec::new();
    let mut attrs = BTreeMap::new();
    let Some(tree) = rs_parse(src) else {
        return (chains, attrs);
    };
    for n in walk(tree.root_node()) {
        if n.kind() == "call_expression" {
            let Some(f) = n
                .child_by_field_name("function")
                .filter(|f| f.kind() == "field_expression")
            else {
                continue;
            };
            if f.child_by_field_name("field")
                .map(|x| text(x, src))
                .as_deref()
                != Some("route")
            {
                continue;
            }
            let a = args(n);
            let Some(path) = rs_str(a.first().copied(), src) else {
                continue;
            };
            if a.len() < 2 {
                continue;
            }
            for (method, h) in rs_handlers(a[1], src) {
                chains.push((method, norm(&path), h));
            }
        } else if n.kind() == "function_item" {
            let mut prev = n.prev_named_sibling();
            while let Some(p) =
                prev.filter(|p| matches!(p.kind(), "attribute_item" | "line_comment"))
            {
                if p.kind() == "attribute_item"
                    && let Some(attr) = named_children(p)
                        .into_iter()
                        .find(|c| c.kind() == "attribute")
                {
                    let kids = named_children(attr);
                    let nm = kids.first().map(|x| text(*x, src)).unwrap_or_default();
                    let targs = kids.iter().find(|c| c.kind() == "token_tree");
                    if let (Some(v), Some(targs)) = (rs_verb(&nm), targs) {
                        let lit = named_children(*targs)
                            .into_iter()
                            .find(|c| c.kind() == "string_literal");
                        if let Some(path) = rs_str(lit, src) {
                            let kw = super::children(n)
                                .into_iter()
                                .find(|c| c.kind() == "fn")
                                .unwrap_or(n);
                            attrs.insert(row(kw), route(v, norm(&path)));
                        }
                    }
                }
                prev = p.prev_named_sibling();
            }
        }
    }
    (chains, attrs)
}

// ---------------------------------------------------------------- 묶기

// ---------------------------------------------------------------- Java·Go (카드 L33)

/// Java 글자 상수의 내용 — `"…"`만
fn java_str(n: Option<Node>, src: &[u8]) -> Option<String> {
    let n = n.filter(|n| n.kind() == "string_literal")?;
    Some(
        named_children(n)
            .into_iter()
            .filter(|c| c.kind() == "string_fragment")
            .map(|c| text(c, src))
            .collect(),
    )
}

/// 선언의 어노테이션 — [(이름의 마지막 조각, 인자 목록)] 적힌 차례
fn java_annotations<'t>(decl: Node<'t>, src: &[u8]) -> Vec<(String, Option<Node<'t>>)> {
    let mut c = decl.walk();
    let Some(mods) = decl.children(&mut c).find(|x| x.kind() == "modifiers") else {
        return Vec::new();
    };
    named_children(mods)
        .into_iter()
        .filter(|a| matches!(a.kind(), "annotation" | "marker_annotation"))
        .filter_map(|a| {
            let name = a.child_by_field_name("name")?;
            let nm = text(name, src);
            let last = nm.rsplit('.').next().unwrap_or("").to_string();
            Some((last, a.child_by_field_name("arguments")))
        })
        .collect()
}

/// `("/x")` · `(value = "/x")` · `(path = {"/x", "/y"})` → 첫 경로
fn java_path(args: Option<Node>, src: &[u8]) -> Option<String> {
    for c in named_children(args?) {
        let mut val = Some(c);
        if c.kind() == "element_value_pair" {
            let key = c.child_by_field_name("key").map(|k| text(k, src));
            if !matches!(key.as_deref(), Some("value" | "path")) {
                continue;
            }
            val = c.child_by_field_name("value");
        }
        if let Some(v) = val
            && v.kind() == "element_value_array_initializer"
        {
            val = named_children(v)
                .into_iter()
                .find(|x| x.kind() == "string_literal");
        }
        if let Some(got) = java_str(val, src) {
            return Some(got);
        }
    }
    None
}

/// `@RequestMapping(method = RequestMethod.POST)` → POST, 없으면 ANY
fn java_method(args: Option<Node>, src: &[u8]) -> String {
    for c in args.map(named_children).unwrap_or_default() {
        if c.kind() != "element_value_pair" {
            continue;
        }
        if c.child_by_field_name("key")
            .map(|k| text(k, src))
            .as_deref()
            != Some("method")
        {
            continue;
        }
        let mut val = c.child_by_field_name("value");
        if let Some(v) = val
            && v.kind() == "element_value_array_initializer"
        {
            val = named_children(v).first().copied();
        }
        if let Some(v) = val {
            let t = text(v, src);
            return t.rsplit('.').next().unwrap_or("").to_uppercase();
        }
    }
    "ANY".into()
}

/// Spring — 클래스 `@RequestMapping` 접두어 + 메서드 `@GetMapping`… → {선언 첫 줄: route}
fn java_routes(src: &[u8]) -> BTreeMap<i64, Value> {
    let mut out = BTreeMap::new();
    let Some(tree) = crate::java::parse(src) else {
        return out;
    };
    for cls in walk(tree.root_node()) {
        if cls.kind() != "class_declaration" {
            continue;
        }
        let prefix = java_annotations(cls, src)
            .into_iter()
            .find(|(n, _)| n == "RequestMapping")
            .map(|(_, a)| java_path(a, src).unwrap_or_default())
            .unwrap_or_default();
        let Some(body) = cls.child_by_field_name("body") else {
            continue;
        };
        for m in named_children(body) {
            if m.kind() != "method_declaration" {
                continue;
            }
            for (name, args) in java_annotations(m, src) {
                let Some(verb) = spring_verb(&name) else {
                    continue;
                };
                let method = verb.map_or_else(|| java_method(args, src), str::to_string);
                let joined = join(&prefix, &java_path(args, src).unwrap_or_default());
                let path = SPRING_PARAM.replace_all(&joined, "{$1}").into_owned();
                out.entry(row(m)).or_insert_with(|| route(&method, path));
                break;
            }
        }
    }
    out
}

/// Go — `X.HandleFunc("경로", h)`·gin·echo·chi 등록 → [(방법, 경로, 핸들러 이름)]
fn go_routes(src: &[u8]) -> Vec<(String, String, String)> {
    let mut out = Vec::new();
    let Some(tree) = crate::go::parse(src) else {
        return out;
    };
    let lit = |n: Option<Node>| -> Option<String> {
        let n = n.filter(|n| {
            matches!(
                n.kind(),
                "interpreted_string_literal" | "raw_string_literal"
            )
        })?;
        Some(
            named_children(n)
                .into_iter()
                .filter(|c| {
                    matches!(
                        c.kind(),
                        "interpreted_string_literal_content" | "raw_string_literal_content"
                    )
                })
                .map(|c| text(c, src))
                .collect(),
        )
    };
    let mut groups: HashMap<String, String> = HashMap::new();
    for n in walk(tree.root_node()) {
        if n.kind() == "short_var_declaration" {
            let names = n
                .child_by_field_name("left")
                .map(named_children)
                .unwrap_or_default();
            let vals = n
                .child_by_field_name("right")
                .map(named_children)
                .unwrap_or_default();
            if names.len() != 1 || vals.len() != 1 || vals[0].kind() != "call_expression" {
                continue;
            }
            let a = args(vals[0]);
            let Some(f) = vals[0]
                .child_by_field_name("function")
                .filter(|f| f.kind() == "selector_expression")
            else {
                continue;
            };
            if a.is_empty() {
                continue;
            }
            let (op, field) = (
                f.child_by_field_name("operand"),
                f.child_by_field_name("field"),
            );
            if let (Some(field), Some(p)) = (field, lit(a.first().copied()))
                && text(field, src) == "Group"
            {
                let base = op
                    .and_then(|o| groups.get(&text(o, src)).cloned())
                    .unwrap_or_default();
                groups.insert(text(names[0], src), base + &p);
            }
            continue;
        }
        if n.kind() != "call_expression" {
            continue;
        }
        let Some(f) = n
            .child_by_field_name("function")
            .filter(|f| f.kind() == "selector_expression")
        else {
            continue;
        };
        let verb = f
            .child_by_field_name("field")
            .and_then(|x| go_verb(&text(x, src)));
        let a = args(n);
        let path = lit(a.first().copied());
        let (Some(verb), Some(path)) = (verb, path) else {
            continue;
        };
        if a.len() < 2 {
            continue;
        }
        let (mut verb, mut path) = (verb.to_string(), path);
        if let Some(c) = GO_PATTERN.captures(&path) {
            let (v, p) = (c[1].to_string(), c[2].to_string());
            verb = v;
            path = p;
        }
        let mut h = Some(unparen(a[a.len() - 1]));
        if let Some(x) = h
            && x.kind() == "selector_expression"
        {
            h = x.child_by_field_name("field");
        }
        let Some(h) = h.filter(|x| matches!(x.kind(), "identifier" | "field_identifier")) else {
            continue;
        };
        let prefix = f
            .child_by_field_name("operand")
            .and_then(|o| groups.get(&text(o, src)).cloned())
            .unwrap_or_default();
        let joined = join(&prefix, &path);
        let gin = GIN_PARAM.replace_all(&joined, "{$1}").into_owned();
        let p = GO_REST.replace_all(&gin, "{$1}").into_owned();
        out.push((verb, p, text(h, src)));
    }
    out
}

fn s(v: &Value, k: &str) -> String {
    v.get(k)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

/// SYNC-MS-026#routes.routes
///
/// 함수마다 받는 라우트 `{method, path}` 또는 null — FastAPI·Flask 데코레이터, Express·Fastify·Hono
/// 등록, NestJS 데코레이터, Next `app/**/route.ts`, axum `.route` 사슬, actix 속성.
pub fn routes(src_dir: &Path, graph: &mut Value) {
    let funcs: Vec<Value> = graph["functions"].as_array().cloned().unwrap_or_default();
    let mut assigned: Vec<Option<Value>> = vec![None; funcs.len()];
    // 파일 → [(줄, 함수 번호)] — 파이썬 사전처럼 같은 줄은 나중 함수가 덮고 자리는 처음 것
    let mut by_file: BTreeMap<String, Here> = BTreeMap::new();
    let mut by_name: HashMap<(String, String), Vec<usize>> = HashMap::new();
    for (i, f) in funcs.iter().enumerate() {
        let file = s(f, "file");
        let line = f["line"].as_i64().unwrap_or(0);
        let here = by_file.entry(file.clone()).or_default();
        match here.iter_mut().find(|(l, _)| *l == line) {
            Some(slot) => slot.1 = i,
            None => here.push((line, i)),
        }
        by_name
            .entry((suffix(&file).to_string(), s(f, "name")))
            .or_default()
            .push(i);
    }
    let names: Vec<String> = funcs.iter().map(|f| s(f, "name")).collect();
    let mut give = |i: usize, r: &Value| {
        if assigned[i].is_none() {
            assigned[i] = Some(r.clone());
        }
    };

    let mut py_files: Vec<String> = by_file
        .keys()
        .filter(|f| f.ends_with(".py"))
        .cloned()
        .collect();
    if let Some(fs) = graph.get("files").and_then(Value::as_array) {
        for f in fs {
            if let Some(p) = f.get("path").and_then(Value::as_str)
                && p.ends_with(".py")
            {
                py_files.push(p.to_string());
            }
        }
    }
    py_files.sort();
    py_files.dedup();
    let mut trees = Vec::new();
    for file in py_files {
        let Some(src) = read(src_dir, &file) else {
            continue;
        };
        let Some(pf) = python::parse(&String::from_utf8_lossy(&src)) else {
            continue;
        };
        trees.push(PyTree { file, pf });
    }
    for ((file, ln), r) in py_routes(&trees) {
        if let Some(i) = by_file.get(&file).and_then(|h| here_get(h, ln)) {
            give(i, &r);
        }
    }

    let mut ts_names: HashMap<String, Vec<usize>> = HashMap::new();
    let mut keys: Vec<&(String, String)> = by_name.keys().collect();
    // 후보가 하나일 때만 쓰므로 잇는 차례는 결과를 바꾸지 않는다
    keys.sort();
    for k in keys {
        if TS_EXTS.contains(&k.0.as_str()) {
            ts_names
                .entry(k.1.clone())
                .or_default()
                .extend(by_name[k].iter().copied());
        }
    }
    for (file, here) in &by_file {
        if !TS_EXTS.iter().any(|e| file.ends_with(e)) {
            continue;
        }
        let Some(src) = read(src_dir, file) else {
            continue;
        };
        for (i, r) in ts_routes(file, &src, &ts_names, here, &names) {
            give(i, &r);
        }
    }

    for (file, here) in &by_file {
        if !file.ends_with(".rs") {
            continue;
        }
        let Some(src) = read(src_dir, file) else {
            continue;
        };
        let (chains, attrs) = rs_routes(&src);
        for (method, path, h) in chains {
            let local: Vec<usize> = here
                .iter()
                .map(|(_, i)| *i)
                .filter(|i| names[*i] == h)
                .collect();
            let cands = if local.is_empty() {
                by_name
                    .get(&(".rs".to_string(), h.clone()))
                    .cloned()
                    .unwrap_or_default()
            } else {
                local
            };
            if cands.len() == 1 {
                give(cands[0], &route(method, path));
            }
        }
        for (ln, r) in attrs {
            if let Some(i) = here_get(here, ln) {
                give(i, &r);
            }
        }
    }

    for (file, here) in &by_file {
        if !file.ends_with(".java") {
            continue;
        }
        let Some(src) = read(src_dir, file) else {
            continue;
        };
        for (ln, r) in java_routes(&src) {
            if let Some(i) = here_get(here, ln) {
                give(i, &r);
            }
        }
    }

    let files_of: Vec<String> = funcs.iter().map(|f| s(f, "file")).collect();
    for file in by_file.keys() {
        if !file.ends_with(".go") {
            continue;
        }
        let Some(src) = read(src_dir, file) else {
            continue;
        };
        let folder = crate::go::dir_of_file(file);
        for (method, path, h) in go_routes(&src) {
            let all = by_name
                .get(&(".go".to_string(), h))
                .cloned()
                .unwrap_or_default();
            let same: Vec<usize> = all
                .iter()
                .copied()
                .filter(|i| crate::go::dir_of_file(&files_of[*i]) == folder)
                .collect();
            let cands = if same.is_empty() { all } else { same };
            if cands.len() == 1 {
                give(cands[0], &route(&method, path));
            }
        }
    }

    if let Some(arr) = graph.get_mut("functions").and_then(Value::as_array_mut) {
        for (f, r) in arr.iter_mut().zip(assigned) {
            if let Some(o) = f.as_object_mut() {
                o.insert("route".into(), r.unwrap_or(Value::Null));
            }
        }
    }
}

fn segs(path: &str) -> Vec<String> {
    path.split('/')
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .collect()
}

/// 칸마다 맞추기 → (글자-글자 맞은 수, 짐작인가) 또는 없음
fn matches(req: &[String], route: &[String]) -> Option<(i64, bool)> {
    if req.len() != route.len() {
        return None;
    }
    let (mut score, mut guess) = (0, false);
    for (a, b) in req.iter().zip(route) {
        let param = b.starts_with('{') && b.ends_with('}');
        if a == "*" {
            guess = guess || !param;
        } else if param {
            continue;
        } else if a == b {
            score += 1;
        } else {
            return None;
        }
    }
    Some((score, guess))
}

type RouteRow = (String, Vec<String>, String);

fn pick(req: &[String], method: &str, routes: &[RouteRow], suffix: bool) -> Vec<(String, bool)> {
    let mut best: Vec<(String, bool)> = Vec::new();
    let mut top = -1;
    for (key, segs, m) in routes {
        if m != method && m != "ANY" {
            continue;
        }
        if suffix && segs.len() <= req.len() {
            continue;
        }
        let cand = if suffix {
            &segs[segs.len() - req.len()..]
        } else {
            &segs[..]
        };
        let Some((score, guess)) = matches(req, cand) else {
            continue;
        };
        if score > top {
            top = score;
            best = vec![(key.clone(), guess || suffix)];
        } else if score == top {
            best.push((key.clone(), guess || suffix));
        }
    }
    if best.len() > 1 {
        for b in &mut best {
            b.1 = true;
        }
    }
    best
}

pub(crate) fn is_front(file: &str, web_dirs: &[String]) -> bool {
    if file.ends_with(".tsx") || file.ends_with(".jsx") {
        return true;
    }
    if ![".ts", ".js", ".mjs"].iter().any(|e| file.ends_with(e)) {
        return false;
    }
    web_dirs
        .iter()
        .any(|d| d.is_empty() || file.starts_with(&format!("{d}/")))
}

/// SYNC-MS-026#routes.http_links
///
/// 화면 파일 함수의 요청(`fetch`·`api.get(…)` — 첫 인자가 `/`로 시작하는 글자)을 라우트 함수에
/// 칸마다 맞춰 잇는다. 맞는 것이 없으면 끝맞춤. `[{from, to, inferred}]`, (from, to) 바이트 순.
pub fn http_links(src_dir: &Path, graph: &Value) -> Vec<Value> {
    let web_dirs: Vec<String> = graph
        .get("units")
        .and_then(Value::as_array)
        .map(|us| {
            us.iter()
                .filter(|u| u.get("kind").and_then(Value::as_str) == Some("web"))
                .map(|u| s(u, "dir"))
                .collect()
        })
        .unwrap_or_default();
    let funcs: Vec<Value> = graph["functions"].as_array().cloned().unwrap_or_default();
    let routes: Vec<RouteRow> = funcs
        .iter()
        .filter(|f| f.get("route").is_some_and(|r| r.is_object()))
        .map(|f| {
            (
                s(f, "key"),
                segs(&s(&f["route"], "path")),
                s(&f["route"], "method"),
            )
        })
        .collect();
    if routes.is_empty() {
        return Vec::new();
    }
    let mut by_file: BTreeMap<String, Vec<&Value>> = BTreeMap::new();
    for f in &funcs {
        let file = s(f, "file");
        if is_front(&file, &web_dirs) {
            by_file.entry(file).or_default().push(f);
        }
    }
    let mut found: BTreeMap<(String, String), bool> = BTreeMap::new();
    for (file, fs) in &by_file {
        let Some(src) = read(src_dir, file) else {
            continue;
        };
        let Some(tree) = ts_parse(file, &src) else {
            continue;
        };
        let root = tree.root_node();
        let routers = ts_router_names(root, &src);
        let defs = super::steps::ts_defs(root);
        for f in fs {
            let Some(body) = defs
                .get(&f["line"].as_i64().unwrap_or(0))
                .and_then(|n| n.child_by_field_name("body"))
            else {
                continue;
            };
            for n in walk(body) {
                if n.kind() != "call_expression" {
                    continue;
                }
                let Some((method, path)) = request(n, &src, &routers) else {
                    continue;
                };
                let sg = segs(path.split('?').next().unwrap_or(""));
                let mut hits = pick(&sg, &method, &routes, false);
                if hits.is_empty() {
                    hits = pick(&sg, &method, &routes, true);
                }
                for (to, inferred) in hits {
                    found.entry((s(f, "key"), to)).or_insert(inferred);
                }
            }
        }
    }
    found
        .into_iter()
        .map(|((a, b), inf)| json!({"from": a, "to": b, "inferred": inf}))
        .collect()
}

fn request(call: Node, src: &[u8], routers: &HashSet<String>) -> Option<(String, String)> {
    let f = unparen(call.child_by_field_name("function")?);
    let name = match f.kind() {
        "identifier" => text(f, src),
        "member_expression" => {
            let prop = f.child_by_field_name("property")?;
            if let Some(obj) = f.child_by_field_name("object")
                && routers.contains(&text(obj, src))
            {
                return None; // 서버의 라우트 등록 — 요청이 아니다
            }
            text(prop, src)
        }
        _ => return None,
    };
    if !REQ_NAMES.contains(&name.as_str()) {
        return None;
    }
    let a = args(call);
    let path = str_value(Some(*a.first()?), src)?;
    if !path.starts_with('/') {
        return None;
    }
    let method = if name == "fetch" || name == "request" {
        let mut method = "GET".to_string();
        if a.len() > 1 && a[1].kind() == "object" {
            for p in named_children(a[1]) {
                if p.kind() != "pair" {
                    continue;
                }
                if let Some(k) = p.child_by_field_name("key")
                    && text(k, src).trim_matches(|c| c == '\'' || c == '"') == "method"
                    && let Some(v) = str_value(p.child_by_field_name("value"), src)
                    && !v.is_empty()
                {
                    method = v.to_uppercase();
                }
            }
        }
        method
    } else if name == "del" {
        "DELETE".into()
    } else {
        name.to_uppercase()
    };
    Some((method, path))
}
