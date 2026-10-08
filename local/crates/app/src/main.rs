//! syncdoc-local 진입 — 인자를 읽어 켜고 끝 코드를 돌려준다 (SYNC-MS-012#runtime.run).
//! 켜는 중 실패는 사람이 읽는 문장으로 표준 오류에 남기고 끝 코드 1.
//!
//! 윈도에서 관리자 권한으로 켜졌으면 맨 처음 그 권한을 내려놓고 자신을 다시 켠다 — PostgreSQL이 관리자 권한을 거부한다
//! (SYNC-MS-012#privilege.drop_admin). tokio를 만들기 전이어야 한다(환경 변수를 바꾼다).
//!
//! 트레이가 있으면 메인 스레드는 트레이 차지다(윈도 메시지 루프) — 서버는 tokio 일꾼에서 돈다(SYNC-MS-012#tray.run).
//! 릴리즈 빌드의 윈도 실행 파일은 콘솔 창 없이 뜬다 — 기록은 데이터 자리의 `logs/`.
//!
//! 일꾼 스레드의 스택을 크게 잡는다 — 파이썬 판은 JSON을 1만 겹 가까이 읽고 검증한다(C 재귀 한도).
//! 같은 입력을 받으려면 읽기·검증·repr·해제가 그만큼 재귀한다 (SYNC-DOM-004 1장 compat, 카드 L3).

#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

use std::process::ExitCode;

use clap::Parser;
use syncdoc_app::runtime::{Args, run};
use syncdoc_app::{privilege, tray};

/// 일꾼 스레드 스택 — 예약일 뿐 쓴 만큼만 잡힌다
const WORKER_STACK: usize = 256 * 1024 * 1024;

fn main() -> ExitCode {
    if let Some(code) = privilege::drop_admin() {
        // 다시 켠 자식의 끝 코드 그대로 — 윈도 끝 코드는 32비트라 ExitCode(8비트)로 줄이지 않는다
        std::process::exit(code as i32);
    }
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
    let args = Args::parse();
    let result = if args.no_tray {
        rt.block_on(run(args, None))
    } else {
        tray::run(&rt, args)
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(p) => {
            tracing::error!("{p}");
            eprintln!("싱크독_로컬을 켜지 못했다 — {p}");
            ExitCode::FAILURE
        }
    }
}
