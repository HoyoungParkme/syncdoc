//! 보강 — 파이썬·TS/JS·화면 ID·Rust (SYNC-MS-022#codegraph.enrich · MS-011 enrich 1~6).

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;
use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;
use syncdoc_pycompat::re::compile;

use crate::graph::{item_of, module};
use crate::python::{self, Ctx, PyFile};
use crate::ts::TS_EXTS;
use crate::{Call, Function, Graph, rust, ts};

/// 화면 코드 파일 첫 주석의 화면 ID — 그 파일 함수 전부의 item (MS-011 enrich 3)
static SCREEN_ID: LazyLock<Regex> = LazyLock::new(|| compile(r"[A-Z][A-Z0-9]*-UI-\d{3}#UI-\d+"));
static HEAD_COMMENT: LazyLock<Regex> =
    LazyLock::new(|| compile(r"^\s*(/\*[\s\S]*?\*/|(?://[^\n]*\n?)+)"));
const SCREEN_EXTS: [&str; 4] = [".ts", ".tsx", ".js", ".jsx"];

/// 파이썬 `read_text(encoding="utf-8", errors="replace")[:4000]` — 보편 줄바꿈
fn head_text(path: &Path) -> Option<String> {
    let bytes = std::fs::read(path).ok()?;
    let text = String::from_utf8_lossy(&bytes)
        .replace("\r\n", "\n")
        .replace('\r', "\n");
    Some(text.chars().take(4000).collect())
}

/// MS-011 enrich 3 — 화면 코드 파일 첫 주석의 화면 ID를 그 파일 함수 중 item 없는 것 전부에
fn screen_items(src_dir: &Path, funcs: &mut [Function]) {
    let mut by_file: IndexMap<String, Vec<usize>> = IndexMap::new();
    for (i, f) in funcs.iter().enumerate() {
        if SCREEN_EXTS.iter().any(|e| f.file.ends_with(e)) {
            by_file.entry(f.file.clone()).or_default().push(i);
        }
    }
    for (file, idxs) in by_file {
        let Some(head) = head_text(&src_dir.join(&file)) else {
            continue;
        };
        let Some(c) = HEAD_COMMENT.find(&head) else {
            continue;
        };
        let Some(m) = SCREEN_ID.find(c.as_str()) else {
            continue;
        };
        for i in idxs {
            if funcs[i].item.as_deref().is_none_or(str::is_empty) {
                funcs[i].item = Some(m.as_str().to_string());
            }
        }
    }
}

/// SYNC-MS-022#codegraph.enrich
///
/// 파이썬 파일을 다시 읽어 끝 줄·이름·항목 ID를 바로잡고 graphify가 놓친 호출을 더한다. TS/JS는 끝 줄·빠진 맨 위
/// 함수·호출, 화면 코드는 첫 주석의 화면 ID, Rust는 정의·항목 ID·호출을 다 채운다. 다른 언어는 손대지 않는다
pub fn enrich(src_dir: &Path, mut graph: Graph) -> Graph {
    let seen = std::mem::take(&mut graph.files);
    let mut by_loc: HashMap<(String, i64), usize> = HashMap::new();
    for (i, f) in graph.functions.iter().enumerate() {
        by_loc.insert((f.file.clone(), f.line), i);
    }
    let mut ctx = Ctx::default();
    let files: Vec<String> = graph
        .functions
        .iter()
        .filter(|f| f.file.ends_with(".py"))
        .map(|f| f.file.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    ctx.index_modules(&files);
    let mut trees: Vec<(String, PyFile)> = Vec::new();
    for file in &files {
        let Ok(bytes) = std::fs::read(src_dir.join(file)) else {
            continue;
        };
        let Ok(text) = String::from_utf8(bytes) else {
            continue;
        };
        if let Some(t) = python::parse(&text) {
            trees.push((file.clone(), t));
        }
    }
    // (파일, 함수 자리, 소속 클래스, 정의 차례) — 호출은 TS·Rust 뒤에 더한다(파이썬 판 차례)
    let mut found: Vec<(usize, usize, Option<String>, usize)> = Vec::new();
    for (ti, (file, tree)) in trees.iter().enumerate() {
        for (di, d) in python::defs(tree).into_iter().enumerate() {
            let heads: Vec<i64> = std::iter::once(d.line)
                .chain(d.decorators.iter().copied())
                .collect();
            let idx = match heads
                .iter()
                .find_map(|ln| by_loc.get(&(file.clone(), *ln)).copied())
            {
                Some(i) => i,
                None => {
                    // graphify가 놓친 정의 — 더한다
                    graph.functions.push(Function {
                        key: format!("{file}:{}", d.line),
                        name: d.name.clone(),
                        qual: String::new(),
                        file: file.clone(),
                        line: d.line,
                        end: None,
                        item: None,
                        ms: None,
                        community: None,
                    });
                    let i = graph.functions.len() - 1;
                    by_loc.insert((file.clone(), d.line), i);
                    i
                }
            };
            let f = &mut graph.functions[idx];
            f.end = Some(d.end);
            f.qual = match &d.cls {
                Some(c) => format!("{c}.{}", d.name),
                None => format!("{}.{}", module(file), d.name),
            };
            if let Some(doc) = &d.doc {
                let (it, m) = item_of(doc);
                if it.is_some() {
                    f.item = it;
                    f.ms = m;
                }
            }
            let key = f.key.clone();
            match &d.cls {
                Some(c) => {
                    ctx.classes
                        .entry(c.clone())
                        .or_default()
                        .insert(d.name.clone(), key);
                    if d.name == "__init__" {
                        let attrs = python::self_attrs(d.node, &tree.src);
                        ctx.attrs.entry(c.clone()).or_default().extend(attrs);
                    }
                }
                None => {
                    ctx.module_funcs
                        .entry(file.clone())
                        .or_default()
                        .insert(d.name.clone(), key);
                }
            }
            found.push((ti, idx, d.cls.clone(), di));
        }
    }
    let ts_seen: Vec<String> = seen
        .iter()
        .filter(|x| TS_EXTS.iter().any(|e| x.ends_with(e)))
        .cloned()
        .collect();
    ts::enrich(src_dir, &mut graph, &ts_seen); // 2a~2d — 화면 ID(3) 앞에
    screen_items(src_dir, &mut graph.functions);
    let rs_seen: Vec<String> = seen
        .iter()
        .filter(|x| x.ends_with(".rs"))
        .cloned()
        .collect();
    rust::enrich(src_dir, &mut graph, &rs_seen); // 2e~2h
    let file_imports: Vec<_> = trees
        .iter()
        .map(|(file, t)| python::imports(&python::top_imports(t), file, &ctx, &t.src))
        .collect();
    let mut have: HashSet<(String, String)> = graph
        .calls
        .iter()
        .map(|c| (c.0.clone(), c.1.clone()))
        .collect();
    for (ti, idx, cls, di) in found {
        let (file, tree) = &trees[ti];
        let d = &python::defs(tree)[di];
        let (mods, names) = &file_imports[ti];
        let (lm, ln) = python::imports(&python::inner_imports(d.node), file, &ctx, &tree.src);
        let mut mods = mods.clone();
        mods.extend(lm);
        let mut names = names.clone();
        names.extend(ln);
        let key = graph.functions[idx].key.clone();
        for dst in python::resolve(cls.as_deref(), d.node, &ctx, &mods, &names, &tree.src) {
            if dst != key && have.insert((key.clone(), dst.clone())) {
                graph.calls.push(Call(key.clone(), dst, "enrich".into()));
            }
        }
    }
    graph
}
