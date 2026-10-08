//! 자리 — 데이터 자리와 PostgreSQL 바이너리·git 실행 파일 자리 (SYNC-INFRA-001 9.2·9.3)

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

/// SYNC-MS-012#paths.git
pub fn git() -> Result<PathBuf, Problem> {
    let exe_dir = if cfg!(windows) {
        std::env::current_exe()?.parent().map(Path::to_path_buf)
    } else {
        None
    };
    git_from(std::env::var_os("SYNCDOC_LOCAL_GIT"), exe_dir)
}

/// 환경 변수 → 윈도 설치 폴더의 MinGit → 시스템 git 차례. 자리를 준 것인데 파일이 없으면 `Problem`
fn git_from(env: Option<std::ffi::OsString>, exe_dir: Option<PathBuf>) -> Result<PathBuf, Problem> {
    let given = env
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        // 윈도는 설치 폴더의 MinGit — PATH를 고치지 않는다
        .or_else(|| exe_dir.map(|d| d.join("mingit").join("cmd").join("git.exe")));
    match given {
        Some(p) if p.is_file() => Ok(p),
        Some(p) => Err(Problem::Internal {
            log: format!("git을 못 찾았다 — {}", p.display()),
        }),
        // 리눅스는 시스템 git — .deb가 의존한다
        None => Ok(PathBuf::from("git")),
    }
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
    fn git_env_then_mingit_then_path() {
        let tmp = tempfile::tempdir().expect("임시");
        let f = tmp.path().join("git");
        std::fs::write(&f, "").expect("파일");
        assert_eq!(
            git_from(Some(f.clone().into()), None).expect("환경 변수"),
            f
        );
        let err = git_from(Some(tmp.path().join("no").into()), None).expect_err("없음");
        assert!(err.to_string().contains("no"));
        assert!(git_from(None, Some(tmp.path().to_path_buf())).is_err()); // MinGit이 없다
        assert_eq!(git_from(None, None).expect("시스템"), PathBuf::from("git"));
    }

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
