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

mod icon;
mod mcp_tools;
mod migrations;
mod package;
mod pg_fetch;
mod schema;
mod testdb;

use std::path::PathBuf;
use std::process::ExitCode;

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
