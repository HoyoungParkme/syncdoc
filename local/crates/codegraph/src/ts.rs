//! TS/JS 보강 — tree-sitter-typescript(파이썬 판과 같은 0.23.2) (SYNC-MS-022 · MS-011 enrich 2a~2d).
//! 맨 위 정의의 끝 줄·qual, 빠진 정의, 중첩 함수 끝 줄, 상대 import를 따라간 호출 선.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;

use tree_sitter::{Node, Parser, Tree};

use crate::graph::module;
use crate::{Call, Function, Graph};

pub(crate) const TS_EXTS: [&str; 5] = [".ts", ".tsx", ".js", ".jsx", ".mjs"];
const FN_NODES: [&str; 5] = [
    "function_declaration",
    "arrow_function",
    "function_expression",
    "method_definition",
    "generator_function_declaration",
];

/// 맨 위 정의 하나 — (소속, 이름, 머리 줄들, 끝 줄, 몸통 노드)
struct Def<'t> {
    owner: Option<String>,
    name: String,
    heads: Vec<i64>,
    end: i64,
    node: Node<'t>,
}

fn parse(file: &str, src: &[u8]) -> Option<Tree> {
    let lang = if file.ends_with(".tsx") || file.ends_with(".jsx") {
        tree_sitter_typescript::LANGUAGE_TSX
    } else {
        tree_sitter_typescript::LANGUAGE_TYPESCRIPT
    };
    let mut p = Parser::new();
    p.set_language(&lang.into()).ok()?;
    p.parse(src, None)
}

/// 파이썬 `src[a:b].decode("utf-8", errors="replace")`
fn text(n: Node, src: &[u8]) -> String {
    String::from_utf8_lossy(&src[n.start_byte()..n.end_byte()]).into_owned()
}

fn children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.children(&mut c).collect()
}

fn row(n: Node) -> i64 {
    n.start_position().row as i64 + 1
}

fn end_row(n: Node) -> i64 {
    n.end_position().row as i64 + 1
}

/// 파이썬 `str.isidentifier()`에 가깝게 — 글자나 `_`로 시작, 나머지는 글자·숫자·`_`
fn is_identifier(s: &str) -> bool {
    let mut cs = s.chars();
    cs.next().is_some_and(|c| c == '_' || c.is_alphabetic())
        && cs.all(|c| c == '_' || c.is_alphanumeric())
}

/// 맨 위 정의와 default export 이름 (파이썬 `_ts_defs`)
fn defs<'t>(root: Node<'t>, src: &[u8]) -> (Vec<Def<'t>>, Option<String>) {
    let mut out: Vec<Def<'t>> = Vec::new();
    let mut default: Option<String> = None;
    for c in children(root) {
        visit(c, c, src, &mut out, &mut default);
    }
    (out, default)
}

fn head(stmt: Node, node: Node) -> Vec<i64> {
    let s: BTreeSet<i64> = [row(stmt), row(node)].into_iter().collect();
    s.into_iter().collect()
}

fn visit<'t>(
    node: Node<'t>,
    stmt: Node<'t>,
    src: &[u8],
    out: &mut Vec<Def<'t>>,
    default: &mut Option<String>,
) {
    match node.kind() {
        "export_statement" => {
            let is_default = children(node).iter().any(|c| c.kind() == "default");
            for c in children(node) {
                let before = out.len();
                visit(c, node, src, out, default);
                if is_default && out.len() > before && out[before].owner.is_none() {
                    *default = Some(out[before].name.clone());
                }
            }
        }
        "function_declaration" | "generator_function_declaration" => {
            if let Some(name) = node.child_by_field_name("name") {
                out.push(Def {
                    owner: None,
                    name: text(name, src),
                    heads: head(stmt, node),
                    end: end_row(stmt),
                    node,
                });
            }
        }
        "lexical_declaration" | "variable_declaration" => {
            for d in children(node) {
                if d.kind() != "variable_declarator" {
                    continue;
                }
                let (Some(name), Some(val)) = (
                    d.child_by_field_name("name"),
                    d.child_by_field_name("value"),
                ) else {
                    continue;
                };
                if name.kind() != "identifier" {
                    continue;
                }
                let nm = text(name, src);
                match val.kind() {
                    "arrow_function" | "function_expression" => out.push(Def {
                        owner: None,
                        name: nm,
                        heads: head(stmt, val),
                        end: end_row(stmt),
                        node: val,
                    }),
                    "object" => {
                        for p in children(val) {
                            let (k, body) = match p.kind() {
                                "method_definition" => (p.child_by_field_name("name"), Some(p)),
                                "pair" => {
                                    let body = p.child_by_field_name("value");
                                    if !body.is_some_and(|b| {
                                        matches!(b.kind(), "arrow_function" | "function_expression")
                                    }) {
                                        continue;
                                    }
                                    (p.child_by_field_name("key"), body)
                                }
                                _ => continue,
                            };
                            let (Some(k), Some(body)) = (k, body) else {
                                continue;
                            };
                            let key = text(k, src).trim_matches(['\'', '"']).to_string();
                            if is_identifier(&key) {
                                out.push(Def {
                                    owner: Some(nm.clone()),
                                    name: key,
                                    heads: vec![row(p)],
                                    end: end_row(p),
                                    node: body,
                                });
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
        "class_declaration" => {
            let (Some(name), Some(body)) = (
                node.child_by_field_name("name"),
                node.child_by_field_name("body"),
            ) else {
                return;
            };
            let cname = text(name, src);
            for m in children(body) {
                if m.kind() == "method_definition"
                    && let Some(mn) = m.child_by_field_name("name")
                {
                    out.push(Def {
                        owner: Some(cname.clone()),
                        name: text(mn, src),
                        heads: vec![row(m)],
                        end: end_row(m),
                        node: m,
                    });
                }
            }
        }
        _ => {}
    }
}

/// 파일의 함수 노드 전부(중첩 포함) — 시작 줄 → 끝 줄. 같은 줄이면 가장 바깥(먼저 만난 것)
fn ends(root: Node) -> HashMap<i64, i64> {
    let mut out = HashMap::new();
    let mut stack = vec![root];
    while let Some(n) = stack.pop() {
        if FN_NODES.contains(&n.kind()) {
            out.entry(row(n)).or_insert(end_row(n));
        }
        let mut cs = children(n);
        cs.reverse();
        stack.extend(cs);
    }
    out
}

/// 파이썬 `posixpath.normpath`
fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".into();
    }
    let initial = if path.starts_with("//") && !path.starts_with("///") {
        2
    } else {
        usize::from(path.starts_with('/'))
    };
    let mut comps: Vec<&str> = Vec::new();
    for c in path.split('/') {
        if c.is_empty() || c == "." {
            continue;
        }
        if c != ".." || (initial == 0 && comps.is_empty()) || comps.last() == Some(&"..") {
            comps.push(c);
        } else if !comps.is_empty() {
            comps.pop();
        }
    }
    let joined = comps.join("/");
    let out = format!("{}{joined}", "/".repeat(initial));
    if out.is_empty() { ".".into() } else { out }
}

/// 상대 import → 그래프의 파일. `./x` → x.ts|x.tsx|… 또는 x/index.*. 패키지·별칭은 없음
fn resolve_path(file: &str, spec: &str, files: &HashSet<String>) -> Option<String> {
    if !spec.starts_with('.') {
        return None;
    }
    let dir = file.rsplit_once('/').map_or("", |(d, _)| d);
    let joined = if dir.is_empty() {
        spec.to_string()
    } else {
        format!("{dir}/{spec}")
    };
    let base = normpath(&joined);
    if files.contains(&base) {
        return Some(base);
    }
    let stem = if [".js", ".jsx", ".mjs"].iter().any(|e| base.ends_with(e)) {
        base.rsplit_once('.')
            .map_or(base.as_str(), |(s, _)| s)
            .to_string()
    } else {
        base.clone()
    };
    for cand in [stem.clone(), format!("{stem}/index")] {
        for ext in TS_EXTS {
            let p = format!("{cand}{ext}");
            if files.contains(&p) {
                return Some(p);
            }
        }
    }
    None
}

/// import → 지역 이름 → (파일, 원래 이름). default는 "default", `* as ns`는 없음(이름공간)
fn imports(
    root: Node,
    src: &[u8],
    file: &str,
    files: &HashSet<String>,
) -> HashMap<String, (String, Option<String>)> {
    let mut out = HashMap::new();
    for c in children(root) {
        if c.kind() != "import_statement" {
            continue;
        }
        let s = c
            .child_by_field_name("source")
            .or_else(|| children(c).into_iter().find(|x| x.kind() == "string"));
        let Some(target) =
            s.and_then(|s| resolve_path(file, text(s, src).trim_matches(['\'', '"']), files))
        else {
            continue;
        };
        for clause in children(c)
            .into_iter()
            .filter(|x| x.kind() == "import_clause")
        {
            for x in children(clause) {
                match x.kind() {
                    "identifier" => {
                        out.insert(text(x, src), (target.clone(), Some("default".into())));
                    }
                    "namespace_import" => {
                        if let Some(ns) = children(x).into_iter().find(|y| y.kind() == "identifier")
                        {
                            out.insert(text(ns, src), (target.clone(), None));
                        }
                    }
                    "named_imports" => {
                        for sp in children(x)
                            .into_iter()
                            .filter(|y| y.kind() == "import_specifier")
                        {
                            let name = sp.child_by_field_name("name");
                            let alias = sp.child_by_field_name("alias");
                            if let Some(name) = name {
                                out.insert(
                                    text(alias.unwrap_or(name), src),
                                    (target.clone(), Some(text(name, src))),
                                );
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }
    out
}

/// 몸통의 호출 — `f(…)` → (f, 없음) · `o.m(…)` → (o, m) · JSX `<Comp>` → (Comp, 없음)
fn calls(node: Node, src: &[u8]) -> BTreeSet<(String, String)> {
    let mut out = BTreeSet::new();
    let mut stack = vec![node];
    while let Some(n) = stack.pop() {
        match n.kind() {
            "call_expression" => {
                if let Some(f) = n.child_by_field_name("function") {
                    if f.kind() == "identifier" {
                        out.insert((text(f, src), String::new()));
                    } else if f.kind() == "member_expression"
                        && let (Some(o), Some(p)) = (
                            f.child_by_field_name("object"),
                            f.child_by_field_name("property"),
                        )
                        && o.kind() == "identifier"
                    {
                        out.insert((text(o, src), text(p, src)));
                    }
                }
            }
            "jsx_opening_element" | "jsx_self_closing_element" => {
                if let Some(nm) = n.child_by_field_name("name")
                    && nm.kind() == "identifier"
                {
                    out.insert((text(nm, src), String::new()));
                }
            }
            _ => {}
        }
        stack.extend(children(n));
    }
    out
}

/// 호출 (a, b) → 그래프 key. 같은 파일의 맨 위 이름이 먼저, 아니면 상대 import한 파일의 이름
fn target(
    a: &str,
    b: &str,
    local: &HashMap<String, String>,
    imports: &HashMap<String, (String, Option<String>)>,
    names: &HashMap<String, HashMap<String, String>>,
    defaults: &HashMap<String, Option<String>>,
) -> Option<String> {
    if b.is_empty() {
        if let Some(k) = local.get(a) {
            return Some(k.clone());
        }
        let (tf, orig) = imports.get(a)?;
        let orig = match orig.as_deref() {
            Some("default") => defaults.get(tf).cloned().flatten(),
            other => other.map(str::to_string),
        }?;
        return names.get(tf).and_then(|m| m.get(&orig)).cloned();
    }
    if let Some(k) = local.get(&format!("{a}.{b}")) {
        return Some(k.clone());
    }
    let (tf, orig) = imports.get(a)?;
    match orig {
        None => names.get(tf).and_then(|m| m.get(b)).cloned(), // import * as ns — ns.f
        Some(o) => names
            .get(tf)
            .and_then(|m| m.get(&format!("{o}.{b}")))
            .cloned(),
    }
}

/// MS-011 enrich 2a~2d — 보강은 더하기만, 읽지 못한 파일은 건너뛴다
pub(crate) fn enrich(src_dir: &Path, graph: &mut Graph, seen_files: &[String]) {
    let mut by_loc: HashMap<(String, i64), usize> = HashMap::new();
    for (i, f) in graph.functions.iter().enumerate() {
        by_loc.insert((f.file.clone(), f.line), i);
    }
    let files: BTreeSet<String> = graph
        .functions
        .iter()
        .filter(|f| TS_EXTS.iter().any(|e| f.file.ends_with(e)))
        .map(|f| f.file.clone())
        .chain(seen_files.iter().cloned())
        .collect();
    let fileset: HashSet<String> = files.iter().cloned().collect();
    let mut sources: Vec<(String, Vec<u8>, Tree)> = Vec::new();
    for file in &files {
        let Ok(src) = std::fs::read(src_dir.join(file)) else {
            continue;
        };
        let Some(tree) = parse(file, &src) else {
            continue;
        };
        sources.push((file.clone(), src, tree));
    }
    let mut names: HashMap<String, HashMap<String, String>> = HashMap::new();
    let mut defaults: HashMap<String, Option<String>> = HashMap::new();
    for (file, src, tree) in &sources {
        let (ds, default) = defs(tree.root_node(), src);
        defaults.insert(file.clone(), default);
        let local = names.entry(file.clone()).or_default();
        for d in &ds {
            let idx = match d
                .heads
                .iter()
                .find_map(|ln| by_loc.get(&(file.clone(), *ln)).copied())
            {
                Some(i) => i,
                None => {
                    // graphify가 놓친 정의 — 더한다 (2a)
                    graph.functions.push(Function {
                        key: format!("{file}:{}", d.heads[0]),
                        name: d.name.clone(),
                        qual: String::new(),
                        file: file.clone(),
                        line: d.heads[0],
                        end: None,
                        item: None,
                        ms: None,
                        community: None,
                    });
                    let i = graph.functions.len() - 1;
                    by_loc.insert((file.clone(), d.heads[0]), i);
                    i
                }
            };
            let f = &mut graph.functions[idx];
            f.end = Some(d.end); // 2b
            f.qual = match &d.owner {
                Some(o) => format!("{o}.{}", d.name),
                None => format!("{}.{}", module(file), d.name),
            };
            let local_name = match &d.owner {
                Some(o) => format!("{o}.{}", d.name),
                None => d.name.clone(),
            };
            local.insert(local_name, f.key.clone());
        }
        let ends = ends(tree.root_node());
        for f in graph.functions.iter_mut() {
            if &f.file == file
                && f.end.is_none_or(|e| e == 0)
                && let Some(e) = ends.get(&f.line)
            {
                f.end = Some(*e); // 2c — graphify가 넣은 중첩 함수
            }
        }
    }
    let mut have: HashSet<(String, String)> = graph
        .calls
        .iter()
        .map(|c| (c.0.clone(), c.1.clone()))
        .collect();
    for (file, src, tree) in &sources {
        let imps = imports(tree.root_node(), src, file, &fileset);
        let (ds, _) = defs(tree.root_node(), src);
        let local = names.get(file).cloned().unwrap_or_default();
        for d in &ds {
            let name = match &d.owner {
                Some(o) => format!("{o}.{}", d.name),
                None => d.name.clone(),
            };
            let Some(src_key) = local.get(&name).cloned() else {
                continue;
            };
            for (a, b) in calls(d.node, src) {
                if let Some(dst) = target(&a, &b, &local, &imps, &names, &defaults)
                    && dst != src_key
                    && have.insert((src_key.clone(), dst.clone()))
                {
                    graph
                        .calls
                        .push(Call(src_key.clone(), dst, "enrich".into()));
                }
            }
        }
    }
}
