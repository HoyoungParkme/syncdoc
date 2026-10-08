//! 도구 부르기 — mcp 2.2.0 `MCPServer._handle_call_tool`·`Tool.run`·`FuncMetadata.pre_parse_json`을 옮겼다.
//! 인자 검증은 파이썬과 같은 문장을 낸다. 검증을 지난 도구는 그 도구를 만들 카드 전까지 `not-implemented`다
//! (SYNC-CODE-002 L3 표, 사용자 결정 2026-10-08).

use crate::compat::pydantic::{Failure, Opts};
use crate::compat::pyjson::{self, Depth};
use crate::compat::pyvalue::{PyDict, PyValue};

use super::decl::decl;

/// 도구 인자의 문자열을 JSON으로 미리 읽을 때 파이썬 C 재귀가 남긴 깊이 — 파이썬 판 MCP 경로에서 잰 값
pub const ARG_JSON_DEPTH: Depth = Depth(9_987);

/// `tools/call` 결과 JSON — 늘 `CallToolResult`(오류도 `isError`로)
pub fn call(name: &str, arguments: Option<&PyValue>) -> String {
    let d = decl();
    let Some(tool) = d.tools.get(name) else {
        return error_result(&format!("Unknown tool: {name}"));
    };
    let args = match arguments {
        Some(PyValue::Dict(a)) => a.clone(),
        _ => PyDict::new(),
    };
    let parsed = pre_parse_json(
        &args,
        |k| tool.keys.contains(k),
        |k| tool.str_fields.contains(k),
    );
    match tool
        .validator
        .validate(&PyValue::Dict(parsed), Opts::default())
    {
        Ok(_) => error_result(&not_implemented(tool.card)),
        Err(Failure::Invalid(e)) => error_result(&format!(
            "Error executing tool {name}: {}",
            e.display(&d.url_prefix)
        )),
        Err(Failure::Exception(_)) => error_result(&format!("Error executing tool {name}")),
    }
}

/// `pre_parse_json` — 모델 필드이고 주석이 `str`가 아닌 인자의 문자열을 JSON으로 읽어 본다.
/// 읽은 것이 str·int·float(bool 포함)면 그대로 둔다. 못 읽으면 그대로 둔다
fn pre_parse_json(
    data: &PyDict,
    is_field: impl Fn(&str) -> bool,
    is_str: impl Fn(&str) -> bool,
) -> PyDict {
    let mut out = data.clone();
    for (k, v) in data {
        let Some(key) = k.as_str() else { continue };
        if !is_field(key) || is_str(key) {
            continue;
        }
        let PyValue::Str(s) = v else { continue };
        match pyjson::loads_str(s, ARG_JSON_DEPTH) {
            Ok(PyValue::Str(_) | PyValue::Int(_) | PyValue::Float(_) | PyValue::Bool(_))
            | Err(_) => {}
            Ok(parsed) => {
                out.insert(k.clone(), parsed);
            }
        }
    }
    out
}

/// 파이썬 판 도구의 `_problem(NotImplementedYet(card))` — `json.dumps(…, ensure_ascii=False)`(기본 구분자)
fn not_implemented(card: &str) -> String {
    format!(
        "{{\"type\": \"urn:syncdoc:not-implemented\", \"title\": \"not-implemented\", \"status\": 501, \"detail\": {}, \"card\": {}}}",
        py_json_str(&format!("{card}: 아직 구현되지 않음")),
        py_json_str(card)
    )
}

/// 파이썬 `json.dumps(str, ensure_ascii=False)` — 제어 글자·따옴표·역슬래시만 이스케이프
fn py_json_str(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_default()
}

/// `CallToolResult(content=[TextContent(text)], is_error=True)`를 판의 꼴로 — 키는 알파벳 차례
fn error_result(text: &str) -> String {
    format!(
        "{{\"content\":[{{\"text\":{},\"type\":\"text\"}}],\"isError\":true}}",
        serde_json::to_string(text).unwrap_or_default()
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_tool_like_python() {
        assert_eq!(
            call("nope", None),
            r#"{"content":[{"text":"Unknown tool: nope","type":"text"}],"isError":true}"#
        );
    }

    #[test]
    fn valid_call_is_not_implemented_with_its_card() {
        let mut a = PyDict::new();
        a.insert("doc_id".into(), PyValue::str("X-PRD-001"));
        let out = call("get_document", Some(&PyValue::Dict(a)));
        assert!(out.contains(r#"\"card\": \"L7\""#), "{out}");
    }
}
