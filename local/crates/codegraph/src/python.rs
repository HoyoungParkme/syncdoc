//! 파이썬 보강 — tree-sitter-python으로 파이썬 `ast`의 뜻을 읽는다 (SYNC-MS-022 0장 · MS-011 enrich 1·2·4·5).
//! 맨 위 정의·클래스 메서드·데코레이터 줄·끝 줄·docstring·인자 주석·대입·속성(읽기만)·호출·import.
//! 걷는 차례는 `ast.walk`처럼 너비 우선 — 같은 이름에 두 번 담으면 나중에 본 것이 이긴다.

use std::collections::{BTreeSet, HashMap, VecDeque};

use tree_sitter::{Node, Parser, Tree};

use syncdoc_pycompat::chars::{lstrip, strip};

use crate::graph::parts;

/// 정의 하나 — (소속 클래스, 이름, `def` 줄, 데코레이터 줄들, 끝 줄, docstring 첫 줄 재료)
pub(crate) struct Def<'t> {
    pub cls: Option<String>,
    /// 소속 클래스의 줄(추출이 클래스 노드를 만든다)
    pub cls_line: Option<i64>,
    pub name: String,
    pub line: i64,
    pub decorators: Vec<i64>,
    pub end: i64,
    pub doc: Option<String>,
    pub node: Node<'t>,
}

/// 파일 하나 — 줄바꿈을 `\n`로 맞춘 글(파이썬 `read_text`의 보편 줄바꿈)과 나무
pub(crate) struct PyFile {
    pub src: String,
    pub tree: Tree,
}

/// 파이썬 `ast.parse`처럼 — 문법 오류(오류·빠진 노드)면 없음
pub(crate) fn parse(text: &str) -> Option<PyFile> {
    let src = text.replace("\r\n", "\n").replace('\r', "\n");
    let mut parser = Parser::new();
    parser
        .set_language(&tree_sitter_python::LANGUAGE.into())
        .ok()?;
    let tree = parser.parse(&src, None)?;
    if tree.root_node().has_error() {
        return None;
    }
    Some(PyFile { src, tree })
}

pub(crate) fn text<'s>(n: Node, src: &'s str) -> &'s str {
    n.utf8_text(src.as_bytes()).unwrap_or("")
}

fn named_children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.named_children(&mut c).collect()
}

fn children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.children(&mut c).collect()
}

/// 주석을 뺀 마지막 글자의 줄 — 파이썬 `end_lineno`는 주석을 모른다
fn end_line(n: Node) -> i64 {
    let mut cur = n;
    loop {
        match children(cur)
            .into_iter()
            .rev()
            .find(|c| c.kind() != "comment")
        {
            Some(last) => cur = last,
            None => return cur.end_position().row as i64 + 1,
        }
    }
}

/// `def`(데코레이터를 벗긴) → (정의 노드, 데코레이터 줄들)
fn unwrap_def<'t>(n: Node<'t>) -> Option<(Node<'t>, Vec<i64>)> {
    match n.kind() {
        "function_definition" => Some((n, Vec::new())),
        "decorated_definition" => {
            let def = n.child_by_field_name("definition")?;
            if def.kind() != "function_definition" {
                return None;
            }
            let decos = named_children(n)
                .into_iter()
                .filter(|c| c.kind() == "decorator")
                .map(|c| c.start_position().row as i64 + 1)
                .collect();
            Some((def, decos))
        }
        _ => None,
    }
}

fn unwrap_class(n: Node) -> Option<Node> {
    match n.kind() {
        "class_definition" => Some(n),
        "decorated_definition" => n
            .child_by_field_name("definition")
            .filter(|d| d.kind() == "class_definition"),
        _ => None,
    }
}

/// 모듈 맨 위 함수와 클래스의 메서드 (파이썬 `_defs`)
pub(crate) fn defs<'t>(f: &'t PyFile) -> Vec<Def<'t>> {
    let mut out = Vec::new();
    for top in named_children(f.tree.root_node()) {
        if let Some((fn_node, decos)) = unwrap_def(top) {
            out.push(def(None, None, fn_node, decos, &f.src));
        } else if let Some(cls) = unwrap_class(top) {
            let cname = cls
                .child_by_field_name("name")
                .map(|n| text(n, &f.src).to_string())
                .unwrap_or_default();
            let Some(body) = cls.child_by_field_name("body") else {
                continue;
            };
            for b in named_children(body) {
                if let Some((fn_node, decos)) = unwrap_def(b) {
                    out.push(def(
                        Some(cname.clone()),
                        Some(cls.start_position().row as i64 + 1),
                        fn_node,
                        decos,
                        &f.src,
                    ));
                }
            }
        }
    }
    out
}

fn def<'t>(
    cls: Option<String>,
    cls_line: Option<i64>,
    n: Node<'t>,
    decorators: Vec<i64>,
    src: &str,
) -> Def<'t> {
    Def {
        cls,
        cls_line,
        name: n
            .child_by_field_name("name")
            .map(|x| text(x, src).to_string())
            .unwrap_or_default(),
        line: n.start_position().row as i64 + 1,
        decorators,
        end: end_line(n),
        doc: docstring(n, src),
        node: n,
    }
}

// ── 글자 상수 ──

/// 글자 상수의 값 — `str` 상수만(파이썬 `ast.Constant`). `b`·`f`는 없음, 이어 붙인 상수는 잇는다
pub(crate) fn string_value(n: Node, src: &str) -> Option<String> {
    match n.kind() {
        "string" => one_string(n, src),
        "concatenated_string" => {
            let mut out = String::new();
            for c in named_children(n) {
                out.push_str(&one_string(c, src)?);
            }
            Some(out)
        }
        _ => None,
    }
}

fn one_string(n: Node, src: &str) -> Option<String> {
    if n.kind() != "string" {
        return None;
    }
    let start = n
        .child_by_field_name("string_start")
        .or_else(|| children(n).into_iter().find(|c| c.kind() == "string_start"))?;
    let prefix: String = text(start, src)
        .chars()
        .take_while(|c| !matches!(c, '"' | '\''))
        .map(|c| c.to_ascii_lowercase())
        .collect();
    if prefix.contains('b') || prefix.contains('f') || prefix.contains('t') {
        return None; // bytes·f-string — 파이썬 `ast.Constant(str)`가 아니다
    }
    let raw = prefix.contains('r');
    let mut out = String::new();
    for c in children(n) {
        match c.kind() {
            "string_content" => {
                // 내용 안의 이스케이프는 따로 노드다 — 그 사이 글자만 여기
                let mut last = c.start_byte();
                for e in children(c) {
                    out.push_str(&src[last..e.start_byte()]);
                    let esc = text(e, src);
                    if raw || e.kind() != "escape_sequence" {
                        out.push_str(esc);
                    } else {
                        out.push_str(&unescape(esc));
                    }
                    last = e.end_byte();
                }
                out.push_str(&src[last..c.end_byte()]);
            }
            "escape_sequence" => {
                let esc = text(c, src);
                out.push_str(&if raw { esc.to_string() } else { unescape(esc) });
            }
            "interpolation" => return None,
            _ => {}
        }
    }
    Some(out)
}

/// 파이썬 글자 이스케이프 하나
fn unescape(esc: &str) -> String {
    let body = &esc[1..];
    let mut it = body.chars();
    let Some(c) = it.next() else {
        return esc.to_string();
    };
    let simple = match c {
        '\\' => Some('\\'),
        '\'' => Some('\''),
        '"' => Some('"'),
        'a' => Some('\u{07}'),
        'b' => Some('\u{08}'),
        'f' => Some('\u{0c}'),
        'n' => Some('\n'),
        'r' => Some('\r'),
        't' => Some('\t'),
        'v' => Some('\u{0b}'),
        '\n' => return String::new(), // 줄 잇기
        _ => None,
    };
    if let Some(s) = simple {
        return s.to_string();
    }
    let hex = |digits: &str| {
        u32::from_str_radix(digits, 16)
            .ok()
            .and_then(char::from_u32)
    };
    match c {
        'x' | 'u' | 'U' => hex(&body[1..]).map_or_else(|| esc.to_string(), String::from),
        '0'..='7' => u32::from_str_radix(body, 8)
            .ok()
            .and_then(char::from_u32)
            .map_or_else(|| esc.to_string(), String::from),
        _ => esc.to_string(),
    }
}

/// 파이썬 `str.expandtabs()` — 칸 8
fn expandtabs(s: &str) -> String {
    let mut out = String::new();
    let mut col = 0usize;
    for c in s.chars() {
        match c {
            '\t' => {
                let n = 8 - col % 8;
                out.push_str(&" ".repeat(n));
                col += n;
            }
            '\n' | '\r' => {
                out.push(c);
                col = 0;
            }
            _ => {
                out.push(c);
                col += 1;
            }
        }
    }
    out
}

/// 파이썬 `inspect.cleandoc`
fn cleandoc(doc: &str) -> String {
    let expanded = expandtabs(doc);
    let mut lines: Vec<String> = expanded.split('\n').map(str::to_string).collect();
    let mut margin = usize::MAX;
    for line in lines.iter().skip(1) {
        let content = lstrip(line).chars().count();
        if content > 0 {
            margin = margin.min(line.chars().count() - content);
        }
    }
    if let Some(first) = lines.first_mut() {
        *first = lstrip(first).to_string();
    }
    if margin < usize::MAX {
        for line in lines.iter_mut().skip(1) {
            *line = line.chars().skip(margin).collect();
        }
    }
    while lines.last().is_some_and(String::is_empty) {
        lines.pop();
    }
    while lines.first().is_some_and(String::is_empty) {
        lines.remove(0);
    }
    lines.join("\n")
}

/// 파이썬 `ast.get_docstring(fn)`의 `strip().splitlines()[0]` — docstring이 없거나 비면 없음
fn docstring(fn_node: Node, src: &str) -> Option<String> {
    let body = fn_node.child_by_field_name("body")?;
    let first = named_children(body)
        .into_iter()
        .find(|c| c.kind() != "comment")?;
    if first.kind() != "expression_statement" {
        return None;
    }
    let inner = named_children(first);
    if inner.len() != 1 {
        return None;
    }
    let doc = cleandoc(&string_value(inner[0], src)?);
    if doc.is_empty() {
        return None;
    }
    syncdoc_pycompat::chars::py_splitlines(strip(&doc))
        .first()
        .map(|s| s.to_string())
}

// ── 이름표 ──

/// 보강에 쓰는 이름표 — 클래스의 메서드, 파일의 맨 위 함수, 점 이름 → 파일, `__init__`의 속성
#[derive(Default)]
pub(crate) struct Ctx {
    pub classes: HashMap<String, HashMap<String, String>>,
    pub module_funcs: HashMap<String, HashMap<String, String>>,
    pub modules: HashMap<String, String>,
    pub attrs: HashMap<String, HashMap<String, String>>,
}

impl Ctx {
    /// 점 이름 꼬리 → 파일. 겹치는 꼬리는 모호하니 뺀다 (파이썬 `index_modules`)
    pub fn index_modules(&mut self, files: &[String]) {
        let mut dup: BTreeSet<String> = BTreeSet::new();
        for f in files {
            let without = f.strip_suffix(crate::graph::suffix(f)).unwrap_or(f);
            let mut ps: Vec<&str> = parts(without);
            if ps.last() == Some(&"__init__") {
                ps.pop();
            }
            for i in 0..ps.len() {
                let name = ps[i..].join(".");
                if self.modules.get(&name).is_some_and(|g| g != f) {
                    dup.insert(name.clone());
                }
                self.modules.insert(name, f.clone());
            }
        }
        for d in dup {
            self.modules.remove(&d);
        }
    }
}

/// 너비 우선으로 모든 노드 — 파이썬 `ast.walk`의 차례
pub(crate) fn walk(root: Node) -> Vec<Node> {
    let mut out = Vec::new();
    let mut q = VecDeque::from([root]);
    while let Some(n) = q.pop_front() {
        out.push(n);
        q.extend(named_children(n));
    }
    out
}

/// 정의를 걷는다 — 데코레이터까지(파이썬 `FunctionDef.decorator_list`는 정의의 자식이다)
fn walk_def(fn_node: Node) -> Vec<Node> {
    let mut nodes = walk(fn_node);
    if let Some(p) = fn_node
        .parent()
        .filter(|p| p.kind() == "decorated_definition")
    {
        for d in named_children(p)
            .into_iter()
            .filter(|c| c.kind() == "decorator")
        {
            nodes.extend(walk(d));
        }
    }
    nodes
}

/// 인자 주석의 클래스 이름 — `Cls` · `mod.Cls` · `"Cls"` · `Cls | None` (파이썬 `_ann_name`)
fn ann_name(n: Option<Node>, src: &str) -> Option<String> {
    let mut n = n?;
    while n.kind() == "type" {
        n = *named_children(n).first()?;
    }
    match n.kind() {
        "identifier" => Some(text(n, src).to_string()),
        "attribute" => n
            .child_by_field_name("attribute")
            .map(|a| text(a, src).to_string()),
        "string" | "concatenated_string" => {
            let v = string_value(n, src)?;
            let head = v.split('|').next().unwrap_or("");
            let last = strip(head).rsplit('.').next().unwrap_or("").to_string();
            (!last.is_empty()).then_some(last)
        }
        "binary_operator" => ann_name(n.child_by_field_name("left"), src)
            .or_else(|| ann_name(n.child_by_field_name("right"), src)),
        "parenthesized_expression" => ann_name(named_children(n).first().copied(), src),
        _ => None,
    }
}

/// 대입 노드가 과녁 하나짜리인가 — `a = b = X()`는 파이썬에서 과녁 둘인 대입 하나다
fn single_target(n: Node) -> bool {
    let right_is_assign = n
        .child_by_field_name("right")
        .is_some_and(|r| r.kind() == "assignment");
    let inside_chain = n
        .parent()
        .is_some_and(|p| p.kind() == "assignment" && p.child_by_field_name("right") == Some(n));
    !right_is_assign && !inside_chain
}

/// 대입 과녁인가 — 대입·덧셈 대입·`for`·`with … as`·`del`의 과녁이면 파이썬 `Store`·`Del`
fn is_store(n: Node) -> bool {
    let mut cur = n;
    loop {
        let Some(p) = cur.parent() else {
            return false;
        };
        match p.kind() {
            "assignment" | "augmented_assignment" => {
                return p.child_by_field_name("left") == Some(cur);
            }
            "for_statement" | "for_in_clause" => return p.child_by_field_name("left") == Some(cur),
            "as_pattern_target" => return true,
            "pattern_list" | "tuple_pattern" | "list_pattern" | "list_splat_pattern" => cur = p,
            "delete_statement" => return true,
            "expression_list" if p.parent().is_some_and(|g| g.kind() == "delete_statement") => {
                return true;
            }
            _ => return false,
        }
    }
}

fn call_class<'s>(
    v: Node,
    classes: &HashMap<String, HashMap<String, String>>,
    src: &'s str,
) -> Option<&'s str> {
    if v.kind() != "call" {
        return None;
    }
    let f = v.child_by_field_name("function")?;
    (f.kind() == "identifier" && classes.contains_key(text(f, src))).then(|| text(f, src))
}

/// `x = Cls(…)` · `a, b = A(…), B(…)` — 타입을 아는 변수로 적는다 (파이썬 `_bind`)
fn bind(
    target: Node,
    value: Node,
    env: &mut HashMap<String, String>,
    classes: &HashMap<String, HashMap<String, String>>,
    src: &str,
) {
    let pairs: Vec<(Node, Node)> = match (target.kind(), value.kind()) {
        ("identifier", _) => vec![(target, value)],
        ("pattern_list" | "tuple_pattern", "expression_list" | "tuple") => named_children(target)
            .into_iter()
            .zip(named_children(value))
            .collect(),
        _ => Vec::new(),
    };
    for (t, v) in pairs {
        if t.kind() == "identifier"
            && let Some(c) = call_class(v, classes, src)
        {
            env.insert(text(t, src).to_string(), c.to_string());
        }
    }
}

/// `__init__`의 `self.x = Cls(…)` · `self.x: Cls = …` → 속성 → 클래스 이름 (파이썬 `_self_attrs`)
pub(crate) fn self_attrs(init: Node, src: &str) -> HashMap<String, String> {
    let mut out = HashMap::new();
    for n in walk(init) {
        if n.kind() != "assignment" {
            continue;
        }
        let target = n.child_by_field_name("left");
        let cls_name = if n.child_by_field_name("type").is_some() {
            ann_name(n.child_by_field_name("type"), src)
        } else if single_target(n) {
            n.child_by_field_name("right").and_then(|v| {
                (v.kind() == "call")
                    .then(|| v.child_by_field_name("function"))
                    .flatten()
                    .filter(|f| f.kind() == "identifier")
                    .map(|f| text(f, src).to_string())
            })
        } else {
            None
        };
        if let (Some(cls), Some(t)) = (cls_name, target)
            && t.kind() == "attribute"
            && t.child_by_field_name("object")
                .is_some_and(|o| o.kind() == "identifier" && text(o, src) == "self")
            && let Some(attr) = t.child_by_field_name("attribute")
        {
            out.insert(text(attr, src).to_string(), cls);
        }
    }
    out
}

/// 상대 import의 점 수와 모듈 — `from ..a.b import x` → (2, "a.b")
pub(crate) fn from_module(n: Node, src: &str) -> (usize, String) {
    let Some(m) = n.child_by_field_name("module_name") else {
        return (0, String::new());
    };
    if m.kind() == "relative_import" {
        let mut level = 0;
        let mut name = String::new();
        for c in named_children(m) {
            match c.kind() {
                "import_prefix" => level = text(c, src).chars().filter(|&c| c == '.').count(),
                "dotted_name" => name = dotted(c, src),
                _ => {}
            }
        }
        (level, name)
    } else {
        (0, dotted(m, src))
    }
}

/// 점 이름 — 사이 공백을 걷는다(`a . b`도 파이썬은 `a.b`)
pub(crate) fn dotted(n: Node, src: &str) -> String {
    named_children(n)
        .into_iter()
        .filter(|c| c.kind() == "identifier")
        .map(|c| text(c, src))
        .collect::<Vec<_>>()
        .join(".")
}

/// import 문 → (모듈 별칭 → 파일, 가져온 함수 이름 → key). 상대 import도 푼다 (파이썬 `_imports`)
pub(crate) fn imports(
    nodes: &[Node],
    file: &str,
    ctx: &Ctx,
    src: &str,
) -> (HashMap<String, String>, HashMap<String, String>) {
    let mut mods = HashMap::new();
    let mut names = HashMap::new();
    let parent = file.rsplit_once('/').map_or("", |(p, _)| p);
    let pkg: Vec<&str> = parts(parent);
    for n in nodes {
        match n.kind() {
            "import_statement" => {
                for al in named_children(*n) {
                    let (name, asname) = match al.kind() {
                        "dotted_name" => (dotted(al, src), None),
                        "aliased_import" => (
                            al.child_by_field_name("name")
                                .map(|x| dotted(x, src))
                                .unwrap_or_default(),
                            al.child_by_field_name("alias")
                                .map(|x| text(x, src).to_string()),
                        ),
                        _ => continue,
                    };
                    match (&asname, ctx.modules.get(&name)) {
                        (Some(a), Some(f)) => {
                            mods.insert(a.clone(), f.clone());
                        }
                        (None, Some(f)) if !name.contains('.') => {
                            mods.insert(name.clone(), f.clone());
                        }
                        _ => {}
                    }
                }
            }
            "import_from_statement" => {
                let (level, module) = from_module(*n, src);
                let mut base = module.clone();
                if level > 0 {
                    let up: Vec<&str> = if level > 1 {
                        pkg[..pkg.len().saturating_sub(level - 1)].to_vec()
                    } else {
                        pkg.clone()
                    };
                    let mut segs: Vec<String> = up.iter().map(|s| s.to_string()).collect();
                    if !module.is_empty() {
                        segs.push(module.clone());
                    }
                    base = segs.join(".");
                }
                let module_node = n.child_by_field_name("module_name");
                for al in named_children(*n) {
                    if Some(al) == module_node {
                        continue;
                    }
                    let (name, asname) = match al.kind() {
                        "dotted_name" => (dotted(al, src), None),
                        "aliased_import" => (
                            al.child_by_field_name("name")
                                .map(|x| dotted(x, src))
                                .unwrap_or_default(),
                            al.child_by_field_name("alias")
                                .map(|x| text(x, src).to_string()),
                        ),
                        "wildcard_import" => ("*".to_string(), None),
                        _ => continue,
                    };
                    let alias = asname.unwrap_or_else(|| name.clone());
                    let sub = if base.is_empty() {
                        name.clone()
                    } else {
                        format!("{base}.{name}")
                    };
                    if let Some(f) = ctx.modules.get(&sub) {
                        mods.insert(alias, f.clone()); // `from app.infra import git` — 모듈을 가져왔다
                    } else if let Some(f) = ctx.modules.get(&base)
                        && let Some(key) = ctx.module_funcs.get(f).and_then(|m| m.get(&name))
                    {
                        names.insert(alias, key.clone()); // `from app.core.x import f` — 함수를 가져왔다
                    }
                }
            }
            _ => {}
        }
    }
    (mods, names)
}

/// 모듈 맨 위 import 문들
pub(crate) fn top_imports<'t>(f: &'t PyFile) -> Vec<Node<'t>> {
    named_children(f.tree.root_node())
        .into_iter()
        .filter(|n| matches!(n.kind(), "import_statement" | "import_from_statement"))
        .collect()
}

/// 함수 안 import 문들 — 순환을 피한 것(`from app.core import pipeline`)
pub(crate) fn inner_imports(fn_node: Node) -> Vec<Node> {
    walk(fn_node)
        .into_iter()
        .filter(|n| matches!(n.kind(), "import_statement" | "import_from_statement"))
        .collect()
}

/// 함수 몸통의 호출과 넘기는 참조 → 그래프 안 함수의 key (파이썬 `_resolve`)
pub(crate) fn resolve(
    cls: Option<&str>,
    fn_node: Node,
    ctx: &Ctx,
    mods: &HashMap<String, String>,
    names: &HashMap<String, String>,
    src: &str,
) -> BTreeSet<String> {
    let classes = &ctx.classes;
    let mut env: HashMap<String, String> = HashMap::new();
    if let Some(params) = fn_node.child_by_field_name("parameters") {
        for p in named_children(params) {
            let (pname, ann) = match p.kind() {
                "typed_parameter" => (
                    named_children(p)
                        .into_iter()
                        .find(|c| c.kind() == "identifier"),
                    p.child_by_field_name("type"),
                ),
                "typed_default_parameter" => {
                    (p.child_by_field_name("name"), p.child_by_field_name("type"))
                }
                _ => continue,
            };
            // `*args: T`·`**kw: T`는 파이썬 `vararg`·`kwarg` — 세지 않는다
            if p.kind() == "typed_parameter"
                && named_children(p)
                    .first()
                    .is_some_and(|c| c.kind() != "identifier")
            {
                continue;
            }
            if let (Some(pn), Some(t)) = (pname, ann_name(ann, src))
                && classes.contains_key(&t)
            {
                env.insert(text(pn, src).to_string(), t);
            }
        }
    }
    let nodes = walk_def(fn_node);
    for n in &nodes {
        if n.kind() != "assignment" {
            continue;
        }
        let (Some(target), value) = (
            n.child_by_field_name("left"),
            n.child_by_field_name("right"),
        ) else {
            continue;
        };
        if n.child_by_field_name("type").is_some() {
            // `x: T = v` — 파이썬 AnnAssign(값이 있을 때만)
            let Some(value) = value else {
                continue;
            };
            match ann_name(n.child_by_field_name("type"), src) {
                Some(t) if target.kind() == "identifier" && classes.contains_key(&t) => {
                    env.insert(text(target, src).to_string(), t);
                }
                _ => bind(target, value, &mut env, classes, src),
            }
        } else if single_target(*n)
            && let Some(value) = value
        {
            bind(target, value, &mut env, classes, src);
        }
    }
    let mut out = BTreeSet::new();
    for n in &nodes {
        match n.kind() {
            "attribute" if !is_store(*n) => {
                let (Some(base), Some(attr)) = (
                    n.child_by_field_name("object"),
                    n.child_by_field_name("attribute"),
                ) else {
                    continue;
                };
                let attr = text(attr, src);
                let base_name = (base.kind() == "identifier").then(|| text(base, src));
                let c: Option<String> = if let Some(cc) = call_class(base, classes, src) {
                    Some(cc.to_string())
                } else if let Some(b) = base_name.filter(|b| env.contains_key(*b)) {
                    env.get(b).cloned()
                } else if let Some(b) = base_name.filter(|b| classes.contains_key(*b)) {
                    Some(b.to_string()) // Cls.m — 클래스 이름으로 (#336)
                } else if base_name == Some("self") && cls.is_some() {
                    cls.map(str::to_string)
                } else if base.kind() == "attribute"
                    && base
                        .child_by_field_name("object")
                        .is_some_and(|o| o.kind() == "identifier" && text(o, src) == "self")
                    && let Some(c) = cls
                    && let Some(a) = base.child_by_field_name("attribute")
                    && let Some(t) = ctx.attrs.get(c).and_then(|m| m.get(text(a, src)))
                {
                    Some(t.clone()) // self.repo.get — __init__에서 담은 속성 (카드 BM)
                } else {
                    None
                };
                if let Some(key) = c
                    .as_ref()
                    .and_then(|c| classes.get(c))
                    .and_then(|m| m.get(attr))
                {
                    out.insert(key.clone());
                } else if let Some(b) = base_name
                    && let Some(f) = mods.get(b)
                    && let Some(key) = ctx.module_funcs.get(f).and_then(|m| m.get(attr))
                {
                    out.insert(key.clone());
                }
            }
            "call" => {
                if let Some(f) = n.child_by_field_name("function")
                    && f.kind() == "identifier"
                    && let Some(key) = names.get(text(f, src))
                {
                    out.insert(key.clone());
                }
            }
            _ => {}
        }
    }
    out
}

/// 정의 몸통의 이름 호출 `f(…)`의 이름들 — 추출이 같은 파일 호출 선으로 쓴다
pub(crate) fn name_calls(fn_node: Node, src: &str) -> Vec<String> {
    walk_def(fn_node)
        .into_iter()
        .filter(|n| n.kind() == "call")
        .filter_map(|n| n.child_by_field_name("function"))
        .filter(|f| f.kind() == "identifier")
        .map(|f| text(f, src).to_string())
        .collect()
}
