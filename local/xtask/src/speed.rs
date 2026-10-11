//! 두 판 속도 — `contract/speed.py`를 돌린다 (SYNC-PRD-001 R15 「빠르다」 · SYNC-INFRA-001 9.8, 카드 L17).
//! 같은 PC에서 Rust 판(release)과 파이썬 판(작업 트리 이미지)을 나란히 띄워 켜기·가져오기·코드 그래프·조회·저장·메모리를 잰다.
//! 표를 찍고 `target/speed.json`에 남긴다. 목표에 못 미치거나 파이썬 판보다 느린 항목이 있으면 실패다.

use std::process::Command;

use crate::{local_root, repo_root};

pub fn run(rounds: usize) -> Result<(), String> {
    let contract = repo_root().join("contract");
    let status = Command::new("uv")
        .args(["run", "--quiet", "--project"])
        .arg(&contract)
        .arg("python")
        .arg(contract.join("speed.py"))
        .args(["--rounds", &rounds.to_string(), "--out"])
        .arg(local_root().join("target").join("speed.json"))
        .current_dir(&contract)
        .status()
        .map_err(|e| format!("uv를 못 돌렸다 — {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err("속도 판정이 통과하지 못했다".into())
    }
}
