//! documents·items·versions 조회 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use std::collections::HashMap;

use sqlx::PgConnection;
use time::OffsetDateTime;

use super::model::{DocumentRow, ItemRow, VersionRow};

const ITEM_COLUMNS: &str = "id, document_id, item_id, display_name, is_deleted, deleted_at";
const VERSION_COLUMNS: &str = "id, document_id, version_no, commit_hash, body, author_kind, \
     author_user_id, instructed_by_user_id, via, message, created_at";

/// 항목 행 + 그 문서의 ID
#[derive(Debug, sqlx::FromRow)]
pub struct ItemDocRow {
    #[sqlx(flatten)]
    pub item: ItemRow,
    pub doc_id: String,
}

/// 새 문서 행의 값 — 판 1
pub struct NewDocument<'a> {
    pub project_id: i32,
    pub doc_id: &'a str,
    pub doc_type: &'a str,
    pub status: &'a str,
    pub body: &'a str,
    pub has_convention_error: bool,
    pub convention_error_detail: Option<&'a str>,
    pub incomplete_warnings: Option<&'a str>,
}

/// 새 판 행의 값
pub struct NewVersion<'a> {
    pub document_id: i32,
    pub version_no: i32,
    pub commit_hash: &'a str,
    pub body: &'a str,
    pub author_kind: &'a str,
    pub author_user_id: i32,
    pub instructed_by_user_id: Option<i32>,
    pub via: &'a str,
    pub message: &'a str,
    pub created_at: OffsetDateTime,
}

/// 새 상태 변경 행의 값
pub struct NewStatusChange<'a> {
    pub document_id: i32,
    pub from_status: Option<&'a str>,
    pub to_status: &'a str,
    pub changed_by_user_id: i32,
    pub via: &'a str,
    pub reason: Option<&'a str>,
    pub commit_hash: Option<&'a str>,
    pub changed_at: OffsetDateTime,
}

/// 저장한 문서 행의 새 값 — 휴지통에서 나오고 갱신 시각은 DB의 `now()`(파이썬 `onupdate=func.now()`)
pub struct SavedDocument<'a> {
    pub id: i32,
    pub body: &'a str,
    pub version_no: i32,
    pub status: &'a str,
    pub has_convention_error: bool,
    pub convention_error_detail: Option<&'a str>,
    pub incomplete_warnings: Option<&'a str>,
}

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

/// 프로젝트의 문서 — 휴지통 것까지(거르기는 서비스가)
pub async fn documents_of_project(
    db: &mut PgConnection,
    project_id: i32,
) -> Result<Vec<DocumentRow>, sqlx::Error> {
    sqlx::query_as::<_, DocumentRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {DOCUMENT_COLUMNS} FROM documents WHERE project_id = $1"
    )))
    .bind(project_id)
    .fetch_all(db)
    .await
}

/// 문서마다 최근 버전 하나 — 쿼리 한 번
pub async fn latest_versions(
    db: &mut PgConnection,
    document_ids: &[i32],
) -> Result<HashMap<i32, VersionRow>, sqlx::Error> {
    if document_ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows = sqlx::query_as::<_, VersionRow>(
        "SELECT v.id, v.document_id, v.version_no, v.commit_hash, v.body, v.author_kind, v.author_user_id, \
         v.instructed_by_user_id, v.via, v.message, v.created_at FROM versions v \
         JOIN (SELECT document_id, max(version_no) AS no FROM versions WHERE document_id = ANY($1) \
         GROUP BY document_id) l ON v.document_id = l.document_id AND v.version_no = l.no",
    )
    .bind(document_ids)
    .fetch_all(db)
    .await?;
    Ok(rows.into_iter().map(|v| (v.document_id, v)).collect())
}

/// 문서 pk로
pub async fn document_by_id(
    db: &mut PgConnection,
    id: i32,
) -> Result<Option<DocumentRow>, sqlx::Error> {
    sqlx::query_as::<_, DocumentRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {DOCUMENT_COLUMNS} FROM documents WHERE id = $1"
    )))
    .bind(id)
    .fetch_optional(db)
    .await
}

/// 문서 pk 여럿으로 — 차례 없음
pub async fn documents_by_ids(
    db: &mut PgConnection,
    ids: &[i32],
) -> Result<Vec<DocumentRow>, sqlx::Error> {
    sqlx::query_as::<_, DocumentRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {DOCUMENT_COLUMNS} FROM documents WHERE id = ANY($1)"
    )))
    .bind(ids)
    .fetch_all(db)
    .await
}

/// 프로젝트에서 그 타입 문서의 ID — 휴지통 것까지 (문서 ID 발급)
pub async fn doc_ids_of_type(
    db: &mut PgConnection,
    project_id: i32,
    doc_type: &str,
) -> Result<Vec<String>, sqlx::Error> {
    sqlx::query_scalar::<_, String>(
        "SELECT doc_id FROM documents WHERE project_id = $1 AND doc_type = $2",
    )
    .bind(project_id)
    .bind(doc_type)
    .fetch_all(db)
    .await
}

/// 문서의 항목 — id 차례. `include_deleted`가 아니면 지운 것은 뺀다
pub async fn items_of(
    db: &mut PgConnection,
    document_id: i32,
    include_deleted: bool,
) -> Result<Vec<ItemRow>, sqlx::Error> {
    sqlx::query_as::<_, ItemRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {ITEM_COLUMNS} FROM items WHERE document_id = $1 AND ($2 OR NOT is_deleted) ORDER BY id"
    )))
    .bind(document_id)
    .bind(include_deleted)
    .fetch_all(db)
    .await
}

/// 문서의 항목 하나 — 지운 것까지
pub async fn item_of(
    db: &mut PgConnection,
    document_id: i32,
    item_id: &str,
) -> Result<Option<ItemRow>, sqlx::Error> {
    sqlx::query_as::<_, ItemRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {ITEM_COLUMNS} FROM items WHERE document_id = $1 AND item_id = $2"
    )))
    .bind(document_id)
    .bind(item_id)
    .fetch_optional(db)
    .await
}

/// 항목 pk 여럿 + 그 문서 ID — 쿼리 한 번
pub async fn items_with_doc_id(
    db: &mut PgConnection,
    pks: &[i32],
) -> Result<Vec<ItemDocRow>, sqlx::Error> {
    sqlx::query_as::<_, ItemDocRow>(
        "SELECT i.id, i.document_id, i.item_id, i.display_name, i.is_deleted, i.deleted_at, d.doc_id \
         FROM items i JOIN documents d ON d.id = i.document_id WHERE i.id = ANY($1)",
    )
    .bind(pks)
    .fetch_all(db)
    .await
}

/// 문서의 최근 판
pub async fn latest_version(
    db: &mut PgConnection,
    document_id: i32,
) -> Result<Option<VersionRow>, sqlx::Error> {
    sqlx::query_as::<_, VersionRow>(sqlx::AssertSqlSafe(format!(
        "SELECT {VERSION_COLUMNS} FROM versions WHERE document_id = $1 ORDER BY version_no DESC LIMIT 1"
    )))
    .bind(document_id)
    .fetch_optional(db)
    .await
}

/// 문서 행을 넣는다 — 판 1, 갱신 시각은 DB 기본값
pub async fn insert_document(
    db: &mut PgConnection,
    d: &NewDocument<'_>,
) -> Result<i32, sqlx::Error> {
    sqlx::query_scalar::<_, i32>(
        "INSERT INTO documents (project_id, doc_id, doc_type, status, current_body, current_version_no, \
         has_convention_error, convention_error_detail, incomplete_warnings) \
         VALUES ($1, $2, $3, $4, $5, 1, $6, $7, $8) RETURNING id",
    )
    .bind(d.project_id)
    .bind(d.doc_id)
    .bind(d.doc_type)
    .bind(d.status)
    .bind(d.body)
    .bind(d.has_convention_error)
    .bind(d.convention_error_detail)
    .bind(d.incomplete_warnings)
    .fetch_one(db)
    .await
}

/// 저장한 문서 행을 고친다
pub async fn update_saved_document(
    db: &mut PgConnection,
    d: &SavedDocument<'_>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE documents SET current_body = $2, current_version_no = $3, status = $4, \
         has_convention_error = $5, convention_error_detail = $6, incomplete_warnings = $7, \
         trashed_at = NULL, trashed_by_user_id = NULL, updated_at = now() WHERE id = $1",
    )
    .bind(d.id)
    .bind(d.body)
    .bind(d.version_no)
    .bind(d.status)
    .bind(d.has_convention_error)
    .bind(d.convention_error_detail)
    .bind(d.incomplete_warnings)
    .execute(db)
    .await?;
    Ok(())
}

/// 항목 행을 넣는다
pub async fn insert_item(
    db: &mut PgConnection,
    document_id: i32,
    item_id: &str,
    display_name: &str,
) -> Result<i32, sqlx::Error> {
    sqlx::query_scalar::<_, i32>(
        "INSERT INTO items (document_id, item_id, display_name) VALUES ($1, $2, $3) RETURNING id",
    )
    .bind(document_id)
    .bind(item_id)
    .bind(display_name)
    .fetch_one(db)
    .await
}

/// 본문에 다시 나타난 항목 — 이름을 고치고 되살린다
pub async fn restore_item(
    db: &mut PgConnection,
    pk: i32,
    display_name: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE items SET display_name = $2, is_deleted = false, deleted_at = NULL WHERE id = $1",
    )
    .bind(pk)
    .bind(display_name)
    .execute(db)
    .await?;
    Ok(())
}

/// 항목을 지운 것으로
pub async fn mark_item_deleted(
    db: &mut PgConnection,
    pk: i32,
    at: OffsetDateTime,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE items SET is_deleted = true, deleted_at = $2 WHERE id = $1")
        .bind(pk)
        .bind(at)
        .execute(db)
        .await?;
    Ok(())
}

/// 판 행을 넣는다
pub async fn insert_version(
    db: &mut PgConnection,
    v: &NewVersion<'_>,
) -> Result<VersionRow, sqlx::Error> {
    sqlx::query_as::<_, VersionRow>(sqlx::AssertSqlSafe(format!(
        "INSERT INTO versions (document_id, version_no, commit_hash, body, author_kind, author_user_id, \
         instructed_by_user_id, via, message, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) \
         RETURNING {VERSION_COLUMNS}"
    )))
    .bind(v.document_id)
    .bind(v.version_no)
    .bind(v.commit_hash)
    .bind(v.body)
    .bind(v.author_kind)
    .bind(v.author_user_id)
    .bind(v.instructed_by_user_id)
    .bind(v.via)
    .bind(v.message)
    .bind(v.created_at)
    .fetch_one(db)
    .await
}

/// 상태 변경 행을 넣는다
pub async fn insert_status_change(
    db: &mut PgConnection,
    c: &NewStatusChange<'_>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO status_changes (document_id, from_status, to_status, changed_by_user_id, via, reason, \
         commit_hash, changed_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
    )
    .bind(c.document_id)
    .bind(c.from_status)
    .bind(c.to_status)
    .bind(c.changed_by_user_id)
    .bind(c.via)
    .bind(c.reason)
    .bind(c.commit_hash)
    .bind(c.changed_at)
    .execute(db)
    .await?;
    Ok(())
}
