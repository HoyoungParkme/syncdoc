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
