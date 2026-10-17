//! 호출 순서 — 함수마다 호출·반환·예외 (SYNC-MS-026 · MS-024 steps, 카드 L22).
//! 차례는 사건이 끝나는 바이트 자리로 정한다. 파이썬 파일은 tree-sitter-python으로 `ast`의 뜻을 읽는다(MS-026 0장).

use std::collections::HashMap;
use std::path::Path;

use serde_json::{Map, Value};
use tree_sitter::Node;

use super::{
    children, label, lang_of, named_children, read, rs_parse, text, ts_parse, unparen, walk,
};
use crate::python;

const MAX_STEPS: usize = 200;
const TS_FN: [&str; 5] = [
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "function_expression",
    "arrow_function",
];

/// 사건 하나 — 차례 열쇠와 내용. `ident`는 (마지막 이름, 맨 이름·경로 호출인가)
struct Ev {
    order: (u8, i64, i64),
    k: &'static str,
    line: i64,
    label: String,
    ident: Option<(String, bool)>,
    deferred: bool,
    awaited: bool,
}

fn row(n: Node) -> i64 {
    n.start_position().row as i64 + 1
}

fn ev(
    n: Node,
    k: &'static str,
    label_text: &str,
    ident: Option<(String, bool)>,
    deferred: bool,
    awaited: bool,
) -> Ev {
    Ev {
        order: (1, n.end_byte() as i64, -(n.start_byte() as i64)),
        k,
        line: row(n),
        label: label(label_text),
        ident,
        deferred,
        awaited,
    }
}

fn first_value(n: Node) -> Option<Node> {
    named_children(n)
        .into_iter()
        .find(|c| c.kind() != "comment" && c.kind() != "line_comment")
}

// ---------------------------------------------------------------- 파이썬

/// 줄 → 함수 정의(중첩 포함) — `def` 줄과 첫 데코레이터 줄. 같은 줄이면 앞선 것
fn py_defs(root: Node) -> HashMap<i64, Node> {
    let mut found: Vec<(i64, usize, Node)> = Vec::new();
    for n in walk(root) {
        if n.kind() != "function_definition" {
            continue;
        }
        let mut lines = vec![row(n)];
        if let Some(p) = n.parent().filter(|p| p.kind() == "decorated_definition")
            && let Some(d) = children(p).into_iter().find(|c| c.kind() == "decorator")
        {
            lines.push(row(d));
        }
        lines.sort();
        lines.dedup();
        for ln in lines {
            found.push((ln, n.start_byte(), n));
        }
    }
    found.sort_by_key(|(ln, b, _)| (*ln, *b));
    let mut out = HashMap::new();
    for (ln, _, n) in found {
        out.entry(ln).or_insert(n);
    }
    out
}

fn py_ident(n: Node, src: &[u8]) -> Option<(String, bool)> {
    let n = unparen(n);
    match n.kind() {
        "identifier" => Some((text(n, src), true)),
        "attribute" => n
            .child_by_field_name("attribute")
            .map(|a| (text(a, src), false)),
        _ => None,
    }
}

fn is_depends(n: Node, src: &[u8]) -> bool {
    if n.kind() != "call" {
        return false;
    }
    let Some(f) = n.child_by_field_name("function").map(unparen) else {
        return false;
    };
    match f.kind() {
        "identifier" => text(f, src) == "Depends",
        "attribute" => f
            .child_by_field_name("attribute")
            .is_some_and(|a| text(a, src) == "Depends"),
        _ => false,
    }
}

/// 호출의 위치 인자들 — 이름 붙은 인자·주석은 뺀다
fn positional(call: Node) -> Vec<Node> {
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

fn py_events(fn_node: Node, src: &[u8]) -> Vec<Ev> {
    let mut out = Vec::new();
    if let Some(params) = fn_node.child_by_field_name("parameters") {
        for p in named_children(params) {
            if !matches!(p.kind(), "default_parameter" | "typed_default_parameter") {
                continue;
            }
            let Some(d) = p.child_by_field_name("value").map(unparen) else {
                continue;
            };
            if !is_depends(d, src) {
                continue;
            }
            let Some(arg) = positional(d).into_iter().next() else {
                continue;
            };
            out.push(Ev {
                order: (0, d.start_byte() as i64, 0),
                k: "call",
                line: row(fn_node),
                label: label(&format!("Depends({})", text(unparen(arg), src))),
                ident: py_ident(arg, src),
                deferred: false,
                awaited: false,
            });
        }
    }
    fn visit(n: Node, src: &[u8], deferred: bool, awaited: bool, out: &mut Vec<Ev>) {
        match n.kind() {
            "decorated_definition" => {
                if let Some(d) = n.child_by_field_name("definition")
                    && d.kind() == "function_definition"
                    && let Some(b) = d.child_by_field_name("body")
                {
                    visit(b, src, true, false, out);
                }
                return;
            }
            "function_definition" => {
                if let Some(b) = n.child_by_field_name("body") {
                    visit(b, src, true, false, out);
                }
                return;
            }
            "lambda" => {
                if let Some(b) = n.child_by_field_name("body") {
                    visit(b, src, true, false, out);
                }
                return;
            }
            "class_definition" => return,
            "await" => {
                if let Some(v) = first_value(n) {
                    visit(unparen(v), src, deferred, true, out);
                }
                return;
            }
            "call" => {
                if let Some(f) = n.child_by_field_name("function") {
                    out.push(ev(
                        n,
                        "call",
                        &text(unparen(f), src),
                        py_ident(f, src),
                        deferred,
                        awaited,
                    ));
                }
            }
            "return_statement" if !deferred => {
                let l = match first_value(n) {
                    Some(v) => format!("return {}", text(unparen(v), src)),
                    None => "return".into(),
                };
                out.push(ev(n, "return", &l, None, false, false));
            }
            "raise_statement" if !deferred => {
                let l = match first_value(n) {
                    Some(v) => format!("raise {}", text(unparen(v), src)),
                    None => "raise".into(),
                };
                out.push(ev(n, "raise", &l, None, false, false));
            }
            _ => {}
        }
        for c in children(n) {
            visit(c, src, deferred, false, out);
        }
    }
    if let Some(body) = fn_node.child_by_field_name("body") {
        for c in children(body) {
            visit(c, src, false, false, &mut out);
        }
    }
    out
}

// ---------------------------------------------------------------- TS/JS

pub(crate) fn ts_defs(root: Node) -> HashMap<i64, Node> {
    let mut found: Vec<(i64, usize, Node)> = Vec::new();
    for n in walk(root) {
        if !TS_FN.contains(&n.kind()) {
            continue;
        }
        let mut lines = vec![row(n)];
        if let Some(p) = n.parent() {
            if p.kind() == "variable_declarator" {
                if let Some(decl) = p.parent()
                    && matches!(decl.kind(), "lexical_declaration" | "variable_declaration")
                {
                    lines.push(row(decl));
                    if let Some(ex) = decl.parent().filter(|x| x.kind() == "export_statement") {
                        lines.push(row(ex));
                    }
                }
            } else if matches!(
                p.kind(),
                "pair" | "public_field_definition" | "export_statement"
            ) {
                lines.push(row(p));
            }
        }
        lines.sort();
        lines.dedup();
        for ln in lines {
            found.push((ln, n.start_byte(), n));
        }
    }
    found.sort_by_key(|(ln, b, _)| (*ln, *b));
    let mut out = HashMap::new();
    for (ln, _, n) in found {
        out.entry(ln).or_insert(n);
    }
    out
}

fn ts_ident(f: Node, src: &[u8]) -> Option<(String, bool)> {
    let f = unparen(f);
    match f.kind() {
        "identifier" => Some((text(f, src), true)),
        "member_expression" => f
            .child_by_field_name("property")
            .map(|p| (text(p, src), false)),
        _ => None,
    }
}

fn ts_events(fn_node: Node, src: &[u8]) -> Vec<Ev> {
    let mut out = Vec::new();
    let Some(body) = fn_node.child_by_field_name("body") else {
        return out;
    };
    fn visit(n: Node, src: &[u8], deferred: bool, awaited: bool, out: &mut Vec<Ev>) {
        let t = n.kind();
        if TS_FN.contains(&t) {
            if let Some(b) = n.child_by_field_name("body") {
                visit(b, src, true, false, out);
            }
            return;
        }
        match t {
            "class_declaration" | "class" => return,
            "await_expression" => {
                for c in named_children(n) {
                    visit(c, src, deferred, true, out);
                }
                return;
            }
            "call_expression" => {
                if let Some(f) = n.child_by_field_name("function")
                    && f.kind() != "import"
                {
                    out.push(ev(
                        n,
                        "call",
                        &text(unparen(f), src),
                        ts_ident(f, src),
                        deferred,
                        awaited,
                    ));
                }
            }
            "jsx_opening_element" | "jsx_self_closing_element" => {
                if let Some(name) = n.child_by_field_name("name") {
                    let nm = text(name, src);
                    if nm.chars().next().is_some_and(char::is_uppercase) {
                        let last = nm.rsplit('.').next().unwrap_or(&nm).to_string();
                        let bare = !nm.contains('.');
                        out.push(ev(
                            n,
                            "call",
                            &format!("<{nm}>"),
                            Some((last, bare)),
                            deferred,
                            false,
                        ));
                    }
                }
            }
            "return_statement" if !deferred => {
                let l = match first_value(n) {
                    Some(v) => format!("return {}", text(unparen(v), src)),
                    None => "return".into(),
                };
                out.push(ev(n, "return", &l, None, false, false));
            }
            "throw_statement" if !deferred => {
                let l = match first_value(n) {
                    Some(v) => format!("throw {}", text(unparen(v), src)),
                    None => "throw".into(),
                };
                out.push(ev(n, "raise", &l, None, false, false));
            }
            _ => {}
        }
        for c in children(n) {
            visit(c, src, deferred, false, out);
        }
    }
    visit(body, src, false, false, &mut out);
    out
}

// ---------------------------------------------------------------- Rust

pub(crate) fn rs_defs(root: Node) -> HashMap<i64, Node> {
    let mut found: Vec<(i64, usize, Node)> = Vec::new();
    for n in walk(root) {
        if n.kind() != "function_item" {
            continue;
        }
        let kw = children(n)
            .into_iter()
            .find(|c| c.kind() == "fn")
            .unwrap_or(n);
        found.push((row(kw), n.start_byte(), n));
    }
    found.sort_by_key(|(ln, b, _)| (*ln, *b));
    let mut out = HashMap::new();
    for (ln, _, n) in found {
        out.entry(ln).or_insert(n);
    }
    out
}

fn rs_ident(f: Node, src: &[u8]) -> Option<(String, bool)> {
    let f = unparen(f);
    match f.kind() {
        "generic_function" => f
            .child_by_field_name("function")
            .and_then(|g| rs_ident(g, src)),
        "identifier" => Some((text(f, src), true)),
        "field_expression" => f
            .child_by_field_name("field")
            .map(|x| (text(x, src), false)),
        "scoped_identifier" => f.child_by_field_name("name").map(|x| (text(x, src), true)),
        _ => None,
    }
}

fn rs_events(fn_node: Node, src: &[u8]) -> Vec<Ev> {
    let mut out = Vec::new();
    let Some(body) = fn_node.child_by_field_name("body") else {
        return out;
    };
    fn visit(n: Node, src: &[u8], deferred: bool, awaited: bool, out: &mut Vec<Ev>) {
        match n.kind() {
            "function_item" | "closure_expression" => {
                if let Some(b) = n.child_by_field_name("body") {
                    visit(b, src, true, false, out);
                }
                return;
            }
            "await_expression" => {
                for (i, c) in named_children(n).into_iter().enumerate() {
                    visit(c, src, deferred, i == 0, out);
                }
                return;
            }
            "call_expression" => {
                if let Some(f) = n.child_by_field_name("function") {
                    out.push(ev(
                        n,
                        "call",
                        &text(unparen(f), src),
                        rs_ident(f, src),
                        deferred,
                        awaited,
                    ));
                }
            }
            "return_expression" if !deferred => {
                let l = match named_children(n)
                    .into_iter()
                    .find(|c| c.kind() != "line_comment")
                {
                    Some(v) => format!("return {}", text(unparen(v), src)),
                    None => "return".into(),
                };
                out.push(ev(n, "return", &l, None, false, false));
            }
            _ => {}
        }
        for c in children(n) {
            visit(c, src, deferred, false, out);
        }
    }
    visit(body, src, false, false, &mut out);
    out
}

// ---------------------------------------------------------------- Java·Go (카드 L33)

/// 줄 → 정의 — 선언의 첫 줄(Java는 어노테이션 줄부터, Go는 `func` 줄). 같은 줄이면 앞선 것
pub(crate) fn start_defs<'t>(root: Node<'t>, kinds: &[&str]) -> HashMap<i64, Node<'t>> {
    let mut found: Vec<Node> = walk(root)
        .into_iter()
        .filter(|n| kinds.contains(&n.kind()))
        .collect();
    found.sort_by_key(|n| n.start_byte());
    let mut out = HashMap::new();
    for n in found {
        out.entry(row(n)).or_insert(n);
    }
    out
}

const JAVA_FN: [&str; 2] = ["method_declaration", "constructor_declaration"];
const GO_FN: [&str; 2] = ["function_declaration", "method_declaration"];
const JAVA_SKIP: [&str; 5] = [
    "class_body",
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
];

fn java_events(fn_node: Node, src: &[u8]) -> Vec<Ev> {
    let mut out = Vec::new();
    let Some(body) = fn_node.child_by_field_name("body") else {
        return out;
    };
    fn first(n: Node) -> Option<Node> {
        named_children(n)
            .into_iter()
            .find(|c| c.kind() != "line_comment" && c.kind() != "block_comment")
    }
    fn visit(n: Node, src: &[u8], deferred: bool, out: &mut Vec<Ev>) {
        let k = n.kind();
        if k == "lambda_expression" {
            if let Some(b) = n.child_by_field_name("body") {
                visit(b, src, true, out);
            }
            return;
        }
        if JAVA_SKIP.contains(&k) {
            return;
        }
        match k {
            "method_invocation" => {
                if let Some(name) = n.child_by_field_name("name") {
                    let l =
                        String::from_utf8_lossy(&src[n.start_byte()..name.end_byte()]).into_owned();
                    let ident = Some((text(name, src), n.child_by_field_name("object").is_none()));
                    out.push(ev(n, "call", &l, ident, deferred, false));
                }
            }
            "object_creation_expression" => {
                if let Some(ty) = n.child_by_field_name("type") {
                    let ident = crate::java::jtype(Some(ty), src).map(|t| (t, true));
                    let l = format!("new {}", text(ty, src));
                    out.push(ev(n, "call", &l, ident, deferred, false));
                }
            }
            "return_statement" if !deferred => {
                let l = match first(n) {
                    Some(v) => format!("return {}", text(unparen(v), src)),
                    None => "return".into(),
                };
                out.push(ev(n, "return", &l, None, false, false));
            }
            "throw_statement" if !deferred => {
                let l = match first(n) {
                    Some(v) => format!("throw {}", text(unparen(v), src)),
                    None => "throw".into(),
                };
                out.push(ev(n, "raise", &l, None, false, false));
            }
            _ => {}
        }
        for c in children(n) {
            visit(c, src, deferred, out);
        }
    }
    visit(body, src, false, &mut out);
    out
}

fn go_ident(f: Node, src: &[u8]) -> Option<(String, bool)> {
    let f = unparen(f);
    match f.kind() {
        "identifier" => Some((text(f, src), true)),
        "selector_expression" => f
            .child_by_field_name("field")
            .map(|x| (text(x, src), false)),
        _ => None,
    }
}

fn go_events(fn_node: Node, src: &[u8]) -> Vec<Ev> {
    let mut out = Vec::new();
    let Some(body) = fn_node.child_by_field_name("body") else {
        return out;
    };
    fn visit(n: Node, src: &[u8], deferred: bool, out: &mut Vec<Ev>) {
        match n.kind() {
            "func_literal" => {
                if let Some(b) = n.child_by_field_name("body") {
                    visit(b, src, true, out);
                }
                return;
            }
            "go_statement" | "defer_statement" => {
                for c in children(n) {
                    visit(c, src, true, out);
                }
                return;
            }
            "call_expression" => {
                if let Some(f) = n.child_by_field_name("function") {
                    out.push(ev(
                        n,
                        "call",
                        &text(unparen(f), src),
                        go_ident(f, src),
                        deferred,
                        false,
                    ));
                }
            }
            "return_statement" if !deferred => {
                let l = match first_value(n) {
                    Some(v) => format!("return {}", text(v, src)),
                    None => "return".into(),
                };
                out.push(ev(n, "return", &l, None, false, false));
            }
            _ => {}
        }
        for c in children(n) {
            visit(c, src, deferred, out);
        }
    }
    visit(body, src, false, &mut out);
    out
}

// ---------------------------------------------------------------- 묶기

/// 파일의 정의 줄 → 그 정의의 사건들. 못 읽으면 빈 사전
fn events_of(lang: &str, file: &str, src: &[u8]) -> HashMap<i64, Vec<Ev>> {
    match lang {
        "py" => {
            let Some(pf) = python::parse(&String::from_utf8_lossy(src)) else {
                return HashMap::new();
            };
            let s = pf.src.as_bytes();
            py_defs(pf.tree.root_node())
                .into_iter()
                .map(|(ln, n)| (ln, py_events(n, s)))
                .collect()
        }
        "ts" => {
            let Some(tree) = ts_parse(file, src) else {
                return HashMap::new();
            };
            ts_defs(tree.root_node())
                .into_iter()
                .map(|(ln, n)| (ln, ts_events(n, src)))
                .collect()
        }
        "rs" => {
            let Some(tree) = rs_parse(src) else {
                return HashMap::new();
            };
            rs_defs(tree.root_node())
                .into_iter()
                .map(|(ln, n)| (ln, rs_events(n, src)))
                .collect()
        }
        "java" => {
            let Some(tree) = crate::java::parse(src) else {
                return HashMap::new();
            };
            start_defs(tree.root_node(), &JAVA_FN)
                .into_iter()
                .map(|(ln, n)| (ln, java_events(n, src)))
                .collect()
        }
        _ => {
            let Some(tree) = crate::go::parse(src) else {
                return HashMap::new();
            };
            start_defs(tree.root_node(), &GO_FN)
                .into_iter()
                .map(|(ln, n)| (ln, go_events(n, src)))
                .collect()
        }
    }
}

fn s(v: &Value, k: &str) -> String {
    v.get(k)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

/// SYNC-MS-026#steps.steps
///
/// 함수마다 `steps` — 정의 몸통의 호출·JSX·반환·예외를 끝 바이트 차례로. 대상은 나가는 호출 선 중 이름이 하나뿐인 것,
/// 없으면 같은 언어에서 하나뿐인 맨 이름(`inferred`). 돌려주는 것은 함수 열쇠 → step마다 마지막 이름(장비 판정용).
pub fn steps(src_dir: &Path, graph: &mut Value) -> HashMap<String, Vec<Option<String>>> {
    let funcs: Vec<Value> = graph["functions"].as_array().cloned().unwrap_or_default();
    let mut by_name: HashMap<(Option<&'static str>, String), Vec<String>> = HashMap::new();
    let mut name_of: HashMap<String, String> = HashMap::new();
    for f in &funcs {
        by_name
            .entry((lang_of(&s(f, "file")), s(f, "name")))
            .or_default()
            .push(s(f, "key"));
        name_of.insert(s(f, "key"), s(f, "name"));
    }
    let mut out_edges: HashMap<String, Vec<String>> = HashMap::new();
    for c in graph["calls"].as_array().cloned().unwrap_or_default() {
        let (a, b) = (
            c[0].as_str().unwrap_or_default(),
            c[1].as_str().unwrap_or_default(),
        );
        let e = out_edges.entry(a.to_string()).or_default();
        if !e.iter().any(|x| x == b) {
            e.push(b.to_string());
        }
    }
    let mut files: Vec<String> = Vec::new();
    for f in &funcs {
        let file = s(f, "file");
        if !files.contains(&file) {
            files.push(file);
        }
    }
    let mut result: HashMap<String, Vec<Value>> = HashMap::new();
    let mut idents: HashMap<String, Vec<Option<String>>> = HashMap::new();
    for file in files {
        let Some(lang) = lang_of(&file) else { continue };
        let Some(src) = read(src_dir, &file) else {
            continue;
        };
        let mut events = events_of(lang, &file, &src);
        for f in funcs.iter().filter(|f| s(f, "file") == file) {
            let line = f["line"].as_i64().unwrap_or(0);
            let Some(evs) = events.get_mut(&line) else {
                continue;
            };
            // 같은 줄의 함수가 둘이면 같은 정의를 함께 쓴다 — 정렬은 안정이라 두 번 해도 같다
            evs.sort_by_key(|e| e.order);
            let evs = &evs[..evs.len().min(MAX_STEPS)];
            let key = s(f, "key");
            let steps: Vec<Value> = evs
                .iter()
                .map(|e| step(e, &key, Some(lang), &out_edges, &by_name, &name_of))
                .collect();
            idents.insert(
                key.clone(),
                evs.iter()
                    .map(|e| {
                        if e.k == "call" {
                            e.ident.as_ref().map(|i| i.0.clone())
                        } else {
                            None
                        }
                    })
                    .collect(),
            );
            result.insert(key, steps);
        }
    }
    if let Some(arr) = graph.get_mut("functions").and_then(Value::as_array_mut) {
        for f in arr.iter_mut().filter_map(Value::as_object_mut) {
            let key = f
                .get("key")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string();
            f.insert(
                "steps".into(),
                Value::Array(result.remove(&key).unwrap_or_default()),
            );
        }
    }
    idents
}

fn step(
    e: &Ev,
    key: &str,
    lang: Option<&'static str>,
    out_edges: &HashMap<String, Vec<String>>,
    by_name: &HashMap<(Option<&'static str>, String), Vec<String>>,
    name_of: &HashMap<String, String>,
) -> Value {
    let (mut to, mut inferred) = (None, false);
    if e.k == "call"
        && let Some((ident, bare)) = &e.ident
    {
        let local: Vec<&String> = out_edges
            .get(key)
            .map(|v| {
                v.iter()
                    .filter(|b| name_of.get(*b) == Some(ident))
                    .collect()
            })
            .unwrap_or_default();
        if local.len() == 1 {
            to = Some(local[0].clone());
        } else if local.is_empty() && *bare {
            let cands = by_name
                .get(&(lang, ident.clone()))
                .cloned()
                .unwrap_or_default();
            if cands.len() == 1 && cands[0] != key {
                to = Some(cands[0].clone());
                inferred = true;
            }
        }
    }
    let mut m = Map::new();
    m.insert("k".into(), e.k.into());
    m.insert("line".into(), e.line.into());
    m.insert("label".into(), e.label.clone().into());
    if let Some(t) = to {
        m.insert("to".into(), t.into());
    }
    if inferred {
        m.insert("inferred".into(), true.into());
    }
    if e.deferred {
        m.insert("deferred".into(), true.into());
    }
    if e.awaited {
        m.insert("awaited".into(), true.into());
    }
    Value::Object(m)
}
