//! 켜기·끄기 — SYNC-INFRA-001 9.1 순서 그대로 (SYNC-MS-012).
//! 켜기: 잠금 → 로그 → 설정 → PostgreSQL → 이전 → 로컬 사용자 → 포트 → 서빙. 끄기는 거꾸로.

use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::time::Duration;

use clap::Parser;
use sqlx::PgPool;
use sqlx::postgres::PgPoolOptions;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::migrate;
use syncdoc_server::state::AppState;
use tokio::net::TcpListener;
use tokio::sync::oneshot;
use tokio::task::JoinHandle;
use tracing_appender::non_blocking::WorkerGuard;

use crate::pg::PgServer;
use crate::settings::Settings;
use crate::{instance, logs, paths, pg, settings};

/// 인자 — 개발·시험용이 섞여 있다
#[derive(Debug, Parser)]
#[command(
    name = "syncdoc-local",
    about = "싱크독_로컬 — 명세를 이 PC에서",
    version
)]
pub struct Args {
    /// 데이터 자리 — 없으면 기본 자리 (INFRA 9.3)
    #[arg(long)]
    pub data_dir: Option<PathBuf>,
    /// 묶을 포트 — 못 쓰면 다음 9개까지, 0이면 아무 포트
    #[arg(long, default_value_t = 8010)]
    pub port: u16,
    /// 트레이 없이 — 카드 L1은 트레이가 없어 받아 두기만 한다 (L4)
    #[arg(long)]
    pub no_tray: bool,
    /// 이미 켜져 있을 때 브라우저를 열지 않는다
    #[arg(long)]
    pub no_browser: bool,
}

/// 켜진 것 — runtime.shutdown이 거꾸로 끈다
pub struct Running {
    pub server: JoinHandle<std::io::Result<()>>,
    pub stop: oneshot::Sender<()>,
    pub pool: PgPool,
    pub pg: PgServer,
    pub data_dir: PathBuf,
    pub lock: File,
    pub logs: WorkerGuard,
}

/// SYNC-MS-012#runtime.run
pub async fn run(args: Args) -> Result<(), Problem> {
    let data = match args.data_dir {
        Some(d) => d,
        None => paths::data_dir()?,
    };
    for dir in [
        data.clone(),
        data.join("logs"),
        data.join("origins"),
        data.join("repos"),
    ] {
        fs::create_dir_all(dir)?;
    }
    let Some(lock) = instance::acquire(&data)? else {
        let url = instance::open_running(&data, !args.no_browser).await?;
        println!("싱크독_로컬이 이미 켜져 있다 — {url}");
        return Ok(());
    };
    let guard = logs::init(&data)?;
    let conf = settings::load(&data)?;
    let pg_dir = paths::pg_dir()?;
    let server = pg::start(&pg_dir, &data).await?;
    let pool = match prepare(&server, &conf).await {
        Ok(pool) => pool,
        Err(p) => {
            let _ = pg::stop(server).await;
            return Err(p);
        }
    };
    let last = if args.port == 0 {
        0
    } else {
        args.port.saturating_add(9)
    };
    let listener = match bind(args.port, last).await {
        Ok(l) => l,
        Err(p) => {
            pool.close().await;
            let _ = pg::stop(server).await;
            return Err(p);
        }
    };
    let port = listener.local_addr()?.port();
    if args.port != 0 && port != args.port {
        let note = format!(
            "{}을 못 써 {port}에 열었다 — 에이전트의 MCP 주소도 바뀐다",
            args.port
        );
        tracing::warn!("{note}");
        println!("{note}");
    }
    instance::publish(&data, port)?;
    let app = syncdoc_server::app(AppState {
        pool: pool.clone(),
        local_login: conf.local_login.clone(),
        local_name: conf.local_name.clone(),
        llm_enabled: conf.llm_enabled,
        public_netloc: format!("127.0.0.1:{port}"),
    });
    let (stop, stopped) = oneshot::channel::<()>();
    let serving = tokio::spawn(async move {
        axum::serve(listener, app)
            .with_graceful_shutdown(async move {
                let _ = stopped.await;
            })
            .await
    });
    tracing::info!("싱크독_로컬 — http://127.0.0.1:{port}/");
    println!("싱크독_로컬 — http://127.0.0.1:{port}/");
    wait_signal().await;
    shutdown(Running {
        server: serving,
        stop,
        pool,
        pg: server,
        data_dir: data,
        lock,
        logs: guard,
    })
    .await
}

/// 연결 풀을 열고 이전 SQL을 올린 뒤 로컬 사용자를 둔다
async fn prepare(server: &PgServer, conf: &Settings) -> Result<PgPool, Problem> {
    let pool = PgPoolOptions::new()
        .connect_with(server.options.clone())
        .await?;
    let mut conn = pool.acquire().await?;
    let applied = migrate::apply(&mut conn).await?;
    if !applied.is_empty() {
        tracing::info!("이전 SQL을 올렸다 — {}", applied.join(" "));
    }
    let mut tx = pool.begin().await?;
    let mut svc = AccountService { db: &mut tx };
    svc.ensure_local_user(&conf.local_login, &conf.local_name)
        .await?;
    tx.commit().await?;
    drop(conn);
    Ok(pool)
}

/// SYNC-MS-012#runtime.bind
pub async fn bind(first: u16, last: u16) -> Result<TcpListener, Problem> {
    for port in first..=last {
        if let Ok(l) = TcpListener::bind(("127.0.0.1", port)).await {
            return Ok(l);
        }
    }
    Err(Problem::Internal {
        log: format!("127.0.0.1의 {first}~{last}를 다 못 쓴다 — 쓰는 프로그램을 끄거나 --port로"),
    })
}

/// SYNC-MS-012#runtime.shutdown
pub async fn shutdown(running: Running) -> Result<(), Problem> {
    let Running {
        server,
        stop,
        pool,
        pg: db,
        data_dir,
        lock,
        logs: guard,
    } = running;
    let _ = stop.send(());
    let abort = server.abort_handle();
    if tokio::time::timeout(Duration::from_secs(10), server)
        .await
        .is_err()
    {
        tracing::warn!("진행 중 요청을 10초 기다렸다 — 끊는다");
        abort.abort();
    }
    pool.close().await;
    let stopped = pg::stop(db).await;
    remove_instance(&data_dir);
    drop(lock);
    tracing::info!("싱크독_로컬을 껐다");
    drop(guard);
    stopped
}

fn remove_instance(data_dir: &Path) {
    let _ = fs::remove_file(data_dir.join(instance::INSTANCE_FILE));
}

/// 끄기 신호 — Ctrl+C, 유닉스는 SIGTERM도
async fn wait_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{SignalKind, signal};
        match signal(SignalKind::terminate()) {
            Ok(mut term) => {
                tokio::select! {
                    _ = tokio::signal::ctrl_c() => {}
                    _ = term.recv() => {}
                }
            }
            Err(_) => {
                let _ = tokio::signal::ctrl_c().await;
            }
        }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}
