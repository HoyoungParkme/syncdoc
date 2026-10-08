//! 요청 하나 → 결과 또는 오류 — mcp 2.2.0 `server/runner.py`(`ServerRunner._on_request`)·
//! `shared/jsonrpc_dispatcher.py`(예외 → 오류)·`MCPServer` 처리기를 옮겼다 (SYNC-API-002 1장).
//! 세션 없는 전송이라 요청마다 연결이 새로 나고 「태어날 때부터 준비됨」이다 — initialize 문지기가 없다.

use crate::compat::pydantic::{Failure, Opts};
use crate::compat::pyvalue::{PyDict, PyStr, PyValue};

use super::decl::decl;
use super::tools;

/// JSON-RPC 오류의 `data` — 파이썬은 넣은 것만 싣는다(`exclude_unset`)
pub enum ErrData {
    Unset,
    Str(String),
    /// 이미 JSON인 값
    Json(String),
}

pub enum Outcome {
    /// 결과 JSON(바이트 그대로)
    Ok(String),
    Err {
        code: i64,
        message: String,
        data: ErrData,
    },
}

fn method_not_found(method: &str) -> Outcome {
    Outcome::Err {
        code: -32601,
        message: "Method not found".into(),
        data: ErrData::Str(method.to_string()),
    }
}

/// `ValidationError` → INVALID_PARAMS, 파이썬 문장은 싣지 않는다
fn invalid_params() -> Outcome {
    Outcome::Err {
        code: -32602,
        message: "Invalid request parameters".into(),
        data: ErrData::Str(String::new()),
    }
}

/// 처리기의 그 밖의 예외 — `code=0, message=str(e)`
fn handler_exception(e: String) -> Outcome {
    Outcome::Err {
        code: 0,
        message: e,
        data: ErrData::Unset,
    }
}

fn opts() -> Opts {
    Opts {
        by_name: Some(false),
        ..Opts::default()
    }
}

fn field<'a>(v: &'a PyValue, name: &str) -> Option<&'a PyValue> {
    v.as_dict().and_then(|d| d.get(&PyStr::from(name)))
}

/// `ServerRunner._on_request` — `version`은 요청 머리의 판(없으면 기본 판)
pub fn dispatch(method: &str, params: Option<&PyValue>, version: &str) -> Outcome {
    let d = decl();
    // RequestStateBoundary — 미들웨어라 판 문지기·검증보다 먼저. 봉인 키가 프로세스마다 새것이라
    // 클라이언트가 보낸 requestState는 무엇이든 풀리지 않는다(mcp server/request_state.py)
    if d.input_required.contains(method)
        && params
            .and_then(|p| field(p, "requestState"))
            .is_some_and(|s| !s.is_none())
    {
        return Outcome::Err {
            code: -32602,
            message: "Invalid or expired requestState".into(),
            data: ErrData::Json("{\"reason\":\"invalid_request_state\"}".into()),
        };
    }
    if d.spec_client_methods.contains(method) {
        // 판 문지기 — 그 판에 없는 메서드는 METHOD_NOT_FOUND
        if !d
            .methods_by_version
            .get(version)
            .is_some_and(|m| m.contains(method))
        {
            return method_not_found(method);
        }
        // 표면 검증 — 봉투 자리표시를 붙여 판의 꼴로 본다
        let Some(surface) = d.surface.get(method) else {
            return method_not_found(method);
        };
        let mut body = PyDict::new();
        body.insert(PyStr::from("jsonrpc"), PyValue::str("2.0"));
        body.insert(PyStr::from("id"), PyValue::Int(0.into()));
        body.insert(PyStr::from("method"), PyValue::str(method));
        if let Some(p) = params {
            body.insert(PyStr::from("params"), p.clone());
        }
        match surface.validate(&PyValue::Dict(body), opts()) {
            Ok(_) => {}
            Err(Failure::Invalid(_)) => return invalid_params(),
            Err(Failure::Exception(e)) => return handler_exception(e),
        }
    }
    if method == "initialize" {
        return initialize(params);
    }
    if !d.handled.contains(method) {
        return method_not_found(method);
    }
    let empty = PyValue::Dict(PyDict::new());
    let input = params.unwrap_or(&empty);
    let typed = match d.handlers.get(method).map(|v| v.validate(input, opts())) {
        Some(Ok(v)) => v,
        Some(Err(Failure::Invalid(_))) => return invalid_params(),
        Some(Err(Failure::Exception(e))) => return handler_exception(e),
        None => return method_not_found(method),
    };
    match method {
        "ping" => Outcome::Ok("{}".into()),
        "tools/list" | "resources/list" | "resources/templates/list" | "prompts/list" => {
            match d.results.get(version).and_then(|m| m.get(method)) {
                Some(r) => Outcome::Ok(r.clone()),
                None => handler_exception(format!("결과 없음 {method} {version}")),
            }
        }
        "prompts/get" => {
            let name = field(&typed, "name").map(text).unwrap_or_default();
            handler_exception(format!("Unknown prompt: {name}"))
        }
        "resources/read" => {
            let uri = field(&typed, "uri").map(text).unwrap_or_default();
            Outcome::Err {
                code: -32602,
                message: format!("Unknown resource: {uri}"),
                data: ErrData::Json(format!(
                    "{{\"uri\":{}}}",
                    serde_json::to_string(&uri).unwrap_or_default()
                )),
            }
        }
        "tools/call" => {
            let name = field(&typed, "name").map(text).unwrap_or_default();
            let args = field(&typed, "arguments").filter(|a| !a.is_none());
            Outcome::Ok(tools::call(&name, args))
        }
        _ => method_not_found(method),
    }
}

fn text(v: &PyValue) -> String {
    match v {
        PyValue::Str(PyStr::Utf8(s)) => s.clone(),
        PyValue::Str(s) => s.repr(),
        other => other.safe_repr(),
    }
}

/// `_handle_initialize` — 판 협상, 결과는 그 판의 고정 결과
fn initialize(params: Option<&PyValue>) -> Outcome {
    let d = decl();
    let empty = PyValue::Dict(PyDict::new());
    let p = match d
        .initialize_params
        .validate(params.unwrap_or(&empty), opts())
    {
        Ok(v) => v,
        Err(Failure::Invalid(_)) => return invalid_params(),
        Err(Failure::Exception(e)) => return handler_exception(e),
    };
    let requested = field(&p, "protocol_version").map(text).unwrap_or_default();
    let negotiated = if d.handshake.contains(&requested) {
        requested
    } else {
        d.latest_handshake.clone()
    };
    match d.results.get(&negotiated).and_then(|m| m.get("initialize")) {
        Some(r) => Outcome::Ok(r.clone()),
        None => handler_exception(format!("결과 없음 initialize {negotiated}")),
    }
}
