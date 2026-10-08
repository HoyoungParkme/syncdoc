//! PostgreSQL 바이너리 — theseus-rs/postgresql-binaries 16.15.0 (SYNC-INFRA-001 9.2).
//! 개발·시험용은 `target/pg/16.15.0`(리눅스). 설치 파일 재료는 `package`가 대상마다 받아 담는다(카드 L4).
//! 받는 것은 개발·빌드 때뿐이고, 실행 중에는 아무것도 받지 않는다(C10).

use std::fs;
use std::process::Command;

use sha2::{Digest, Sha256};

use crate::local_root;

pub const VERSION: &str = "16.15.0";
pub const LINUX: &str = "x86_64-unknown-linux-gnu";
pub const WINDOWS: &str = "x86_64-pc-windows-msvc";

/// 받은 압축 파일의 sha256 — GitHub 릴리즈의 digest로 고정한다(옆에 딸린 .sha256 파일은 대상마다 꼴이 다르다)
fn sha256_of(target: &str) -> Result<&'static str, String> {
    match target {
        LINUX => Ok("77dd669eda3985ea8be26256f6af28d3c8414152ada713797555bb7423b4486a"),
        WINDOWS => Ok("157bd7322f8c653f06b0373d1b2280e9cb238b6a6d3bd05541aeb8f33885a8ad"),
        other => Err(format!("해시를 모르는 대상 {other}")),
    }
}

/// `cargo xtask pg-fetch [--target T]` — 리눅스(기본)는 개발용 자리, 다른 대상은 `target/pg/{대상}/16.15.0`
pub fn run(target: Option<String>) -> Result<(), String> {
    let target = target.unwrap_or_else(|| LINUX.to_string());
    let root = local_root().join("target").join("pg");
    let dest = if target == LINUX {
        root.join(VERSION)
    } else {
        root.join(&target).join(VERSION)
    };
    fetch(&target, &dest)
}

/// 대상의 바이너리를 `dest`에 푼다 — 해시를 보고, 이미 있으면 그대로
pub fn fetch(target: &str, dest: &std::path::Path) -> Result<(), String> {
    let root = local_root().join("target").join("pg");
    let postgres = if target.contains("windows") {
        "postgres.exe"
    } else {
        "postgres"
    };
    if dest.join("bin").join(postgres).is_file() {
        println!("이미 있다 — {}", dest.display());
        return Ok(());
    }
    let name = format!("postgresql-{VERSION}-{target}.tar.gz");
    let url = format!(
        "https://github.com/theseus-rs/postgresql-binaries/releases/download/{VERSION}/{name}"
    );
    let dl = root.join("dl");
    fs::create_dir_all(&dl).map_err(|e| e.to_string())?;
    let archive = dl.join(&name);
    curl(&url, &archive)?;
    let want = sha256_of(target)?;
    let got: String = Sha256::digest(fs::read(&archive).map_err(|e| e.to_string())?)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    if got != want {
        return Err(format!("sha256이 다르다 — {name}"));
    }
    fs::create_dir_all(dest).map_err(|e| e.to_string())?;
    let ok = Command::new("tar")
        .arg("-xzf")
        .arg(&archive)
        .arg("-C")
        .arg(dest)
        .arg("--strip-components=1")
        .status()
        .map_err(|e| e.to_string())?
        .success();
    if !ok {
        return Err("tar로 풀지 못했다".into());
    }
    if target.contains("windows") {
        println!("받았다 — {}", dest.display());
        return Ok(());
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

pub fn curl(url: &str, to: &std::path::Path) -> Result<(), String> {
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
