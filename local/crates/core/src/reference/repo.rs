//! references 조회 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use std::collections::HashMap;

use sqlx::PgConnection;

use super::model::ReferenceRow;

const COLUMNS: &str = "id, from_item_id, from_document_id, to_item_id, to_document_id, raw_target, \
     is_missing, extracted_version_id";

/// 새 참조 행의 값
pub struct NewReference<'a> {
    pub from_item_id: Option<i32>,
    pub from_document_id: i32,
    pub to_item_id: Option<i32>,
    pub to_document_id: Option<i32>,
    pub raw_target: &'a str,
    pub is_missing: bool,
    pub extracted_version_id: i32,
}

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

/// 문서에서 나가는 참조 — id 차례. `include_missing`이 아니면 미존재는 뺀다
pub async fn from_document(
    db: &mut PgConnection,
    document_id: i32,
    include_missing: bool,
) -> Result<Vec<ReferenceRow>, sqlx::Error> {
    sqlx::query_as::<_, ReferenceRow>(sqlx::AssertSqlSafe(format!(
        r#"SELECT {COLUMNS} FROM "references" WHERE from_document_id = $1 AND ($2 OR NOT is_missing) ORDER BY id"#
    )))
    .bind(document_id)
    .bind(include_missing)
    .fetch_all(db)
    .await
}

/// 항목에서 나가는 참조 — id 차례 (#353)
pub async fn from_item(
    db: &mut PgConnection,
    item_pk: i32,
) -> Result<Vec<ReferenceRow>, sqlx::Error> {
    sqlx::query_as::<_, ReferenceRow>(sqlx::AssertSqlSafe(format!(
        r#"SELECT {COLUMNS} FROM "references" WHERE from_item_id = $1 ORDER BY id"#
    )))
    .bind(item_pk)
    .fetch_all(db)
    .await
}

/// 항목을 가리키는 참조 — id 차례 (#353)
pub async fn to_item(
    db: &mut PgConnection,
    item_pk: i32,
) -> Result<Vec<ReferenceRow>, sqlx::Error> {
    sqlx::query_as::<_, ReferenceRow>(sqlx::AssertSqlSafe(format!(
        r#"SELECT {COLUMNS} FROM "references" WHERE to_item_id = $1 ORDER BY id"#
    )))
    .bind(item_pk)
    .fetch_all(db)
    .await
}

/// 프로젝트의 미존재 참조 — 휴지통 문서에서 나간 것까지, id 차례. `target`이면 그 문서(또는 그 항목)를 가리키는 것만.
/// `LIKE`는 파이썬 SQLAlchemy `startswith`가 내는 SQL 그대로 — 글자를 거르지 않는다
pub async fn missing_in_project(
    db: &mut PgConnection,
    project_id: i32,
    target: Option<&str>,
) -> Result<Vec<ReferenceRow>, sqlx::Error> {
    sqlx::query_as::<_, ReferenceRow>(sqlx::AssertSqlSafe(format!(
        r#"SELECT {COLUMNS} FROM "references" WHERE is_missing
           AND from_document_id IN (SELECT id FROM documents WHERE project_id = $1)
           AND ($2::text IS NULL OR raw_target = $2 OR raw_target LIKE $2 || '#' || '%')
           ORDER BY id"#
    )))
    .bind(project_id)
    .bind(target)
    .fetch_all(db)
    .await
}

/// 그 항목들을 가리키던 참조를 미존재로 — `to_*` 둘 다 비운다(`ck_references_target`). 바뀐 행 수
pub async fn mark_missing(db: &mut PgConnection, item_pks: &[i32]) -> Result<u64, sqlx::Error> {
    Ok(sqlx::query(
        r#"UPDATE "references" SET to_item_id = NULL, to_document_id = NULL, is_missing = true
           WHERE to_item_id = ANY($1)"#,
    )
    .bind(item_pks)
    .execute(db)
    .await?
    .rows_affected())
}

/// 문서 ID → pk — 휴지통 것까지
pub async fn document_id_of(
    db: &mut PgConnection,
    doc_id: &str,
) -> Result<Option<i32>, sqlx::Error> {
    sqlx::query_scalar::<_, i32>("SELECT id FROM documents WHERE doc_id = $1")
        .bind(doc_id)
        .fetch_optional(db)
        .await
}

/// 문서의 항목 ID → pk — 지운 항목은 없다
pub async fn item_pk_of(
    db: &mut PgConnection,
    document_id: i32,
    item_id: &str,
) -> Result<Option<i32>, sqlx::Error> {
    sqlx::query_scalar::<_, i32>(
        "SELECT id FROM items WHERE document_id = $1 AND item_id = $2 AND NOT is_deleted",
    )
    .bind(document_id)
    .bind(item_id)
    .fetch_optional(db)
    .await
}

/// 참조 행을 넣는다
pub async fn insert(db: &mut PgConnection, r: &NewReference<'_>) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"INSERT INTO "references" (from_item_id, from_document_id, to_item_id, to_document_id, raw_target,
           is_missing, extracted_version_id) VALUES ($1, $2, $3, $4, $5, $6, $7)"#,
    )
    .bind(r.from_item_id)
    .bind(r.from_document_id)
    .bind(r.to_item_id)
    .bind(r.to_document_id)
    .bind(r.raw_target)
    .bind(r.is_missing)
    .bind(r.extracted_version_id)
    .execute(db)
    .await?;
    Ok(())
}

/// 참조 행을 지운다
pub async fn delete(db: &mut PgConnection, id: i32) -> Result<(), sqlx::Error> {
    sqlx::query(r#"DELETE FROM "references" WHERE id = $1"#)
        .bind(id)
        .execute(db)
        .await?;
    Ok(())
}

/// 같은 참조가 새 판에도 있다 — 뽑은 판만 바꾼다
pub async fn set_extracted(
    db: &mut PgConnection,
    id: i32,
    version_id: i32,
) -> Result<(), sqlx::Error> {
    sqlx::query(r#"UPDATE "references" SET extracted_version_id = $2 WHERE id = $1"#)
        .bind(id)
        .bind(version_id)
        .execute(db)
        .await?;
    Ok(())
}

/// 미존재 참조를 잇는다
pub async fn set_target(
    db: &mut PgConnection,
    id: i32,
    to_item_id: Option<i32>,
    to_document_id: Option<i32>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"UPDATE "references" SET to_item_id = $2, to_document_id = $3, is_missing = false WHERE id = $1"#,
    )
    .bind(id)
    .bind(to_item_id)
    .bind(to_document_id)
    .execute(db)
    .await?;
    Ok(())
}
