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
    /// `status-blocked` — 규약 오류·미완성·끊어진 참조가 있어 완료로 못 올린다 (UC-H8 1a)
    #[error("규약 오류 또는 미완성 문서는 완료로 올릴 수 없음")]
    StatusBlocked {
        convention_error_detail: Option<String>,
        warnings: Vec<String>,
    },
    /// `already-current` — 지금 판으로는 되돌릴 수 없다
    #[error("현재 버전으로는 되돌릴 수 없음")]
    AlreadyCurrent,
    /// `document-deletion-needs-confirm` — 휴지통에 넣기 전 확인. 끊어질 것을 담는다 (UC-A7 2~4)
    #[error("휴지통에 넣기는 사람 확인이 필요함")]
    DocumentDeletionNeedsConfirm {
        doc_id: String,
        title: String,
        version_count: i32,
        inbound_refs: Vec<String>,
    },
    /// `document-not-trashed` — 휴지통에 없는 문서를 되살리거나 완전히 지우려 함 (UC-A8 1a)
    #[error("휴지통에 없는 문서")]
    DocumentNotTrashed,
    /// `document-has-history` — 아직 가리키는 곳이 있어 완전히 못 지운다 (UC-H18 7)
    #[error("아직 가리키는 곳이 있어 완전히 지울 수 없다")]
    DocumentHasHistory { inbound_refs: Vec<String> },
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
    /// `bundle-invalid` — git 번들이 아니거나 깨졌거나 main 가지가 없다 (UC-A1 1c2, L15)
    #[error("{reason}")]
    BundleInvalid { reason: String },
    /// `backup-unconfigured` — 백업 폴더를 정하지 않았다 (싱크독_로컬 Rust만, L16)
    #[error("백업 폴더를 정하지 않았다")]
    BackupUnconfigured,
    /// `backup-invalid` — 되살릴 파일이 싱크독 백업이 아니거나 깨졌거나 암호가 틀리다 (L16)
    #[error("{reason}")]
    BackupInvalid { reason: String },
    /// `backup-failed` — 백업을 만들다 실패했다 (L16)
    #[error("{reason}")]
    BackupFailed { reason: String },
    /// `data-dir-invalid` — 옮길 데이터 자리가 맞지 않다 (L16)
    #[error("{reason}")]
    DataDirInvalid { reason: String },
    /// `existing-specs` — 저장소에 명세가 이미 있다, 또는 같은 코드의 보관본이 있다(`archived_at`)
    #[error("{}", if .archived_at.is_some() { "보관된 서버 저장소가 있음" } else { "docs/specs/가 이미 있음" })]
    ExistingSpecs {
        doc_count: i64,
        archived_at: Option<String>,
    },
    /// `push-failed` — git이 원격에 못 밀었다(424)
    #[error("{reason}")]
    PushFailed { reason: String },
    /// `storage-mismatch` — 그 저장 방식에서는 안 되는 일(409). `detail`이 없으면 기본 문장
    #[error("{}", .detail.clone().unwrap_or_else(|| format!("{} 저장 프로젝트다 — 코드는 GitHub에 push한다", .storage)))]
    StorageMismatch {
        storage: String,
        detail: Option<String>,
    },
    /// `upload-too-large` — 코드 올리기 한도(413). 나눠 보낸다
    #[error("한도를 넘는다 — 나눠 보낸다")]
    UploadTooLarge {
        limit_bytes: i64,
        limit_count: i64,
        size: i64,
        count: i64,
    },
    /// `upload-path-refused` — 올릴 수 없는 경로(422). 하나라도 있으면 아무것도 올리지 않는다 — `(path, reason)`
    #[error("올릴 수 없는 경로 {}개", .paths.len())]
    UploadPathRefused { paths: Vec<(String, String)> },
    /// `rebuild-failed` — 재구축 실패, 롤백됨(500). `reason`은 실패한 단계의 문장
    #[error("재구축 실패, 롤백됨")]
    RebuildFailed { reason: String },
    /// `attachment-type` — 받지 않는 파일 종류(415)
    #[error("받지 않는 종류: {mime}")]
    AttachmentType { mime: String },
    /// `attachment-too-large` — 상한 초과(413). 이미지 10MiB, 글자·PDF 1MiB
    #[error("너무 큽니다: {size}B > {limit}B")]
    AttachmentTooLarge { limit: i64, size: i64 },
    /// `attachment-limit` — 아직 안 보낸 첨부가 이미 상한(409)
    #[error("한 질문에 {limit}개까지")]
    AttachmentLimit { limit: i64 },
    /// `attachment-sent` — 보낸 첨부는 턴의 일부라 못 뺀다(409)
    #[error("이미 보낸 첨부는 뺄 수 없다")]
    AttachmentSent { attachment_id: i64 },
    /// `llm-not-configured` — 모델 키·주소가 없다(503)
    #[error("모델 키가 없다 — 읽는 중 질의가 꺼져 있다")]
    LlmNotConfigured,
    /// `llm-unavailable` — 모델 호출 실패(424). 사용량 초과도 여기 접힌다
    #[error("{reason}")]
    LlmUnavailable { reason: String },
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
            Problem::StatusBlocked { .. } => Some("status-blocked"),
            Problem::AlreadyCurrent => Some("already-current"),
            Problem::DocumentDeletionNeedsConfirm { .. } => Some("document-deletion-needs-confirm"),
            Problem::DocumentNotTrashed => Some("document-not-trashed"),
            Problem::DocumentHasHistory { .. } => Some("document-has-history"),
            Problem::MethodNotAllowed { .. } => Some("method-not-allowed"),
            Problem::ForbiddenOrigin { .. } => Some("forbidden-origin"),
            Problem::InvalidRequest { .. } => Some("invalid-request"),
            Problem::ConventionViolation { .. } => Some("convention-violation"),
            Problem::StorageUnavailable { .. } => Some("storage-unavailable"),
            Problem::ProjectCodeInvalid { .. } => Some("project-code-invalid"),
            Problem::ProjectCodeConflict { .. } => Some("project-code-conflict"),
            Problem::BundleInvalid { .. } => Some("bundle-invalid"),
            Problem::BackupUnconfigured => Some("backup-unconfigured"),
            Problem::BackupInvalid { .. } => Some("backup-invalid"),
            Problem::BackupFailed { .. } => Some("backup-failed"),
            Problem::DataDirInvalid { .. } => Some("data-dir-invalid"),
            Problem::ExistingSpecs { .. } => Some("existing-specs"),
            Problem::PushFailed { .. } => Some("push-failed"),
            Problem::RebuildFailed { .. } => Some("rebuild-failed"),
            Problem::StorageMismatch { .. } => Some("storage-mismatch"),
            Problem::UploadTooLarge { .. } => Some("upload-too-large"),
            Problem::UploadPathRefused { .. } => Some("upload-path-refused"),
            Problem::AttachmentType { .. } => Some("attachment-type"),
            Problem::AttachmentTooLarge { .. } => Some("attachment-too-large"),
            Problem::AttachmentLimit { .. } => Some("attachment-limit"),
            Problem::AttachmentSent { .. } => Some("attachment-sent"),
            Problem::LlmNotConfigured => Some("llm-not-configured"),
            Problem::LlmUnavailable { .. } => Some("llm-unavailable"),
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
            | Problem::DocumentTrashed { .. }
            | Problem::StatusBlocked { .. }
            | Problem::DocumentDeletionNeedsConfirm { .. }
            | Problem::DocumentNotTrashed
            | Problem::DocumentHasHistory { .. } => 409,
            Problem::AlreadyCurrent => 422,
            Problem::PreconditionUnmet { .. } => 422,
            Problem::MethodNotAllowed { .. } => 405,
            Problem::ForbiddenOrigin { .. } => 403,
            Problem::InvalidRequest { .. } => 422,
            Problem::ConventionViolation { .. } => 422,
            Problem::StorageUnavailable { .. }
            | Problem::ProjectCodeInvalid { .. }
            | Problem::BundleInvalid { .. }
            | Problem::BackupInvalid { .. }
            | Problem::DataDirInvalid { .. } => 422,
            Problem::BackupUnconfigured => 409,
            Problem::BackupFailed { .. } => 500,
            Problem::ProjectCodeConflict { .. } | Problem::ExistingSpecs { .. } => 409,
            Problem::PushFailed { .. } => 424,
            Problem::RebuildFailed { .. } => 500,
            Problem::StorageMismatch { .. } => 409,
            Problem::UploadTooLarge { .. } => 413,
            Problem::UploadPathRefused { .. } => 422,
            Problem::AttachmentType { .. } => 415,
            Problem::AttachmentTooLarge { .. } => 413,
            Problem::AttachmentLimit { .. } | Problem::AttachmentSent { .. } => 409,
            Problem::LlmNotConfigured => 503,
            Problem::LlmUnavailable { .. } => 424,
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
            Problem::StatusBlocked {
                convention_error_detail,
                warnings,
            } => vec![
                (
                    "convention_error_detail",
                    Value::from(convention_error_detail.clone()),
                ),
                ("warnings", Value::from(warnings.clone())),
            ],
            Problem::DocumentDeletionNeedsConfirm {
                doc_id,
                title,
                version_count,
                inbound_refs,
            } => vec![
                ("doc_id", Value::from(doc_id.as_str())),
                ("title", Value::from(title.as_str())),
                ("version_count", Value::from(*version_count)),
                ("inbound_refs", Value::from(inbound_refs.clone())),
            ],
            Problem::DocumentHasHistory { inbound_refs } => {
                vec![("inbound_refs", Value::from(inbound_refs.clone()))]
            }
            Problem::AlreadyCurrent
            | Problem::DocumentNotTrashed
            | Problem::LlmNotConfigured
            | Problem::BackupUnconfigured => {
                vec![]
            }
            Problem::AttachmentType { mime } => vec![("mime", Value::from(mime.as_str()))],
            Problem::AttachmentTooLarge { limit, size } => {
                vec![("limit", Value::from(*limit)), ("size", Value::from(*size))]
            }
            Problem::AttachmentLimit { limit } => vec![("limit", Value::from(*limit))],
            Problem::AttachmentSent { attachment_id } => {
                vec![("attachment_id", Value::from(*attachment_id))]
            }
            Problem::LlmUnavailable { reason }
            | Problem::BundleInvalid { reason }
            | Problem::BackupInvalid { reason }
            | Problem::BackupFailed { reason }
            | Problem::DataDirInvalid { reason } => {
                vec![("reason", Value::from(reason.as_str()))]
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
            Problem::PushFailed { reason } | Problem::RebuildFailed { reason } => {
                vec![("reason", Value::from(reason.as_str()))]
            }
            Problem::NotImplemented { card } => vec![("card", Value::from(card.as_str()))],
            Problem::StorageMismatch { storage, .. } => {
                vec![("storage", Value::from(storage.as_str()))]
            }
            Problem::UploadTooLarge {
                limit_bytes,
                limit_count,
                size,
                count,
            } => {
                let mut limit = serde_json::Map::new();
                limit.insert("bytes".into(), Value::from(*limit_bytes));
                limit.insert("count".into(), Value::from(*limit_count));
                vec![
                    ("limit", Value::Object(limit)),
                    ("size", Value::from(*size)),
                    ("count", Value::from(*count)),
                ]
            }
            Problem::UploadPathRefused { paths } => vec![(
                "paths",
                Value::from(
                    paths
                        .iter()
                        .map(|(p, r)| {
                            let mut m = serde_json::Map::new();
                            m.insert("path".into(), Value::from(p.as_str()));
                            m.insert("reason".into(), Value::from(r.as_str()));
                            Value::Object(m)
                        })
                        .collect::<Vec<_>>(),
                ),
            )],
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
