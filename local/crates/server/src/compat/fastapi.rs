//! FastAPI 요청 읽기 — FastAPI 0.141.1 `routing.py`(본문)·`dependencies`(경로 값)를 옮겼다 (SYNC-DOM-004 1장 compat).
//! 실패는 파이썬 판 처리기(`main.py`)가 바꿔 내는 그대로 — `invalid-request`(loc·msg) 또는 400 `about:blank`.

use axum::http::HeaderMap;
use syncdoc_core::errors::Problem;

use super::pydantic::{ErrorKind, Failure, LineError, LocItem, Opts, Validator};
use super::pyjson::{self, Depth, LoadsError};
use super::pyvalue::{PyStr, PyValue};

/// 본문을 JSON으로 읽을 때 파이썬 C 재귀가 남긴 깊이 — 파이썬 판 FastAPI 경로에서 잰 값
pub const BODY_JSON_DEPTH: Depth = Depth(9_986);

/// FastAPI가 읽은 본문
pub enum Body {
    /// 비었거나 `null`
    None,
    Json(PyValue),
    /// JSON으로 읽지 않은 바이트(Content-Type이 JSON이 아니거나 없다)
    Raw,
}

/// 첫 `content-type` 머리 (starlette `Headers.get` — latin-1)
fn first_header(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get(name)
        .map(|v| v.as_bytes().iter().map(|&b| char::from(b)).collect())
}

/// `email.message.Message.get_content_type()` — 꼴이 틀리면 `text/plain`
fn content_type(value: &str) -> (String, String) {
    let ctype = value.split(';').next().unwrap_or("").to_lowercase();
    let ctype = ctype.trim();
    if ctype.matches('/').count() != 1 {
        return ("text".into(), "plain".into());
    }
    let (main, sub) = ctype.split_once('/').unwrap_or(("text", "plain"));
    (main.to_string(), sub.to_string())
}

/// 본문 읽기 — `strict_content_type`(기본 참): Content-Type이 없으면 JSON으로 읽지 않는다
pub fn read_body(headers: &HeaderMap, bytes: &[u8]) -> Result<Body, Problem> {
    if bytes.is_empty() {
        return Ok(Body::None);
    }
    let Some(ct) = first_header(headers, "content-type") else {
        return Ok(Body::Raw);
    };
    let (main, sub) = content_type(&ct);
    if !(main == "application" && (sub == "json" || sub.ends_with("+json"))) {
        return Ok(Body::Raw);
    }
    match pyjson::loads_bytes(bytes, BODY_JSON_DEPTH) {
        Ok(PyValue::None) => Ok(Body::None),
        Ok(v) => Ok(Body::Json(v)),
        Err(LoadsError::Decode { pos, .. }) => Err(Problem::InvalidRequest {
            errors: vec![(format!("body.{pos}"), "JSON decode error".into())],
        }),
        Err(_) => Err(Problem::Blank {
            status: 400,
            title: "There was an error parsing the body".into(),
            detail: None,
        }),
    }
}

/// `(loc, msg)` — 파이썬 처리기가 `".".join(str(x) for x in loc)`로 낸다
fn pair(prefix: &str, l: &LineError) -> (String, String) {
    let mut loc = vec![prefix.to_string()];
    loc.extend(l.loc.iter().map(LocItem::plain));
    (loc.join("."), l.kind.message())
}

/// 본문 모델 하나(임베드 안 함) — FastAPI는 `from_attributes=True`로 검증한다
pub fn body_model(body: &Body, v: &Validator) -> Result<PyValue, Problem> {
    let missing = |kind: ErrorKind| Problem::InvalidRequest {
        errors: vec![("body".into(), kind.message())],
    };
    match body {
        Body::None => Err(missing(ErrorKind::Missing)),
        Body::Raw => Err(missing(ErrorKind::ModelAttributesType)),
        Body::Json(x @ PyValue::Dict(_)) => match v.validate(x, Opts::default()) {
            Ok(out) => Ok(out),
            Err(Failure::Invalid(e)) => Err(Problem::InvalidRequest {
                errors: e.lines.iter().map(|l| pair("body", l)).collect(),
            }),
            Err(Failure::Exception(log)) => Err(Problem::Internal { log }),
        },
        Body::Json(_) => Err(missing(ErrorKind::ModelAttributesType)),
    }
}

/// 경로 값 정수 — `int` 필드의 lax 검증(문자열 → 정수)
pub fn path_int(name: &str, raw: &str, v: &Validator) -> Result<num_bigint::BigInt, Problem> {
    match v.validate(&PyValue::Str(PyStr::from(raw)), Opts::default()) {
        Ok(PyValue::Int(i)) => Ok(i),
        Ok(_) => Err(Problem::Internal {
            log: "경로 값이 정수가 아니다".into(),
        }),
        Err(Failure::Invalid(e)) => Err(Problem::InvalidRequest {
            errors: e
                .lines
                .iter()
                .map(|l| (format!("path.{name}"), l.kind.message()))
                .collect(),
        }),
        Err(Failure::Exception(log)) => Err(Problem::Internal { log }),
    }
}

/// 손으로 쓴 core schema — 파이썬 판 `web/schemas`의 요청 모델 (스키마가 작아 옮겨 적는다)
pub mod schemas {
    use serde_json::json;

    use crate::compat::pydantic::Validator;

    /// `IssueToken` — `label: str = Field(max_length=50)` (SYNC-API-001#POST/api/me/tokens)
    pub fn issue_token() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "IssueToken", "schema": {"type": "model-fields",
                "fields": {"label": {"type": "model-field", "schema": {"type": "str", "max_length": 50}}},
                "model_name": "IssueToken"}, "config": {"title": "IssueToken"}}),
            "IssueToken",
        )
        .expect("IssueToken 스키마")
    }

    /// `InitProject` — 파이썬 판 `web/schemas/projects.py`의 core schema 그대로 (SYNC-API-001#POST/api/projects)
    pub fn init_project() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "InitProject", "schema": {"type": "model-fields", "fields": {
                "storage": {"type": "model-field", "schema": {"type": "literal", "expected": ["github", "server"]}},
                "remote_url": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}},
                "code": {"type": "model-field", "schema": {"type": "str", "pattern": "^[A-Z]{1,4}$"}},
                "name": {"type": "model-field", "schema": {"type": "str", "max_length": 100}},
                "import_existing": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "bool"}, "default": false}},
                "create_repo": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "bool"}, "default": false}},
                "private": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "bool"}}, "default": null}}},
                "model_name": "InitProject"}, "config": {"title": "InitProject"}}),
            "InitProject",
        )
        .expect("InitProject 스키마")
    }

    /// 경로의 `int` 값
    pub fn int() -> Validator {
        Validator::new(&json!({"type": "int"}), "int").expect("int 스키마")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_type_like_email_message() {
        assert_eq!(
            content_type("Application/JSON; charset=utf-8"),
            ("application".into(), "json".into())
        );
        assert_eq!(
            content_type("application/json/x"),
            ("text".into(), "plain".into())
        );
        assert_eq!(
            content_type("application/vnd.a+json"),
            ("application".into(), "vnd.a+json".into())
        );
    }
}
