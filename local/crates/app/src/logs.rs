//! 로그 — 데이터 자리 `logs/`, 날마다 한 파일·최근 14개 (SYNC-INFRA-001 9.3, 사용자 결정 2026-10-07).
//! 앱은 `syncdoc-local.{날짜}.log`, PostgreSQL은 `postgresql-{날짜}.log`(SYNC-MS-012#pg.start).

use std::fs;
use std::io::Write;
use std::path::Path;
use std::sync::Mutex;

use syncdoc_core::errors::Problem;
use tracing_appender::non_blocking::{NonBlocking, WorkerGuard};
use tracing_appender::rolling::{Builder, Rotation};
use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::fmt::MakeWriter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::{Layer, fmt};

/// 종류마다 남기는 파일 수
pub const KEEP: usize = 14;

/// 파일 쪽 쓰기 대상 — 옮긴 자리로 바꿀 수 있다(카드 L16)
static TARGET: Mutex<Option<NonBlocking>> = Mutex::new(None);

/// 줄마다 지금 대상에 쓴다
#[derive(Clone, Copy)]
struct Current;

impl<'a> MakeWriter<'a> for Current {
    type Writer = Sink;

    fn make_writer(&'a self) -> Self::Writer {
        Sink(
            TARGET
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .clone(),
        )
    }
}

/// 대상이 없으면 버린다
struct Sink(Option<NonBlocking>);

impl Write for Sink {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        match &mut self.0 {
            Some(w) => w.write(buf),
            None => Ok(buf.len()),
        }
    }

    fn flush(&mut self) -> std::io::Result<()> {
        match &mut self.0 {
            Some(w) => w.flush(),
            None => Ok(()),
        }
    }
}

/// `logs/`를 열어 대상을 바꾼다 — 날마다 한 파일, 종류마다 최근 KEEP개
fn open(data_dir: &Path) -> Result<WorkerGuard, Problem> {
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
    *TARGET
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(writer);
    Ok(guard)
}

/// SYNC-MS-012#logs.init
pub fn init(data_dir: &Path) -> Result<WorkerGuard, Problem> {
    let guard = open(data_dir)?;
    let subscriber = tracing_subscriber::registry()
        .with(
            fmt::layer()
                .with_writer(Current)
                .with_ansi(false)
                .with_filter(LevelFilter::INFO),
        )
        .with(
            fmt::layer()
                .with_writer(std::io::stderr)
                .with_filter(LevelFilter::INFO),
        );
    // 같은 프로세스에서 이미 걸었으면 그대로 둔다 — 대상은 위에서 바뀌었다
    let _ = tracing::subscriber::set_global_default(subscriber);
    Ok(guard)
}

/// SYNC-MS-012#logs.retarget
///
/// 옮긴 자리의 `logs/`로 — 이 뒤의 줄은 새 파일에. 옛 지킴이를 놓으면 옛 파일의 남은 줄을 마저 쓴다
pub fn retarget(data_dir: &Path) -> Result<WorkerGuard, Problem> {
    open(data_dir)
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
