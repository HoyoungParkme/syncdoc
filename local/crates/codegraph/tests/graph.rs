//! SYNC-MS-022 테스트 관점 — touches_code · load · extract · widen (나머지는 정답 파일과 `cargo xtask codegraph-diff`가 본다)

use std::path::PathBuf;

use std::collections::HashSet;

use serde_json::Value;
use syncdoc_codegraph::{communities, enrich, extract, load, reduce, touches_code, widen};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture")
}

#[test]
fn touches_code_skips_specs_and_graphify_out() {
    let t = |ps: &[&str]| touches_code(&ps.iter().map(|s| s.to_string()).collect::<Vec<_>>());
    assert!(!t(&["docs/specs/02-PRD/X.md"]));
    assert!(t(&["a.py"]));
    assert!(!t(&["docs/specs/assets/x.js"]));
    assert!(!t(&["graphify-out/graph.json"]));
    assert!(!t(&["a/graphify-out/x.py"]));
    assert!(t(&["src/X.RS"]));
    assert!(!t(&["README.md", "Makefile"]));
    assert!(t(&["README.md", "web/app.tsx"]));
}

#[test]
fn load_prefers_committed_graph_json() {
    let tmp = tempfile::tempdir().expect("임시");
    std::fs::write(tmp.path().join("a.py"), "def f():\n    return 1\n").expect("코드");
    let (source, raw) = load(tmp.path()).expect("추출");
    assert_eq!(source, "server");
    assert!(raw["nodes"].as_array().is_some_and(|n| n.len() == 2));
    std::fs::create_dir_all(tmp.path().join("graphify-out")).expect("폴더");
    std::fs::write(
        tmp.path().join("graphify-out/graph.json"),
        r#"{"nodes": [], "links": []}"#,
    )
    .expect("그래프");
    let (source, raw) = load(tmp.path()).expect("저장소 것");
    assert_eq!(
        (source.as_str(), raw["nodes"].as_array().map(Vec::len)),
        ("repo", Some(0))
    );
    std::fs::write(tmp.path().join("graphify-out/graph.json"), "{깨짐").expect("깨진 그래프");
    assert_eq!(load(tmp.path()).expect_err("형식").0, "graph.json 형식");
    assert_eq!(
        extract(&tmp.path().join("없음")).expect_err("폴더").0,
        "폴더 없음: 없음"
    );
}

#[test]
fn extract_python_defs_same_file_calls_and_file_nodes() {
    let tmp = tempfile::tempdir().expect("임시");
    let p = tmp.path();
    for (path, text) in [
        (
            "app/svc.py",
            "import functools\n\n\nclass Repo:\n    def get(self):\n        return helper()\n\n\n@functools.cache\ndef helper():\n    return other()\n\n\ndef other():\n    return 1\n",
        ),
        ("app/broken.py", "def f(:\n"),
        ("web/a.ts", "export function a() {}\n"),
        ("lib/x.rs", "fn x() {}\n"),
        ("node_modules/m/index.js", "function m() {}\n"),
        ("README.md", "# 글\n"),
    ] {
        let f = p.join(path);
        std::fs::create_dir_all(f.parent().expect("부모")).expect("폴더");
        std::fs::write(f, text).expect("파일");
    }
    let raw = extract(p).expect("추출");
    let files: Vec<&str> = raw["nodes"]
        .as_array()
        .expect("노드")
        .iter()
        .filter(|n| n.get("_callable").is_none())
        .map(|n| n["id"].as_str().expect("id"))
        .collect();
    assert_eq!(
        files,
        ["app/broken.py", "app/svc.py", "lib/x.rs", "web/a.ts"]
    );
    let g = enrich(p, reduce(&raw));
    let quals: Vec<(&str, i64, Option<i64>)> = g
        .functions
        .iter()
        .map(|f| (f.qual.as_str(), f.line, f.end))
        .collect();
    assert_eq!(
        quals,
        [
            ("Repo.get", 5, Some(6)),
            ("svc.helper", 10, Some(11)), // 데코레이터 줄이 아니라 def 줄
            ("svc.other", 14, Some(15)),
            ("a.a", 1, Some(1)),
            ("x.x", 1, Some(1)),
        ]
    );
    let calls: Vec<(&str, &str, &str)> = g
        .calls
        .iter()
        .map(|c| (c.0.as_str(), c.1.as_str(), c.2.as_str()))
        .collect();
    assert_eq!(
        calls,
        [
            ("app/svc.py:5", "app/svc.py:10", "graphify"),
            ("app/svc.py:10", "app/svc.py:14", "graphify"),
        ]
    );
}

#[test]
fn fixture_extract_reduces_and_enriches_without_files() {
    let g = enrich(&fixture(), reduce(&extract(&fixture()).expect("추출")));
    assert!(g.files.is_empty());
    assert!(g.functions.iter().any(|f| f.qual == "ThingService.create"
        && f.ms.as_deref() == Some("FX-MS-001#ThingService.create")));
    assert!(!g.functions.iter().any(|f| f.file.contains("tests/")));
}

/// 추출 원형만으로 묶으면 TS·Rust 함수가 커뮤니티 없이 남는다 → 넓히면 함수가 다 커뮤니티를 받는다 (카드 L20)
#[test]
fn widen_gives_ts_and_rust_functions_communities() {
    let raw = extract(&fixture()).expect("추출");
    let g = enrich(&fixture(), reduce(&raw));
    let other = |f: &&syncdoc_codegraph::Function| !f.file.ends_with(".py");
    assert!(g.functions.iter().filter(other).count() > 5);
    let before = communities(&raw, g.clone());
    assert!(
        before
            .functions
            .iter()
            .filter(other)
            .all(|f| f.community.is_none())
    );
    let after = communities(&widen(&raw, &g), g.clone());
    assert!(after.functions.iter().all(|f| f.community.is_some()));
    let sizes: i64 = after
        .communities
        .as_ref()
        .expect("목록")
        .iter()
        .map(|c| c.size)
        .sum();
    assert_eq!(sizes, after.functions.len() as i64);
}

/// 넓힌 원형의 모양 — 원래 것 뒤에 더하고, 파이썬 노드는 다시 안 더하고, contains·calls, 같은 쌍은 하나
#[test]
fn widen_appends_function_nodes_contains_and_calls() {
    let raw = extract(&fixture()).expect("추출");
    let g = enrich(&fixture(), reduce(&raw));
    let wide = widen(&raw, &g);
    let arr = |v: &Value, k: &str| v[k].as_array().expect(k).clone();
    let (nodes, links) = (arr(&wide, "nodes"), arr(&wide, "links"));
    let (raw_nodes, raw_links) = (arr(&raw, "nodes"), arr(&raw, "links"));
    assert_eq!(nodes[..raw_nodes.len()], raw_nodes[..]);
    assert_eq!(links[..raw_links.len()], raw_links[..]);
    // 함수 key마다 노드가 꼭 하나
    let ids: Vec<&str> = nodes
        .iter()
        .map(|n| n["id"].as_str().expect("id"))
        .collect();
    for f in &g.functions {
        assert_eq!(ids.iter().filter(|i| **i == f.key).count(), 1, "{}", f.key);
    }
    // 더한 노드는 graphify 함수 노드 꼴
    let rs = g
        .functions
        .iter()
        .find(|f| f.file.ends_with(".rs"))
        .expect("Rust 함수");
    let node = nodes
        .iter()
        .find(|n| n["id"] == rs.key.as_str())
        .expect("노드");
    assert_eq!(node["source_file"], rs.file.as_str());
    assert_eq!(node["source_location"], format!("L{}", rs.line).as_str());
    assert_eq!(node["_callable"], true);
    let has = |s: &str, t: &str, rel: &str| {
        links
            .iter()
            .any(|e| e["source"] == s && e["target"] == t && e["relation"] == rel)
    };
    assert!(has(&rs.file, &rs.key, "contains"));
    // 보강이 이은 다른 파일 호출이 calls 선으로
    let cross = g
        .calls
        .iter()
        .find(|c| c.0.split(':').next() != c.1.split(':').next())
        .expect("다른 파일 호출");
    assert!(links.iter().any(|e| e["relation"] == "calls"
        && ((e["source"] == cross.0.as_str() && e["target"] == cross.1.as_str())
            || (e["source"] == cross.1.as_str() && e["target"] == cross.0.as_str()))));
    // 같은 쌍(무향)은 하나
    let mut seen = HashSet::new();
    for e in &links {
        let (a, b) = (
            e["source"].as_str().expect("s"),
            e["target"].as_str().expect("t"),
        );
        assert!(
            seen.insert(if a <= b { (a, b) } else { (b, a) }),
            "{a} — {b}"
        );
    }
}
