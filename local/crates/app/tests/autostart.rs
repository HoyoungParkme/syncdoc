//! SYNC-MS-023#autostart.enabled·autostart.set 테스트 관점 — 리눅스.
//! 사용자의 진짜 자동 시작 폴더를 건드리지 않게, 같은 시험 실행 파일을 임시 XDG_CONFIG_HOME으로 다시 부른다

#![cfg(all(unix, not(target_os = "macos")))]

use std::process::Command;

use syncdoc_app::autostart::{enabled, set};

#[test]
#[ignore = "부모 시험이 임시 XDG_CONFIG_HOME으로 부른다"]
fn child_set_and_clear() {
    let Some(home) = std::env::var_os("SYNCDOC_AUTOSTART_CHILD") else {
        return;
    };
    assert_eq!(std::env::var_os("XDG_CONFIG_HOME"), Some(home.clone()));
    assert!(!enabled().unwrap());
    set(true).unwrap();
    assert!(enabled().unwrap());
    let file = std::path::Path::new(&home).join("autostart/syncdoc-local.desktop");
    let text = std::fs::read_to_string(&file).unwrap();
    assert!(
        text.contains("Type=Application") && text.contains("--autostart\n"),
        "{text}"
    );
    set(false).unwrap();
    assert!(!enabled().unwrap() && !file.exists());
    set(false).unwrap();
}

#[test]
fn set_and_clear_in_a_temp_config() {
    let tmp = tempfile::tempdir().unwrap();
    let out = Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "child_set_and_clear", "--ignored", "--nocapture"])
        .env("XDG_CONFIG_HOME", tmp.path())
        .env("SYNCDOC_AUTOSTART_CHILD", tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(String::from_utf8_lossy(&out.stdout).contains("1 passed"));
}
