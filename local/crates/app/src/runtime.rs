//! 켜기·끄기 — SYNC-INFRA-001 9.1 순서 그대로 (SYNC-MS-012).
//! 켜기: 잠금 → 로그 → PostgreSQL → 설정 → 이전 → 로컬 사용자 → 포트 → 작업 사본 맞추기 → 서빙. 끄기는 거꾸로.
//! 고리가 둘이다(카드 L16) — 바깥은 데이터 자리, 안은 켜기. 설정 저장·되살리기는 안을, 옮기기는 바깥을 다시 돈다

use std::fs::{self, File};
use std::net::{IpAddr, Ipv4Addr};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use clap::Parser;
use sqlx::PgPool;
use sqlx::postgres::PgPoolOptions;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::git::Git;
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::{migrate, pipeline};
use syncdoc_server::local::LocalOps;
use syncdoc_server::state::AppState;
use tokio::net::TcpListener;
use tokio::sync::{mpsc, oneshot};
use tokio::task::JoinHandle;
use tracing_appender::non_blocking::WorkerGuard;

use crate::local::{Local, Op, PgInfo, Shared};
use crate::pg::PgServer;
use crate::settings::Settings;
use crate::tray::TrayLink;
use crate::{backup, datadir, instance, logs, paths, pg, settings};

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
    /// 트레이 없이 — 개발·시험
    #[arg(long)]
    pub no_tray: bool,
    /// 브라우저를 열지 않는다 — 시험
    #[arg(long)]
    pub no_browser: bool,
    /// 로그인 때 자동 시작 — 트레이로만, 브라우저를 열지 않는다 (INFRA 9.5)
    #[arg(long)]
    pub autostart: bool,
}

/// 서빙 중인 것 — runtime.shutdown이 내린다. PostgreSQL·잠금·로그는 runtime.run이 쥔다
pub struct Serving {
    pub server: JoinHandle<std::io::Result<()>>,
    pub stop: oneshot::Sender<()>,
    /// 따라잡기·주기 확인(카드 L11)·하루 한 번 백업(카드 L16)
    pub background: Vec<JoinHandle<()>>,
    pub pool: PgPool,
    /// 이 PC — 트레이의 「지금 백업」이 부른다
    pub local: Arc<Local>,
    /// git 읽기 프로세스를 끌 때 모두 끈다(카드 L19)
    pub git: Git,
}

/// 데이터 자리의 git 전역 설정 — 사용자 설정 대신(카드 L6). 자동 gc·maintenance를 끄고 하루 한 번
/// `Git.gc`가 대신한다(카드 L19). 켤 때마다 이 내용으로 쓴다
const GITCONFIG: &str =
    "[gc]\n\tauto = 0\n[maintenance]\n\tauto = false\n[receive]\n\tautogc = false\n";

/// 주기 확인 — 파이썬 판 `POLL_INTERVAL_SECONDS` 기본값. 설정 키에 없어 고정한다(INFRA 9.3)
const POLL_INTERVAL: Duration = Duration::from_secs(300);

/// 기다림이 끝난 까닭
enum Next {
    Quit,
    Op(Op),
}

/// 데이터 자리와 그 안의 폴더 · git이 사용자 전역 설정 대신 읽는 빈 파일 (SYNC-MS-019 0장)
fn make_dirs(data: &Path) -> Result<(), Problem> {
    for dir in [
        data.to_path_buf(),
        data.join("logs"),
        data.join("origins"),
        data.join("repos"),
    ] {
        fs::create_dir_all(dir)?;
    }
    fs::write(data.join("gitconfig"), GITCONFIG)?;
    Ok(())
}

/// SYNC-MS-012#runtime.run
pub async fn run(args: Args, tray: Option<TrayLink>) -> Result<(), Problem> {
    let from_arg = args.data_dir.is_some();
    let mut data = match &args.data_dir {
        Some(d) => d.clone(),
        None => paths::data_dir()?,
    };
    make_dirs(&data)?;
    let Some(mut lock) = instance::acquire(&data)? else {
        let url = instance::open_running(&data, !args.no_browser && !args.autostart).await?;
        println!("싱크독_로컬이 이미 켜져 있다 — {url}");
        return Ok(());
    };
    let mut guard = logs::init(&data)?;
    let pg_dir = paths::pg_dir()?;
    let git_exe = paths::git()?;
    let shared = Arc::new(Shared::default());
    let (ops, mut ops_rx) = mpsc::unbounded_channel::<Op>();
    let (mut url_tx, mut quit, mut tray_backup) = match tray {
        Some(link) => (Some(link.url), Some(link.quit), Some(link.backup)),
        None => (None, None, None),
    };
    let mut last_port: Option<u16> = None;
    // 바깥 고리 — 데이터 자리(잠금·로그 대상·PostgreSQL)
    loop {
        let pg = pg::start(&pg_dir, &data).await?;
        // 안 고리 — 켜기(설정·연결 풀·서빙)
        loop {
            let (serving, port) =
                match serve(&args, &data, &pg, &git_exe, &shared, &ops, last_port).await {
                    Ok(s) => s,
                    Err(p) => {
                        let _ = pg::stop(pg).await;
                        remove_instance(&data);
                        return Err(p);
                    }
                };
            let url = format!("http://127.0.0.1:{port}/");
            if last_port.is_none() {
                tracing::info!("싱크독_로컬 — {url}");
                println!("싱크독_로컬 — {url}");
                if let Some(tx) = url_tx.take() {
                    let _ = tx.send(url.clone());
                }
                if !args.autostart && !args.no_browser {
                    open_browser(url);
                }
            }
            last_port = Some(port);
            let next = loop {
                tokio::select! {
                    () = wait_signal() => break Next::Quit,
                    () = wait_quit(&mut quit) => break Next::Quit,
                    () = wait_tray_backup(&mut tray_backup) => backup_in_background(&serving.local),
                    Some(op) = ops_rx.recv() => break Next::Op(op),
                }
            };
            shutdown(serving).await;
            match next {
                Next::Quit => {
                    let stopped = pg::stop(pg).await;
                    remove_instance(&data);
                    drop(lock);
                    tracing::info!("싱크독_로컬을 껐다");
                    drop(guard);
                    return stopped;
                }
                Next::Op(Op::Settings) => {
                    shared.record("settings", true, "설정을 저장하고 다시 켰다".into());
                }
                Next::Op(Op::Restore(opened)) => match backup::restore(&opened, &pg, &data).await {
                    Ok(()) => shared.record("restore", true, format!("{}로 되살렸다", opened.name)),
                    Err(p) => {
                        shared.record("restore", false, format!("되살리지 못해 되돌렸다 — {p}"))
                    }
                },
                Next::Op(Op::Move(target)) => {
                    if let Err(p) = pg::stop(pg).await {
                        shared.record(
                            "move",
                            false,
                            format!("옮기지 못했다 — {p} (지금 자리 그대로)"),
                        );
                        break;
                    }
                    match relocate(&data, &target, from_arg) {
                        Ok((new_lock, new_guard)) => {
                            remove_instance(&data);
                            lock = new_lock;
                            guard = new_guard;
                            data = target;
                            shared.record("move", true, format!("{}로 옮겼다", data.display()));
                        }
                        Err(p) => shared.record(
                            "move",
                            false,
                            format!("옮기지 못했다 — {p} (지금 자리 그대로)"),
                        ),
                    }
                    break;
                }
            }
        }
    }
}

/// 트레이의 「지금 백업」 — 따로 띄우고 기다리지 않는다(결과는 로그와 마지막 백업)
fn backup_in_background(local: &Arc<Local>) {
    let local = local.clone();
    tokio::spawn(async move {
        if let Err(p) = Local::backup_now(&local).await {
            tracing::warn!("트레이 「지금 백업」 — {p}");
        }
    });
}

/// 옮기기 — 복사·확인 → 가리키는 파일 → 새 자리의 잠금·로그. 실패하면 새 자리에 만든 것을 지운다
fn relocate(data: &Path, target: &Path, from_arg: bool) -> Result<(File, WorkerGuard), Problem> {
    datadir::copy(data, target)?;
    let done = (|| {
        make_dirs(target)?;
        let Some(new_lock) = instance::acquire(target)? else {
            return Err(Problem::DataDirInvalid {
                reason: "새 자리를 다른 싱크독_로컬이 쓰고 있다".into(),
            });
        };
        // --data-dir로 켰으면(개발·시험) 가리키는 파일을 건드리지 않는다
        if !from_arg {
            paths::set_data_dir(target)?;
        }
        let new_guard = logs::retarget(target)?;
        Ok((new_lock, new_guard))
    })();
    if done.is_err() {
        let _ = fs::remove_dir_all(target);
    }
    done
}

/// 안 고리 한 번 — 설정 → 연결 풀 → 묶기 → 조립(작업 사본 맞추기) → 서빙. (서빙, 실제 포트)
async fn serve(
    args: &Args,
    data: &Path,
    pg: &PgServer,
    git_exe: &Path,
    shared: &Arc<Shared>,
    ops: &mpsc::UnboundedSender<Op>,
    last_port: Option<u16>,
) -> Result<(Serving, u16), Problem> {
    let conf = settings::load(data)?;
    let pool = prepare(pg, &conf).await?;
    let host: IpAddr = if conf.public_base_url.is_empty() {
        Ipv4Addr::LOCALHOST.into()
    } else {
        Ipv4Addr::UNSPECIFIED.into() // 같은 망 열기 (INFRA 9.4)
    };
    let listener = match last_port {
        Some(p) => match bind(host, p, p).await {
            Ok(l) => l,
            Err(_) => bind(host, args.port, last_of(args.port)).await?,
        },
        None => bind(host, args.port, last_of(args.port)).await?,
    };
    let port = listener.local_addr()?.port();
    if args.port != 0 && port != args.port && last_port != Some(port) {
        let note = format!(
            "{}을 못 써 {port}에 열었다 — 에이전트의 MCP 주소도 바뀐다",
            args.port
        );
        tracing::warn!("{note}");
        println!("{note}");
    }
    instance::publish(data, port)?;
    let public = if conf.public_base_url.is_empty() {
        format!("http://127.0.0.1:{port}")
    } else {
        conf.public_base_url.clone()
    };
    let root = std::path::absolute(data)?;
    let git = Git::new(git_exe.to_path_buf(), root.join("gitconfig"));
    let repos = Arc::new(ServerRepos {
        git: git.clone(),
        origins: root.join("origins"),
        repos: root.join("repos"),
        specs_url: format!("{public}/specs"),
    });
    // 작업 사본 맞추기 — 옮긴 자리·되살린 백업 (카드 L16)
    {
        let mut c = pool.acquire().await?;
        let made = ProjectService {
            db: &mut c,
            repos: &repos,
        }
        .rehome()
        .await?;
        if !made.is_empty() {
            tracing::info!("작업 사본을 다시 만들었다 — {}", made.join(" "));
        }
    }
    let local = Arc::new(Local {
        data_dir: root.clone(),
        pg: PgInfo {
            bin: pg.bin.clone(),
            port: pg.port,
            password: pg.password.clone(),
        },
        git: git.clone(),
        shared: shared.clone(),
        ops: ops.clone(),
    });
    let app = syncdoc_server::app(AppState {
        pool: pool.clone(),
        local_login: conf.local_login.clone(),
        local_name: conf.local_name.clone(),
        llm_enabled: conf.llm_enabled,
        public_netloc: settings::host_of(&public).unwrap_or_else(|| format!("127.0.0.1:{port}")),
        repos: repos.clone(),
        llm: syncdoc_core::infra::llm::Llm {
            url: conf.llm_api_url.clone(),
            key: conf.llm_api_key.clone(),
            model: conf.llm_model.clone(),
        },
        local: Some(local.clone()),
    });
    let (stop, stopped) = oneshot::channel::<()>();
    let server = tokio::spawn(async move {
        axum::serve(listener, app)
            .with_graceful_shutdown(async move {
                let _ = stopped.await;
            })
            .await
    });
    // 따라잡기 — 꺼져 있던 동안 쌓인 커밋(기다리지 않는다) · 주기 확인 · 하루 한 번 백업 (INFRA 9.1·9.6)
    let catching = {
        let (p, r) = (pool.clone(), repos.clone());
        tokio::spawn(async move {
            if let Err(e) = pipeline::catch_up(&p, &r).await {
                tracing::warn!("켤 때 따라잡기: {e}");
            }
        })
    };
    let polling = tokio::spawn(pipeline::poll_loop(pool.clone(), repos, POLL_INTERVAL));
    let daily = tokio::spawn(backup::daily(local.clone()));
    Ok((
        Serving {
            server,
            stop,
            background: vec![catching, polling, daily],
            pool,
            local,
            git,
        },
        port,
    ))
}

/// 연결 풀을 열고 이전 SQL을 올린 뒤 로컬 사용자를 둔다
async fn prepare(server: &PgServer, conf: &Settings) -> Result<PgPool, Problem> {
    // 쉬는 연결을 닫지 않는다 — 윈도는 연결마다 postgres 프로세스를 띄워 다시 맺는 값이 크다(카드 L19)
    let pool = PgPoolOptions::new()
        .max_connections(10)
        .idle_timeout(None)
        .max_lifetime(None)
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

/// 첫 포트에서 아홉 더 — 0이면 0
fn last_of(first: u16) -> u16 {
    if first == 0 {
        0
    } else {
        first.saturating_add(9)
    }
}

/// SYNC-MS-012#runtime.bind
pub async fn bind(host: IpAddr, first: u16, last: u16) -> Result<TcpListener, Problem> {
    for port in first..=last {
        if let Ok(l) = TcpListener::bind((host, port)).await {
            return Ok(l);
        }
    }
    Err(Problem::Internal {
        log: format!("{host}의 {first}~{last}를 다 못 쓴다 — 쓰는 프로그램을 끄거나 --port로"),
    })
}

/// SYNC-MS-012#runtime.shutdown
pub async fn shutdown(serving: Serving) {
    let Serving {
        server,
        stop,
        background,
        pool,
        local,
        git,
    } = serving;
    drop(local);
    let _ = stop.send(());
    // 따라잡기·주기 확인·하루 한 번 백업을 멈춘다 — 그 안의 저장은 따로 돌아 아래에서 기다린다
    for task in background {
        task.abort();
    }
    let abort = server.abort_handle();
    // 진행 중 요청과 쓰기 락을 합쳐 10초 — 요청이 끊겨도 저장은 따로 돌아 git과 DB 사이에 있을 수 있다 (INFRA 9.1)
    let limit = Duration::from_secs(10);
    let started = tokio::time::Instant::now();
    if tokio::time::timeout(limit, server).await.is_err() {
        tracing::warn!("진행 중 요청을 10초 기다렸다 — 끊는다");
        abort.abort();
    }
    if !pipeline::wait_idle(limit.saturating_sub(started.elapsed())).await {
        tracing::warn!("저장이 끝나기를 10초 기다렸다 — 끊는다");
    }
    pool.close().await;
    // 5. 읽기 프로세스를 모두 끈다 — 되살리기·옮기기가 서버 저장소 폴더를 바꾸기 전에(윈도는 열린 팩 파일이 있으면 못 한다)
    Git::close_all(&git).await;
}

fn remove_instance(data_dir: &Path) {
    let _ = fs::remove_file(data_dir.join(instance::INSTANCE_FILE));
}

/// 바로 가기로 켠 사람에게 화면을 연다 — 못 열면 로그만(브라우저 없는 곳)
fn open_browser(url: String) {
    tokio::task::spawn_blocking(move || {
        if let Err(e) = webbrowser::open(&url) {
            tracing::warn!("브라우저를 못 열었다 — {url}: {e}");
        }
    });
}

/// 트레이의 「끝내기」 — 트레이가 없거나 보낼 쪽이 사라졌으면 끝없이 기다린다
async fn wait_quit(quit: &mut Option<oneshot::Receiver<()>>) {
    if let Some(rx) = quit.as_mut() {
        if rx.await.is_ok() {
            return;
        }
        *quit = None;
    }
    std::future::pending().await
}

/// 트레이의 「지금 백업」 — 트레이가 없으면 끝없이 기다린다
async fn wait_tray_backup(rx: &mut Option<mpsc::UnboundedReceiver<()>>) {
    if let Some(r) = rx.as_mut() {
        if r.recv().await.is_some() {
            return;
        }
        *rx = None;
    }
    std::future::pending().await
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
