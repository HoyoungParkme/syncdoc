//! 개발·시험용 PostgreSQL 바이너리 — theseus-rs/postgresql-binaries 16.15.0 (SYNC-INFRA-001 9.2).
//! 설치판은 설치 파일이 담는다(카드 L4). 받는 것은 개발 때 한 번이고, 실행 중에는 아무것도 받지 않는다(C10).

use std::fs;
use std::process::Command;

use sha2::{Digest, Sha256};

use crate::local_root;

pub const VERSION: &str = "16.15.0";
const TARGET: &str = "x86_64-unknown-linux-gnu";

pub fn run() -> Result<(), String> {
    let root = local_root().join("target").join("pg");
    let dest = root.join(VERSION);
    if dest.join("bin").join("postgres").is_file() {
        println!("이미 있다 — {}", dest.display());
        return Ok(());
    }
    let name = format!("postgresql-{VERSION}-{TARGET}.tar.gz");
    let url = format!(
        "https://github.com/theseus-rs/postgresql-binaries/releases/download/{VERSION}/{name}"
    );
    let dl = root.join("dl");
    fs::create_dir_all(&dl).map_err(|e| e.to_string())?;
    let archive = dl.join(&name);
    let sums = dl.join(format!("{name}.sha256"));
    curl(&url, &archive)?;
    curl(&format!("{url}.sha256"), &sums)?;
    let want = fs::read_to_string(&sums).map_err(|e| e.to_string())?;
    let want = want.split_whitespace().next().unwrap_or("").to_lowercase();
    let got: String = Sha256::digest(fs::read(&archive).map_err(|e| e.to_string())?)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    if got != want {
        return Err(format!("sha256이 다르다 — {name}"));
    }
    fs::create_dir_all(&dest).map_err(|e| e.to_string())?;
    let ok = Command::new("tar")
        .arg("-xzf")
        .arg(&archive)
        .arg("-C")
        .arg(&dest)
        .arg("--strip-components=1")
        .status()
        .map_err(|e| e.to_string())?
        .success();
    if !ok {
        return Err("tar로 풀지 못했다".into());
    }
    let ldd = Command::new("ldd")
        .arg(dest.join("bin").join("postgres"))
        .output();
    if let Ok(out) = ldd {
        let text = String::from_utf8_lossy(&out.stdout);
        let missing: Vec<&str> = text.lines().filter(|l| l.contains("not found")).collect();
        if !missing.is_empty() {
            println!(
                "빠진 시스템 라이브러리 — apt로 깐다:\n{}",
                missing.join("\n")
            );
        }
    }
    println!("받았다 — {}", dest.display());
    Ok(())
}

fn curl(url: &str, to: &std::path::Path) -> Result<(), String> {
    let ok = Command::new("curl")
        .args(["-fsSL", "--retry", "3", "-o"])
        .arg(to)
        .arg(url)
        .status()
        .map_err(|e| e.to_string())?
        .success();
    if ok {
        Ok(())
    } else {
        Err(format!("받지 못했다 — {url}"))
    }
}
