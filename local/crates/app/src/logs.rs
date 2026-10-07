//! 로그 — 데이터 자리 `logs/`, 날마다 한 파일·최근 14개 (SYNC-INFRA-001 9.3, 사용자 결정 2026-10-07).
//! 앱은 `syncdoc-local.{날짜}.log`, PostgreSQL은 `postgresql-{날짜}.log`(SYNC-MS-012#pg.start).

use std::fs;
use std::path::Path;

use syncdoc_core::errors::Problem;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_appender::rolling::{Builder, Rotation};
use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::{Layer, fmt};

/// 종류마다 남기는 파일 수
pub const KEEP: usize = 14;

/// SYNC-MS-012#logs.init
pub fn init(data_dir: &Path) -> Result<WorkerGuard, Problem> {
    let dir = data_dir.join("logs");
    fs::create_dir_all(&dir)?;
    prune(&dir, "syncdoc-local.", ".log")?;
    prune(&dir, "postgresql-", ".log")?;
    let appender = Builder::new()
        .rotation(Rotation::DAILY)
        .filename_prefix("syncdoc-local")
        .filename_suffix("log")
        .max_log_files(KEEP)
        .build(&dir)
        .map_err(|e| Problem::Internal {
            log: format!("로그를 못 연다 — {e}"),
        })?;
    let (writer, guard) = tracing_appender::non_blocking(appender);
    let subscriber = tracing_subscriber::registry()
        .with(
            fmt::layer()
                .with_writer(writer)
                .with_ansi(false)
                .with_filter(LevelFilter::INFO),
        )
        .with(
            fmt::layer()
                .with_writer(std::io::stderr)
                .with_filter(LevelFilter::INFO),
        );
    // 같은 프로세스에서 이미 걸었으면 그대로 둔다
    let _ = tracing::subscriber::set_global_default(subscriber);
    Ok(guard)
}

/// 이름이 `prefix…suffix`인 파일을 이름 순으로 최근 KEEP개만 — 이름의 날짜가 순서다
fn prune(dir: &Path, prefix: &str, suffix: &str) -> Result<(), Problem> {
    let mut names: Vec<String> = fs::read_dir(dir)?
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| n.starts_with(prefix) && n.ends_with(suffix))
        .collect();
    names.sort();
    let extra = names.len().saturating_sub(KEEP);
    for n in &names[..extra] {
        fs::remove_file(dir.join(n))?;
    }
    Ok(())
}
