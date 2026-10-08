//! 파이썬 문자 분류 표 — 파이썬 3.12에서 뽑는다 (SYNC-STD-004#DEV-7 · SYNC-DOM-004 1장 pycompat, 카드 L5).
//! `re`의 `\s`·`\d`·`\w`와 `str.isprintable()`을 `crates/core/src/pycompat/unicode.rs` 하나에 담는다.
//! 파이썬이 원본이다 — 이 파일을 손으로 고치지 않는다. 스크립트는 `xtask/py/export_unicode.py`.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::{local_root, python};

fn dest() -> PathBuf {
    local_root()
        .join("crates")
        .join("core")
        .join("src")
        .join("pycompat")
        .join("unicode.rs")
}

pub fn run(check: bool) -> Result<(), String> {
    let dest = dest();
    if check {
        let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
        let fresh = tmp.path().join("unicode.rs");
        generate(&fresh)?;
        if fs::read(&fresh).ok() == fs::read(&dest).ok() {
            println!("문자 분류 표가 파이썬 판과 같다");
            return Ok(());
        }
        return Err(
            "문자 분류 표가 파이썬 판과 다르다 — cargo xtask unicode-tables로 다시 만든다"
                .to_string(),
        );
    }
    generate(&dest)?;
    println!("문자 분류 표를 만들었다 — {}", dest.display());
    Ok(())
}

/// 파이썬이 쓴 소스를 rustfmt로 다듬는다 — `cargo fmt --check`와 같은 꼴
fn generate(to: &Path) -> Result<(), String> {
    python("export_unicode.py", &[to.as_os_str()])?;
    let out = Command::new("rustfmt")
        .args(["--edition", "2024"])
        .arg(to)
        .output()
        .map_err(|e| format!("rustfmt를 못 돌렸다 — {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "rustfmt 실패 — {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(())
}
