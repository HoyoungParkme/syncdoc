//! projects·repositories 조회·저장 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use sqlx::{AssertSqlSafe, PgConnection};
use time::OffsetDateTime;

use super::model::{ProjectRow, RepositoryRow};

const PROJECT: &str = "id, code, name, created_at, owner_user_id";
const REPOSITORY: &str = "id, project_id, remote_url, workdir_path, last_processed_commit, synced_at, \
     registered_by_user_id, storage, hook_id, hook_error, fetch_error, behind_by, fetched_at";

async fn repository_of(
    db: &mut PgConnection,
    project_id: i32,
) -> Result<Option<RepositoryRow>, sqlx::Error> {
    sqlx::query_as::<_, RepositoryRow>(AssertSqlSafe(format!(
        "SELECT {REPOSITORY} FROM repositories WHERE project_id = $1"
    )))
    .bind(project_id)
    .fetch_optional(db)
    .await
}

/// 코드로 — 저장소 행까지. 저장소가 없는 프로젝트는 없는 것과 같다
pub async fn by_code(
    db: &mut PgConnection,
    code: &str,
) -> Result<Option<(ProjectRow, RepositoryRow)>, sqlx::Error> {
    let p = sqlx::query_as::<_, ProjectRow>(AssertSqlSafe(format!(
        "SELECT {PROJECT} FROM projects WHERE code = $1"
    )))
    .bind(code)
    .fetch_optional(&mut *db)
    .await?;
    let Some(p) = p else { return Ok(None) };
    Ok(repository_of(db, p.id).await?.map(|r| (p, r)))
}

/// 소유자의 프로젝트 — 코드 차례
pub async fn owned_by(
    db: &mut PgConnection,
    user_id: i32,
) -> Result<Vec<(ProjectRow, RepositoryRow)>, sqlx::Error> {
    let ps = sqlx::query_as::<_, ProjectRow>(AssertSqlSafe(format!(
        "SELECT {PROJECT} FROM projects WHERE owner_user_id = $1 ORDER BY code"
    )))
    .bind(user_id)
    .fetch_all(&mut *db)
    .await?;
    let mut out = Vec::with_capacity(ps.len());
    for p in ps {
        if let Some(r) = repository_of(db, p.id).await? {
            out.push((p, r));
        }
    }
    Ok(out)
}

pub async fn exists(db: &mut PgConnection, code: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>("SELECT EXISTS (SELECT 1 FROM projects WHERE code = $1)")
        .bind(code)
        .fetch_one(db)
        .await
}

pub async fn add_project(
    db: &mut PgConnection,
    code: &str,
    name: &str,
    owner_user_id: i32,
) -> Result<ProjectRow, sqlx::Error> {
    sqlx::query_as::<_, ProjectRow>(AssertSqlSafe(format!(
        "INSERT INTO projects (code, name, owner_user_id) VALUES ($1, $2, $3) RETURNING {PROJECT}"
    )))
    .bind(code)
    .bind(name)
    .bind(owner_user_id)
    .fetch_one(db)
    .await
}

pub async fn add_repository(
    db: &mut PgConnection,
    project_id: i32,
    storage: &str,
    remote_url: &str,
    workdir_path: &str,
    registered_by_user_id: i32,
) -> Result<RepositoryRow, sqlx::Error> {
    sqlx::query_as::<_, RepositoryRow>(AssertSqlSafe(format!(
        "INSERT INTO repositories (project_id, storage, remote_url, workdir_path, registered_by_user_id) \
         VALUES ($1, $2, $3, $4, $5) RETURNING {REPOSITORY}"
    )))
    .bind(project_id)
    .bind(storage)
    .bind(remote_url)
    .bind(workdir_path)
    .bind(registered_by_user_id)
    .fetch_one(db)
    .await
}

pub async fn set_last_processed(
    db: &mut PgConnection,
    repository_id: i32,
    commit: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE repositories SET last_processed_commit = $2 WHERE id = $1")
        .bind(repository_id)
        .bind(commit)
        .execute(db)
        .await?;
    Ok(())
}

/// 프로젝트에 딸린 행을 자식부터 지운다 (MS-013 delete_project 2) — 대화(턴·첨부는 FK로)·코드 그래프부터
pub async fn delete_all_of(db: &mut PgConnection, project_id: i32) -> Result<(), sqlx::Error> {
    for stmt in [
        "DELETE FROM conversations WHERE project_id = $1",
        "DELETE FROM code_graphs WHERE project_id = $1",
        r#"DELETE FROM "references" WHERE from_document_id IN (SELECT id FROM documents WHERE project_id = $1)"#,
        r#"DELETE FROM "references" WHERE to_document_id IN (SELECT id FROM documents WHERE project_id = $1)"#,
        r#"DELETE FROM "references" WHERE to_item_id IN (SELECT id FROM items WHERE document_id IN (SELECT id FROM documents WHERE project_id = $1))"#,
        "DELETE FROM status_changes WHERE document_id IN (SELECT id FROM documents WHERE project_id = $1)",
        "DELETE FROM items WHERE document_id IN (SELECT id FROM documents WHERE project_id = $1)",
        "DELETE FROM versions WHERE document_id IN (SELECT id FROM documents WHERE project_id = $1)",
        "DELETE FROM documents WHERE project_id = $1",
        "DELETE FROM repositories WHERE project_id = $1",
        "DELETE FROM projects WHERE id = $1",
    ] {
        sqlx::query(stmt).bind(project_id).execute(&mut *db).await?;
    }
    Ok(())
}

/// 저장소의 처리 지점 — 행이 없으면 None
pub async fn last_processed_of(
    db: &mut PgConnection,
    repository_id: i32,
) -> Result<Option<Option<String>>, sqlx::Error> {
    sqlx::query_scalar::<_, Option<String>>(
        "SELECT last_processed_commit FROM repositories WHERE id = $1",
    )
    .bind(repository_id)
    .fetch_optional(db)
    .await
}

/// 방금 받아 와 밀린 것이 없다 — 화면이 보여줄 「확인한 시각」
pub async fn set_fetched(
    db: &mut PgConnection,
    repository_id: i32,
    at: OffsetDateTime,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE repositories SET behind_by = 0, fetched_at = $2 WHERE id = $1")
        .bind(repository_id)
        .bind(at)
        .execute(db)
        .await?;
    Ok(())
}

/// 처리 지점을 앞당긴다 — 앱이 민 커밋은 그 저장이 곧 처리다
pub async fn advance_processed(
    db: &mut PgConnection,
    repository_id: i32,
    commit: &str,
    at: OffsetDateTime,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE repositories SET last_processed_commit = $2, synced_at = $3 WHERE id = $1")
        .bind(repository_id)
        .bind(commit)
        .bind(at)
        .execute(db)
        .await?;
    Ok(())
}
