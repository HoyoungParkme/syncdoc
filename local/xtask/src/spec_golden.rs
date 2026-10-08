//! 명세 엔진의 정답 파일 — 파이썬 판으로 만든다 (SYNC-STD-004#DEV-7 · SYNC-MS-014 0장, 카드 L5).
//! 손으로 만든 꼴 모음을 입력째 얼려 `crates/core/tests/golden/spec.json`에 담는다 — `cargo test`가 비교한다.
//! 파이썬이 원본이다 — 이 파일을 손으로 고치지 않는다. 스크립트는 `xtask/py/spec_golden.py`.

use std::fs;
use std::path::{Path, PathBuf};

use crate::{local_root, python};

fn dest() -> PathBuf {
    local_root()
        .join("crates")
        .join("core")
        .join("tests")
        .join("golden")
        .join("spec.json")
}

pub fn run(check: bool) -> Result<(), String> {
    let dest = dest();
    if check {
        let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
        let fresh = tmp.path().join("spec.json");
        generate(&fresh)?;
        if fs::read(&fresh).ok() == fs::read(&dest).ok() {
            println!("명세 엔진 정답 파일이 파이썬 판과 같다");
            return Ok(());
        }
        return Err(
            "명세 엔진 정답 파일이 파이썬 판과 다르다 — cargo xtask spec-golden으로 다시 만든다"
                .to_string(),
        );
    }
    generate(&dest)?;
    println!("명세 엔진 정답 파일을 만들었다 — {}", dest.display());
    Ok(())
}

fn generate(to: &Path) -> Result<(), String> {
    if let Some(p) = to.parent() {
        fs::create_dir_all(p).map_err(|e| e.to_string())?;
    }
    python("spec_golden.py", &[to.as_os_str()]).map(|_| ())
}
