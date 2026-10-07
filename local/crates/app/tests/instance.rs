//! SYNC-MS-012#instance.acquire·publish·open_running · runtime.bind 테스트 관점

use std::fs;
use std::time::Duration;

use syncdoc_app::instance::{INSTANCE_FILE, acquire, open_running, publish};
use syncdoc_app::runtime::bind;

#[test]
fn lock_once_then_again_after_release() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join(INSTANCE_FILE),
        "{\"url\":\"http://127.0.0.1:1/\"}",
    )
    .unwrap();
    let held = acquire(dir.path()).expect("잠금").expect("처음은 잡힌다");
    assert!(
        !dir.path().join(INSTANCE_FILE).exists(),
        "남은 instance.json을 지운다"
    );
    assert!(
        acquire(dir.path()).expect("다시").is_none(),
        "잡고 있는 동안은 못 잡는다"
    );
    drop(held);
    assert!(acquire(dir.path()).expect("놓은 뒤").is_some());
}

#[tokio::test]
async fn publish_then_open_running_without_browser() {
    let dir = tempfile::tempdir().unwrap();
    publish(dir.path(), 8015).expect("적는다");
    let url = open_running(dir.path(), false).await.expect("읽는다");
    assert_eq!(url, "http://127.0.0.1:8015/");
    let v: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(dir.path().join(INSTANCE_FILE)).unwrap()).unwrap();
    assert_eq!(v["port"], 8015);
}

#[tokio::test]
async fn open_running_waits_for_a_starting_instance() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().to_path_buf();
    let writer = tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(600)).await;
        publish(&path, 8016).expect("늦게 적는다");
    });
    let url = open_running(dir.path(), false)
        .await
        .expect("기다려 읽는다");
    assert_eq!(url, "http://127.0.0.1:8016/");
    writer.await.unwrap();
}

#[tokio::test]
async fn bind_moves_to_the_next_port() {
    let taken = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let p = taken.local_addr().unwrap().port();
    let l = bind(p, p.saturating_add(9)).await.expect("다음 포트");
    let got = l.local_addr().unwrap();
    assert!(got.ip().is_loopback() && got.port() > p, "{got}");
    let any = bind(0, 0).await.expect("아무 포트");
    assert!(any.local_addr().unwrap().port() > 0);
    let err = bind(p, p).await.expect_err("다 막혔다");
    assert!(err.to_string().contains("다 못 쓴다"));
}
