//! Java 보강 — tree-sitter-java(파이썬 판과 같은 0.23.5) (SYNC-MS-022 · MS-011 enrich 2i·2j, 카드 L32).
//! 타입 몸통의 메서드·생성자, 선언 앞 주석 첫 줄의 항목, 받는 쪽 타입(필드·매개변수·지역 변수)으로 푼 호출 선.
//! 흐름(`flow`)도 여기의 파서·타입 읽기를 쓴다.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;

use indexmap::IndexMap;
use tree_sitter::{Node, Parser, Tree};

use crate::graph::item_of;
use crate::{Call, Function, Graph};

pub(crate) const JAVA_TYPES: [&str; 4] = [
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
];
const JAVA_FNS: [&str; 2] = ["method_declaration", "constructor_declaration"];
const JAVA_COMMENTS: [&str; 2] = ["line_comment", "block_comment"];

pub(crate) fn parse(src: &[u8]) -> Option<Tree> {
    let mut p = Parser::new();
    p.set_language(&tree_sitter_java::LANGUAGE.into()).ok()?;
    p.parse(src, None)
}

pub(crate) fn text(n: Node, src: &[u8]) -> String {
    String::from_utf8_lossy(&src[n.start_byte()..n.end_byte()]).into_owned()
}

pub(crate) fn named_children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.named_children(&mut c).collect()
}

/// 앞에서부터 내려가는 차례(파이썬 판 `_walk`) — 노드 자신, 그다음 자식들
pub(crate) fn walk(root: Node) -> Vec<Node> {
    let mut out = Vec::new();
    let mut stack = vec![root];
    while let Some(n) = stack.pop() {
        out.push(n);
        let mut c = n.walk();
        let kids: Vec<Node> = n.children(&mut c).collect();
        stack.extend(kids.into_iter().rev());
    }
    out
}

/// 주석 하나의 첫 내용 줄 — 블록 주석은 기호와 줄 앞 `*`를 떼고, `//`는 그 뒤
fn comment_first(t: &str) -> Option<String> {
    if let Some(rest) = t.strip_prefix("/*") {
        let body = rest.strip_suffix("*/").unwrap_or(rest);
        let body = body.strip_prefix('*').unwrap_or(body);
        for line in body.split('\n') {
            let mut line = line.trim();
            if let Some(r) = line.strip_prefix('*') {
                line = r.trim();
            }
            if !line.is_empty() {
                return Some(line.to_string());
            }
        }
        return None;
    }
    let line = t.get(2..).unwrap_or("").trim();
    (!line.is_empty()).then(|| line.to_string())
}

/// 선언 바로 앞의 주석(빈 줄 없이 붙은 것) — 블록 주석 하나 또는 줄 주석 묶음의 첫 내용 줄 (Java·Go 같이 쓴다)
pub(crate) fn doc(node: Node, src: &[u8], kinds: &[&str]) -> Option<String> {
    let mut run: Vec<String> = Vec::new();
    let mut top = node.start_position().row as i64;
    let mut p = node.prev_sibling();
    while let Some(n) = p {
        if !kinds.contains(&n.kind()) || (n.end_position().row as i64) < top - 1 {
            break;
        }
        let t = text(n, src);
        let block = t.starts_with("/*");
        run.push(t);
        if block {
            break;
        }
        top = n.start_position().row as i64;
        p = n.prev_sibling();
    }
    run.iter().rev().find_map(|t| comment_first(t))
}

/// 타입 노드 → 단순 이름. 제네릭은 뗀다(`List<T>` → List) · `a.b.T` → T
pub(crate) fn jtype(node: Option<Node>, src: &[u8]) -> Option<String> {
    let mut node = node;
    while let Some(n) = node {
        match n.kind() {
            "type_identifier" => return Some(text(n, src)),
            "generic_type" => node = named_children(n).first().copied(),
            "scoped_type_identifier" => {
                return named_children(n)
                    .into_iter()
                    .rfind(|c| c.kind() == "type_identifier")
                    .map(|c| text(c, src));
            }
            _ => return None,
        }
    }
    None
}

/// 정의 하나 — 타입·이름·선언 첫 줄(어노테이션 포함)·끝 줄·노드·문서 첫 줄
pub(crate) struct JavaDef<'t> {
    pub owner: String,
    pub name: String,
    pub line: i64,
    pub end: i64,
    pub node: Node<'t>,
    pub doc: Option<String>,
}

pub(crate) struct JavaFile<'t> {
    pub file: String,
    pub src: &'t [u8],
    pub defs: Vec<JavaDef<'t>>,
    pub types: Vec<String>,
    /// 타입 → 필드 → 타입
    pub fields: HashMap<String, HashMap<String, String>>,
}

impl<'t> JavaFile<'t> {
    pub(crate) fn new(file: &str, tree: &'t Tree, src: &'t [u8]) -> Self {
        let mut jf = JavaFile {
            file: file.to_string(),
            src,
            defs: Vec::new(),
            types: Vec::new(),
            fields: HashMap::new(),
        };
        for c in named_children(tree.root_node()) {
            if JAVA_TYPES.contains(&c.kind()) {
                jf.add_type(c);
            }
        }
        jf
    }

    fn add_type(&mut self, decl: Node<'t>) {
        let (Some(name_node), Some(body)) = (
            decl.child_by_field_name("name"),
            decl.child_by_field_name("body"),
        ) else {
            return;
        };
        let src = self.src;
        let owner = text(name_node, src);
        self.types.push(owner.clone());
        self.fields.entry(owner.clone()).or_default();
        let mut members = named_children(body);
        for m in named_children(body) {
            if m.kind() == "enum_body_declarations" {
                members.extend(named_children(m));
            }
        }
        for m in members {
            let k = m.kind();
            if JAVA_FNS.contains(&k) && m.child_by_field_name("body").is_some() {
                let Some(n) = m.child_by_field_name("name") else {
                    continue;
                };
                self.defs.push(JavaDef {
                    owner: owner.clone(),
                    name: text(n, src),
                    line: m.start_position().row as i64 + 1,
                    end: m.end_position().row as i64 + 1,
                    node: m,
                    doc: doc(m, src, &JAVA_COMMENTS),
                });
            } else if k == "field_declaration" {
                let t = jtype(m.child_by_field_name("type"), src);
                for d in named_children(m) {
                    if d.kind() != "variable_declarator" {
                        continue;
                    }
                    if let (Some(t), Some(dn)) = (&t, d.child_by_field_name("name")) {
                        self.fields
                            .entry(owner.clone())
                            .or_default()
                            .insert(text(dn, src), t.clone());
                    }
                }
            } else if JAVA_TYPES.contains(&k) {
                self.add_type(m);
            }
        }
    }
}

/// 매개변수·지역 변수의 타입 — `T x`, `var x = new T(…)`
pub(crate) fn locals(fnode: Node, src: &[u8]) -> HashMap<String, String> {
    let mut out = HashMap::new();
    if let Some(params) = fnode.child_by_field_name("parameters") {
        for p in named_children(params) {
            if !matches!(p.kind(), "formal_parameter" | "spread_parameter") {
                continue;
            }
            let t = jtype(p.child_by_field_name("type"), src);
            let n = p.child_by_field_name("name").or_else(|| {
                named_children(p)
                    .into_iter()
                    .find(|c| c.kind() == "variable_declarator")
                    .and_then(|d| d.child_by_field_name("name"))
            });
            if let (Some(t), Some(n)) = (t, n) {
                out.insert(text(n, src), t);
            }
        }
    }
    let Some(body) = fnode.child_by_field_name("body") else {
        return out;
    };
    for n in walk(body) {
        if n.kind() != "local_variable_declaration" {
            continue;
        }
        let tnode = n.child_by_field_name("type");
        let t = jtype(tnode, src);
        let is_var = tnode.is_some_and(|tn| text(tn, src) == "var");
        for d in named_children(n) {
            if d.kind() != "variable_declarator" {
                continue;
            }
            let dn = d.child_by_field_name("name");
            let v = d.child_by_field_name("value");
            let vt = if is_var {
                v.filter(|v| v.kind() == "object_creation_expression")
                    .and_then(|v| jtype(v.child_by_field_name("type"), src))
            } else {
                t.clone()
            };
            if let (Some(vt), Some(dn)) = (vt, dn) {
                out.insert(text(dn, src), vt);
            }
        }
    }
    out
}

/// MS-011 enrich 2i·2j — Java 메서드·생성자의 끝 줄·qual·항목, 빠진 정의, 호출 선
pub(crate) fn enrich(src_dir: &Path, graph: &mut Graph, seen_files: &[String]) {
    let mut by_loc: HashMap<(String, i64), usize> = HashMap::new();
    for (i, f) in graph.functions.iter().enumerate() {
        by_loc.insert((f.file.clone(), f.line), i);
    }
    let files: BTreeSet<String> = graph
        .functions
        .iter()
        .filter(|f| f.file.ends_with(".java"))
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
    let parsed: Vec<JavaFile> = sources
        .iter()
        .zip(&trees)
        .filter_map(|((file, src), tree)| tree.as_ref().map(|t| JavaFile::new(file, t, src)))
        .collect();
    let mut count: HashMap<&str, usize> = HashMap::new();
    for jf in &parsed {
        let uniq: HashSet<&str> = jf.types.iter().map(String::as_str).collect();
        for t in uniq {
            *count.entry(t).or_default() += 1;
        }
    }
    // 타입 → 이름 → key들
    let mut methods: HashMap<String, IndexMap<String, Vec<String>>> = HashMap::new();
    for jf in &parsed {
        for d in &jf.defs {
            let idx = match by_loc.get(&(jf.file.clone(), d.line)) {
                Some(i) => *i,
                None => {
                    graph.functions.push(Function {
                        key: format!("{}:{}", jf.file, d.line),
                        name: d.name.clone(),
                        qual: String::new(),
                        file: jf.file.clone(),
                        line: d.line,
                        end: None,
                        item: None,
                        ms: None,
                        community: None,
                    });
                    let i = graph.functions.len() - 1;
                    by_loc.insert((jf.file.clone(), d.line), i);
                    i
                }
            };
            let f = &mut graph.functions[idx];
            f.name = d.name.clone();
            f.end = Some(d.end);
            f.qual = format!("{}.{}", d.owner, d.name);
            if let Some(doc) = &d.doc {
                let (it, m) = item_of(doc);
                if it.is_some() {
                    f.item = it;
                    f.ms = m;
                }
            }
            if count.get(d.owner.as_str()) == Some(&1) {
                let keys = methods
                    .entry(d.owner.clone())
                    .or_default()
                    .entry(d.name.clone())
                    .or_default();
                if !keys.contains(&f.key) {
                    keys.push(f.key.clone());
                }
            }
        }
    }
    let mut have: HashSet<(String, String)> = graph
        .calls
        .iter()
        .map(|c| (c.0.clone(), c.1.clone()))
        .collect();
    let empty = HashMap::new();
    for jf in &parsed {
        let src = jf.src;
        for d in &jf.defs {
            let key = format!("{}:{}", jf.file, d.line);
            let local = locals(d.node, src);
            let fields = jf.fields.get(&d.owner).unwrap_or(&empty);
            let mut dsts: BTreeSet<String> = BTreeSet::new();
            let Some(body) = d.node.child_by_field_name("body") else {
                continue;
            };
            for n in walk(body) {
                let (t, m) = match n.kind() {
                    "method_invocation" => {
                        let m = n.child_by_field_name("name").map(|x| text(x, src));
                        let t = match n.child_by_field_name("object") {
                            None => Some(d.owner.clone()),
                            Some(o) if o.kind() == "this" => Some(d.owner.clone()),
                            Some(o) if o.kind() == "identifier" => {
                                let x = text(o, src);
                                local
                                    .get(&x)
                                    .or_else(|| fields.get(&x))
                                    .cloned()
                                    .or_else(|| methods.contains_key(&x).then_some(x))
                            }
                            Some(o) if o.kind() == "field_access" => o
                                .child_by_field_name("object")
                                .filter(|x| x.kind() == "this")
                                .and_then(|_| o.child_by_field_name("field"))
                                .and_then(|f_| fields.get(&text(f_, src)).cloned()),
                            _ => None,
                        };
                        (t, m)
                    }
                    "object_creation_expression" => {
                        let t = jtype(n.child_by_field_name("type"), src);
                        (t.clone(), t)
                    }
                    _ => continue,
                };
                if let (Some(t), Some(m)) = (t, m)
                    && let Some(keys) = methods.get(&t).and_then(|ms| ms.get(&m))
                {
                    dsts.extend(keys.iter().cloned());
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
