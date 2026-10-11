//! code_graphs 조회·저장 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use sqlx::PgConnection;
use syncdoc_codegraph::Graph;
use time::OffsetDateTime;

use super::model::CodeGraphRow;
use crate::errors::Problem;

const COLUMNS: &str = "project_id, commit_hash, source, graph::text, function_count, call_count, \
     built_at, error";

type Raw = (
    i32,
    Option<String>,
    Option<String>,
    String,
    i32,
    i32,
    OffsetDateTime,
    Option<String>,
);

fn row(
    (project_id, commit_hash, source, graph, function_count, call_count, built_at, error): Raw,
) -> Result<CodeGraphRow, Problem> {
    let graph: Graph = serde_json::from_str(&graph).map_err(|e| Problem::Internal {
        log: format!("code_graphs {project_id}의 graph를 못 읽었다: {e}"),
    })?;
    Ok(CodeGraphRow {
        project_id,
        commit_hash,
        source,
        graph,
        function_count,
        call_count,
        built_at,
        error,
    })
}

/// 프로젝트의 행 — 없으면 없음
pub async fn get(db: &mut PgConnection, project_id: i32) -> Result<Option<CodeGraphRow>, Problem> {
    let raw = sqlx::query_as::<_, Raw>(sqlx::AssertSqlSafe(format!(
        "SELECT {COLUMNS} FROM code_graphs WHERE project_id = $1"
    )))
    .bind(project_id)
    .fetch_optional(db)
    .await?;
    raw.map(row).transpose()
}

/// 새 그래프로 — 행이 없으면 만들고 있으면 한 번에 바꿔 끼운다. 실패 이유는 지운다
pub async fn put(
    db: &mut PgConnection,
    project_id: i32,
    commit_hash: &str,
    source: &str,
    graph: &Graph,
    built_at: OffsetDateTime,
) -> Result<CodeGraphRow, Problem> {
    let body = serde_json::to_string(graph).map_err(|e| Problem::Internal {
        log: format!("그래프를 JSON으로 못 바꿨다: {e}"),
    })?;
    let raw = sqlx::query_as::<_, Raw>(sqlx::AssertSqlSafe(format!(
        "INSERT INTO code_graphs (project_id, commit_hash, source, graph, function_count, call_count, built_at, error)
         VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, NULL)
         ON CONFLICT (project_id) DO UPDATE SET commit_hash = EXCLUDED.commit_hash,
             source = EXCLUDED.source, graph = EXCLUDED.graph,
             function_count = EXCLUDED.function_count, call_count = EXCLUDED.call_count,
             built_at = EXCLUDED.built_at, error = NULL
         RETURNING {COLUMNS}"
    )))
    .bind(project_id)
    .bind(commit_hash)
    .bind(source)
    .bind(body)
    .bind(graph.functions.len() as i32)
    .bind(graph.calls.len() as i32)
    .bind(built_at)
    .fetch_one(db)
    .await?;
    row(raw)
}

/// 실패 이유만 — 옛 그래프·커밋·출처는 그대로. 행이 없으면 빈 그래프로 만든다
pub async fn put_error(
    db: &mut PgConnection,
    project_id: i32,
    error: &str,
    built_at: OffsetDateTime,
) -> Result<CodeGraphRow, Problem> {
    let raw = sqlx::query_as::<_, Raw>(sqlx::AssertSqlSafe(format!(
        r#"INSERT INTO code_graphs (project_id, graph, function_count, call_count, built_at, error)
           VALUES ($1, '{{"functions": [], "calls": []}}'::jsonb, 0, 0, $2, $3)
           ON CONFLICT (project_id) DO UPDATE SET built_at = EXCLUDED.built_at, error = EXCLUDED.error
           RETURNING {COLUMNS}"#
    )))
    .bind(project_id)
    .bind(built_at)
    .bind(error)
    .fetch_one(db)
    .await?;
    row(raw)
}

/// 프로젝트의 행을 지운다
pub async fn delete_by_project(db: &mut PgConnection, project_id: i32) -> Result<(), Problem> {
    sqlx::query("DELETE FROM code_graphs WHERE project_id = $1")
        .bind(project_id)
        .execute(db)
        .await?;
    Ok(())
}
