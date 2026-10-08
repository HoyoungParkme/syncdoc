//! references 조회 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use std::collections::HashMap;

use sqlx::PgConnection;

/// 문서별 미존재 참조 수 — 쿼리 한 번
pub async fn count_missing_by_document(
    db: &mut PgConnection,
    document_ids: &[i32],
) -> Result<HashMap<i32, i64>, sqlx::Error> {
    let rows = sqlx::query_as::<_, (i32, i64)>(
        r#"SELECT from_document_id, count(*) FROM "references"
           WHERE from_document_id = ANY($1) AND is_missing GROUP BY from_document_id"#,
    )
    .bind(document_ids)
    .fetch_all(db)
    .await?;
    Ok(rows.into_iter().collect())
}
