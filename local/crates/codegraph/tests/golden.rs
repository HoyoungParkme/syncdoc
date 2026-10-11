//! SYNC-MS-022 테스트 관점 — 파이썬 판이 같은 원형·같은 파일로 낸 줄이기·보강·커뮤니티 결과와 바이트로 같다.
//! 정답은 `cargo xtask codegraph-golden`이 고정 시험 저장소(`tests/fixture`)에서 만든다.

use std::path::PathBuf;

use serde_json::Value;
use syncdoc_codegraph::{communities, enrich, reduce};

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn golden() -> Value {
    let text = std::fs::read_to_string(here().join("golden/codegraph.json")).expect("정답 파일");
    serde_json::from_str(&text).expect("정답 JSON")
}

/// 줄마다 비교해 처음 다른 곳을 보인다
fn same(label: &str, got: &Value, want: &Value) {
    if got == want {
        return;
    }
    let (g, w) = (got.as_array(), want.as_array());
    if let (Some(g), Some(w)) = (g, w) {
        for (i, (a, b)) in g.iter().zip(w).enumerate() {
            assert_eq!(a, b, "{label}[{i}]");
        }
        assert_eq!(g.len(), w.len(), "{label} 수");
    }
    assert_eq!(got, want, "{label}");
}

#[test]
fn reduce_matches_python() {
    let g = golden();
    let got = serde_json::to_value(reduce(&g["raw"])).expect("직렬화");
    same(
        "reduced.functions",
        &got["functions"],
        &g["reduced"]["functions"],
    );
    same("reduced.calls", &got["calls"], &g["reduced"]["calls"]);
    same("reduced.files", &got["files"], &g["reduced"]["files"]);
}

#[test]
fn enrich_matches_python() {
    let g = golden();
    let got = enrich(&here().join("fixture"), reduce(&g["raw"]));
    let got = serde_json::to_value(&got).expect("직렬화");
    same(
        "enriched.functions",
        &got["functions"],
        &g["enriched"]["functions"],
    );
    same("enriched.calls", &got["calls"], &g["enriched"]["calls"]);
    assert!(got.get("files").is_none(), "보강 뒤에는 files가 없다");
}

#[test]
fn communities_match_python() {
    let g = golden();
    let got = communities(
        &g["raw"],
        enrich(&here().join("fixture"), reduce(&g["raw"])),
    );
    let mut got = serde_json::to_value(&got).expect("직렬화");
    // 파이썬은 커뮤니티 없는 함수에도 `community: null`을 둔다
    for f in got["functions"].as_array_mut().expect("함수") {
        f.as_object_mut()
            .expect("객체")
            .entry("community")
            .or_insert(Value::Null);
    }
    same(
        "communities.functions",
        &got["functions"],
        &g["communities"]["functions"],
    );
    same(
        "communities.communities",
        &got["communities"],
        &g["communities"]["communities"],
    );
}
