//! ConversationService — SYNC-MS-021 (파이썬 판 SYNC-MS-010과 같은 이름·같은 처리·같은 표). conversations·turns·attachments만.
//! 읽는 중 질의(R11)의 보관. 소유 판정은 대화의 프로젝트로 한다 — 남의 것은 있는지 없는지를 말하지 않는다

use serde_json::Value;
use sqlx::PgConnection;

use super::model::{AttachmentRow, ConversationRow, TurnRow};
use super::repo;
use crate::account::model::UserRow;
use crate::clock;
use crate::errors::Problem;
use crate::project::model::ProjectRow;
use crate::project::repo as project_repo;
use crate::project::service::{ProjectService, ServerRepos};
use crate::pycompat::chars::strip;
use crate::types::{
    AttachmentMeta, ConversationBrief, ConversationView, LlmMessage, Progress, TurnView,
};

pub const NEW_TITLE: &str = "새 대화";
const TITLE_LEN: usize = 40;
/// 첨부 종류 — 확장자로 정한다(INFRA 5.3 첨부). 이 밖은 415
const MIME_OF: [(&str, &str); 12] = [
    ("png", "image/png"),
    ("jpg", "image/jpeg"),
    ("jpeg", "image/jpeg"),
    ("webp", "image/webp"),
    ("gif", "image/gif"),
    ("md", "text/markdown"),
    ("txt", "text/plain"),
    ("csv", "text/csv"),
    ("json", "application/json"),
    ("yaml", "application/yaml"),
    ("yml", "application/yaml"),
    ("pdf", "application/pdf"),
];
const IMAGE_LIMIT: i64 = 10 * 1024 * 1024;
const TEXT_LIMIT: i64 = 1024 * 1024;
const PENDING_LIMIT: i64 = 8;

fn not_found(resource: &str, id: i64) -> Problem {
    Problem::NotFound {
        resource: resource.to_string(),
        id: Value::from(id),
    }
}

fn chars(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

/// PDF 쪽마다 글자 — 공백뿐인 쪽은 빼고 `\n\n`으로. 깨진 PDF는 `""` (파이썬 pypdf 대신 lopdf — 글자는 다를 수 있다)
fn pdf_text(data: &[u8]) -> String {
    let Ok(doc) = lopdf::Document::load_mem(data) else {
        return String::new();
    };
    let mut pages = Vec::new();
    for n in doc.get_pages().keys() {
        match doc.extract_text(&[*n]) {
            Ok(t) => pages.push(t),
            Err(_) => return String::new(),
        }
    }
    pages
        .into_iter()
        .filter(|p| !strip(p).is_empty())
        .collect::<Vec<_>>()
        .join("\n\n")
}

/// 글자 파일은 그대로(깨진 바이트는 대체 글자), PDF는 쪽마다. 이미지는 없음
fn extract_text(mime: &str, data: &[u8]) -> Option<String> {
    if mime.starts_with("image/") {
        return None;
    }
    if mime == "application/pdf" {
        return Some(pdf_text(data));
    }
    Some(String::from_utf8_lossy(data).into_owned())
}

fn progress_of(v: &Value) -> Vec<Progress> {
    serde_json::from_value(v.clone()).unwrap_or_default()
}

fn ids_of(v: &Value) -> Vec<String> {
    serde_json::from_value(v.clone()).unwrap_or_default()
}

/// 대화 서비스 — 연결을 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10)
pub struct ConversationService<'c> {
    pub db: &'c mut PgConnection,
    pub repos: &'c ServerRepos,
}

impl ConversationService<'_> {
    /// 대화 → 프로젝트 소유 판정. 없거나 남의 것이면 같은 not-found(conversation) (파이썬 `_owned`)
    async fn owned(
        &mut self,
        conv_id: i32,
        user: &UserRow,
    ) -> Result<(ConversationRow, ProjectRow), Problem> {
        let conv = repo::get(&mut *self.db, conv_id).await?;
        let project = match &conv {
            Some(c) => project_repo::by_id(&mut *self.db, c.project_id).await?,
            None => None,
        };
        match (conv, project) {
            (Some(c), Some(p)) if p.owner_user_id == user.id => Ok((c, p)),
            _ => Err(not_found("conversation", i64::from(conv_id))),
        }
    }

    /// SYNC-MS-021#ConversationService.list
    pub async fn list(
        &mut self,
        code: &str,
        user: &UserRow,
    ) -> Result<Vec<ConversationBrief>, Problem> {
        let (project, _) = ProjectService {
            db: &mut *self.db,
            repos: self.repos,
        }
        .get_owned(code, user)
        .await?;
        Ok(repo::list_for(&mut *self.db, project.id, user.id)
            .await?
            .into_iter()
            .map(|(c, n)| ConversationBrief {
                id: c.id,
                title: c.title,
                turn_count: n,
                updated_at: c.updated_at,
            })
            .collect())
    }

    /// SYNC-MS-021#ConversationService.create
    pub async fn create(
        &mut self,
        code: &str,
        user: &UserRow,
        title: Option<&str>,
    ) -> Result<ConversationRow, Problem> {
        let (project, _) = ProjectService {
            db: &mut *self.db,
            repos: self.repos,
        }
        .get_owned(code, user)
        .await?;
        let t = chars(strip(title.unwrap_or("")), TITLE_LEN * 2);
        let title = if t.is_empty() { NEW_TITLE } else { &t };
        repo::add(&mut *self.db, project.id, user.id, title, clock::now()).await
    }

    /// SYNC-MS-021#ConversationService.get
    ///
    /// 턴 전부 + 첨부 메타. 바이트·글자는 안 읽는다
    pub async fn get(&mut self, conv_id: i32, user: &UserRow) -> Result<ConversationView, Problem> {
        let (conv, project) = self.owned(conv_id, user).await?;
        let metas = repo::attachment_metas(&mut *self.db, conv.id).await?;
        let turns: Vec<TurnView> = repo::turns(&mut *self.db, conv.id)
            .await?
            .into_iter()
            .map(|t| TurnView {
                id: t.id,
                seq: t.seq,
                question: t.question,
                answer: t.answer,
                progress: progress_of(&t.progress),
                context_item_ids: ids_of(&t.context_item_ids),
                error: t.error,
                attachments: metas
                    .iter()
                    .filter(|m| m.turn_id == Some(t.id))
                    .cloned()
                    .collect(),
                created_at: t.created_at,
                missing_refs: Vec::new(),
            })
            .collect();
        Ok(ConversationView {
            id: conv.id,
            title: conv.title,
            turn_count: turns.len() as i64,
            updated_at: conv.updated_at,
            turns,
            pending: metas.into_iter().filter(|m| m.turn_id.is_none()).collect(),
            project_code: project.code,
        })
    }

    /// SYNC-MS-021#ConversationService.delete
    ///
    /// 턴·첨부는 cascade
    pub async fn delete(&mut self, conv_id: i32, user: &UserRow) -> Result<(), Problem> {
        let (conv, _) = self.owned(conv_id, user).await?;
        repo::delete(&mut *self.db, conv.id).await
    }

    /// SYNC-MS-021#ConversationService.delete_by_project
    ///
    /// 소유 판정은 부르는 쪽이 했다
    pub async fn delete_by_project(&mut self, project_id: i32) -> Result<(), Problem> {
        repo::delete_by_project(&mut *self.db, project_id).await
    }

    /// SYNC-MS-021#ConversationService.add_turn
    pub async fn add_turn(
        &mut self,
        conv_id: i32,
        question: &str,
        attachment_ids: &[i64],
    ) -> Result<TurnRow, Problem> {
        let Some(conv) = repo::get(&mut *self.db, conv_id).await? else {
            return Err(not_found("conversation", i64::from(conv_id)));
        };
        let seq = repo::max_seq(&mut *self.db, conv.id).await? + 1;
        let turn = repo::add_turn(&mut *self.db, conv.id, seq, question, clock::now()).await?;
        // int4 밖의 id는 어느 첨부와도 같지 않다
        let ids: Vec<i32> = attachment_ids
            .iter()
            .filter_map(|i| i32::try_from(*i).ok())
            .collect();
        repo::attach_pending(&mut *self.db, conv.id, turn.id, &ids).await?;
        let title = if seq == 1 || conv.title == NEW_TITLE {
            let t = chars(strip(question), TITLE_LEN);
            if t.is_empty() {
                NEW_TITLE.to_string()
            } else {
                t
            }
        } else {
            conv.title.clone()
        };
        repo::set_title_updated(&mut *self.db, conv.id, &title, clock::now()).await?;
        Ok(turn)
    }

    /// SYNC-MS-021#ConversationService.finish_turn
    ///
    /// 답이거나 error 하나
    pub async fn finish_turn(
        &mut self,
        turn_id: i32,
        answer: Option<&str>,
        progress: &[Progress],
        context_item_ids: &[String],
        error: Option<&str>,
    ) -> Result<TurnRow, Problem> {
        let Some(mut turn) = repo::turn(&mut *self.db, turn_id).await? else {
            return Err(not_found("turn", i64::from(turn_id)));
        };
        let error = match error.filter(|e| !e.is_empty()) {
            Some(e) => Some(e.to_string()),
            None if answer.is_none() => Some("답 없이 끊겼다".to_string()),
            None => None,
        };
        let answer = if error.is_some() {
            None
        } else {
            answer.map(str::to_string)
        };
        let p = serde_json::to_string(progress)
            .map_err(|e| Problem::Internal { log: e.to_string() })?;
        let c = serde_json::to_string(context_item_ids)
            .map_err(|e| Problem::Internal { log: e.to_string() })?;
        repo::close_turn(
            &mut *self.db,
            turn.id,
            answer.as_deref(),
            error.as_deref(),
            &p,
            &c,
        )
        .await?;
        repo::touch(&mut *self.db, turn.conversation_id, clock::now()).await?;
        turn.answer = answer;
        turn.error = error;
        turn.progress = serde_json::to_value(progress).unwrap_or_default();
        turn.context_item_ids = serde_json::to_value(context_item_ids).unwrap_or_default();
        Ok(turn)
    }

    /// SYNC-MS-021#ConversationService.history
    ///
    /// 실패한 턴은 빠진다. 뒤에서 limit턴
    pub async fn history(&mut self, conv_id: i32, limit: i64) -> Result<Vec<LlmMessage>, Problem> {
        if limit <= 0 {
            return Ok(Vec::new());
        }
        let done: Vec<TurnRow> = repo::turns(&mut *self.db, conv_id)
            .await?
            .into_iter()
            .filter(|t| t.error.is_none() && t.answer.is_some())
            .collect();
        let skip = done.len().saturating_sub(limit as usize);
        let mut out = Vec::new();
        for t in done.into_iter().skip(skip) {
            out.push(LlmMessage::Text {
                role: "user",
                text: t.question,
                images: Vec::new(),
            });
            out.push(LlmMessage::Text {
                role: "assistant",
                text: t.answer.unwrap_or_default(),
                images: Vec::new(),
            });
        }
        Ok(out)
    }

    /// SYNC-MS-021#ConversationService.add_attachment
    ///
    /// 종류·상한이 여기서 막힌다. 글자·PDF는 올릴 때 한 번 글자를 뽑아 둔다
    pub async fn add_attachment(
        &mut self,
        conv_id: i32,
        user: &UserRow,
        name: &str,
        mime: &str,
        data: &[u8],
    ) -> Result<AttachmentMeta, Problem> {
        let (conv, _) = self.owned(conv_id, user).await?;
        let ext = match name.rsplit_once('.') {
            Some((_, e)) => e.to_lowercase(),
            None => String::new(),
        };
        let want = MIME_OF.iter().find(|(e, _)| *e == ext).map(|(_, m)| *m);
        let base = strip(mime.split(';').next().unwrap_or("")).to_lowercase();
        // 클라이언트 mime이 비었거나 octet-stream이면 확장자로 정한다. 표와 어긋나면 거절
        let want = match want {
            Some(w) if base.is_empty() || base == "application/octet-stream" || base == w => w,
            _ => {
                let shown = if !base.is_empty() {
                    base
                } else if !ext.is_empty() {
                    ext
                } else {
                    "?".to_string()
                };
                return Err(Problem::AttachmentType { mime: shown });
            }
        };
        let limit = if want.starts_with("image/") {
            IMAGE_LIMIT
        } else {
            TEXT_LIMIT
        };
        let size = data.len() as i64;
        if size > limit {
            return Err(Problem::AttachmentTooLarge { limit, size });
        }
        if repo::pending_count(&mut *self.db, conv.id).await? >= PENDING_LIMIT {
            return Err(Problem::AttachmentLimit {
                limit: PENDING_LIMIT,
            });
        }
        let text = extract_text(want, data);
        repo::add_attachment(
            &mut *self.db,
            repo::NewAttachment {
                conversation_id: conv.id,
                user_id: user.id,
                name: &chars(name, 200),
                mime: want,
                bytes: data,
                text_cache: text.as_deref(),
                created_at: clock::now(),
            },
        )
        .await
    }

    /// 첨부 → 대화 → 소유 판정. 없거나 남의 것이면 not-found(attachment)
    async fn owned_attachment(
        &mut self,
        att_id: i32,
        user: &UserRow,
    ) -> Result<AttachmentRow, Problem> {
        let Some(a) = repo::attachment(&mut *self.db, att_id).await? else {
            return Err(not_found("attachment", i64::from(att_id)));
        };
        if self.owned(a.conversation_id, user).await.is_err() {
            return Err(not_found("attachment", i64::from(att_id)));
        }
        Ok(a)
    }

    /// SYNC-MS-021#ConversationService.remove_attachment
    ///
    /// 아직 안 보낸 것만. 보낸 첨부는 턴의 일부다
    pub async fn remove_attachment(&mut self, att_id: i32, user: &UserRow) -> Result<(), Problem> {
        let a = self.owned_attachment(att_id, user).await?;
        if a.turn_id.is_some() {
            return Err(Problem::AttachmentSent {
                attachment_id: i64::from(att_id),
            });
        }
        repo::delete_attachment(&mut *self.db, a.id).await
    }

    /// SYNC-MS-021#ConversationService.attachment_meta
    pub async fn attachment_meta(
        &mut self,
        att_id: i32,
        user: &UserRow,
    ) -> Result<AttachmentMeta, Problem> {
        let a = self.owned_attachment(att_id, user).await?;
        Ok(AttachmentMeta {
            id: a.id,
            name: a.name,
            mime: a.mime,
            size: a.size,
            turn_id: a.turn_id,
            created_at: a.created_at,
        })
    }

    /// SYNC-MS-021#ConversationService.attachment_bytes
    pub async fn attachment_bytes(
        &mut self,
        att_id: i32,
        user: &UserRow,
    ) -> Result<(String, String, Vec<u8>), Problem> {
        let a = self.owned_attachment(att_id, user).await?;
        Ok((a.name, a.mime, a.bytes))
    }

    /// SYNC-MS-021#ConversationService.attachment_text
    ///
    /// 이 대화의 첨부만. 이미지는 없음 — 붙인 질문에 이미 보였다. 소유 판정은 질문이 대화 단위로 했다
    pub async fn attachment_text(
        &mut self,
        conv_id: i32,
        att_id: i64,
    ) -> Result<Option<String>, Problem> {
        let Ok(att_id) = i32::try_from(att_id) else {
            return Ok(None);
        };
        Ok(match repo::attachment(&mut *self.db, att_id).await? {
            Some(a) if a.conversation_id == conv_id && !a.mime.starts_with("image/") => {
                Some(a.text_cache.unwrap_or_default())
            }
            _ => None,
        })
    }

    /// SYNC-MS-021#ConversationService.pending_images
    pub async fn pending_images(
        &mut self,
        turn_id: i32,
    ) -> Result<Vec<(String, Vec<u8>)>, Problem> {
        repo::images_of_turn(&mut *self.db, turn_id).await
    }
}
