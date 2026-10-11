//! 코드 그래프 정답 파일 — 파이썬 판으로 만든다 (SYNC-STD-004#DEV-7 · SYNC-MS-022 0장, 카드 L12).
//! 고정 시험 저장소의 graphify 원형과 파이썬 판의 줄이기·보강 결과를 `crates/codegraph/tests/golden/codegraph.json`에
//! 얼린다 — `cargo test`가 같은 원형·같은 파일로 비교한다. 스크립트는 `xtask/py/codegraph_golden.py`.

use std::fs;
use std::path::{Path, PathBuf};

use crate::{local_root, python};

fn crate_dir() -> PathBuf {
    local_root().join("crates").join("codegraph")
}

fn dest() -> PathBuf {
    crate_dir()
        .join("tests")
        .join("golden")
        .join("codegraph.json")
}

pub fn run(check: bool) -> Result<(), String> {
    let dest = dest();
    if check {
        let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
        let fresh = tmp.path().join("codegraph.json");
        generate(&fresh)?;
        if fs::read(&fresh).ok() == fs::read(&dest).ok() {
            println!("코드 그래프 정답 파일이 파이썬 판과 같다");
            return Ok(());
        }
        return Err(
            "코드 그래프 정답 파일이 파이썬 판과 다르다 — cargo xtask codegraph-golden으로 다시 만든다"
                .to_string(),
        );
    }
    generate(&dest)?;
    println!("코드 그래프 정답 파일을 만들었다 — {}", dest.display());
    Ok(())
}

fn generate(to: &Path) -> Result<(), String> {
    if let Some(p) = to.parent() {
        fs::create_dir_all(p).map_err(|e| e.to_string())?;
    }
    let fixture = crate_dir().join("tests").join("fixture");
    python(
        "codegraph_golden.py",
        &[fixture.as_os_str(), to.as_os_str()],
    )
    .map(|_| ())
}
