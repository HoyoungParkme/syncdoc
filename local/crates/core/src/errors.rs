//! 에러 — problem+json 종류마다 갈래 하나 (SYNC-STD-004#DEV-5 · SYNC-API-001 2장).
//! HTTP는 모른다. 응답 꼴(상태 코드·머리·본문 바이트)은 `syncdoc_server::web::problem`이 만든다.

use serde_json::Value;
use thiserror::Error;

use crate::types::{DeletedItem, Violation, Warning};

/// `internal`의 본문 — 고정 문구. 예외 종류·메시지는 로그로만 (API-001 2장)
pub const INTERNAL_DETAIL: &str = "서버에서 처리하지 못한 오류입니다. 로그를 확인하세요.";

/// 앱이 내는 문제. 갈래가 problem+json의 `type` 하나에 맞는다
#[derive(Debug, Error)]
pub enum Problem {
    /// `about:blank` — 종류 없는 문제(화면 빌드 없음)와 프레임워크 HTTP 오류
    #[error("{title}: {}", .detail.as_deref().unwrap_or(""))]
    Blank {
        status: u16,
        title: String,
        detail: Option<String>,
    },
    /// `not-found` — 없는 자원·없는 경로. `id`는 문자열이거나 정수다(파이썬 판이 받은 그대로)
    #[error("{resource} {} 없음", id_text(.id))]
    NotFound { resource: String, id: Value },
    /// `not-found` — 없는 항목. 그 문서의 지우지 않은 항목 ID를 함께 (파이썬 `NotFound(…, available_items=…)`)
    #[error("{resource} {id} 없음")]
    NotFoundWithItems {
        resource: String,
        id: String,
        available_items: Vec<String>,
    },
    /// `item-deleted` — 지운 항목. 시각은 파이썬 `isoformat()`, 없으면 null
    #[error("삭제된 항목")]
    ItemDeleted { deleted_at: Option<String> },
    /// `method-not-allowed` — 그 경로에 없는 메서드
    #[error("이 경로에 {method} 메서드는 없습니다")]
    MethodNotAllowed { method: String, allow: Vec<String> },
    /// `forbidden-origin` — 폐쇄망판 Host·Origin 가드. `host`·`origin` 가운데 하나 (SEQ-C3)
    #[error("폐쇄망판은 이 PC(또는 PUBLIC_BASE_URL)에서만 쓴다")]
    ForbiddenOrigin {
        host: Option<String>,
        origin: Option<String>,
    },
    /// `invalid-request` — 요청 본문·경로 값이 정의에 안 맞다. `(loc, msg)`들 (API-001 2장, 파이썬 `InvalidRequest`)
    #[error("{}", invalid_detail(.errors))]
    InvalidRequest { errors: Vec<(String, String)> },
    /// `convention-violation` — 규약 위반(STD-001 3장). 본문 「규약 위반」, 위반·경고 목록 (파이썬 `ConventionViolation`)
    #[error("규약 위반")]
    ConventionViolation {
        violations: Vec<Violation>,
        warnings: Vec<Warning>,
    },
    /// `version-conflict` — 기대한 판이 현재 판이 아니다. 현재 판과 본문을 함께
    #[error("버전 불일치")]
    VersionConflict {
        current_version: i32,
        current_body: String,
    },
    /// `item-deletion-needs-confirm` — 지우는 항목에 하위 참조가 있다. 하위는 이름으로 (#50)
    #[error("항목 삭제에 하위 참조가 있음")]
    ItemDeletionNeedsConfirm { deleted_items: Vec<DeletedItem> },
    /// `precondition-unmet` — DOM 셋의 순서 (STD-001 2.6)
    #[error("먼저 있어야 한다: {requires}")]
    PreconditionUnmet { requires: String, have: Vec<String> },
    /// `document-trashed` — 휴지통에 있는 문서. 시각은 파이썬 `isoformat()` (UC-A7 1a)
    #[error("휴지통에 있는 문서")]
    DocumentTrashed { trashed_at: String },
    /// `storage-unavailable` — 이 서버에서 켜지 않은 저장 방식 (UC-A1 1a)
    #[error("이 서버에서 켜지 않은 저장 방식 {storage}")]
    StorageUnavailable {
        storage: String,
        enabled: Vec<String>,
    },
    /// `project-code-invalid` — 프로젝트 코드 형식
    #[error("프로젝트 코드 형식")]
    ProjectCodeInvalid { rule: String },
    /// `project-code-conflict` — 이미 쓰이는 코드
    #[error("이미 쓰이는 코드 {code}")]
    ProjectCodeConflict { code: String },
    /// `existing-specs` — 저장소에 명세가 이미 있다, 또는 같은 코드의 보관본이 있다(`archived_at`)
    #[error("{}", if .archived_at.is_some() { "보관된 서버 저장소가 있음" } else { "docs/specs/가 이미 있음" })]
    ExistingSpecs {
        doc_count: i64,
        archived_at: Option<String>,
    },
    /// `push-failed` — git이 원격에 못 밀었다(424)
    #[error("{reason}")]
    PushFailed { reason: String },
    /// `not-implemented` — 뒤 카드가 여는 기능 (파이썬 `NotImplementedYet`)
    #[error("{card}: 아직 구현되지 않음")]
    NotImplemented { card: String },
    /// git이 실패했다(파이썬 `GitError`) — `internal`로 나간다. `cmd`는 `git …`
    #[error("{cmd}: {}", crate::pycompat::chars::strip(.stderr))]
    Git { cmd: String, stderr: String },
    /// `internal` — 처리하지 못한 오류. `log`는 로그로만 간다 — 켤 때는 사람이 읽는 문장이다
    #[error("{log}")]
    Internal { log: String },
}

impl Problem {
    /// `urn:syncdoc:{종류}`의 종류 — `about:blank`면 None
    pub fn kind(&self) -> Option<&'static str> {
        match self {
            Problem::Blank { .. } => None,
            Problem::NotFound { .. } | Problem::NotFoundWithItems { .. } => Some("not-found"),
            Problem::ItemDeleted { .. } => Some("item-deleted"),
            Problem::VersionConflict { .. } => Some("version-conflict"),
            Problem::ItemDeletionNeedsConfirm { .. } => Some("item-deletion-needs-confirm"),
            Problem::PreconditionUnmet { .. } => Some("precondition-unmet"),
            Problem::DocumentTrashed { .. } => Some("document-trashed"),
            Problem::MethodNotAllowed { .. } => Some("method-not-allowed"),
            Problem::ForbiddenOrigin { .. } => Some("forbidden-origin"),
            Problem::InvalidRequest { .. } => Some("invalid-request"),
            Problem::ConventionViolation { .. } => Some("convention-violation"),
            Problem::StorageUnavailable { .. } => Some("storage-unavailable"),
            Problem::ProjectCodeInvalid { .. } => Some("project-code-invalid"),
            Problem::ProjectCodeConflict { .. } => Some("project-code-conflict"),
            Problem::ExistingSpecs { .. } => Some("existing-specs"),
            Problem::PushFailed { .. } => Some("push-failed"),
            Problem::NotImplemented { .. } => Some("not-implemented"),
            Problem::Internal { .. } | Problem::Git { .. } => Some("internal"),
        }
    }

    pub fn status(&self) -> u16 {
        match self {
            Problem::Blank { status, .. } => *status,
            Problem::NotFound { .. } | Problem::NotFoundWithItems { .. } => 404,
            Problem::ItemDeleted { .. } => 410,
            Problem::VersionConflict { .. }
            | Problem::ItemDeletionNeedsConfirm { .. }
            | Problem::DocumentTrashed { .. } => 409,
            Problem::PreconditionUnmet { .. } => 422,
            Problem::MethodNotAllowed { .. } => 405,
            Problem::ForbiddenOrigin { .. } => 403,
            Problem::InvalidRequest { .. } => 422,
            Problem::ConventionViolation { .. } => 422,
            Problem::StorageUnavailable { .. } | Problem::ProjectCodeInvalid { .. } => 422,
            Problem::ProjectCodeConflict { .. } | Problem::ExistingSpecs { .. } => 409,
            Problem::PushFailed { .. } => 424,
            Problem::NotImplemented { .. } => 501,
            Problem::Internal { .. } | Problem::Git { .. } => 500,
        }
    }

    /// 제목 — 종류 이름 그대로, `about:blank`면 그 제목
    pub fn title(&self) -> String {
        match self {
            Problem::Blank { title, .. } => title.clone(),
            _ => self.kind().unwrap_or("error").to_string(),
        }
    }

    /// 본문의 `detail` — 비면 본문에서 뺀다
    pub fn detail(&self) -> Option<String> {
        match self {
            Problem::Blank { detail, .. } => detail.clone(),
            Problem::Internal { .. } | Problem::Git { .. } => Some(INTERNAL_DETAIL.to_string()),
            _ => Some(self.to_string()),
        }
    }

    /// 확장 필드 — 파이썬 판과 같은 순서
    pub fn extras(&self) -> Vec<(&'static str, Value)> {
        match self {
            Problem::NotFound { resource, id } => vec![
                ("resource", Value::from(resource.as_str())),
                ("id", id.clone()),
            ],
            Problem::NotFoundWithItems {
                resource,
                id,
                available_items,
            } => vec![
                ("resource", Value::from(resource.as_str())),
                ("id", Value::from(id.as_str())),
                ("available_items", Value::from(available_items.clone())),
            ],
            Problem::ItemDeleted { deleted_at } => {
                vec![("deleted_at", Value::from(deleted_at.clone()))]
            }
            Problem::VersionConflict {
                current_version,
                current_body,
            } => vec![
                ("current_version", Value::from(*current_version)),
                ("current_body", Value::from(current_body.as_str())),
            ],
            Problem::ItemDeletionNeedsConfirm { deleted_items } => vec![(
                "deleted_items",
                Value::from(
                    deleted_items
                        .iter()
                        .map(|d| {
                            let mut m = serde_json::Map::new();
                            m.insert("item_id".into(), Value::from(d.item_id.as_str()));
                            m.insert(
                                "downstream".into(),
                                Value::from(
                                    d.downstream
                                        .iter()
                                        .map(|r| {
                                            let mut x = serde_json::Map::new();
                                            x.insert(
                                                "doc_id".into(),
                                                Value::from(r.doc_id.clone()),
                                            );
                                            x.insert(
                                                "item_id".into(),
                                                Value::from(r.item_id.clone()),
                                            );
                                            x.insert(
                                                "display_name".into(),
                                                Value::from(r.display_name.clone()),
                                            );
                                            Value::Object(x)
                                        })
                                        .collect::<Vec<_>>(),
                                ),
                            );
                            Value::Object(m)
                        })
                        .collect::<Vec<_>>(),
                ),
            )],
            Problem::PreconditionUnmet { requires, have } => vec![
                ("requires", Value::from(requires.as_str())),
                ("have", Value::from(have.clone())),
            ],
            Problem::DocumentTrashed { trashed_at } => {
                vec![("trashed_at", Value::from(trashed_at.as_str()))]
            }
            Problem::MethodNotAllowed { allow, .. } => vec![("allow", Value::from(allow.clone()))],
            Problem::ForbiddenOrigin { host, origin } => match (host, origin) {
                (Some(h), _) => vec![("host", Value::from(h.as_str()))],
                (None, Some(o)) => vec![("origin", Value::from(o.as_str()))],
                (None, None) => vec![],
            },
            Problem::InvalidRequest { errors } => vec![(
                "errors",
                Value::from(
                    errors
                        .iter()
                        .map(|(loc, msg)| {
                            let mut m = serde_json::Map::new();
                            m.insert("loc".into(), Value::from(loc.as_str()));
                            m.insert("msg".into(), Value::from(msg.as_str()));
                            Value::Object(m)
                        })
                        .collect::<Vec<_>>(),
                ),
            )],
            Problem::ConventionViolation {
                violations,
                warnings,
            } => vec![
                (
                    "violations",
                    Value::from(
                        violations
                            .iter()
                            .map(|v| {
                                let mut m = serde_json::Map::new();
                                m.insert("line".into(), Value::from(v.line));
                                m.insert("rule".into(), Value::from(v.rule.as_str()));
                                m.insert("message".into(), Value::from(v.message.as_str()));
                                Value::Object(m)
                            })
                            .collect::<Vec<_>>(),
                    ),
                ),
                (
                    "warnings",
                    Value::from(
                        warnings
                            .iter()
                            .map(|w| {
                                let mut m = serde_json::Map::new();
                                m.insert("rule".into(), Value::from(w.rule.as_str()));
                                m.insert("message".into(), Value::from(w.message.as_str()));
                                Value::Object(m)
                            })
                            .collect::<Vec<_>>(),
                    ),
                ),
            ],
            Problem::StorageUnavailable { storage, enabled } => vec![
                ("storage", Value::from(storage.as_str())),
                ("enabled", Value::from(enabled.clone())),
            ],
            Problem::ProjectCodeInvalid { rule } => vec![("rule", Value::from(rule.as_str()))],
            Problem::ProjectCodeConflict { code } => vec![("code", Value::from(code.as_str()))],
            Problem::ExistingSpecs {
                doc_count,
                archived_at,
            } => {
                let mut v = vec![("doc_count", Value::from(*doc_count))];
                if let Some(a) = archived_at {
                    v.push(("archived_at", Value::from(a.as_str())));
                }
                v
            }
            Problem::PushFailed { reason } => vec![("reason", Value::from(reason.as_str()))],
            Problem::NotImplemented { card } => vec![("card", Value::from(card.as_str()))],
            Problem::Blank { .. } | Problem::Internal { .. } | Problem::Git { .. } => vec![],
        }
    }
}

/// 첫 오류 `{loc} — {msg}`, loc이 비면 msg (파이썬 `InvalidRequest.__init__`)
fn invalid_detail(errors: &[(String, String)]) -> String {
    match errors.first() {
        Some((loc, msg)) if !loc.is_empty() => format!("{loc} — {msg}"),
        Some((_, msg)) => msg.clone(),
        None => "입력이 정의에 맞지 않습니다".to_string(),
    }
}

/// 파이썬 `str(id)` — 문자열은 그대로, 수는 숫자
fn id_text(id: &Value) -> String {
    match id {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

impl From<sqlx::Error> for Problem {
    fn from(e: sqlx::Error) -> Self {
        Problem::Internal {
            log: format!("DB: {e}"),
        }
    }
}

impl From<std::io::Error> for Problem {
    fn from(e: std::io::Error) -> Self {
        Problem::Internal {
            log: format!("파일: {e}"),
        }
    }
}
