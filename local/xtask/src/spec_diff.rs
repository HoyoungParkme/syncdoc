//! 명세 엔진 차이 시험 — 두 판에 같은 본문을 돌려 바이트로 비교한다 (SYNC-MS-014 0장 · SYNC-CODE-002 2장, 카드 L5).
//! 파이썬 쪽(`xtask/py/spec_cases.py`)이 지금의 명세·템플릿, git 이력 diff, 씨앗 고정 무작위 사례를 만들어 답을 붙이고
//! Rust가 같은 입력으로 답을 만든다. 답을 만드는 Rust 쪽은 `cargo test`의 정답 비교와 같은 코드다. 커밋하지 않는다.

use std::fs;
use std::io::{BufRead, BufReader};

use serde_json::Value;

use crate::python;

#[path = "../../crates/core/tests/support/spec_answers.rs"]
mod spec_answers;

pub fn run(seed: u64, count: usize) -> Result<(), String> {
    let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
    let out = tmp.path().join("cases.jsonl");
    let (seed_s, count_s) = (seed.to_string(), count.to_string());
    python(
        "spec_cases.py",
        &[
            "--seed".as_ref(),
            seed_s.as_ref(),
            "--count".as_ref(),
            count_s.as_ref(),
            out.as_os_str(),
        ],
    )?;
    let file = fs::File::open(&out).map_err(|e| e.to_string())?;
    let (mut seen, mut kinds) = (0usize, std::collections::BTreeMap::<String, usize>::new());
    let mut bad = Vec::new();
    for line in BufReader::new(file).lines() {
        let line = line.map_err(|e| e.to_string())?;
        let py: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
        let rs = spec_answers::answer(&spec_answers::input_of(&py));
        seen += 1;
        *kinds
            .entry(py["kind"].as_str().unwrap_or("?").to_string())
            .or_default() += 1;
        if let Some(d) = spec_answers::first_difference("", &py, &rs) {
            bad.push(format!("{} — {d}", py["name"]));
        }
    }
    let kinds: Vec<String> = kinds.iter().map(|(k, n)| format!("{k} {n}")).collect();
    println!(
        "명세 엔진 차이 시험 — 씨앗 {seed} · 사례 {seen}({}) · 다른 것 {}",
        kinds.join(" · "),
        bad.len()
    );
    if bad.is_empty() {
        return Ok(());
    }
    for b in bad.iter().take(10) {
        println!("  {b}");
    }
    Err(format!("파이썬 판과 다른 사례 {}", bad.len()))
}
