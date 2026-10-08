//! SYNC-MS-012#runtime.run·tray.run 테스트 관점 — 트레이의 「끝내기」도 Ctrl+C와 같은 끄는 순서로 끝낸다 (카드 L4).
//! 트레이 그림 자체는 데스크톱이 있어야 뜨므로 사람 확인(DEV-17)이 본다 — 여기는 runtime과 트레이 사이의 짝.

#![cfg(unix)]

use std::sync::mpsc;
use std::time::Duration;

use clap::Parser;
use syncdoc_app::runtime::{Args, run};
use syncdoc_app::tray::TrayLink;
use tokio::sync::oneshot;

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn quit_from_tray_shuts_down_in_order() {
    let data = tempfile::tempdir().expect("임시 자리");
    let args = Args::parse_from([
        "syncdoc-local",
        "--data-dir",
        data.path().to_str().expect("경로"),
        "--port",
        "0",
        "--no-browser",
    ]);
    let (url_tx, url_rx) = mpsc::channel();
    let (quit_tx, quit_rx) = oneshot::channel();
    let running = tokio::spawn(run(
        args,
        Some(TrayLink {
            url: url_tx,
            quit: quit_rx,
        }),
    ));
    let url = tokio::task::spawn_blocking(move || url_rx.recv_timeout(Duration::from_secs(60)))
        .await
        .expect("기다림")
        .expect("켜진 주소");
    assert!(
        url.starts_with("http://127.0.0.1:") && url.ends_with('/'),
        "{url}"
    );
    assert!(data.path().join("instance.json").is_file());
    quit_tx.send(()).expect("끝내기");
    tokio::time::timeout(Duration::from_secs(20), running)
        .await
        .expect("20초 안에 끝난다")
        .expect("작업")
        .expect("Ok");
    assert!(!data.path().join("instance.json").exists());
    assert!(!data.path().join("pgdata").join("postmaster.pid").exists());
}

#[tokio::test]
async fn autostart_flag_is_accepted() {
    let args = Args::parse_from(["syncdoc-local", "--autostart", "--no-tray"]);
    assert!(args.autostart && args.no_tray && !args.no_browser);
}
