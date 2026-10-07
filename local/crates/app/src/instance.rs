//! 한 번만 실행 — 잠금 파일과 켜진 주소 (SYNC-INFRA-001 9.1).
//! 두 번째 실행은 잠금을 못 잡고 `instance.json`의 주소를 브라우저로 연 뒤 끝난다.

use std::fs::{self, File, OpenOptions, TryLockError};
use std::path::Path;
use std::time::Duration;

use syncdoc_core::errors::Problem;
use tokio::time::Instant;

pub const LOCK_FILE: &str = "syncdoc-local.lock";
pub const INSTANCE_FILE: &str = "instance.json";

/// SYNC-MS-012#instance.acquire
pub fn acquire(data_dir: &Path) -> Result<Option<File>, Problem> {
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(data_dir.join(LOCK_FILE))?;
    match file.try_lock() {
        Ok(()) => {
            let _ = fs::remove_file(data_dir.join(INSTANCE_FILE));
            Ok(Some(file))
        }
        Err(TryLockError::WouldBlock) => Ok(None),
        Err(TryLockError::Error(e)) => Err(Problem::Internal {
            log: format!("잠금을 못 잡는다 — {e}"),
        }),
    }
}

/// SYNC-MS-012#instance.publish
pub fn publish(data_dir: &Path, port: u16) -> Result<(), Problem> {
    let body = serde_json::json!({
        "pid": std::process::id(),
        "port": port,
        "url": format!("http://127.0.0.1:{port}/"),
    });
    let tmp = data_dir.join("instance.json.tmp");
    fs::write(&tmp, body.to_string())?;
    fs::rename(&tmp, data_dir.join(INSTANCE_FILE))?;
    Ok(())
}

/// SYNC-MS-012#instance.open_running
pub async fn open_running(data_dir: &Path, browser: bool) -> Result<String, Problem> {
    let path = data_dir.join(INSTANCE_FILE);
    let deadline = Instant::now() + Duration::from_secs(60);
    let url = loop {
        if let Some(url) = read_url(&path) {
            break url;
        }
        if Instant::now() >= deadline {
            return Err(Problem::Internal {
                log: format!("이미 켜져 있는데 주소를 못 읽었다 — {}", path.display()),
            });
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    };
    if browser && let Err(e) = webbrowser::open(&url) {
        eprintln!("브라우저를 열지 못했다 — {e}");
    }
    Ok(url)
}

fn read_url(path: &Path) -> Option<String> {
    let text = fs::read_to_string(path).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    v.get("url")?.as_str().map(str::to_string)
}
