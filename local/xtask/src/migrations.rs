//! 이전 SQL — 리비전마다 `alembic upgrade --sql`로 (SYNC-STD-004#DEV-7).
//! Alembic이 유일한 원본이다. 오프라인 모드라 DB에 붙지 않는다 — `DATABASE_URL`은 어디도 아닌 주소다.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::{local_root, repo_root};

/// 어디에도 붙지 않는 주소 — 오프라인 모드가 방언만 읽는다. 혹시 온라인으로 돌아도 붙을 곳이 없다
const OFFLINE_URL: &str = "postgresql+psycopg://offline@offline.invalid/none";

pub fn run(check: bool) -> Result<(), String> {
    let dest = local_root().join("migrations");
    if check {
        let tmp = tempfile::tempdir().map_err(|e| e.to_string())?;
        generate(tmp.path())?;
        let diff = compare(tmp.path(), &dest)?;
        if diff.is_empty() {
            println!("이전 SQL이 Alembic과 같다 — {}개", count(&dest)?);
            return Ok(());
        }
        return Err(format!(
            "이전 SQL이 Alembic과 다르다 — cargo xtask migrations로 다시 만든다:\n{}",
            diff.join("\n")
        ));
    }
    fs::create_dir_all(&dest).map_err(|e| e.to_string())?;
    for f in sql_files(&dest)? {
        fs::remove_file(f).map_err(|e| e.to_string())?;
    }
    generate(&dest)?;
    println!("이전 SQL을 만들었다 — {}개", count(&dest)?);
    Ok(())
}

/// 리비전 목록 — `backend/alembic/versions/NNNN_이름.py`를 이름 순으로. 리비전 ID = 앞 네 자리
fn revisions() -> Result<Vec<(String, String)>, String> {
    let dir = repo_root().join("backend").join("alembic").join("versions");
    let mut out: Vec<(String, String)> = fs::read_dir(&dir)
        .map_err(|e| format!("{}: {e}", dir.display()))?
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| n.ends_with(".py") && n.len() > 5 && n[..4].chars().all(|c| c.is_ascii_digit()))
        .map(|n| (n[..4].to_string(), n.trim_end_matches(".py").to_string()))
        .collect();
    out.sort();
    Ok(out)
}

fn generate(to: &Path) -> Result<(), String> {
    let backend = repo_root().join("backend");
    let mut prev: Option<String> = None;
    for (rev, stem) in revisions()? {
        let range = match &prev {
            None => rev.clone(),
            Some(p) => format!("{p}:{rev}"),
        };
        let out = Command::new("uv")
            .args(["run", "--quiet", "alembic", "upgrade", "--sql", &range])
            .current_dir(&backend)
            .env("DATABASE_URL", OFFLINE_URL)
            .output()
            .map_err(|e| format!("uv를 못 돌렸다 — {e}"))?;
        if !out.status.success() {
            return Err(format!(
                "alembic upgrade --sql {range} 실패 — {}",
                String::from_utf8_lossy(&out.stderr)
            ));
        }
        fs::write(to.join(format!("{stem}.sql")), &out.stdout).map_err(|e| e.to_string())?;
        prev = Some(rev);
    }
    Ok(())
}

fn sql_files(dir: &Path) -> Result<Vec<PathBuf>, String> {
    let mut v: Vec<PathBuf> = fs::read_dir(dir)
        .map_err(|e| format!("{}: {e}", dir.display()))?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "sql"))
        .collect();
    v.sort();
    Ok(v)
}

fn count(dir: &Path) -> Result<usize, String> {
    Ok(sql_files(dir)?.len())
}

/// 이름과 바이트가 다른 파일들
fn compare(fresh: &Path, committed: &Path) -> Result<Vec<String>, String> {
    let names = |d: &Path| -> Result<Vec<String>, String> {
        Ok(sql_files(d)?
            .iter()
            .filter_map(|p| p.file_name().and_then(|n| n.to_str()).map(str::to_string))
            .collect())
    };
    let (a, b) = (names(fresh)?, names(committed)?);
    let mut diff = Vec::new();
    for n in &a {
        if !b.contains(n) {
            diff.push(format!("없다 — {n}"));
        } else if fs::read(fresh.join(n)).ok() != fs::read(committed.join(n)).ok() {
            diff.push(format!("다르다 — {n}"));
        }
    }
    for n in &b {
        if !a.contains(n) {
            diff.push(format!("남는다 — {n}"));
        }
    }
    Ok(diff)
}
