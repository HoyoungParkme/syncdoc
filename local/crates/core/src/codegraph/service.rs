//! CodeGraphService — SYNC-MS-022 (파이썬 판 SYNC-MS-011 `CodeGraphService`와 같은 이름·같은 처리). code_graphs 한 행.
//! 성공하면 통째로 바꿔 끼우고, 실패하면 옛 그래프를 두고 이유만 남긴다

use std::path::Path;

use serde_json::Value;
use sqlx::PgConnection;

use super::model::CodeGraphRow;
use super::repo;
use crate::clock;
use crate::errors::Problem;
use crate::infra::git::Git;
use crate::pycompat::chars::py_splitlines;
use crate::types::CodeText;

/// 한 번에 읽는 줄 상한 — 코드 탭과 질문 탭 `read_code`가 같이 (2026-09-30 사용자 결정)
const MAX_LINES: i64 = 300;
/// 커밋돼 있어도 읽어 주지 않는 이름 — 키·인증서·비밀 설정 (파이썬 `DENY`, 여기 한곳에 둔다)
pub(crate) const DENY: [&str; 6] = [".env*", "*.pem", "*.key", "id_rsa*", "*.p12", "*secret*"];

/// 파이썬 `fnmatch` — `*`·`?`만(위 꼴에 쓰는 것)
fn fnmatch(name: &[char], pat: &[char]) -> bool {
    match pat.split_first() {
        None => name.is_empty(),
        Some(('*', rest)) => (0..=name.len()).any(|i| fnmatch(&name[i..], rest)),
        Some(('?', rest)) => !name.is_empty() && fnmatch(&name[1..], rest),
        Some((c, rest)) => name.first() == Some(c) && fnmatch(&name[1..], rest),
    }
}

/// 이름(소문자로)이 비밀 꼴인가 — 코드 읽기와 코드 올리기가 같이 쓴다
pub(crate) fn secret(name: &str) -> bool {
    let name: Vec<char> = name.to_lowercase().chars().collect();
    DENY.iter()
        .any(|pat| fnmatch(&name, &pat.chars().collect::<Vec<_>>()))
}

/// 파이썬 `PurePosixPath(p)` — (절대인가, 조각들). 빈 조각·`.`은 버린다
fn pure_posix(p: &str) -> (bool, Vec<&str>) {
    let absolute = p.starts_with('/');
    let parts = p
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();
    (absolute, parts)
}

fn not_found(resource: &str, id: &str) -> Problem {
    Problem::NotFound {
        resource: resource.to_string(),
        id: Value::String(id.to_string()),
    }
}

/// 코드 그래프 서비스 — 연결을 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10)
pub struct CodeGraphService<'c> {
    pub db: &'c mut PgConnection,
}

impl CodeGraphService<'_> {
    /// SYNC-MS-022#CodeGraphService.get
    pub async fn get(&mut self, project_id: i32) -> Result<Option<CodeGraphRow>, Problem> {
        repo::get(&mut *self.db, project_id).await
    }

    /// SYNC-MS-022#CodeGraphService.value
    ///
    /// 저장된 그래프 값 그대로 — 흐름 키는 `Graph` 밖이라 따로 읽는다(SYNC-MS-026 0장)
    pub async fn value(&mut self, project_id: i32) -> Result<Option<Value>, Problem> {
        repo::value(&mut *self.db, project_id).await
    }

    /// SYNC-MS-022#CodeGraphService.save
    ///
    /// 한 행을 한 번에 바꿔 끼운다 — 반쯤 바뀐 그래프를 읽는 일이 없다. 앞의 실패 이유는 지운다
    pub async fn save(
        &mut self,
        project_id: i32,
        commit_hash: &str,
        source: &str,
        graph: &Value,
    ) -> Result<CodeGraphRow, Problem> {
        repo::put(
            &mut *self.db,
            project_id,
            commit_hash,
            source,
            graph,
            clock::now(),
        )
        .await
    }

    /// SYNC-MS-022#CodeGraphService.fail
    ///
    /// 옛 그래프·커밋·출처는 그대로 — 이유만. 첫 빌드부터 실패했으면 빈 그래프로 행을 만든다
    pub async fn fail(
        &mut self,
        project_id: i32,
        commit_hash: &str,
        reason: &str,
    ) -> Result<CodeGraphRow, Problem> {
        let head: String = commit_hash.chars().take(7).collect();
        let error: String = format!("{head}: {reason}").chars().take(300).collect();
        repo::put_error(&mut *self.db, project_id, &error, clock::now()).await
    }

    /// SYNC-MS-022#CodeGraphService.read
    ///
    /// 그래프를 만든 커밋의 **커밋된 파일만** 읽는다 — 작업 사본·.gitignore 파일은 못 본다.
    /// 비밀 꼴·저장소 밖 경로는 없는 파일과 **같은** not-found — 있는지가 새지 않게
    pub async fn read(
        &mut self,
        git: &Git,
        project_id: i32,
        origin: &Path,
        path: &str,
        start: i64,
        end: Option<i64>,
    ) -> Result<CodeText, Problem> {
        let row = self.get(project_id).await?;
        let Some(commit) = row.and_then(|r| r.commit_hash) else {
            return Err(not_found("code_graph", &project_id.to_string()));
        };
        let posix = path.replace('\\', "/");
        let (absolute, parts) = pure_posix(&posix);
        if absolute || parts.contains(&"..") || parts.is_empty() {
            return Err(not_found("file", path));
        }
        if secret(parts.last().copied().unwrap_or("")) {
            return Err(not_found("file", path));
        }
        let rel = parts.join("/");
        let text = match git.read(origin, &rel, &commit).await {
            Ok(t) => t,
            Err(_) => return Err(not_found("file", path)),
        };
        let lines = py_splitlines(&text);
        let n = lines.len() as i64;
        let first = start.max(1);
        let mut last = n.min(end.filter(|e| *e != 0).unwrap_or(n));
        let truncated = last - first + 1 > MAX_LINES;
        if truncated {
            last = first + MAX_LINES - 1;
        }
        // 파이썬 `lines[first - 1 : last]` — 범위 밖은 비고, 끝이 앞보다 작으면 빈 것
        let lo = (first - 1).clamp(0, n) as usize;
        let hi = (last.clamp(0, n) as usize).max(lo);
        Ok(CodeText {
            path: rel,
            start: first,
            end: last,
            commit_hash: commit,
            text: lines[lo..hi].join("\n"),
            truncated,
        })
    }

    /// SYNC-MS-022#CodeGraphService.delete_by_project
    ///
    /// 소유 판정은 부르는 쪽이 했다
    pub async fn delete_by_project(&mut self, project_id: i32) -> Result<(), Problem> {
        repo::delete_by_project(&mut *self.db, project_id).await
    }
}
