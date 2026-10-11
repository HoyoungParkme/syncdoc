//! Rust 보강 — tree-sitter-rust(파이썬 판과 같은 0.24.2) (SYNC-MS-022 · MS-011 enrich 2e~2h).
//! 맨 위 fn·impl 메서드, `///` 첫 줄 항목, 이름표(모듈 경로·use·필드 타입)로 푼 호출 선.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;

use tree_sitter::{Node, Parser, Tree};

use crate::graph::{is_test, item_of, parent_name, parts, stem};
use crate::{Call, Function, Graph};

/// 타입 이름을 벗길 감싸개 — `Arc<SpecService>`의 메서드는 SpecService의 것이다 (2g)
const WRAPPERS: [&str; 8] = [
    "Arc", "Box", "Rc", "Option", "RefCell", "Mutex", "RwLock", "Cow",
];
const SELF_SEGS: [&str; 3] = ["crate", "self", "super"];

fn parse(src: &[u8]) -> Option<Tree> {
    let mut p = Parser::new();
    p.set_language(&tree_sitter_rust::LANGUAGE.into()).ok()?;
    p.parse(src, None)
}

fn text(n: Node, src: &[u8]) -> String {
    String::from_utf8_lossy(&src[n.start_byte()..n.end_byte()]).into_owned()
}

fn children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.children(&mut c).collect()
}

fn named_children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.named_children(&mut c).collect()
}

/// qual의 모듈 — 파일 이름. `mod.rs`는 폴더, `src/lib.rs`·`src/main.rs`는 crate 폴더 (2e)
fn rs_module(file: &str) -> String {
    let st = stem(file);
    let ps = parts(file);
    if st == "mod" && !parent_name(file).is_empty() {
        return parent_name(file).to_string();
    }
    if matches!(st, "lib" | "main") && parent_name(file) == "src" && ps.len() >= 3 {
        let gp = ps[ps.len() - 3];
        if gp != "/" {
            return gp.to_string();
        }
    }
    st.to_string()
}

/// 모듈 경로 — 파일의 `src/` 아래. `a/b.rs`·`a/b/mod.rs` → [a, b] · `src/lib.rs` → [] (2g)
fn mod_path(file: &str) -> Vec<String> {
    let without = file
        .strip_suffix(crate::graph::suffix(file))
        .unwrap_or(file);
    let mut ps: Vec<String> = parts(without).into_iter().map(str::to_string).collect();
    if let Some(i) = ps.iter().rposition(|p| p == "src") {
        ps = ps[i + 1..].to_vec();
    }
    if ps.last().map(String::as_str) == Some("mod") {
        ps.pop();
    }
    if ps == ["lib"] || ps == ["main"] {
        ps.clear();
    }
    ps
}

/// 타입 노드 → 이름. `&T`·`&mut T`·`T<'a>`·`a::T`, 감싸개 `Arc<T>`·`Option<T>`는 벗긴다
fn rs_type(node: Option<Node>, src: &[u8]) -> Option<String> {
    let mut node = node;
    while let Some(n) = node {
        match n.kind() {
            "reference_type" | "pointer_type" => node = n.child_by_field_name("type"),
            "generic_type" => {
                let name = rs_type(n.child_by_field_name("type"), src);
                if !name.as_deref().is_some_and(|nm| WRAPPERS.contains(&nm)) {
                    return name;
                }
                let inner: Vec<Node> = n
                    .child_by_field_name("type_arguments")
                    .map(|a| {
                        named_children(a)
                            .into_iter()
                            .filter(|c| c.kind() != "lifetime")
                            .collect()
                    })
                    .unwrap_or_default();
                node = inner.first().copied();
            }
            "type_identifier" => return Some(text(n, src)),
            "scoped_type_identifier" => {
                return n.child_by_field_name("name").map(|nm| text(nm, src));
            }
            _ => return None,
        }
    }
    None
}

/// 경로 `crate::a::b` → [crate, a, b]. `T::<U>::m`의 제네릭은 뗀다
fn rs_path(node: Option<Node>, src: &[u8]) -> Vec<String> {
    let Some(n) = node else {
        return Vec::new();
    };
    match n.kind() {
        "scoped_identifier" => {
            let mut out = rs_path(n.child_by_field_name("path"), src);
            if let Some(name) = n.child_by_field_name("name") {
                out.push(text(name, src));
            }
            out
        }
        "identifier" | "type_identifier" | "crate" | "self" | "super" => vec![text(n, src)],
        "generic_type" => rs_path(n.child_by_field_name("type"), src),
        _ => Vec::new(),
    }
}

/// use 인자 → [(지역 이름, 경로)]. `a::*`는 ("*", a)
fn rs_uses(node: Option<Node>, src: &[u8], prefix: &[String]) -> Vec<(String, Vec<String>)> {
    let Some(n) = node else {
        return Vec::new();
    };
    let with = |tail: Vec<String>| -> Vec<String> {
        let mut v = prefix.to_vec();
        v.extend(tail);
        v
    };
    match n.kind() {
        "identifier" | "crate" | "self" | "super" => {
            let seg = text(n, src);
            if seg == "self" && !prefix.is_empty() {
                return vec![(prefix[prefix.len() - 1].clone(), prefix.to_vec())];
            }
            vec![(seg.clone(), with(vec![seg]))]
        }
        "scoped_identifier" => {
            let full = with(rs_path(Some(n), src));
            match full.last() {
                Some(last) => vec![(last.clone(), full.clone())],
                None => Vec::new(),
            }
        }
        "use_as_clause" => {
            let full = with(rs_path(n.child_by_field_name("path"), src));
            match n.child_by_field_name("alias") {
                Some(alias) if !full.is_empty() => vec![(text(alias, src), full)],
                _ => Vec::new(),
            }
        }
        "scoped_use_list" => {
            let base = with(rs_path(n.child_by_field_name("path"), src));
            rs_uses(n.child_by_field_name("list"), src, &base)
        }
        "use_list" => named_children(n)
            .into_iter()
            .flat_map(|c| rs_uses(Some(c), src, prefix))
            .collect(),
        "use_wildcard" => {
            let inner = named_children(n).first().copied();
            vec![("*".into(), with(rs_path(inner, src)))]
        }
        _ => Vec::new(),
    }
}

/// `crate::a` · `self::a` · `super::a` → `src/` 기준 모듈 경로
fn rs_abs(segs: &[String], here: &[String]) -> Vec<String> {
    if segs.is_empty() {
        return Vec::new();
    }
    if segs[0] == "crate" {
        return segs[1..].to_vec();
    }
    if segs[0] == "self" {
        let mut v = here.to_vec();
        v.extend_from_slice(&segs[1..]);
        return v;
    }
    let n = segs.iter().take_while(|s| *s == "super").count();
    if n == 0 {
        return segs.to_vec();
    }
    let mut v = here[..here.len().saturating_sub(n)].to_vec();
    v.extend_from_slice(&segs[n..]);
    v
}

/// 정의 바로 앞 `///` 묶음의 첫 줄 — 사이의 속성 `#[…]`은 건너뛴다 (2f)
fn rs_doc(node: Node, src: &[u8]) -> Option<String> {
    let mut first = None;
    let mut p = node.prev_sibling();
    while let Some(n) = p {
        if !matches!(n.kind(), "line_comment" | "attribute_item") {
            break;
        }
        if n.kind() == "line_comment" {
            let t = text(n, src);
            if !t.starts_with("///") || t.starts_with("////") {
                break; // 보통 주석에서 묶음이 끝난다
            }
            first = Some(syncdoc_pycompat::chars::strip(&t[3..]).to_string());
        }
        p = n.prev_sibling();
    }
    first
}

struct RsDef<'t> {
    owner: Option<String>,
    name: String,
    line: i64,
    end: i64,
    node: Node<'t>,
}

/// Rust 파일 하나 — 맨 위 정의·구조체 필드·use. 인라인 `mod { }`(테스트 포함)는 안 본다
struct RsFile<'t> {
    file: String,
    src: &'t [u8],
    here: Vec<String>,
    defs: Vec<RsDef<'t>>,
    fields: Vec<(String, Vec<(String, String)>)>,
    uses: Vec<(String, Vec<String>)>,
}

fn rs_file<'t>(file: &str, tree: &'t Tree, src: &'t [u8]) -> RsFile<'t> {
    let mut rf = RsFile {
        file: file.to_string(),
        src,
        here: mod_path(file),
        defs: Vec::new(),
        fields: Vec::new(),
        uses: Vec::new(),
    };
    for c in named_children(tree.root_node()) {
        match c.kind() {
            "function_item" => add(&mut rf, None, c),
            "impl_item" => {
                let owner = rs_type(c.child_by_field_name("type"), src);
                if let (Some(owner), Some(body)) = (owner, c.child_by_field_name("body")) {
                    for m in named_children(body) {
                        if m.kind() == "function_item" {
                            add(&mut rf, Some(owner.clone()), m);
                        }
                    }
                }
            }
            "struct_item" => {
                if let (Some(name), Some(body)) =
                    (c.child_by_field_name("name"), c.child_by_field_name("body"))
                    && body.kind() == "field_declaration_list"
                {
                    let sname = text(name, src);
                    let idx = match rf.fields.iter().position(|(n, _)| *n == sname) {
                        Some(i) => i,
                        None => {
                            rf.fields.push((sname, Vec::new()));
                            rf.fields.len() - 1
                        }
                    };
                    for fd in named_children(body) {
                        if fd.kind() != "field_declaration" {
                            continue;
                        }
                        if let (Some(fname), Some(ftype)) = (
                            fd.child_by_field_name("name"),
                            rs_type(fd.child_by_field_name("type"), src),
                        ) {
                            let fname = text(fname, src);
                            let slot = &mut rf.fields[idx].1;
                            match slot.iter_mut().find(|(n, _)| *n == fname) {
                                Some(x) => x.1 = ftype,
                                None => slot.push((fname, ftype)),
                            }
                        }
                    }
                }
            }
            "use_declaration" => {
                let u = rs_uses(c.child_by_field_name("argument"), src, &[]);
                rf.uses.extend(u);
            }
            _ => {}
        }
    }
    rf
}

fn add<'t>(rf: &mut RsFile<'t>, owner: Option<String>, fn_node: Node<'t>) {
    if let Some(name) = fn_node.child_by_field_name("name") {
        rf.defs.push(RsDef {
            owner,
            name: text(name, rf.src),
            line: fn_node.start_position().row as i64 + 1,
            end: fn_node.end_position().row as i64 + 1,
            node: fn_node,
        });
    }
}

/// Rust 이름표 — 모듈 경로 꼬리 → 파일 · 파일 → 맨 위 fn · 타입 → 메서드 · 구조체 → 필드 타입
struct RsCtx {
    modules: HashMap<String, String>,
    funcs: HashMap<String, HashMap<String, String>>,
    methods: HashMap<String, HashMap<String, String>>,
    fields: HashMap<String, HashMap<String, String>>,
    paths: HashMap<String, Vec<String>>,
}

impl RsCtx {
    fn new(parsed: &[RsFile]) -> RsCtx {
        let mut modules: HashMap<String, String> = HashMap::new();
        let mut dup: HashSet<String> = HashSet::new();
        for rf in parsed {
            for i in 0..rf.here.len() {
                let key = rf.here[i..].join("::");
                if modules.get(&key).is_some_and(|f| *f != rf.file) {
                    dup.insert(key.clone());
                }
                modules.insert(key, rf.file.clone());
            }
        }
        for d in dup {
            modules.remove(&d); // 두 파일에 겹치는 꼬리는 모호하다
        }
        let mut ctx = RsCtx {
            modules,
            funcs: HashMap::new(),
            methods: HashMap::new(),
            fields: HashMap::new(),
            paths: parsed
                .iter()
                .map(|rf| (rf.file.clone(), rf.here.clone()))
                .collect(),
        };
        for rf in parsed {
            for (s, fs) in &rf.fields {
                // 파이썬 `dict.update` — 같은 구조체면 뒤 파일의 것으로 통째로
                ctx.fields.insert(s.clone(), fs.iter().cloned().collect());
            }
            for d in &rf.defs {
                let key = format!("{}:{}", rf.file, d.line);
                match &d.owner {
                    Some(o) => {
                        ctx.methods
                            .entry(o.clone())
                            .or_default()
                            .insert(d.name.clone(), key);
                    }
                    None => {
                        ctx.funcs
                            .entry(rf.file.clone())
                            .or_default()
                            .insert(d.name.clone(), key);
                    }
                }
            }
        }
        ctx
    }

    /// 모듈 경로 → 파일. 앞에서부터 떼어 가며 가장 긴 꼬리로 찾는다
    fn module(&self, segs: &[String]) -> Option<String> {
        let segs: Vec<&String> = segs
            .iter()
            .filter(|s| !SELF_SEGS.contains(&s.as_str()))
            .collect();
        for i in 0..segs.len() {
            let key = segs[i..]
                .iter()
                .map(|s| s.as_str())
                .collect::<Vec<_>>()
                .join("::");
            if let Some(f) = self.modules.get(&key) {
                return Some(f.clone());
            }
        }
        None
    }

    fn is_type(&self, t: &str) -> bool {
        self.methods.contains_key(t) || self.fields.contains_key(t)
    }
}

enum Alias {
    Mod(String),
    Fn(String),
    Type(String),
}

/// 파일 맨 위 use → (지역 이름 → 뜻, `*` 모듈들)
fn aliases(rf: &RsFile, ctx: &RsCtx) -> (HashMap<String, Alias>, Vec<String>) {
    let mut out = HashMap::new();
    let mut globs = Vec::new();
    for (alias, segs) in &rf.uses {
        let full = rs_abs(segs, &rf.here);
        if alias == "*" {
            if let Some(f) = ctx.module(&full) {
                globs.push(f);
            }
            continue;
        }
        let f = if full.is_empty() {
            None
        } else {
            ctx.module(&full)
        };
        if let Some(f) = f {
            out.insert(alias.clone(), Alias::Mod(f));
        } else if full.len() >= 2
            && let Some(m) = ctx.module(&full[..full.len() - 1])
            && let Some(key) = ctx
                .funcs
                .get(&m)
                .and_then(|fs| fs.get(&full[full.len() - 1]))
        {
            out.insert(alias.clone(), Alias::Fn(key.clone()));
        } else if let Some(last) = full.last()
            && ctx.is_type(last)
        {
            out.insert(alias.clone(), Alias::Type(last.clone()));
        }
    }
    (out, globs)
}

/// 몸통의 호출과 넘기는 경로 → 그래프 안 함수의 key (2h)
fn resolve(
    owner: Option<&str>,
    fn_node: Node,
    rf: &RsFile,
    ctx: &RsCtx,
    aliases: &HashMap<String, Alias>,
    globs: &[String],
) -> BTreeSet<String> {
    let src = rf.src;
    let type_of_alias = |name: &str| -> String {
        match aliases.get(name) {
            Some(Alias::Type(t)) => t.clone(),
            _ => name.to_string(),
        }
    };
    let mut env: HashMap<String, String> = HashMap::new();
    if let Some(params) = fn_node.child_by_field_name("parameters") {
        for p in named_children(params) {
            if p.kind() != "parameter" {
                continue;
            }
            let pat = p.child_by_field_name("pattern");
            let ty = rs_type(p.child_by_field_name("type"), src);
            if let (Some(pat), Some(ty)) = (pat, ty)
                && pat.kind() == "identifier"
                && ctx.is_type(&type_of_alias(&ty))
            {
                env.insert(text(pat, src), type_of_alias(&ty));
            }
        }
    }
    let value_type = |v: Option<Node>| -> Option<String> {
        let mut v = v;
        while let Some(n) = v {
            if !matches!(n.kind(), "try_expression" | "await_expression") {
                break;
            }
            v = named_children(n).first().copied();
        }
        let n = v?;
        match n.kind() {
            "call_expression" => {
                let f = n.child_by_field_name("function");
                let segs = match f {
                    Some(f) if f.kind() == "scoped_identifier" => rs_path(Some(f), src),
                    _ => Vec::new(),
                };
                if segs.len() >= 2 {
                    let t = type_of_alias(&segs[segs.len() - 2]);
                    if ctx.is_type(&t) {
                        return Some(t); // `T::new(…)` — 만든 것의 타입
                    }
                }
                None
            }
            "struct_expression" => {
                let name = n.child_by_field_name("name");
                let path = rs_path(name, src);
                let t = path.last().map(|x| type_of_alias(x))?;
                ctx.is_type(&t).then_some(t)
            }
            _ => None,
        }
    };
    // 깊이 우선 — 파이썬 `_rs_walk`(꼭대기부터, 자식은 거꾸로 쌓는다)
    let mut nodes = Vec::new();
    let mut stack = vec![fn_node];
    while let Some(n) = stack.pop() {
        nodes.push(n);
        stack.extend(children(n));
    }
    for n in &nodes {
        if n.kind() != "let_declaration" {
            continue;
        }
        let Some(pat) = n.child_by_field_name("pattern") else {
            continue;
        };
        if pat.kind() != "identifier" {
            continue;
        }
        let t = match rs_type(n.child_by_field_name("type"), src) {
            Some(ty) => Some(type_of_alias(&ty)),
            None => value_type(n.child_by_field_name("value")),
        };
        if let Some(t) = t.filter(|t| ctx.is_type(t)) {
            env.insert(text(pat, src), t);
        }
    }
    fn recv_type(
        v: Option<Node>,
        owner: Option<&str>,
        env: &HashMap<String, String>,
        ctx: &RsCtx,
        src: &[u8],
        value_type: &dyn Fn(Option<Node>) -> Option<String>,
    ) -> Option<String> {
        let v = v?;
        match v.kind() {
            "self" => owner.map(str::to_string),
            "identifier" => env.get(&text(v, src)).cloned(),
            "field_expression" => {
                let base = recv_type(
                    v.child_by_field_name("value"),
                    owner,
                    env,
                    ctx,
                    src,
                    value_type,
                );
                let fld = v.child_by_field_name("field")?;
                ctx.fields
                    .get(base.as_deref().unwrap_or(""))
                    .and_then(|m| m.get(&text(fld, src)))
                    .cloned()
            }
            _ => value_type(Some(v)),
        }
    }
    let mut out = BTreeSet::new();
    for n in &nodes {
        match n.kind() {
            "scoped_identifier" => {
                // `T::m` · `Self::m` · `모듈::f` — 부르든 넘기든
                let segs = rs_path(Some(*n), src);
                if segs.len() < 2 {
                    continue;
                }
                let (head, name) = (&segs[segs.len() - 2], &segs[segs.len() - 1]);
                let t = if head == "Self" {
                    owner.map(str::to_string)
                } else {
                    Some(type_of_alias(head))
                };
                if let Some(key) = t
                    .as_ref()
                    .and_then(|t| ctx.methods.get(t))
                    .and_then(|m| m.get(name))
                {
                    out.insert(key.clone());
                    continue;
                }
                let mods = &segs[..segs.len() - 1];
                let f = match aliases.get(&mods[0]) {
                    Some(Alias::Mod(af)) => {
                        if mods.len() > 1 {
                            let mut p = ctx.paths.get(af).cloned().unwrap_or_default();
                            p.extend_from_slice(&mods[1..]);
                            ctx.module(&p)
                        } else {
                            Some(af.clone())
                        }
                    }
                    _ => ctx.module(&rs_abs(mods, &rf.here)),
                };
                if let Some(key) = f
                    .as_ref()
                    .and_then(|f| ctx.funcs.get(f))
                    .and_then(|m| m.get(name))
                {
                    out.insert(key.clone());
                }
            }
            "call_expression" => {
                let mut f = n.child_by_field_name("function");
                if let Some(g) = f.filter(|g| g.kind() == "generic_function") {
                    f = g.child_by_field_name("function");
                }
                let Some(f) = f else {
                    continue;
                };
                if f.kind() == "identifier" {
                    // `f(…)` — 같은 파일 · use한 함수 · `*` 모듈
                    let name = text(f, src);
                    if let Some(key) = ctx.funcs.get(&rf.file).and_then(|m| m.get(&name)) {
                        out.insert(key.clone());
                    } else if let Some(Alias::Fn(key)) = aliases.get(&name) {
                        out.insert(key.clone());
                    } else if let Some(key) = globs
                        .iter()
                        .find_map(|g| ctx.funcs.get(g).and_then(|m| m.get(&name)))
                    {
                        out.insert(key.clone());
                    }
                } else if f.kind() == "field_expression" {
                    // `x.m(…)` — 타입을 아는 x
                    let t = recv_type(
                        f.child_by_field_name("value"),
                        owner,
                        &env,
                        ctx,
                        src,
                        &value_type,
                    );
                    if let (Some(t), Some(m)) = (t, f.child_by_field_name("field"))
                        && let Some(key) = ctx.methods.get(&t).and_then(|ms| ms.get(&text(m, src)))
                    {
                        out.insert(key.clone());
                    }
                }
            }
            _ => {}
        }
    }
    out
}

/// MS-011 enrich 2e~2h — graphify의 Rust 추출은 함수에 `_callable`이 없어 정의부터 여기서 채운다
pub(crate) fn enrich(src_dir: &Path, graph: &mut Graph, seen_files: &[String]) {
    let mut by_loc: HashMap<(String, i64), usize> = HashMap::new();
    for (i, f) in graph.functions.iter().enumerate() {
        by_loc.insert((f.file.clone(), f.line), i);
    }
    let files: BTreeSet<String> = graph
        .functions
        .iter()
        .filter(|f| f.file.ends_with(".rs"))
        .map(|f| f.file.clone())
        .chain(seen_files.iter().cloned())
        .collect();
    let mut sources: Vec<(String, Vec<u8>)> = Vec::new();
    for file in files {
        if is_test(&file) {
            continue;
        }
        if let Ok(src) = std::fs::read(src_dir.join(&file)) {
            sources.push((file, src));
        }
    }
    let trees: Vec<Option<Tree>> = sources.iter().map(|(_, s)| parse(s)).collect();
    let parsed: Vec<RsFile> = sources
        .iter()
        .zip(&trees)
        .filter_map(|((file, src), tree)| tree.as_ref().map(|t| rs_file(file, t, src)))
        .collect();
    let ctx = RsCtx::new(&parsed);
    for rf in &parsed {
        for d in &rf.defs {
            let idx = match by_loc.get(&(rf.file.clone(), d.line)) {
                Some(i) => *i,
                None => {
                    graph.functions.push(Function {
                        key: format!("{}:{}", rf.file, d.line),
                        name: d.name.clone(),
                        qual: String::new(),
                        file: rf.file.clone(),
                        line: d.line,
                        end: None,
                        item: None,
                        ms: None,
                        community: None,
                    });
                    let i = graph.functions.len() - 1;
                    by_loc.insert((rf.file.clone(), d.line), i);
                    i
                }
            };
            let f = &mut graph.functions[idx];
            f.end = Some(d.end);
            f.qual = match &d.owner {
                Some(o) => format!("{o}.{}", d.name),
                None => format!("{}.{}", rs_module(&rf.file), d.name),
            };
            if let Some(doc) = rs_doc(d.node, rf.src) {
                let (it, m) = item_of(&doc);
                if it.is_some() {
                    f.item = it;
                    f.ms = m;
                }
            }
        }
    }
    let mut have: HashSet<(String, String)> = graph
        .calls
        .iter()
        .map(|c| (c.0.clone(), c.1.clone()))
        .collect();
    for rf in &parsed {
        let (al, globs) = aliases(rf, &ctx);
        for d in &rf.defs {
            let key = format!("{}:{}", rf.file, d.line);
            for dst in resolve(d.owner.as_deref(), d.node, rf, &ctx, &al, &globs) {
                if dst != key && have.insert((key.clone(), dst.clone())) {
                    graph.calls.push(Call(key.clone(), dst, "enrich".into()));
                }
            }
        }
    }
}
