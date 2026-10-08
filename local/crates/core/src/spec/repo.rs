//! documents·items·versions 조회 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use std::collections::HashMap;

use sqlx::PgConnection;

use super::model::DocumentRow;

const DOCUMENT_COLUMNS: &str = "id, project_id, doc_id, doc_type, status, current_body, \
     current_version_no, has_convention_error, convention_error_detail, incomplete_warnings, \
     trashed_at, trashed_by_user_id, updated_at";

/// 문서 ID로 — 프로젝트를 가리지 않는다(문서 ID는 전체에서 하나)
pub async fn document_by_doc_id(
    db: &mut PgConnection,
    doc_id: &str,
) -> Result<Option<DocumentRow>, sqlx::Error> {
    sqlx::query_as::<_, DocumentRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {DOCUMENT_COLUMNS} FROM documents WHERE doc_id = $1"
    )))
    .bind(doc_id)
    .fetch_optional(db)
    .await
}

/// 지운 항목의 ID — `item.reused`가 본다
pub async fn deleted_item_ids(
    db: &mut PgConnection,
    document_id: i32,
) -> Result<Vec<String>, sqlx::Error> {
    sqlx::query_scalar::<_, String>(
        "SELECT item_id FROM items WHERE document_id = $1 AND is_deleted ORDER BY id",
    )
    .bind(document_id)
    .fetch_all(db)
    .await
}

/// 판 번호 → 본문 — 없는 판은 지도에 없다
pub async fn version_bodies(
    db: &mut PgConnection,
    document_id: i32,
    nos: &[i32],
) -> Result<HashMap<i32, String>, sqlx::Error> {
    let rows = sqlx::query_as::<_, (i32, String)>(
        "SELECT version_no, body FROM versions WHERE document_id = $1 AND version_no = ANY($2)",
    )
    .bind(document_id)
    .bind(nos)
    .fetch_all(db)
    .await?;
    Ok(rows.into_iter().collect())
}
