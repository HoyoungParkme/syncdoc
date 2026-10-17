//! Go 보강 — tree-sitter-go(파이썬 판과 같은 0.25.0) (SYNC-MS-022 · MS-011 enrich 2k·2l, 카드 L32).
//! `func`·메서드, `//` 첫 줄 항목, 같은 폴더·`go.mod` 모듈의 다른 패키지·받는 쪽 타입으로 푼 호출 선.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::Path;

use tree_sitter::{Node, Parser, Tree};

use crate::graph::item_of;
use crate::java::{doc, named_children, text, walk};
use crate::{Call, Function, Graph};

pub(crate) fn parse(src: &[u8]) -> Option<Tree> {
    let mut p = Parser::new();
    p.set_language(&tree_sitter_go::LANGUAGE.into()).ok()?;
    p.parse(src, None)
}

/// 타입 노드 → 이름. 포인터·제네릭을 뗀다(`*T`·`T[K]` → T)
pub(crate) fn gotype(node: Option<Node>, src: &[u8]) -> Option<String> {
    let mut node = node;
    while let Some(n) = node {
        match n.kind() {
            "type_identifier" => return Some(text(n, src)),
            "pointer_type" | "generic_type" | "parenthesized_type" => {
                node = named_children(n).first().copied();
            }
            _ => return None,
        }
    }
    None
}

/// `a/b` → `a` (파이썬 `PurePosixPath(file).parent`, 맨 위면 `.`)
pub(crate) fn dir_of_file(file: &str) -> String {
    match file.rfind('/') {
        Some(i) if i > 0 => file[..i].to_string(),
        Some(_) => "/".to_string(),
        None => ".".to_string(),
    }
}

/// 정의 하나 — 받는 쪽 타입(없으면 함수)·이름·`func` 줄·끝 줄·노드·받는 쪽 이름·문서 첫 줄
pub(crate) struct GoDef<'t> {
    pub owner: Option<String>,
    pub name: String,
    pub line: i64,
    pub end: i64,
    pub node: Node<'t>,
    pub recv: Option<String>,
    pub doc: Option<String>,
}

pub(crate) struct GoFile<'t> {
    pub file: String,
    pub dir: String,
    pub src: &'t [u8],
    pub package: String,
    pub defs: Vec<GoDef<'t>>,
    /// 이름 → import 경로
    pub imports: HashMap<String, String>,
}

impl<'t> GoFile<'t> {
    pub(crate) fn new(file: &str, tree: &'t Tree, src: &'t [u8]) -> Self {
        let mut gf = GoFile {
            file: file.to_string(),
            dir: dir_of_file(file),
            src,
            package: String::new(),
            defs: Vec::new(),
            imports: HashMap::new(),
        };
        for c in named_children(tree.root_node()) {
            match c.kind() {
                "package_clause" => {
                    gf.package = named_children(c)
                        .into_iter()
                        .find(|x| x.kind() == "package_identifier")
                        .map(|x| text(x, src))
                        .unwrap_or_default();
                }
                "import_declaration" => {
                    for spec in walk(c) {
                        if spec.kind() != "import_spec" {
                            continue;
                        }
                        let Some(path_node) = spec.child_by_field_name("path") else {
                            continue;
                        };
                        let path = text(path_node, src)
                            .trim_matches(|ch| ch == '"' || ch == '`')
                            .to_string();
                        let name = match spec.child_by_field_name("name") {
                            Some(a) => text(a, src),
                            None => path.rsplit('/').next().unwrap_or("").to_string(),
                        };
                        if name != "_" && name != "." {
                            gf.imports.insert(name, path);
                        }
                    }
                }
                "function_declaration" | "method_declaration" => {
                    let (Some(n), Some(_)) =
                        (c.child_by_field_name("name"), c.child_by_field_name("body"))
                    else {
                        continue;
                    };
                    let (mut owner, mut recv) = (None, None);
                    if c.kind() == "method_declaration" {
                        let p = c.child_by_field_name("receiver").and_then(|r| {
                            named_children(r)
                                .into_iter()
                                .find(|x| x.kind() == "parameter_declaration")
                        });
                        if let Some(p) = p {
                            owner = gotype(p.child_by_field_name("type"), src);
                            recv = p.child_by_field_name("name").map(|rn| text(rn, src));
                        }
                        if owner.is_none() {
                            continue;
                        }
                    }
                    gf.defs.push(GoDef {
                        owner,
                        name: text(n, src),
                        line: c.start_position().row as i64 + 1,
                        end: c.end_position().row as i64 + 1,
                        node: c,
                        recv,
                        doc: doc(c, src, &["comment"]),
                    });
                }
                _ => {}
            }
        }
        gf
    }
}

fn locals(
    fnode: Node,
    src: &[u8],
    owner: Option<&str>,
    recv: Option<&str>,
) -> HashMap<String, String> {
    let mut out = HashMap::new();
    if let (Some(o), Some(r)) = (owner, recv) {
        out.insert(r.to_string(), o.to_string());
    }
    if let Some(params) = fnode.child_by_field_name("parameters") {
        for p in named_children(params) {
            if p.kind() != "parameter_declaration" {
                continue;
            }
            let Some(t) = gotype(p.child_by_field_name("type"), src) else {
                continue;
            };
            for nm in named_children(p) {
                if nm.kind() == "identifier" {
                    out.insert(text(nm, src), t.clone());
                }
            }
        }
    }
    let Some(body) = fnode.child_by_field_name("body") else {
        return out;
    };
    for n in walk(body) {
        match n.kind() {
            "short_var_declaration" => {
                let (Some(left), Some(right)) = (
                    n.child_by_field_name("left"),
                    n.child_by_field_name("right"),
                ) else {
                    continue;
                };
                let names: Vec<Node> = named_children(left)
                    .into_iter()
                    .filter(|c| c.kind() == "identifier")
                    .collect();
                for (nm, v) in names.into_iter().zip(named_children(right)) {
                    let mut v = v;
                    if v.kind() == "unary_expression" {
                        v = v.child_by_field_name("operand").unwrap_or(v);
                    }
                    if v.kind() == "composite_literal"
                        && let Some(t) = gotype(v.child_by_field_name("type"), src)
                    {
                        out.insert(text(nm, src), t);
                    }
                }
            }
            "var_spec" => {
                if let Some(t) = gotype(n.child_by_field_name("type"), src) {
                    for nm in named_children(n) {
                        if nm.kind() == "identifier" {
                            out.insert(text(nm, src), t.clone());
                        }
                    }
                }
            }
            _ => {}
        }
    }
    out
}

/// go.mod 모듈 경로 → 그 폴더 — 패키지 폴더에서 위로 찾은 것들, 모듈 경로 바이트 순
fn modules(src_dir: &Path, dirs: &BTreeSet<String>) -> Vec<(String, String)> {
    let mut found: BTreeMap<String, String> = BTreeMap::new();
    for d in dirs {
        let mut cur = d.clone();
        loop {
            let at = if cur == "." {
                String::new()
            } else {
                cur.clone()
            };
            // 못 읽거나 UTF-8이 아니면 위로 더 간다(파이썬 판과 같다)
            if let Some(t) = std::fs::read(src_dir.join(&at).join("go.mod"))
                .ok()
                .and_then(|b| String::from_utf8(b).ok())
            {
                if let Some(m) = t.lines().find_map(|l| {
                    l.strip_prefix("module")
                        .filter(|r| r.starts_with([' ', '\t']))
                        .and_then(|r| r.split_whitespace().next())
                }) {
                    found.insert(m.to_string(), at);
                }
                break;
            }
            if cur == "." || cur.is_empty() {
                break;
            }
            cur = dir_of_file(&cur);
        }
    }
    found.into_iter().collect()
}

/// MS-011 enrich 2k·2l — Go 함수·메서드의 정의·끝 줄·qual·항목과 호출 선
pub(crate) fn enrich(src_dir: &Path, graph: &mut Graph, seen_files: &[String]) {
    let mut by_loc: HashMap<(String, i64), usize> = HashMap::new();
    for (i, f) in graph.functions.iter().enumerate() {
        by_loc.insert((f.file.clone(), f.line), i);
    }
    let files: BTreeSet<String> = graph
        .functions
        .iter()
        .filter(|f| f.file.ends_with(".go"))
        .map(|f| f.file.clone())
        .chain(seen_files.iter().cloned())
        .collect();
    let mut sources: Vec<(String, Vec<u8>)> = Vec::new();
    for file in files {
        if crate::graph::is_test(&file) {
            continue;
        }
        if let Ok(src) = std::fs::read(src_dir.join(&file)) {
            sources.push((file, src));
        }
    }
    let trees: Vec<Option<Tree>> = sources.iter().map(|(_, s)| parse(s)).collect();
    let parsed: Vec<GoFile> = sources
        .iter()
        .zip(&trees)
        .filter_map(|((file, src), tree)| tree.as_ref().map(|t| GoFile::new(file, t, src)))
        .collect();
    // 폴더 → 함수 이름 → key · 폴더 → 타입 → 메서드 → key
    let mut fns: HashMap<String, HashMap<String, String>> = HashMap::new();
    let mut meths: HashMap<String, HashMap<String, HashMap<String, String>>> = HashMap::new();
    for gf in &parsed {
        for d in &gf.defs {
            let idx = match by_loc.get(&(gf.file.clone(), d.line)) {
                Some(i) => *i,
                None => {
                    graph.functions.push(Function {
                        key: format!("{}:{}", gf.file, d.line),
                        name: d.name.clone(),
                        qual: String::new(),
                        file: gf.file.clone(),
                        line: d.line,
                        end: None,
                        item: None,
                        ms: None,
                        community: None,
                    });
                    let i = graph.functions.len() - 1;
                    by_loc.insert((gf.file.clone(), d.line), i);
                    i
                }
            };
            let f = &mut graph.functions[idx];
            f.name = d.name.clone();
            f.end = Some(d.end);
            f.qual = match &d.owner {
                Some(o) => format!("{o}.{}", d.name),
                None => format!("{}.{}", gf.package, d.name),
            };
            if let Some(doc) = &d.doc {
                let (it, m) = item_of(doc);
                if it.is_some() {
                    f.item = it;
                    f.ms = m;
                }
            }
            let key = f.key.clone();
            match &d.owner {
                Some(o) => {
                    meths
                        .entry(gf.dir.clone())
                        .or_default()
                        .entry(o.clone())
                        .or_default()
                        .entry(d.name.clone())
                        .or_insert(key);
                }
                None => {
                    fns.entry(gf.dir.clone())
                        .or_default()
                        .entry(d.name.clone())
                        .or_insert(key);
                }
            }
        }
    }
    let dirs: BTreeSet<String> = parsed.iter().map(|g| g.dir.clone()).collect();
    let mods = modules(src_dir, &dirs);
    let dir_of = |path: &str| -> Option<String> {
        for (m, d) in &mods {
            if path == m || path.starts_with(&format!("{m}/")) {
                let rest = path[m.len()..].trim_start_matches('/');
                return Some(if !d.is_empty() && !rest.is_empty() {
                    format!("{d}/{rest}")
                } else if !rest.is_empty() {
                    rest.to_string()
                } else if !d.is_empty() {
                    d.clone()
                } else {
                    ".".to_string()
                });
            }
        }
        None
    };
    let mut have: HashSet<(String, String)> = graph
        .calls
        .iter()
        .map(|c| (c.0.clone(), c.1.clone()))
        .collect();
    for gf in &parsed {
        let src = gf.src;
        for d in &gf.defs {
            let key = format!("{}:{}", gf.file, d.line);
            let local = locals(d.node, src, d.owner.as_deref(), d.recv.as_deref());
            let mut dsts: BTreeSet<String> = BTreeSet::new();
            let Some(body) = d.node.child_by_field_name("body") else {
                continue;
            };
            for n in walk(body) {
                if n.kind() != "call_expression" {
                    continue;
                }
                let Some(fnode) = n.child_by_field_name("function") else {
                    continue;
                };
                let hit = match fnode.kind() {
                    "identifier" => fns
                        .get(&gf.dir)
                        .and_then(|m| m.get(&text(fnode, src)))
                        .cloned(),
                    "selector_expression" => {
                        let (Some(op), Some(field)) = (
                            fnode.child_by_field_name("operand"),
                            fnode.child_by_field_name("field"),
                        ) else {
                            continue;
                        };
                        if op.kind() != "identifier" {
                            continue;
                        }
                        let (x, m) = (text(op, src), text(field, src));
                        if let Some(t) = local.get(&x) {
                            meths
                                .get(&gf.dir)
                                .and_then(|ts| ts.get(t))
                                .and_then(|ms| ms.get(&m))
                                .cloned()
                        } else if let Some(d2) = gf.imports.get(&x).and_then(|p| dir_of(p)) {
                            fns.get(&d2).and_then(|fs| fs.get(&m)).cloned()
                        } else {
                            None
                        }
                    }
                    _ => None,
                };
                if let Some(h) = hit {
                    dsts.insert(h);
                }
            }
            for dst in dsts {
                if dst != key && have.insert((key.clone(), dst.clone())) {
                    graph.calls.push(Call(key.clone(), dst, "enrich".into()));
                }
            }
        }
    }
}
