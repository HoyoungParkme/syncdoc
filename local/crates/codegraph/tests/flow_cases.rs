//! SYNC-MS-026 테스트 관점 — 파이썬 판 흐름 시험의 입력을 Rust 판에 돌려 같은 답인지 (카드 L22~L24).
//! 사례와 답은 `cargo xtask codegraph-golden`이 `xtask/py/flow_cases.py`로 얼린다(정답 파일의 `flow_cases`).

use std::path::{Path, PathBuf};

use serde_json::Value;
use syncdoc_codegraph::flow::{self, infra, routes, steps};

fn golden() -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/golden/codegraph.json");
    serde_json::from_str(&std::fs::read_to_string(path).expect("정답 파일")).expect("정답 JSON")
}

fn write(root: &Path, files: &Value) {
    for (rel, body) in files.as_object().expect("파일") {
        let p = root.join(rel);
        std::fs::create_dir_all(p.parent().expect("폴더")).expect("폴더");
        let bytes = match body {
            Value::String(s) => s.as_bytes().to_vec(),
            other => {
                let hex = other["hex"].as_str().expect("hex");
                (0..hex.len())
                    .step_by(2)
                    .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).expect("hex"))
                    .collect()
            }
        };
        std::fs::write(p, bytes).expect("쓰기");
    }
}

fn run(case: &Value) -> Value {
    let tmp = tempfile::tempdir().expect("임시");
    let root = tmp.path();
    write(root, &case["files"]);
    let mut g = case["graph"].clone();
    match case["op"].as_str().expect("op") {
        "files" => Value::Array(flow::files(root)),
        "steps" => {
            steps::steps(root, &mut g);
            g
        }
        "extend" => {
            flow::extend(root, &mut g);
            g
        }
        "routes" => {
            routes::routes(root, &mut g);
            g
        }
        "http" => Value::Array(routes::http_links(root, &g)),
        "units" => Value::Array(infra::units(root)),
        _ => {
            let idents = steps::steps(root, &mut g);
            infra::infra(root, &mut g, &idents);
            g
        }
    }
}

#[test]
fn flow_cases_match_python() {
    let g = golden();
    let cases = g["flow_cases"].as_array().expect("사례");
    assert!(cases.len() >= 20);
    let mut bad = Vec::new();
    for c in cases {
        let got = run(c);
        if got != c["out"] {
            bad.push(format!(
                "{}\n  파이썬 {}\n  Rust   {}",
                c["name"], c["out"], got
            ));
        }
    }
    assert!(bad.is_empty(), "{}", bad.join("\n"));
}
