//! SYNC-MS-022 테스트 관점 — touches_code · load · extract (나머지는 정답 파일과 `cargo xtask codegraph-diff`가 본다)

use std::path::PathBuf;

use syncdoc_codegraph::{enrich, extract, load, reduce, touches_code};

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
