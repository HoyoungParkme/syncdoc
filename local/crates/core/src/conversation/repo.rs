//! conversations·turns·attachments 조회·저장 — DB만 안다 (SYNC-DOM-004 4장 · SYNC-DOM-003)

use serde_json::Value;
use sqlx::PgConnection;
use time::OffsetDateTime;

use super::model::{AttachmentRow, ConversationRow, TurnRow};
use crate::errors::Problem;
use crate::types::AttachmentMeta;

const CONV: &str = "id, project_id, user_id, title, created_at, updated_at";
const TURN: &str = "id, conversation_id, seq, question, answer, progress::text, context_item_ids::text, error, created_at";
const META: &str = "id, name, mime, size, turn_id, created_at";

type RawTurn = (
    i32,
    i32,
    i32,
    String,
    Option<String>,
    String,
    String,
    Option<String>,
    OffsetDateTime,
);

fn turn_of(r: RawTurn) -> TurnRow {
    let json = |s: &str| serde_json::from_str::<Value>(s).unwrap_or(Value::Array(Vec::new()));
    TurnRow {
        id: r.0,
        conversation_id: r.1,
        seq: r.2,
        question: r.3,
        answer: r.4,
        progress: json(&r.5),
        context_item_ids: json(&r.6),
        error: r.7,
        created_at: r.8,
    }
}

type RawMeta = (i32, String, String, i32, Option<i32>, OffsetDateTime);

fn meta_of(r: RawMeta) -> AttachmentMeta {
    AttachmentMeta {
        id: r.0,
        name: r.1,
        mime: r.2,
        size: r.3,
        turn_id: r.4,
        created_at: r.5,
    }
}

pub async fn get(db: &mut PgConnection, conv_id: i32) -> Result<Option<ConversationRow>, Problem> {
    Ok(
        sqlx::query_as::<_, ConversationRow>(sqlx::AssertSqlSafe(format!(
            "SELECT {CONV} FROM conversations WHERE id = $1"
        )))
        .bind(conv_id)
        .fetch_optional(db)
        .await?,
    )
}

/// (대화, 턴 수) — updated_at 내림차순, 같으면 id 내림차순
pub async fn list_for(
    db: &mut PgConnection,
    project_id: i32,
    user_id: i32,
) -> Result<Vec<(ConversationRow, i64)>, Problem> {
    let rows = sqlx::query_as::<_, (i32, i32, i32, String, OffsetDateTime, OffsetDateTime, i64)>(
        "SELECT c.id, c.project_id, c.user_id, c.title, c.created_at, c.updated_at,
                (SELECT count(t.id) FROM turns t WHERE t.conversation_id = c.id)
         FROM conversations c WHERE c.project_id = $1 AND c.user_id = $2
         ORDER BY c.updated_at DESC, c.id DESC",
    )
    .bind(project_id)
    .bind(user_id)
    .fetch_all(db)
    .await?;
    Ok(rows
        .into_iter()
        .map(|r| {
            (
                ConversationRow {
                    id: r.0,
                    project_id: r.1,
                    user_id: r.2,
                    title: r.3,
                    created_at: r.4,
                    updated_at: r.5,
                },
                r.6,
            )
        })
        .collect())
}

pub async fn add(
    db: &mut PgConnection,
    project_id: i32,
    user_id: i32,
    title: &str,
    at: OffsetDateTime,
) -> Result<ConversationRow, Problem> {
    Ok(
        sqlx::query_as::<_, ConversationRow>(sqlx::AssertSqlSafe(format!(
            "INSERT INTO conversations (project_id, user_id, title, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $4) RETURNING {CONV}"
        )))
        .bind(project_id)
        .bind(user_id)
        .bind(title)
        .bind(at)
        .fetch_one(db)
        .await?,
    )
}

pub async fn set_title_updated(
    db: &mut PgConnection,
    conv_id: i32,
    title: &str,
    at: OffsetDateTime,
) -> Result<(), Problem> {
    sqlx::query("UPDATE conversations SET title = $2, updated_at = $3 WHERE id = $1")
        .bind(conv_id)
        .bind(title)
        .bind(at)
        .execute(db)
        .await?;
    Ok(())
}

pub async fn touch(db: &mut PgConnection, conv_id: i32, at: OffsetDateTime) -> Result<(), Problem> {
    sqlx::query("UPDATE conversations SET updated_at = $2 WHERE id = $1")
        .bind(conv_id)
        .bind(at)
        .execute(db)
        .await?;
    Ok(())
}

pub async fn delete(db: &mut PgConnection, conv_id: i32) -> Result<(), Problem> {
    sqlx::query("DELETE FROM conversations WHERE id = $1")
        .bind(conv_id)
        .execute(db)
        .await?;
    Ok(())
}

pub async fn delete_by_project(db: &mut PgConnection, project_id: i32) -> Result<(), Problem> {
    sqlx::query("DELETE FROM conversations WHERE project_id = $1")
        .bind(project_id)
        .execute(db)
        .await?;
    Ok(())
}

/// 턴들 — seq 순
pub async fn turns(db: &mut PgConnection, conv_id: i32) -> Result<Vec<TurnRow>, Problem> {
    let rows = sqlx::query_as::<_, RawTurn>(sqlx::AssertSqlSafe(format!(
        "SELECT {TURN} FROM turns WHERE conversation_id = $1 ORDER BY seq"
    )))
    .bind(conv_id)
    .fetch_all(db)
    .await?;
    Ok(rows.into_iter().map(turn_of).collect())
}

pub async fn turn(db: &mut PgConnection, turn_id: i32) -> Result<Option<TurnRow>, Problem> {
    let row = sqlx::query_as::<_, RawTurn>(sqlx::AssertSqlSafe(format!(
        "SELECT {TURN} FROM turns WHERE id = $1"
    )))
    .bind(turn_id)
    .fetch_optional(db)
    .await?;
    Ok(row.map(turn_of))
}

pub async fn max_seq(db: &mut PgConnection, conv_id: i32) -> Result<i32, Problem> {
    let n: Option<i32> =
        sqlx::query_scalar("SELECT max(seq) FROM turns WHERE conversation_id = $1")
            .bind(conv_id)
            .fetch_one(db)
            .await?;
    Ok(n.unwrap_or(0))
}

pub async fn add_turn(
    db: &mut PgConnection,
    conv_id: i32,
    seq: i32,
    question: &str,
    at: OffsetDateTime,
) -> Result<TurnRow, Problem> {
    let row = sqlx::query_as::<_, RawTurn>(sqlx::AssertSqlSafe(format!(
        "INSERT INTO turns (conversation_id, seq, question, progress, context_item_ids, created_at)
         VALUES ($1, $2, $3, '[]'::jsonb, '[]'::jsonb, $4) RETURNING {TURN}"
    )))
    .bind(conv_id)
    .bind(seq)
    .bind(question)
    .bind(at)
    .fetch_one(db)
    .await?;
    Ok(turn_of(row))
}

/// 턴을 닫는다 — 답·오류·진행 줄·본 것
pub async fn close_turn(
    db: &mut PgConnection,
    turn_id: i32,
    answer: Option<&str>,
    error: Option<&str>,
    progress: &str,
    context_item_ids: &str,
) -> Result<(), Problem> {
    sqlx::query(
        "UPDATE turns SET answer = $2, error = $3, progress = $4::jsonb, context_item_ids = $5::jsonb
         WHERE id = $1",
    )
    .bind(turn_id)
    .bind(answer)
    .bind(error)
    .bind(progress)
    .bind(context_item_ids)
    .execute(db)
    .await?;
    Ok(())
}

/// 첨부 메타 — 바이트·글자 없이, id 순
pub async fn attachment_metas(
    db: &mut PgConnection,
    conv_id: i32,
) -> Result<Vec<AttachmentMeta>, Problem> {
    let rows = sqlx::query_as::<_, RawMeta>(sqlx::AssertSqlSafe(format!(
        "SELECT {META} FROM attachments WHERE conversation_id = $1 ORDER BY id"
    )))
    .bind(conv_id)
    .fetch_all(db)
    .await?;
    Ok(rows.into_iter().map(meta_of).collect())
}

pub async fn attachment(
    db: &mut PgConnection,
    att_id: i32,
) -> Result<Option<AttachmentRow>, Problem> {
    Ok(sqlx::query_as::<_, AttachmentRow>(
        "SELECT id, conversation_id, turn_id, user_id, name, mime, size, bytes, text_cache, created_at
         FROM attachments WHERE id = $1",
    )
    .bind(att_id)
    .fetch_optional(db)
    .await?)
}

pub async fn pending_count(db: &mut PgConnection, conv_id: i32) -> Result<i64, Problem> {
    Ok(sqlx::query_scalar(
        "SELECT count(id) FROM attachments WHERE conversation_id = $1 AND turn_id IS NULL",
    )
    .bind(conv_id)
    .fetch_one(db)
    .await?)
}

/// 새 첨부의 값
pub struct NewAttachment<'a> {
    pub conversation_id: i32,
    pub user_id: i32,
    pub name: &'a str,
    pub mime: &'a str,
    pub bytes: &'a [u8],
    pub text_cache: Option<&'a str>,
    pub created_at: OffsetDateTime,
}

pub async fn add_attachment(
    db: &mut PgConnection,
    a: NewAttachment<'_>,
) -> Result<AttachmentMeta, Problem> {
    let row = sqlx::query_as::<_, RawMeta>(sqlx::AssertSqlSafe(format!(
        "INSERT INTO attachments (conversation_id, turn_id, user_id, name, mime, size, bytes, text_cache, created_at)
         VALUES ($1, NULL, $2, $3, $4, $5, $6, $7, $8) RETURNING {META}"
    )))
    .bind(a.conversation_id)
    .bind(a.user_id)
    .bind(a.name)
    .bind(a.mime)
    .bind(a.bytes.len() as i32)
    .bind(a.bytes)
    .bind(a.text_cache)
    .bind(a.created_at)
    .fetch_one(db)
    .await?;
    Ok(meta_of(row))
}

pub async fn delete_attachment(db: &mut PgConnection, att_id: i32) -> Result<(), Problem> {
    sqlx::query("DELETE FROM attachments WHERE id = $1")
        .bind(att_id)
        .execute(db)
        .await?;
    Ok(())
}

/// 이 턴의 이미지 — id 순
pub async fn images_of_turn(
    db: &mut PgConnection,
    turn_id: i32,
) -> Result<Vec<(String, Vec<u8>)>, Problem> {
    Ok(sqlx::query_as::<_, (String, Vec<u8>)>(
        "SELECT mime, bytes FROM attachments WHERE turn_id = $1 AND mime LIKE 'image/%' ORDER BY id",
    )
    .bind(turn_id)
    .fetch_all(db)
    .await?)
}

/// 아직 안 보낸 이 대화의 첨부만 턴에 붙인다 — 남의 것·보낸 것은 건너뛴다
pub async fn attach_pending(
    db: &mut PgConnection,
    conv_id: i32,
    turn_id: i32,
    ids: &[i32],
) -> Result<(), Problem> {
    if ids.is_empty() {
        return Ok(());
    }
    sqlx::query(
        "UPDATE attachments SET turn_id = $3
         WHERE id = ANY($1) AND conversation_id = $2 AND turn_id IS NULL",
    )
    .bind(ids)
    .bind(conv_id)
    .bind(turn_id)
    .execute(db)
    .await?;
    Ok(())
}
