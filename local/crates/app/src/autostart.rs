//! 자동 시작 — 로그인할 때 트레이로 켜기 (SYNC-MS-023 · SYNC-INFRA-001 9.5, 카드 L16).
//! 윈도는 설치 화면의 체크가 쓰는 것과 같은 `HKCU\…\Run` 값, 리눅스는 XDG autostart 파일이다.

use std::path::PathBuf;

use syncdoc_core::errors::Problem;

/// 설치 파일(NSIS `APPKEY`)과 같은 값 이름
#[cfg(windows)]
const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
#[cfg(windows)]
const VALUE: &str = "SyncDoc Local";

fn internal(what: &str, e: impl std::fmt::Display) -> Problem {
    Problem::Internal {
        log: format!("자동 시작 {what} — {e}"),
    }
}

/// 걸 실행 파일 — 리눅스 AppImage면 `$APPIMAGE`(지금 실행 파일은 풀린 임시 자리다)
fn exe() -> Result<PathBuf, Problem> {
    if cfg!(not(windows))
        && let Some(image) = std::env::var_os("APPIMAGE").filter(|v| !v.is_empty())
    {
        return Ok(PathBuf::from(image));
    }
    std::env::current_exe().map_err(|e| internal("실행 파일", e))
}

/// `{XDG_CONFIG_HOME 또는 ~/.config}/autostart/syncdoc-local.desktop`
#[cfg(not(windows))]
fn desktop_file() -> Result<PathBuf, Problem> {
    let base =
        directories::BaseDirs::new().ok_or_else(|| internal("자리", "사용자 폴더를 모른다"))?;
    Ok(base
        .config_dir()
        .join("autostart")
        .join("syncdoc-local.desktop"))
}

/// SYNC-MS-023#autostart.enabled
pub fn enabled() -> Result<bool, Problem> {
    #[cfg(windows)]
    {
        use winreg::RegKey;
        use winreg::enums::{HKEY_CURRENT_USER, KEY_READ};
        match RegKey::predef(HKEY_CURRENT_USER).open_subkey_with_flags(RUN_KEY, KEY_READ) {
            Ok(key) => Ok(key.get_raw_value(VALUE).is_ok()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
            Err(e) => Err(internal("읽기", e)),
        }
    }
    #[cfg(not(windows))]
    {
        Ok(desktop_file()?.is_file())
    }
}

/// SYNC-MS-023#autostart.set
pub fn set(on: bool) -> Result<(), Problem> {
    #[cfg(windows)]
    {
        use winreg::RegKey;
        use winreg::enums::HKEY_CURRENT_USER;
        let (key, _) = RegKey::predef(HKEY_CURRENT_USER)
            .create_subkey(RUN_KEY)
            .map_err(|e| internal("열기", e))?;
        if on {
            let command = format!("\"{}\" --autostart", exe()?.display());
            key.set_value(VALUE, &command)
                .map_err(|e| internal("쓰기", e))?;
        } else {
            match key.delete_value(VALUE) {
                Ok(()) => {}
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => return Err(internal("지우기", e)),
            }
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let file = desktop_file()?;
        if on {
            if let Some(dir) = file.parent() {
                std::fs::create_dir_all(dir).map_err(|e| internal("폴더", e))?;
            }
            let text = format!(
                "[Desktop Entry]\nType=Application\nName=싱크독_로컬\nExec=\"{}\" --autostart\nX-GNOME-Autostart-enabled=true\n",
                exe()?.display()
            );
            std::fs::write(&file, text).map_err(|e| internal("쓰기", e))?;
        } else {
            match std::fs::remove_file(&file) {
                Ok(()) => {}
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => return Err(internal("지우기", e)),
            }
        }
        Ok(())
    }
}
