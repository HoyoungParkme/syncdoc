//! 자리 — 데이터 자리와 PostgreSQL 바이너리 자리 (SYNC-INFRA-001 9.3)

use std::path::{Path, PathBuf};

use directories::BaseDirs;
use syncdoc_core::errors::Problem;

/// 데이터 자리 이름 — 윈도 `%LOCALAPPDATA%\SyncDoc Local`, 리눅스 `~/.local/share/syncdoc-local`
#[cfg(windows)]
const DATA_NAME: &str = "SyncDoc Local";
#[cfg(not(windows))]
const DATA_NAME: &str = "syncdoc-local";

/// SYNC-MS-012#paths.data_dir
pub fn data_dir() -> Result<PathBuf, Problem> {
    let base = BaseDirs::new().ok_or_else(|| Problem::Internal {
        log: "사용자 폴더를 모른다 — --data-dir로 데이터 자리를 준다".into(),
    })?;
    Ok(base.data_local_dir().join(DATA_NAME))
}

/// SYNC-MS-012#paths.pg_dir
pub fn pg_dir() -> Result<PathBuf, Problem> {
    let dir = match std::env::var_os("SYNCDOC_LOCAL_PG_DIR").filter(|v| !v.is_empty()) {
        Some(d) => PathBuf::from(d),
        None => std::env::current_exe()?
            .parent()
            .map(|p| p.join("postgresql"))
            .ok_or_else(|| Problem::Internal {
                log: "실행 파일 자리를 모른다".into(),
            })?,
    };
    checked(dir)
}

/// `bin/postgres`가 있는 자리만
fn checked(dir: PathBuf) -> Result<PathBuf, Problem> {
    let postgres = exe(&dir.join("bin"), "postgres");
    if postgres.is_file() {
        Ok(dir)
    } else {
        Err(Problem::Internal {
            log: format!("PostgreSQL을 못 찾았다 — {}", postgres.display()),
        })
    }
}

/// 실행 파일 이름 — 윈도는 `.exe`
fn exe(bin: &Path, name: &str) -> PathBuf {
    if cfg!(windows) {
        bin.join(format!("{name}.exe"))
    } else {
        bin.join(name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn data_dir_ends_with_edition_name() {
        let d = data_dir().expect("데이터 자리");
        assert_eq!(d.file_name().and_then(|n| n.to_str()), Some(DATA_NAME));
        let base = BaseDirs::new().expect("사용자 폴더");
        assert!(d.starts_with(base.data_local_dir()));
    }

    #[test]
    fn checked_needs_postgres_binary() {
        let tmp = std::env::temp_dir().join(format!("syncdoc-pg-dir-{}", std::process::id()));
        let err = checked(tmp.clone()).expect_err("바이너리 없음");
        assert!(
            err.to_string()
                .contains(&tmp.join("bin").display().to_string())
        );
        std::fs::create_dir_all(tmp.join("bin")).expect("bin");
        std::fs::write(exe(&tmp.join("bin"), "postgres"), b"").expect("postgres");
        assert_eq!(checked(tmp.clone()).expect("자리"), tmp);
        std::fs::remove_dir_all(&tmp).expect("정리");
    }
}
