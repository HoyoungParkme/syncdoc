//! 에러 — problem+json 종류마다 갈래 하나 (SYNC-STD-004#DEV-5 · SYNC-API-001 2장).
//! HTTP는 모른다. 응답 꼴(상태 코드·머리·본문 바이트)은 `syncdoc_server::web::problem`이 만든다.

use serde_json::Value;
use thiserror::Error;

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
    /// `not-found` — 없는 자원·없는 경로
    #[error("{resource} {id} 없음")]
    NotFound { resource: String, id: String },
    /// `method-not-allowed` — 그 경로에 없는 메서드
    #[error("이 경로에 {method} 메서드는 없습니다")]
    MethodNotAllowed { method: String, allow: Vec<String> },
    /// `forbidden-origin` — 폐쇄망판 Host·Origin 가드. `host`·`origin` 가운데 하나 (SEQ-C3)
    #[error("폐쇄망판은 이 PC(또는 PUBLIC_BASE_URL)에서만 쓴다")]
    ForbiddenOrigin {
        host: Option<String>,
        origin: Option<String>,
    },
    /// `internal` — 처리하지 못한 오류. `log`는 로그로만 간다 — 켤 때는 사람이 읽는 문장이다
    #[error("{log}")]
    Internal { log: String },
}

impl Problem {
    /// `urn:syncdoc:{종류}`의 종류 — `about:blank`면 None
    pub fn kind(&self) -> Option<&'static str> {
        match self {
            Problem::Blank { .. } => None,
            Problem::NotFound { .. } => Some("not-found"),
            Problem::MethodNotAllowed { .. } => Some("method-not-allowed"),
            Problem::ForbiddenOrigin { .. } => Some("forbidden-origin"),
            Problem::Internal { .. } => Some("internal"),
        }
    }

    pub fn status(&self) -> u16 {
        match self {
            Problem::Blank { status, .. } => *status,
            Problem::NotFound { .. } => 404,
            Problem::MethodNotAllowed { .. } => 405,
            Problem::ForbiddenOrigin { .. } => 403,
            Problem::Internal { .. } => 500,
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
            Problem::Internal { .. } => Some(INTERNAL_DETAIL.to_string()),
            _ => Some(self.to_string()),
        }
    }

    /// 확장 필드 — 파이썬 판과 같은 순서
    pub fn extras(&self) -> Vec<(&'static str, Value)> {
        match self {
            Problem::NotFound { resource, id } => vec![
                ("resource", Value::from(resource.as_str())),
                ("id", Value::from(id.as_str())),
            ],
            Problem::MethodNotAllowed { allow, .. } => vec![("allow", Value::from(allow.clone()))],
            Problem::ForbiddenOrigin { host, origin } => match (host, origin) {
                (Some(h), _) => vec![("host", Value::from(h.as_str()))],
                (None, Some(o)) => vec![("origin", Value::from(o.as_str()))],
                (None, None) => vec![],
            },
            Problem::Blank { .. } | Problem::Internal { .. } => vec![],
        }
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
