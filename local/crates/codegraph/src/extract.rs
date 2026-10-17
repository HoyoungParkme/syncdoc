//! graphify 대신 — tree-sitter로 원형을 만든다 (SYNC-MS-022#codegraph.extract, INFRA 9.2).
//! graphify `graph.json`(node-link)의 모양으로, 줄이기·보강·커뮤니티가 읽는 것만: 파일 노드, 파이썬 맨 위 함수·클래스·
//! 메서드와 그 사이 `contains`·`method` 선, 같은 파일 이름 호출. TS/JS·Rust·Java·Go는 파일 노드만 — 보강이 다 채운다.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;

use serde_json::{Value, json};

use crate::CodeGraphFailed;
use crate::graph::name;
use crate::python;

const EXTS: [&str; 9] = [
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".rs", ".java", ".go",
];
const SKIP_DIRS: [&str; 4] = [".git", "graphify-out", "node_modules", "target"];

fn walk(root: &Path, rel: &str, out: &mut BTreeSet<String>) {
    let Ok(entries) = std::fs::read_dir(root.join(rel)) else {
        return;
    };
    for e in entries.flatten() {
        let fname = e.file_name().to_string_lossy().into_owned();
        let path = if rel.is_empty() {
            fname.clone()
        } else {
            format!("{rel}/{fname}")
        };
        let Ok(ft) = e.file_type() else {
            continue;
        };
        if ft.is_dir() {
            if !SKIP_DIRS.contains(&fname.as_str()) {
                walk(root, &path, out);
            }
        } else if ft.is_file() && EXTS.iter().any(|x| fname.ends_with(x)) {
            out.insert(path);
        }
    }
}

/// SYNC-MS-022#codegraph.extract
///
/// 파일을 경로 순으로 — 파이썬은 맨 위 함수·클래스·메서드 노드와 같은 파일 이름 호출 선까지
pub fn extract(src_dir: &Path) -> Result<Value, CodeGraphFailed> {
    if !src_dir.is_dir() {
        let base = src_dir
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        return Err(CodeGraphFailed(format!("폴더 없음: {base}")));
    }
    let mut files = BTreeSet::new();
    walk(src_dir, "", &mut files);
    let mut nodes: Vec<Value> = Vec::new();
    let mut links: Vec<Value> = Vec::new();
    for file in &files {
        nodes.push(
            json!({"id": file, "label": name(file), "file_type": "code", "source_file": file}),
        );
        if !file.ends_with(".py") {
            continue;
        }
        let Some(text) = std::fs::read(src_dir.join(file))
            .ok()
            .and_then(|b| String::from_utf8(b).ok())
        else {
            continue;
        };
        let Some(tree) = python::parse(&text) else {
            continue;
        };
        let defs = python::defs(&tree);
        let mut top: HashMap<&str, String> = HashMap::new();
        let mut classes: HashSet<i64> = HashSet::new();
        for d in &defs {
            let fid = format!("{file}:{}", d.line);
            let label = match d.cls {
                Some(_) => format!(".{}()", d.name),
                None => format!("{}()", d.name),
            };
            if let (Some(cls), Some(cl)) = (&d.cls, d.cls_line) {
                let cid = format!("{file}:{cl}:class");
                if classes.insert(cl) {
                    nodes.push(json!({
                        "id": cid, "label": cls, "file_type": "code", "source_file": file,
                        "source_location": format!("L{cl}"), "_callable": true, "_callable_class": true,
                    }));
                    links.push(json!({"source": file, "target": cid, "relation": "contains", "confidence": "EXTRACTED"}));
                }
                links.push(json!({"source": cid, "target": fid, "relation": "method", "confidence": "EXTRACTED"}));
            } else {
                top.insert(d.name.as_str(), fid.clone());
                links.push(json!({"source": file, "target": fid, "relation": "contains", "confidence": "EXTRACTED"}));
            }
            nodes.push(json!({
                "id": fid, "label": label, "file_type": "code", "source_file": file,
                "source_location": format!("L{}", d.line), "_callable": true,
            }));
        }
        let mut seen: HashSet<(String, String)> = HashSet::new();
        for d in &defs {
            let fid = format!("{file}:{}", d.line);
            for callee in python::name_calls(d.node, &tree.src) {
                if let Some(target) = top.get(callee.as_str())
                    && seen.insert((fid.clone(), target.clone()))
                {
                    links.push(json!({
                        "source": fid, "target": target, "relation": "calls", "confidence": "EXTRACTED",
                    }));
                }
            }
        }
    }
    Ok(json!({"directed": false, "multigraph": false, "graph": {}, "nodes": nodes, "links": links}))
}
