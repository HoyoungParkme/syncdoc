//! ProjectService — SYNC-MS-013 (파이썬 판 SYNC-MS-001의 서버 저장 갈래와 같은 처리).
//! 싱크독_로컬은 서버 저장뿐이다 — 서버 저장소 `origins/{code}.git`, 작업 사본 `repos/{code}`,
//! 지우면 `origins/_archive/{code}-{UTC}.git`으로 보관한다(지우지 않는다).

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, LazyLock, Mutex};

use sqlx::{Connection, PgConnection};

use super::model::{ProjectRow, RepositoryRow};
use super::repo;
use crate::account::model::UserRow;
use crate::clock;
use crate::errors::Problem;
use crate::infra::git::Git;
use crate::pycompat::chars::strip;
use crate::types::Storage;

/// 서버 저장소 자리 — git·서버 저장소·작업 사본·README의 규약 주소. 켤 때 `runtime.run`이 만든다
#[derive(Clone, Debug)]
pub struct ServerRepos {
    pub git: Git,
    pub origins: PathBuf,
    pub repos: PathBuf,
    pub specs_url: String,
}

/// 코드마다 잠금 (MS-001 0 · UC-A1 2c) — 같은 코드의 만들기·지우기가 서로의 작업 사본을 지우지 않게
static LOCKS: LazyLock<Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn lock_of(code: &str) -> Arc<tokio::sync::Mutex<()>> {
    let mut map = LOCKS
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    map.entry(code.to_string()).or_default().clone()
}

/// 프로젝트 코드 — `[A-Z]{1,4}` 전체
fn valid_code(code: &str) -> bool {
    (1..=4).contains(&code.chars().count()) && code.chars().all(|c| c.is_ascii_uppercase())
}

/// 보관본 이름의 (시각, 번호) — 꼴이 다르면 가장 오래된 것으로
fn archive_key(name: &str, code: &str) -> (String, u64, String) {
    let rest = name
        .strip_prefix(code)
        .and_then(|r| r.strip_prefix('-'))
        .and_then(|r| r.strip_suffix(".git"))
        .unwrap_or("");
    let (stamp, n) = rest.split_once('-').unwrap_or((rest, ""));
    let digits = |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit());
    if stamp.len() == 14 && digits(stamp) && (n.is_empty() || digits(n)) {
        let n = if n.is_empty() {
            0
        } else {
            n.parse().unwrap_or(u64::MAX)
        };
        (stamp.to_string(), n, name.to_string())
    } else {
        (String::new(), 0, name.to_string())
    }
}

/// 보관본 이름의 시각 → 파이썬 `isoformat()`(UTC). 읽을 수 없으면 이름 그대로
fn archived_at(path: &Path, code: &str) -> String {
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let stamp: String = name
        .chars()
        .skip(code.chars().count() + 1)
        .take(14)
        .collect();
    let fmt = time::macros::format_description!("[year][month][day][hour][minute][second]");
    match time::PrimitiveDateTime::parse(&stamp, &fmt) {
        Ok(t) if stamp.len() == 14 => {
            let out = time::macros::format_description!(
                "[year]-[month]-[day]T[hour]:[minute]:[second]+00:00"
            );
            t.format(&out).unwrap_or(name)
        }
        _ => name,
    }
}

/// 프로젝트 서비스 — 연결과 저장소 자리를 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10)
pub struct ProjectService<'c> {
    pub db: &'c mut PgConnection,
    pub repos: &'c ServerRepos,
}

impl ProjectService<'_> {
    fn archive_dir(&self) -> PathBuf {
        self.repos.origins.join("_archive")
    }

    /// 그 코드의 보관본 — (UTC 시각, 번호) 순이라 끝이 가장 최근이다 (#349)
    fn archives(&self, code: &str) -> Vec<PathBuf> {
        let Ok(entries) = fs::read_dir(self.archive_dir()) else {
            return Vec::new();
        };
        let prefix = format!("{code}-");
        let mut found: Vec<(PathBuf, (String, u64, String))> = entries
            .filter_map(Result::ok)
            .filter_map(|e| {
                let name = e.file_name().to_string_lossy().into_owned();
                (name.starts_with(&prefix)
                    && name.ends_with(".git")
                    && name.len() >= prefix.len() + 4)
                    .then(|| (e.path(), archive_key(&name, code)))
            })
            .collect();
        found.sort_by(|a, b| a.1.cmp(&b.1));
        found.into_iter().map(|(p, _)| p).collect()
    }

    /// 보관할 자리 `_archive/{code}-{UTC %Y%m%d%H%M%S}.git` — 같은 초에 있으면 뒤에 번호
    fn archive_path(&self, code: &str) -> Result<PathBuf, Problem> {
        let dir = self.archive_dir();
        fs::create_dir_all(&dir)?;
        let fmt = time::macros::format_description!("[year][month][day][hour][minute][second]");
        let stamp = clock::now()
            .to_offset(time::UtcOffset::UTC)
            .format(&fmt)
            .map_err(|e| Problem::Internal {
                log: format!("보관 시각: {e}"),
            })?;
        let mut path = dir.join(format!("{code}-{stamp}.git"));
        let mut n = 1;
        while path.exists() {
            path = dir.join(format!("{code}-{stamp}-{n}.git"));
            n += 1;
        }
        Ok(path)
    }

    /// init_project 4 — 서버 저장소를 준비한다. (원본, 되살린 보관본의 원래 자리)
    async fn server_origin(
        &self,
        code: &str,
        import_existing: bool,
    ) -> Result<(PathBuf, Option<PathBuf>), Problem> {
        let origin = self.repos.origins.join(format!("{code}.git"));
        if origin.exists() {
            // 등록되지 않은 원본(지난 실패, 사람이 넣은 것) — 지우지 않고 보관한다
            fs::rename(&origin, self.archive_path(code)?)?;
        }
        if let Some(latest) = self.archives(code).pop() {
            if !import_existing {
                let n = match self
                    .repos
                    .git
                    .list(&latest, "docs/specs/*/*.md", "HEAD")
                    .await
                {
                    Ok(v) => v.len() as i64,
                    Err(Problem::Git { .. }) => 0, // 커밋이 하나도 없는 원본
                    Err(other) => return Err(other),
                };
                return Err(Problem::ExistingSpecs {
                    doc_count: n,
                    archived_at: Some(archived_at(&latest, code)),
                });
            }
            fs::rename(&latest, &origin)?; // 가장 최근 것을 되살린다
            return Ok((origin, Some(latest)));
        }
        self.repos.git.init_bare(&origin).await?;
        Ok((origin, None))
    }

    /// SYNC-MS-013#ProjectService.init_project
    pub async fn init_project(
        &mut self,
        code: &str,
        name: &str,
        user: &UserRow,
        import_existing: bool,
        storage: Storage,
    ) -> Result<(ProjectRow, RepositoryRow), Problem> {
        let lock = lock_of(code);
        let _held = lock.lock().await;
        if storage != Storage::Server {
            return Err(Problem::StorageUnavailable {
                storage: storage.as_str().to_string(),
                enabled: vec!["server".to_string()],
            });
        }
        if !valid_code(code) {
            return Err(Problem::ProjectCodeInvalid {
                rule: "^[A-Z]{1,4}$".to_string(),
            });
        }
        if repo::exists(&mut *self.db, code).await? {
            return Err(Problem::ProjectCodeConflict {
                code: code.to_string(),
            });
        }
        let workdir = self.repos.repos.join(code);
        let _ = fs::remove_dir_all(&workdir); // 지난 실패 잔재
        let (origin, restored) = self.server_origin(code, import_existing).await?;
        // 되돌림 — 새로 만든 원본은 지우고, 되살린 것은 보관 자리로 돌려놓는다
        let undo_origin = || match &restored {
            Some(back) => {
                let _ = fs::rename(&origin, back);
            }
            None => {
                let _ = fs::remove_dir_all(&origin);
            }
        };
        let remote = origin.to_string_lossy().into_owned();
        if let Err(p) = self.repos.git.clone(&remote, &workdir).await {
            let _ = fs::remove_dir_all(&workdir);
            undo_origin();
            return Err(match p {
                Problem::Git { stderr, .. } => Problem::PushFailed {
                    reason: format!("clone: {}", strip(&stderr)),
                },
                other => other,
            });
        }
        let has = self.repos.git.exists(&workdir, "docs/specs").await?;
        if has && !import_existing {
            let n = self
                .repos
                .git
                .list(&workdir, "docs/specs/*/*.md", "HEAD")
                .await?
                .len() as i64;
            let _ = fs::remove_dir_all(&workdir);
            undo_origin();
            return Err(Problem::ExistingSpecs {
                doc_count: n,
                archived_at: None,
            });
        }
        let mut tx = self.db.begin().await?;
        let project = repo::add_project(&mut tx, code, name, user.id).await?;
        let repository = repo::add_repository(
            &mut tx,
            project.id,
            Storage::Server.as_str(),
            &remote,
            &workdir.to_string_lossy(),
            user.id,
        )
        .await?;
        if has {
            // 되살린 보관본의 명세를 재구축으로 올리는 갈래 — 카드 L11
            tx.rollback().await?;
            let _ = fs::remove_dir_all(&workdir);
            undo_origin();
            return Err(Problem::NotImplemented {
                card: "L11".to_string(),
            });
        }
        let files = Git::init_specs(&self.repos.specs_url);
        let message = format!("chore({code}): init syncdoc");
        let hash = match self
            .repos
            .git
            .commit_push(&workdir, &message, user, &files, &[])
            .await
        {
            Ok(h) => h,
            Err(p @ Problem::PushFailed { .. }) => {
                tx.rollback().await?;
                let _ = fs::remove_dir_all(&workdir);
                undo_origin();
                return Err(p);
            }
            Err(other) => return Err(other),
        };
        repo::set_last_processed(&mut tx, repository.id, &hash).await?;
        tx.commit().await?;
        self.get(code).await
    }

    /// SYNC-MS-013#ProjectService.delete_project
    pub async fn delete_project(&mut self, code: &str, user: &UserRow) -> Result<(), Problem> {
        let lock = lock_of(code);
        let _held = lock.lock().await;
        let (project, repository) = self.get_owned(code, user).await?;
        let workdir = PathBuf::from(&repository.workdir_path);
        let origin = PathBuf::from(&repository.remote_url);
        let server = repository.storage == Storage::Server.as_str();
        repo::delete_all_of(&mut *self.db, project.id).await?;
        let _ = fs::remove_dir_all(&workdir);
        // 서버 저장이면 원본을 지우지 않고 보관한다 — 같은 코드로 가져오면 되살아난다(L11)
        if server && origin.exists() {
            fs::rename(&origin, self.archive_path(code)?)?;
        }
        Ok(())
    }

    /// SYNC-MS-013#ProjectService.get
    pub async fn get(&mut self, code: &str) -> Result<(ProjectRow, RepositoryRow), Problem> {
        repo::by_code(&mut *self.db, code)
            .await?
            .ok_or_else(|| Problem::NotFound {
                resource: "project".to_string(),
                id: serde_json::Value::from(code),
            })
    }

    /// SYNC-MS-013#ProjectService.get_owned
    pub async fn get_owned(
        &mut self,
        code: &str,
        user: &UserRow,
    ) -> Result<(ProjectRow, RepositoryRow), Problem> {
        let (p, r) = self.get(code).await?;
        if p.owner_user_id != user.id {
            // 남의 것은 없는 것과 같은 답이다
            return Err(Problem::NotFound {
                resource: "project".to_string(),
                id: serde_json::Value::from(code),
            });
        }
        Ok((p, r))
    }

    /// SYNC-MS-013#ProjectService.list_owned
    pub async fn list_owned(
        &mut self,
        user: &UserRow,
    ) -> Result<Vec<(ProjectRow, RepositoryRow)>, Problem> {
        Ok(repo::owned_by(&mut *self.db, user.id).await?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn archive_order_and_time() {
        let mut names = vec![
            "ARC-20261008120000-10.git",
            "ARC-20261008120000.git",
            "ARC-junk.git",
            "ARC-20261008120000-2.git",
            "ARC-20261008115959.git",
            "ARC-20261008120000-1.git",
        ];
        names.sort_by_key(|n| archive_key(n, "ARC"));
        assert_eq!(
            names,
            [
                "ARC-junk.git",
                "ARC-20261008115959.git",
                "ARC-20261008120000.git",
                "ARC-20261008120000-1.git",
                "ARC-20261008120000-2.git",
                "ARC-20261008120000-10.git",
            ]
        );
        assert_eq!(
            archived_at(Path::new("/o/_archive/ARC-20261008123456-1.git"), "ARC"),
            "2026-10-08T12:34:56+00:00"
        );
        assert_eq!(
            archived_at(Path::new("ARC-junk.git"), "ARC"),
            "ARC-junk.git"
        );
        assert!(valid_code("SYNC") && !valid_code("SYNCX") && !valid_code("sy") && !valid_code(""));
    }
}
