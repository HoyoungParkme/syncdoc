//! MCP 선언 — 파이썬 판 MCP 서버(폐쇄망판 설정)에서 뽑는다 (SYNC-STD-004#DEV-7 · SYNC-DOM-004 1장 mcp/).
//! 도구 13개의 선언·안내문·고정 결과의 바이트와 pydantic core schema를 `declarations.json` 하나에 담는다.
//! 파이썬이 원본이다 — 이 파일을 손으로 고치지 않는다. 스크립트는 `xtask/py/export_mcp.py`.

use crate::{local_root, python};
use std::fs;
use std::path::{Path, PathBuf};

fn dest() -> PathBuf {
    local_root()
        .join("crates")
        .join("server")
        .join("src")
        .join("mcp")
        .join("declarations.json")
}

pub fn run(check: bool) -> Result<(), String> {
    let dest = dest();
    if check {
        let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
        let fresh = tmp.path().join("declarations.json");
        generate(&fresh)?;
        if fs::read(&fresh).ok() == fs::read(&dest).ok() {
            println!("MCP 선언이 파이썬 판과 같다");
            return Ok(());
        }
        return Err(
            "MCP 선언이 파이썬 판과 다르다 — cargo xtask mcp-tools로 다시 만든다".to_string(),
        );
    }
    generate(&dest)?;
    println!("MCP 선언을 만들었다 — {}", dest.display());
    Ok(())
}

/// `uv run --project backend python xtask/py/export_mcp.py OUT` — 작업 자리는 `local/`(`.env`가 없다)
fn generate(to: &Path) -> Result<(), String> {
    python("export_mcp.py", &[to.as_os_str()]).map(|_| ())
}
