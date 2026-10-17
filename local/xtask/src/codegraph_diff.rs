//! 코드 그래프 차이 시험 — 지금 커밋을 풀어 두 판의 줄이기·보강·커뮤니티·흐름을 같은 원형으로 돌려 비교한다 (SYNC-MS-022·026, 카드 L12·L13·L22).
//! 원형은 파이썬 판 graphify가 만든다. 다르면 처음 몇 곳을 보이고 실패한다. 커밋하지 않는다(정답 파일은 codegraph-golden).

use std::process::Command;

use serde_json::Value;

use crate::{python, repo_root};

pub fn run() -> Result<(), String> {
    let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
    let src = tmp.path().join("src");
    std::fs::create_dir_all(&src).map_err(|e| e.to_string())?;
    let tar = tmp.path().join("head.tar");
    let ok = Command::new("git")
        .args(["archive", "--format=tar", "-o"])
        .arg(&tar)
        .arg("HEAD")
        .current_dir(repo_root())
        .status()
        .map_err(|e| e.to_string())?
        .success()
        && Command::new("tar")
            .arg("-xf")
            .arg(&tar)
            .arg("-C")
            .arg(&src)
            .status()
            .map_err(|e| e.to_string())?
            .success();
    if !ok {
        return Err("커밋을 풀지 못했다".into());
    }
    let out = tmp.path().join("python.json");
    python("codegraph_diff.py", &[src.as_os_str(), out.as_os_str()])?;
    let py: Value = serde_json::from_slice(&std::fs::read(&out).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let rs = syncdoc_codegraph::enrich(&src, syncdoc_codegraph::reduce(&py["raw"]));
    let rs = serde_json::to_value(&rs).map_err(|e| e.to_string())?;
    let mut diffs = Vec::new();
    for part in ["functions", "calls"] {
        let (a, b) = (py["enriched"][part].as_array(), rs[part].as_array());
        let (Some(a), Some(b)) = (a, b) else {
            return Err(format!("{part}가 없다"));
        };
        println!("{part}: 파이썬 {} · Rust {}", a.len(), b.len());
        for (i, (x, y)) in a.iter().zip(b).enumerate() {
            if x != y {
                diffs.push(format!("{part}[{i}]\n  파이썬 {x}\n  Rust   {y}"));
            }
        }
        if a.len() != b.len() {
            diffs.push(format!(
                "{part} 수가 다르다 — 파이썬 {} · Rust {}",
                a.len(),
                b.len()
            ));
        }
    }
    // 커뮤니티 — 같은 원형·같은 보강으로(카드 L13). 파이썬은 커뮤니티 없는 함수에도 `community: null`을 둔다
    let grouped = syncdoc_codegraph::communities(
        &py["raw"],
        syncdoc_codegraph::enrich(&src, syncdoc_codegraph::reduce(&py["raw"])),
    );
    let mut grouped = serde_json::to_value(&grouped).map_err(|e| e.to_string())?;
    null_community(&mut grouped);
    for part in ["functions", "communities"] {
        let (a, b) = (py["communities"][part].as_array(), grouped[part].as_array());
        let (Some(a), Some(b)) = (a, b) else {
            return Err(format!("communities.{part}가 없다"));
        };
        println!("communities.{part}: 파이썬 {} · Rust {}", a.len(), b.len());
        for (i, (x, y)) in a.iter().zip(b).enumerate() {
            if x != y {
                diffs.push(format!(
                    "communities.{part}[{i}]\n  파이썬 {x}\n  Rust   {y}"
                ));
            }
        }
        if a.len() != b.len() {
            diffs.push(format!("communities.{part} 수가 다르다"));
        }
    }
    // 대조·층 — 같은 재료(MS 항목·클래스 명세 본문)로
    let graph = syncdoc_codegraph::enrich(&src, syncdoc_codegraph::reduce(&py["raw"]));
    let items: Vec<(String, String)> =
        serde_json::from_value(py["items"].clone()).map_err(|e| e.to_string())?;
    let impl_of: std::collections::HashMap<String, String> =
        serde_json::from_value(py["impl_of"].clone()).map_err(|e| e.to_string())?;
    let spec = syncdoc_codegraph::spec_calls(&items, Some(&impl_of));
    let compared: Vec<Value> = syncdoc_codegraph::compare(&graph, &spec)
        .into_iter()
        .map(|d| {
            serde_json::json!({"ms_id": d.ms_id, "function": d.function, "same": d.same,
            "code_only": d.code_only, "spec_only": d.spec_only})
        })
        .collect();
    let bodies: Vec<String> =
        serde_json::from_value(py["bodies"].clone()).map_err(|e| e.to_string())?;
    let rows: Vec<syncdoc_codegraph::LayerRow> = bodies
        .iter()
        .flat_map(|b| syncdoc_codegraph::layer_table(b))
        .collect();
    let (layer_of, unmatched) = syncdoc_codegraph::layers(&graph, &rows);
    let layer_of: std::collections::BTreeMap<_, _> = layer_of.into_iter().collect();
    let item_ids: std::collections::BTreeSet<String> = graph
        .functions
        .iter()
        .filter_map(|f| f.item.clone())
        .filter(|i| !i.is_empty())
        .collect();
    let item_function: serde_json::Map<String, Value> = item_ids
        .iter()
        .map(|i| {
            (
                i.clone(),
                serde_json::json!(
                    syncdoc_codegraph::item_function(&graph, i).map(|f| f.key.clone())
                ),
            )
        })
        .collect();
    let item_neighbors: serde_json::Map<String, Value> = graph
        .functions
        .iter()
        .map(|f| {
            let (a, b) = syncdoc_codegraph::item_neighbors(&graph, &f.key);
            (f.key.clone(), serde_json::json!([a, b]))
        })
        .collect();
    let spec_json: serde_json::Map<String, Value> = spec
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::json!(v)))
        .collect();
    let checks: [(&str, Value); 7] = [
        ("spec", Value::Object(spec_json)),
        ("diffs", Value::Array(compared)),
        (
            "rows",
            serde_json::to_value(&rows).map_err(|e| e.to_string())?,
        ),
        (
            "layers",
            serde_json::to_value(&layer_of).map_err(|e| e.to_string())?,
        ),
        (
            "unmatched",
            serde_json::to_value(&unmatched).map_err(|e| e.to_string())?,
        ),
        ("item_function", Value::Object(item_function)),
        ("item_neighbors", Value::Object(item_neighbors)),
    ];
    for (name, got) in checks {
        if got != py[name] {
            diffs.push(format!("{name}가 다르다"));
            if let (Some(a), Some(b)) = (py[name].as_object(), got.as_object()) {
                for (k, v) in a {
                    if b.get(k) != Some(v) {
                        diffs.push(format!(
                            "  {name}[{k}]\n    파이썬 {v}\n    Rust   {:?}",
                            b.get(k)
                        ));
                        break;
                    }
                }
            } else if let (Some(a), Some(b)) = (py[name].as_array(), got.as_array()) {
                if let Some((i, (x, y))) = a.iter().zip(b).enumerate().find(|(_, (x, y))| x != y) {
                    diffs.push(format!("  {name}[{i}]\n    파이썬 {x}\n    Rust   {y}"));
                }
                if a.len() != b.len() {
                    diffs.push(format!(
                        "  {name} 수 — 파이썬 {} · Rust {}",
                        a.len(),
                        b.len()
                    ));
                }
            }
        } else {
            println!("{name}: 같다");
        }
    }
    // 흐름 — 같은 보강 결과에 흐름 키를 더한다(카드 L22~L24)
    let mut flowed = serde_json::to_value(&graph).map_err(|e| e.to_string())?;
    syncdoc_codegraph::flow::extend(&src, &mut flowed);
    for part in ["files", "units", "functions", "http", "infra"] {
        let (a, b) = (&py["flow"][part], &flowed[part]);
        if a == b {
            println!("flow.{part}: 같다");
            continue;
        }
        diffs.push(format!("flow.{part}가 다르다"));
        match (a.as_array(), b.as_array()) {
            (Some(a), Some(b)) => {
                if let Some((i, (x, y))) = a.iter().zip(b).enumerate().find(|(_, (x, y))| x != y) {
                    diffs.push(format!(
                        "  flow.{part}[{i}]\n    파이썬 {x}\n    Rust   {y}"
                    ));
                }
                if a.len() != b.len() {
                    diffs.push(format!(
                        "  flow.{part} 수 — 파이썬 {} · Rust {}",
                        a.len(),
                        b.len()
                    ));
                }
            }
            _ => diffs.push(format!("  파이썬 {a}\n  Rust   {b}")),
        }
    }
    if diffs.is_empty() {
        println!("코드 그래프가 파이썬 판과 같다");
        return Ok(());
    }
    for d in diffs.iter().take(10) {
        println!("{d}");
    }
    Err(format!("{}곳이 다르다", diffs.len()))
}

/// 파이썬처럼 함수마다 `community` 열쇠를 둔다(없으면 null)
pub fn null_community(graph: &mut Value) {
    if let Some(fs) = graph.get_mut("functions").and_then(Value::as_array_mut) {
        for f in fs {
            if let Some(o) = f.as_object_mut() {
                o.entry("community").or_insert(Value::Null);
            }
        }
    }
}
