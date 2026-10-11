//! 데이터 자리 옮기기 — 자리 보기·복사·확인 (SYNC-MS-023 · SYNC-INFRA-001 9.3, 카드 L16).
//! 복사는 PostgreSQL이 멈춘 뒤 runtime이 부른다. 작업 사본·로그·잠금은 복사하지 않는다(켤 때 다시 만든다)

use std::fs;
use std::path::{Path, PathBuf};

use syncdoc_core::errors::Problem;

/// 옮기는 것 — 폴더 둘과 파일 둘
const DIRS: [&str; 2] = ["pgdata", "origins"];
const FILES: [&str; 2] = ["settings.toml", "gitconfig"];

fn invalid(reason: impl Into<String>) -> Problem {
    Problem::DataDirInvalid {
        reason: reason.into(),
    }
}

/// 있는 데까지 실제 경로 — 없는 꼬리는 그대로 붙인다(비교용)
fn real(p: &Path) -> PathBuf {
    let mut head = p.to_path_buf();
    let mut tail = Vec::new();
    while !head.exists() {
        match (head.file_name().map(|n| n.to_os_string()), head.parent()) {
            (Some(name), Some(parent)) => {
                tail.push(name);
                head = parent.to_path_buf();
            }
            _ => break,
        }
    }
    let mut out = fs::canonicalize(&head).unwrap_or(head);
    for name in tail.into_iter().rev() {
        out.push(name);
    }
    out
}

/// SYNC-MS-023#datadir.check
pub fn check(current: &Path, target: &str) -> Result<PathBuf, Problem> {
    let t = target.trim();
    let path = PathBuf::from(t);
    if t.is_empty() || !path.is_absolute() {
        return Err(invalid("절대 경로가 아니다"));
    }
    let (cur, tgt) = (real(current), real(&path));
    if cur == tgt || tgt.starts_with(&cur) || cur.starts_with(&tgt) {
        return Err(invalid("지금 데이터 자리와 겹친다"));
    }
    if path.exists() {
        let empty = path.is_dir()
            && fs::read_dir(&path)
                .map(|mut d| d.next().is_none())
                .unwrap_or(false);
        if !empty {
            return Err(invalid("비어 있지 않은 폴더다"));
        }
    }
    let probe = path.join(".syncdoc-write-test");
    fs::create_dir_all(&path)
        .and_then(|()| fs::write(&probe, b"ok"))
        .and_then(|()| fs::remove_file(&probe))
        .map_err(|e| invalid(format!("쓸 수 없다 — {e}")))?;
    std::path::absolute(&path).map_err(|e| invalid(format!("쓸 수 없다 — {e}")))
}

/// 폴더째 복사 — 빈 폴더와 권한까지(PostgreSQL은 pgdata가 0700이어야 켠다)
fn copy_tree(from: &Path, to: &Path) -> std::io::Result<()> {
    fs::create_dir_all(to)?;
    fs::set_permissions(to, fs::metadata(from)?.permissions())?;
    for entry in fs::read_dir(from)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        let dest = to.join(entry.file_name());
        if kind.is_dir() {
            copy_tree(&entry.path(), &dest)?;
        } else if kind.is_file() {
            fs::copy(entry.path(), &dest)?;
        }
    }
    Ok(())
}

/// (상대 경로, 크기) 목록 — 폴더는 크기 0. 이름 순
fn listing(root: &Path) -> std::io::Result<Vec<(String, u64)>> {
    fn walk(root: &Path, dir: &Path, out: &mut Vec<(String, u64)>) -> std::io::Result<()> {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let kind = entry.file_type()?;
            let rel = entry
                .path()
                .strip_prefix(root)
                .map(|p| p.to_string_lossy().replace('\\', "/"))
                .unwrap_or_default();
            if kind.is_dir() {
                out.push((format!("{rel}/"), 0));
                walk(root, &entry.path(), out)?;
            } else if kind.is_file() {
                out.push((rel, entry.metadata()?.len()));
            }
        }
        Ok(())
    }
    let mut out = Vec::new();
    for d in DIRS {
        if root.join(d).is_dir() {
            out.push((format!("{d}/"), 0));
            walk(root, &root.join(d), &mut out)?;
        }
    }
    for f in FILES {
        if root.join(f).is_file() {
            out.push((f.to_string(), fs::metadata(root.join(f))?.len()));
        }
    }
    out.sort();
    Ok(out)
}

/// SYNC-MS-023#datadir.copy
pub fn copy(from: &Path, to: &Path) -> Result<(), Problem> {
    let done = (|| -> Result<(), Problem> {
        for d in DIRS {
            if from.join(d).is_dir() {
                copy_tree(&from.join(d), &to.join(d))
                    .map_err(|e| invalid(format!("복사하지 못했다 — {d}: {e}")))?;
            }
        }
        for f in FILES {
            if from.join(f).is_file() {
                fs::copy(from.join(f), to.join(f))
                    .map_err(|e| invalid(format!("복사하지 못했다 — {f}: {e}")))?;
            }
        }
        let (a, b) = (
            listing(from).map_err(|e| invalid(format!("확인하지 못했다 — {e}")))?,
            listing(to).map_err(|e| invalid(format!("확인하지 못했다 — {e}")))?,
        );
        if let Some(diff) = a.iter().zip(&b).find(|(x, y)| x != y).map(|(x, _)| &x.0) {
            return Err(invalid(format!("복사가 맞지 않다 — {diff}")));
        }
        if a.len() != b.len() {
            return Err(invalid("복사가 맞지 않다 — 파일 수"));
        }
        Ok(())
    })();
    if done.is_err() {
        for d in DIRS {
            let _ = fs::remove_dir_all(to.join(d));
        }
        for f in FILES {
            let _ = fs::remove_file(to.join(f));
        }
    }
    done
}
