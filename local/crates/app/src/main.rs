//! syncdoc-local 진입 — 인자를 읽어 켜고 끝 코드를 돌려준다 (SYNC-MS-012#runtime.run).
//! 켜는 중 실패는 사람이 읽는 문장으로 표준 오류에 남기고 끝 코드 1.
//!
//! 일꾼 스레드의 스택을 크게 잡는다 — 파이썬 판은 JSON을 1만 겹 가까이 읽고 검증한다(C 재귀 한도).
//! 같은 입력을 받으려면 읽기·검증·repr·해제가 그만큼 재귀한다 (SYNC-DOM-004 1장 compat, 카드 L3).

use std::process::ExitCode;

use clap::Parser;
use syncdoc_app::runtime::{Args, run};

/// 일꾼 스레드 스택 — 예약일 뿐 쓴 만큼만 잡힌다
const WORKER_STACK: usize = 256 * 1024 * 1024;

fn main() -> ExitCode {
    let rt = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_stack_size(WORKER_STACK)
        .build()
    {
        Ok(rt) => rt,
        Err(e) => {
            eprintln!("싱크독_로컬을 켜지 못했다 — tokio: {e}");
            return ExitCode::FAILURE;
        }
    };
    match rt.block_on(run(Args::parse())) {
        Ok(()) => ExitCode::SUCCESS,
        Err(p) => {
            tracing::error!("{p}");
            eprintln!("싱크독_로컬을 켜지 못했다 — {p}");
            ExitCode::FAILURE
        }
    }
}
