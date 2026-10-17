//! FastAPI 요청 읽기 — FastAPI 0.141.1 `routing.py`(본문)·`dependencies`(경로 값·질의 값)를 옮겼다 (SYNC-DOM-004 1장 compat).
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

/// 선택 본문 모델 하나 — `req: Model | None = None`. 비었거나 `null`이면 없음
pub fn body_model_optional(body: &Body, v: &Validator) -> Result<Option<PyValue>, Problem> {
    match body {
        Body::None => Ok(None),
        other => body_model(other, v).map(Some),
    }
}

pub use super::form::{FormValue, Upload, read_form};

/// FastAPI `_get_multidict_value` — 같은 이름은 뒤의 것, 빈 문자열은 없는 것(`Form`·`File` 칸). (자리, 값)
fn form_value<'a>(form: &'a [(String, FormValue)], name: &str) -> Option<(usize, &'a FormValue)> {
    form.iter()
        .enumerate()
        .rev()
        .find(|(_, (n, _))| n == name)
        .map(|(i, (_, v))| (i, v))
        .filter(|(_, v)| !matches!(v, FormValue::Text(t) if t.is_empty()))
}

/// 글자 칸 하나 — `Annotated[str, Form(...)]`. 없으면 `Field required`, 파일이면 pydantic `str`의 `string_type`,
/// 아니면 그 검증. 오류는 `(body.{이름}, 문장)`들로 `errors`에 쌓는다(FastAPI는 선언 차례로 모은다)
pub fn form_text(
    form: &[(String, FormValue)],
    name: &str,
    v: &Validator,
    errors: &mut Vec<(String, String)>,
) -> Option<String> {
    let loc = format!("body.{name}");
    match form_value(form, name) {
        None => {
            errors.push((loc, ErrorKind::Missing.message()));
            None
        }
        Some((_, FormValue::File(_))) => {
            errors.push((loc, ErrorKind::StringType.message()));
            None
        }
        Some((_, FormValue::Text(t))) => {
            match v.validate(&PyValue::Str(PyStr::from(t.as_str())), Opts::default()) {
                Ok(PyValue::Str(out)) => out.as_str().map(str::to_string),
                Ok(_) => {
                    errors.push((loc, "검증한 값이 글자가 아니다".into()));
                    None
                }
                Err(Failure::Invalid(e)) => {
                    errors.extend(e.lines.iter().map(|l| pair(&loc, l)));
                    None
                }
                Err(Failure::Exception(log)) => {
                    errors.push((loc, log));
                    None
                }
            }
        }
    }
}

/// 파일 칸 하나 — `UploadFile`(`File()`). 없으면 `Field required`, 글자면 FastAPI `UploadFile._validate`의
/// `Expected UploadFile`. 폼에서 꺼내 간다(번들은 클 수 있다)
pub fn form_upload(
    form: &mut Vec<(String, FormValue)>,
    name: &str,
    errors: &mut Vec<(String, String)>,
) -> Option<Upload> {
    let loc = format!("body.{name}");
    let at = match form_value(form, name) {
        None => {
            errors.push((loc, ErrorKind::Missing.message()));
            return None;
        }
        Some((_, FormValue::Text(_))) => {
            errors.push((
                loc,
                "Value error, Expected UploadFile, received: <class 'str'>".into(),
            ));
            return None;
        }
        Some((at, FormValue::File(_))) => at,
    };
    match form.remove(at) {
        (_, FormValue::File(f)) => Some(f),
        _ => None,
    }
}

/// `file: UploadFile` 하나 — starlette `request.form()` + FastAPI 검증(L14 첨부)
pub fn form_file(headers: &HeaderMap, bytes: &[u8], name: &str) -> Result<Upload, Problem> {
    let mut form = read_form(headers, bytes)?;
    let mut errors = Vec::new();
    match form_upload(&mut form, name, &mut errors) {
        Some(u) => Ok(u),
        None => Err(Problem::InvalidRequest { errors }),
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

/// 파이썬 `urllib.parse.unquote_to_bytes` + UTF-8 `errors="replace"` — `%XX`만 바이트로, 나머지는 그대로
fn py_unquote(s: &str) -> String {
    let b = s.as_bytes();
    let hex = |c: u8| (c as char).to_digit(16).map(|d| d as u8);
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'%'
            && i + 2 < b.len()
            && let (Some(h), Some(l)) = (hex(b[i + 1]), hex(b[i + 2]))
        {
            out.push(h * 16 + l);
            i += 3;
            continue;
        }
        out.push(b[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// starlette `QueryParams` — `parse_qsl(keep_blank_values=True)`: `&`로 나누고, 빈 조각은 버리고,
/// `=`가 없으면 값이 빈 것, `+`는 빈칸, `%XX`를 푼다. 받은 차례 그대로
pub fn query_params(raw: Option<&str>) -> Vec<(String, String)> {
    let Some(q) = raw.filter(|q| !q.is_empty()) else {
        return Vec::new();
    };
    q.split('&')
        .filter(|kv| !kv.is_empty())
        .map(|kv| {
            let (k, v) = kv.split_once('=').unwrap_or((kv, ""));
            (
                py_unquote(&k.replace('+', " ")),
                py_unquote(&v.replace('+', " ")),
            )
        })
        .collect()
}

/// 질의 값 하나 — 같은 이름이 여럿이면 마지막(starlette `QueryParams.get`)
pub fn query_get<'a>(params: &'a [(String, String)], name: &str) -> Option<&'a str> {
    params
        .iter()
        .rev()
        .find(|(k, _)| k == name)
        .map(|(_, v)| v.as_str())
}

/// 질의 필드 하나 검증 — FastAPI `request_params_to_args`: 없으면 필수일 때 `Field required`, 아니면 기본값(None).
/// 오류는 `(query.{이름}, 문장)`들로 `errors`에 쌓는다
pub fn query_field(
    params: &[(String, String)],
    name: &str,
    v: &Validator,
    required: bool,
    errors: &mut Vec<(String, String)>,
) -> Option<PyValue> {
    let Some(raw) = query_get(params, name) else {
        if required {
            errors.push((format!("query.{name}"), ErrorKind::Missing.message()));
        }
        return None;
    };
    match v.validate(&PyValue::Str(PyStr::from(raw)), Opts::default()) {
        Ok(out) => Some(out),
        Err(Failure::Invalid(e)) => {
            errors.extend(e.lines.iter().map(|l| pair(&format!("query.{name}"), l)));
            None
        }
        Err(Failure::Exception(log)) => {
            errors.push((format!("query.{name}"), log));
            None
        }
    }
}

/// 쌓인 검증 오류 → `invalid-request` (없으면 통과)
pub fn check_errors(errors: Vec<(String, String)>) -> Result<(), Problem> {
    if errors.is_empty() {
        Ok(())
    } else {
        Err(Problem::InvalidRequest { errors })
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

    /// 이 PC 설정 저장 — 칸마다 없어도 된다 (SYNC-API-001#PUT/api/local/settings, Rust 판만, 카드 L16)
    pub fn local_settings() -> Validator {
        let opt = |max: Option<u64>| {
            let s = match max {
                Some(m) => json!({"type": "str", "max_length": m}),
                None => json!({"type": "str"}),
            };
            json!({"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": s}, "default": null}})
        };
        Validator::new(
            &json!({"type": "model", "cls": "LocalSettings", "schema": {"type": "model-fields", "fields": {
                "name": opt(Some(100)), "llm_api_url": opt(None), "llm_api_key": opt(None),
                "llm_model": opt(Some(100)), "backup_dir": opt(None), "backup_password": opt(None)},
                "model_name": "LocalSettings"}, "config": {"title": "LocalSettings"}}),
            "LocalSettings",
        )
        .expect("LocalSettings 스키마")
    }

    /// 자동 시작 `{on: bool}` (SYNC-API-001#PUT/api/local/autostart)
    pub fn local_autostart() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "LocalAutostart", "schema": {"type": "model-fields", "fields": {
                "on": {"type": "model-field", "schema": {"type": "bool"}}},
                "model_name": "LocalAutostart"}, "config": {"title": "LocalAutostart"}}),
            "LocalAutostart",
        )
        .expect("LocalAutostart 스키마")
    }

    /// 되살리기 `{name: str, password: str | None}` (SYNC-API-001#POST/api/local/restore)
    pub fn local_restore() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "LocalRestore", "schema": {"type": "model-fields", "fields": {
                "name": {"type": "model-field", "schema": {"type": "str", "min_length": 1}},
                "password": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}}},
                "model_name": "LocalRestore"}, "config": {"title": "LocalRestore"}}),
            "LocalRestore",
        )
        .expect("LocalRestore 스키마")
    }

    /// 요청 보내기 `{method, url, body}` (SYNC-API-001#POST/api/local/request, 카드 L30 — 파이썬 판에 없다)
    pub fn local_request() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "LocalRequest", "schema": {"type": "model-fields", "fields": {
                "method": {"type": "model-field", "schema": {"type": "literal", "expected": ["GET", "POST", "PUT", "PATCH", "DELETE"]}},
                "url": {"type": "model-field", "schema": {"type": "str", "min_length": 1}},
                "body": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}}},
                "model_name": "LocalRequest"}, "config": {"title": "LocalRequest"}}),
            "LocalRequest",
        )
        .expect("LocalRequest 스키마")
    }

    /// 옮기기 `{dir: str}` (SYNC-API-001#POST/api/local/move)
    pub fn local_move() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "LocalMove", "schema": {"type": "model-fields", "fields": {
                "dir": {"type": "model-field", "schema": {"type": "str", "min_length": 1}}},
                "model_name": "LocalMove"}, "config": {"title": "LocalMove"}}),
            "LocalMove",
        )
        .expect("LocalMove 스키마")
    }

    /// 폼 `code: Annotated[str, Form(pattern=r"^[A-Z]{1,4}$")]` (SYNC-API-001#POST/api/projects/bundle, 카드 L15)
    pub fn bundle_code() -> Validator {
        Validator::new(&json!({"type": "str", "pattern": "^[A-Z]{1,4}$"}), "code")
            .expect("code 스키마")
    }

    /// 폼 `name: Annotated[str, Form(max_length=100)]`
    pub fn bundle_name() -> Validator {
        Validator::new(&json!({"type": "str", "max_length": 100}), "name").expect("name 스키마")
    }

    /// 질의 `stage: int | None = Query(None, ge=1, le=11)` (SYNC-API-001#GET/api/projects/{code}/docs)
    pub fn stage() -> Validator {
        Validator::new(
            &json!({"type": "nullable", "schema": {"type": "int", "ge": 1, "le": 11}}),
            "stage",
        )
        .expect("stage 스키마")
    }

    /// 질의 `status: str | None = Query(None, pattern="^(draft|approved)$")`
    pub fn doc_status() -> Validator {
        Validator::new(
            &json!({"type": "nullable", "schema": {"type": "str", "pattern": "^(draft|approved)$"}}),
            "status",
        )
        .expect("status 스키마")
    }

    /// 질의 `kind: str = Query(pattern="^(broken_ref|convention_errors|incomplete)$")` (…/flags)
    pub fn flag_kind() -> Validator {
        Validator::new(
            &json!({"type": "str", "pattern": "^(broken_ref|convention_errors|incomplete)$"}),
            "kind",
        )
        .expect("kind 스키마")
    }

    /// 질의 `scope: GraphScope = GraphScope.all` — 값이 둘인 StrEnum(오류 문장이 literal과 같다)
    pub fn graph_scope() -> Validator {
        Validator::new(
            &json!({"type": "literal", "expected": ["all", "approved"]}),
            "scope",
        )
        .expect("scope 스키마")
    }

    /// 질의 `int = Query(ge=1)` (…/diff의 `from`·`to`)
    pub fn version_no() -> Validator {
        Validator::new(&json!({"type": "int", "ge": 1}), "int").expect("판 번호 스키마")
    }

    /// `ChangeStatus` — `to: Literal["draft", "approved"]`, `reason: str | None = None` (POST …/status)
    pub fn change_status() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "ChangeStatus", "schema": {"type": "model-fields", "fields": {
                "to": {"type": "model-field", "schema": {"type": "literal", "expected": ["draft", "approved"]}},
                "reason": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}}},
                "model_name": "ChangeStatus"}, "config": {"title": "ChangeStatus"}}),
            "ChangeStatus",
        )
        .expect("ChangeStatus 스키마")
    }

    /// `Revert` — `to_version: int = Field(ge=1)`, `confirm_item_deletion: bool = False` (POST …/revert)
    pub fn revert() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "Revert", "schema": {"type": "model-fields", "fields": {
                "to_version": {"type": "model-field", "schema": {"type": "int", "ge": 1}},
                "confirm_item_deletion": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "bool"}, "default": false}}},
                "model_name": "Revert"}, "config": {"title": "Revert"}}),
            "Revert",
        )
        .expect("Revert 스키마")
    }

    /// `MoveToGithub` — `remote_url: str = Field(min_length=1)` (POST /api/admin/repos/{code}/move-to-github)
    pub fn move_to_github() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "MoveToGithub", "schema": {"type": "model-fields", "fields": {
                "remote_url": {"type": "model-field", "schema": {"type": "str", "min_length": 1}}},
                "model_name": "MoveToGithub"}, "config": {"title": "MoveToGithub"}}),
            "MoveToGithub",
        )
        .expect("MoveToGithub 스키마")
    }

    /// 질의 `file: str = Query(min_length=1)` (GET /api/projects/{code}/code/source)
    pub fn code_file() -> Validator {
        Validator::new(&json!({"type": "str", "min_length": 1}), "str").expect("file 스키마")
    }

    /// `AskRequest` — 파이썬 판 `web/schemas/documents.py` (POST /api/docs/{docId}/ask, 카드 L14)
    pub fn ask_request() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "AskRequest", "schema": {"type": "model-fields", "fields": {
                "question": {"type": "model-field", "schema": {"type": "str"}},
                "conversation_id": {"type": "model-field", "schema": {"type": "int"}},
                "item_id": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}},
                "attachment_ids": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "list", "items_schema": {"type": "int"}}, "default": []}}},
                "model_name": "AskRequest"}, "config": {"title": "AskRequest"}}),
            "AskRequest",
        )
        .expect("AskRequest 스키마")
    }

    /// `AskCodeRequest` — 파이썬 판 `web/schemas/documents.py` (POST /api/projects/{code}/code/ask, 카드 L14)
    pub fn ask_code_request() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "AskCodeRequest", "schema": {"type": "model-fields", "fields": {
                "question": {"type": "model-field", "schema": {"type": "str"}},
                "conversation_id": {"type": "model-field", "schema": {"type": "int"}},
                "key": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}},
                "attachment_ids": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "list", "items_schema": {"type": "int"}}, "default": []}}},
                "model_name": "AskCodeRequest"}, "config": {"title": "AskCodeRequest"}}),
            "AskCodeRequest",
        )
        .expect("AskCodeRequest 스키마")
    }

    /// `CreateConversation` — `title: str | None = None` (POST /api/projects/{code}/conversations, 카드 L14)
    pub fn create_conversation() -> Validator {
        Validator::new(
            &json!({"type": "model", "cls": "CreateConversation", "schema": {"type": "model-fields", "fields": {
                "title": {"type": "model-field", "schema": {"type": "default", "schema": {"type": "nullable", "schema": {"type": "str"}}, "default": null}}},
                "model_name": "CreateConversation"}, "config": {"title": "CreateConversation"}}),
            "CreateConversation",
        )
        .expect("CreateConversation 스키마")
    }

    /// 질의 `confirm: bool = Query(False)` (DELETE /api/docs/{docId})
    pub fn flag() -> Validator {
        Validator::new(&json!({"type": "bool"}), "bool").expect("bool 스키마")
    }

    /// 경로의 `int` 값
    /// `TraceRecord` — 파이썬 판 `web/schemas/trace.py`의 core schema 그대로 (POST /api/projects/{code}/traces, 카드 L28)
    pub fn trace_record() -> Validator {
        let schema: serde_json::Value =
            serde_json::from_str(include_str!("trace_record.json")).expect("TraceRecord JSON");
        Validator::new(&schema, "TraceRecord").expect("TraceRecord 스키마")
    }

    pub fn int() -> Validator {
        Validator::new(&json!({"type": "int"}), "int").expect("int 스키마")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn query_like_parse_qsl() {
        let q = query_params(Some("a=1&&b&c=x+y%20z&a=2&d=%zz%E2%82%AC%FF"));
        assert_eq!(
            q,
            [
                ("a".to_string(), "1".to_string()),
                ("b".to_string(), String::new()),
                ("c".to_string(), "x y z".to_string()),
                ("a".to_string(), "2".to_string()),
                ("d".to_string(), "%zz€\u{fffd}".to_string()),
            ]
        );
        assert_eq!(query_get(&q, "a"), Some("2"));
        assert!(query_params(None).is_empty());
    }

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
