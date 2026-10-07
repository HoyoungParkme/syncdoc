//! syncdoc-local 진입 — 인자를 읽어 켜고 끝 코드를 돌려준다 (SYNC-MS-012#runtime.run).
//! 켜는 중 실패는 사람이 읽는 문장으로 표준 오류에 남기고 끝 코드 1.

use std::process::ExitCode;

use clap::Parser;
use syncdoc_app::runtime::{Args, run};

#[tokio::main]
async fn main() -> ExitCode {
    match run(Args::parse()).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(p) => {
            tracing::error!("{p}");
            eprintln!("싱크독_로컬을 켜지 못했다 — {p}");
            ExitCode::FAILURE
        }
    }
}
