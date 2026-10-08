//! 싱크독_로컬 개발 도구 — `cargo xtask …` (SYNC-DOM-004 1장 · SYNC-STD-004#DEV-7·DEV-14).
//!
//! - `pg-fetch [--target T]` — PostgreSQL 16.15 바이너리를 받는다(리눅스 기본은 개발·시험용 `target/pg/16.15.0`)
//! - `package windows|linux` — 설치 파일을 만든다(카드 L4) — `cargo build --release -p syncdoc_app` 뒤에
//! - `migrations [--check]` — Alembic 리비전마다 `alembic upgrade --sql`로 `migrations/NNNN_*.sql`을 만든다.
//!   `--check`는 다시 만들어 바이트를 비교한다(손으로 고친 것·빠뜨린 리비전을 잡는다)
//! - `schema-check` — 시험 서버(5434)에 Alembic이 올린 DB와 Rust 판이 올린 DB를 만들어 스키마 덤프를 비교한다
//! - `test-db-clean` — 시험이 남긴 `syncdoc_local_test_*` DB를 지운다
//! - `icon` — `packaging/icon.svg`에서 icon.ico·icon.png·tray.rgba를 만든다(카드 L4)
//! - `mcp-tools [--check]` — 파이썬 판 MCP 서버에서 `crates/server/src/mcp/declarations.json`을 뽑는다(카드 L3)
//! - `unicode-tables [--check]` — 파이썬 3.12의 문자 분류 표 `crates/core/src/pycompat/unicode.rs`를 뽑는다(카드 L5)
//! - `spec-golden [--check]` — 명세 엔진의 정답 파일 `crates/core/tests/golden/spec.json`을 파이썬 판으로 만든다(카드 L5)
//! - `spec-diff [--seed S] [--count N]` — 지금의 명세·git 이력·무작위 본문을 두 판에 돌려 비교한다(카드 L5)

mod icon;
mod mcp_tools;
mod migrations;
mod package;
mod pg_fetch;
mod schema;
mod spec_diff;
mod spec_golden;
mod testdb;
mod unicode_tables;

use std::ffi::OsStr;
use std::path::PathBuf;
use std::process::{Command, ExitCode};

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "xtask", about = "싱크독_로컬 개발 도구")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// PostgreSQL 바이너리를 받는다
    PgFetch {
        /// 대상 — 기본 x86_64-unknown-linux-gnu(개발·시험용)
        #[arg(long)]
        target: Option<String>,
    },
    /// 설치 파일을 만든다 — windows: setup.exe(makensis) · linux: .deb·AppImage
    Package {
        #[arg(value_parser = ["windows", "linux"])]
        os: String,
    },
    /// 이전 SQL을 만든다 (--check: 다시 만들어 비교만)
    Migrations {
        #[arg(long)]
        check: bool,
    },
    /// 두 판의 스키마가 같은지
    SchemaCheck,
    /// 시험이 남긴 DB를 지운다
    TestDbClean,
    /// 아이콘 그림을 만든다
    Icon,
    /// MCP 선언을 파이썬 판에서 뽑는다 (--check: 다시 뽑아 비교만)
    McpTools {
        #[arg(long)]
        check: bool,
    },
    /// 파이썬 문자 분류 표를 뽑는다 (--check: 다시 뽑아 비교만)
    UnicodeTables {
        #[arg(long)]
        check: bool,
    },
    /// 명세 엔진의 정답 파일을 파이썬 판으로 만든다 (--check: 다시 만들어 비교만)
    SpecGolden {
        #[arg(long)]
        check: bool,
    },
    /// 명세 엔진 차이 시험 — 두 판에 같은 본문을 돌려 비교한다
    SpecDiff {
        #[arg(long, default_value_t = 20261008)]
        seed: u64,
        #[arg(long, default_value_t = 2000)]
        count: usize,
    },
}

#[tokio::main]
async fn main() -> ExitCode {
    let result = match Cli::parse().cmd {
        Cmd::PgFetch { target } => pg_fetch::run(target),
        Cmd::Package { os } => package::run(&os),
        Cmd::Migrations { check } => migrations::run(check),
        Cmd::SchemaCheck => schema::run().await,
        Cmd::TestDbClean => testdb::clean().await,
        Cmd::McpTools { check } => mcp_tools::run(check),
        Cmd::Icon => icon::run(),
        Cmd::UnicodeTables { check } => unicode_tables::run(check),
        Cmd::SpecGolden { check } => spec_golden::run(check),
        Cmd::SpecDiff { seed, count } => spec_diff::run(seed, count),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("xtask: {e}");
            ExitCode::FAILURE
        }
    }
}

/// `local/` — xtask의 Cargo.toml 한 단계 위
pub fn local_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("local/")
        .to_path_buf()
}

/// 저장소 뿌리 — `local/` 한 단계 위
pub fn repo_root() -> PathBuf {
    local_root().parent().expect("저장소 뿌리").to_path_buf()
}

/// `uv run --project backend python xtask/py/{script} 인자…` → 표준 출력.
/// 작업 자리는 `local/`이다 — `.env`가 없어 파이썬 판 설정이 운영 값을 읽지 않는다
pub fn python(script: &str, args: &[&OsStr]) -> Result<Vec<u8>, String> {
    let out = Command::new("uv")
        .args(["run", "--quiet", "--project"])
        .arg(repo_root().join("backend"))
        .arg("python")
        .arg(local_root().join("xtask").join("py").join(script))
        .args(args)
        .current_dir(local_root())
        .output()
        .map_err(|e| format!("uv를 못 돌렸다 — {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "{script} 실패 — {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(out.stdout)
}
