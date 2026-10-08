//! MCP 선언 — `declarations.json`(파이썬 판에서 `cargo xtask mcp-tools`가 뽑은 것)을 읽어 둔다.
//! 서버 이름·안내문이 든 고정 결과, 판 목록, 검증기(봉투·메서드 표면·처리기 인자·도구 인자).

use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use serde_json::Value;

use crate::compat::pydantic::Validator;

const RAW: &str = include_str!("declarations.json");

/// 도구 하나 — 인자 검증기와 그 도구를 만들 Rust 카드
pub struct ToolDecl {
    pub validator: Validator,
    /// 주석이 `str` 그대로인 인자 — `pre_parse_json`이 JSON으로 미리 읽지 않는다
    pub str_fields: HashSet<String>,
    /// 인자 이름·별칭 → 모델 필드가 있나
    pub keys: HashSet<String>,
    pub card: &'static str,
}

pub struct Decl {
    pub url_prefix: String,
    pub handshake: Vec<String>,
    pub latest_handshake: String,
    pub default_negotiated: String,
    pub spec_client_methods: HashSet<String>,
    pub methods_by_version: HashMap<String, HashSet<String>>,
    pub handled: HashSet<String>,
    /// `requestState`를 실어 오면 검증 전에 거절하는 메서드 (`RequestStateBoundary`)
    pub input_required: HashSet<String>,
    /// 판 → 메서드 → 결과 JSON(바이트 그대로)
    pub results: HashMap<String, HashMap<String, String>>,
    pub envelope: Validator,
    pub surface: HashMap<String, Validator>,
    pub handlers: HashMap<String, Validator>,
    pub initialize_params: Validator,
    pub tools: HashMap<String, ToolDecl>,
}

/// 못 만든 도구 → 그 도구를 만들 카드 (SYNC-CODE-002 L3 표)
fn card_of(tool: &str) -> &'static str {
    match tool {
        "init_project" | "get_template" => "L6",
        "list_documents" | "get_document" | "get_item" | "get_references" | "create_document"
        | "update_document" => "L7",
        "delete_document" | "restore_document" | "change_status" => "L9",
        "upload_code" => "L10",
        "get_code_graph" => "L12",
        _ => "L3",
    }
}

fn strings(v: &Value) -> Vec<String> {
    v.as_array()
        .map(|a| {
            a.iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn validator(v: &Value) -> Validator {
    let title = v.get("title").and_then(Value::as_str).unwrap_or("");
    Validator::new(&v["schema"], title)
        .unwrap_or_else(|e| panic!("declarations.json 스키마 {title}: {}", e.0))
}

fn load() -> Decl {
    let d: Value = serde_json::from_str(RAW).expect("declarations.json");
    let s = &d["schemas"];
    let map = |v: &Value| -> HashMap<String, Validator> {
        v.as_object()
            .map(|o| o.iter().map(|(k, v)| (k.clone(), validator(v))).collect())
            .unwrap_or_default()
    };
    let mut tools = HashMap::new();
    if let Some(o) = s["tool_args"].as_object() {
        for (name, t) in o {
            let mut keys: HashSet<String> = HashSet::new();
            if let Some(f) = t["schema"]["schema"]["fields"].as_object() {
                for (fname, f) in f {
                    keys.insert(fname.clone());
                    if let Some(a) = f.get("validation_alias").and_then(Value::as_str) {
                        keys.insert(a.to_string());
                    }
                }
            }
            tools.insert(
                name.clone(),
                ToolDecl {
                    validator: validator(t),
                    str_fields: strings(&t["str_fields"]).into_iter().collect(),
                    keys,
                    card: card_of(name),
                },
            );
        }
    }
    let results = d["results"]
        .as_object()
        .map(|o| {
            o.iter()
                .map(|(ver, m)| {
                    let inner = m
                        .as_object()
                        .map(|mm| {
                            mm.iter()
                                .map(|(k, v)| (k.clone(), v.as_str().unwrap_or("").to_string()))
                                .collect()
                        })
                        .unwrap_or_default();
                    (ver.clone(), inner)
                })
                .collect()
        })
        .unwrap_or_default();
    let methods_by_version = d["methods_by_version"]
        .as_object()
        .map(|o| {
            o.iter()
                .map(|(v, m)| (v.clone(), strings(m).into_iter().collect()))
                .collect()
        })
        .unwrap_or_default();
    Decl {
        url_prefix: d["pydantic_url_prefix"].as_str().unwrap_or("").to_string(),
        handshake: strings(&d["protocol"]["handshake"]),
        latest_handshake: d["protocol"]["latest_handshake"]
            .as_str()
            .unwrap_or("")
            .to_string(),
        default_negotiated: d["protocol"]["default_negotiated"]
            .as_str()
            .unwrap_or("")
            .to_string(),
        spec_client_methods: strings(&d["spec_client_methods"]).into_iter().collect(),
        methods_by_version,
        handled: strings(&d["handled_methods"]).into_iter().collect(),
        input_required: strings(&d["input_required_methods"]).into_iter().collect(),
        results,
        envelope: validator(&s["envelope"]),
        surface: map(&s["surface"]),
        handlers: map(&s["handlers"]),
        initialize_params: validator(&s["initialize_params"]),
        tools,
    }
}

static DECL: LazyLock<Decl> = LazyLock::new(load);

/// 읽어 둔 선언 — 처음 부를 때 읽고 검증기를 만든다. 켤 때 한 번 불러 둔다(`router`)
pub fn decl() -> &'static Decl {
    &DECL
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn declarations_load() {
        let d = decl();
        assert_eq!(d.tools.len(), 13);
        assert!(d.handshake.contains(&"2025-06-18".to_string()));
        assert!(d.results["2025-06-18"]["initialize"].contains("\"syncdoc_local\""));
    }
}
