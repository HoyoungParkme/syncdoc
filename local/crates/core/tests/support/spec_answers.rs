//! 명세 엔진의 답 — Rust 쪽 (SYNC-MS-014 0장). `xtask/py/spec_answers.py`와 같은 꼴로 만든다.
//! `cargo test`(정답 파일)와 `cargo xtask spec-diff`(무작위·실제 명세)가 같이 쓴다 — xtask는 `#[path]`로 가져간다.

#![allow(dead_code)]

use std::collections::HashSet;

use serde_json::{Map, Value, json};
use syncdoc_core::errors::Problem;
use syncdoc_core::markdown;
use syncdoc_core::pycompat::difflib::unified_diff;
use syncdoc_core::spec::{SUBTYPES, SpecService, TYPES};
use syncdoc_core::types::{DocStatus, DocType, Entry};

fn s<'a>(case: &'a Value, k: &str) -> &'a str {
    case[k]
        .as_str()
        .unwrap_or_else(|| panic!("사례에 {k}가 없다"))
}

fn doc_type(v: &str) -> DocType {
    DocType::parse(v).unwrap_or_else(|| panic!("모르는 타입 {v}"))
}

/// 파이썬 `Problem.to_dict()` 꼴
fn problem_dict(p: &Problem) -> Value {
    let mut m = Map::new();
    m.insert(
        "type".into(),
        Value::from(match p.kind() {
            Some(k) => format!("urn:syncdoc:{k}"),
            None => "about:blank".to_string(),
        }),
    );
    m.insert("title".into(), Value::from(p.title()));
    m.insert("status".into(), Value::from(p.status()));
    if let Some(d) = p.detail() {
        m.insert("detail".into(), Value::from(d));
    }
    for (k, v) in p.extras() {
        m.insert(k.into(), v);
    }
    Value::Object(m)
}

/// TYPES·SUBTYPES — 파이썬 `spec_answers.patterns()` 꼴
pub fn patterns() -> Value {
    json!({
        "types": TYPES.iter().map(|(k, p, s)| json!([k, p, s])).collect::<Vec<_>>(),
        "subtypes": SUBTYPES.iter().map(|(t, k, p, s)| json!([t, k, p, s])).collect::<Vec<_>>(),
    })
}

/// 본문 하나 — 파이썬 `body_answer`
pub fn body_answer(case: &Value) -> Value {
    let body = s(case, "body");
    let dt = doc_type(s(case, "doc_type"));
    let mut out = case.as_object().cloned().unwrap_or_default();
    let (fm, n) = markdown::parse_frontmatter(body);
    out.insert(
        "frontmatter".into(),
        Value::from(fm.iter().map(|(k, v)| json!([k, v])).collect::<Vec<_>>()),
    );
    out.insert("frontmatter_lines".into(), Value::from(n));
    out.insert("masked".into(), json!(markdown::masked_lines(body)));
    out.insert(
        "headings".into(),
        Value::from(
            markdown::headings(body)
                .into_iter()
                .map(|(i, l, t, r)| json!([i, l, t, r]))
                .collect::<Vec<_>>(),
        ),
    );
    out.insert(
        "item_blocks".into(),
        json!(SpecService::item_blocks(body, dt, case["title"].as_str())),
    );
    let mut checks = Vec::new();
    for c in case["checks"].as_array().into_iter().flatten() {
        let deleted: HashSet<String> = c["deleted"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|x| x.as_str().map(str::to_string))
            .collect();
        let entry = Entry::parse(s(c, "entry")).expect("입구");
        let cs = c["current_status"]
            .as_str()
            .map(|x| DocStatus::parse(x).expect("상태"));
        let r = SpecService::check(body, s(case, "doc_type"), entry, cs, &deleted);
        let mut m = c.as_object().cloned().unwrap_or_default();
        m.insert("result".into(), json!(r));
        checks.push(Value::Object(m));
    }
    out.insert("checks".into(), Value::from(checks));
    let mut applied = Vec::new();
    for a in case["apply"].as_array().into_iter().flatten() {
        let mut m = a.as_object().cloned().unwrap_or_default();
        match SpecService::apply_frontmatter(
            body,
            s(a, "doc_id"),
            s(a, "doc_type"),
            DocStatus::parse(s(a, "status")).expect("상태"),
        ) {
            Ok(b) => m.insert("ok".into(), Value::from(b)),
            Err(p) => m.insert("error".into(), problem_dict(&p)),
        };
        applied.push(Value::Object(m));
    }
    out.insert("apply".into(), Value::from(applied));
    Value::Object(out)
}

/// 두 본문 diff — 파이썬 `diff_answer`
pub fn diff_answer(case: &Value) -> Value {
    let mut out = case.as_object().cloned().unwrap_or_default();
    let d = SpecService::diff_bodies(
        s(case, "from"),
        s(case, "to"),
        doc_type(s(case, "doc_type")),
        case["from_no"].as_i64().expect("from_no") as i32,
        case["to_no"].as_i64().expect("to_no") as i32,
        case["context"].as_u64().expect("context") as usize,
    );
    out.insert("diff".into(), json!(d));
    Value::Object(out)
}

/// 줄 목록 둘의 unified_diff — 파이썬 `difflib_answer`
pub fn difflib_answer(case: &Value) -> Value {
    let lines = |k: &str| -> Vec<String> {
        case[k]
            .as_array()
            .into_iter()
            .flatten()
            .map(|x| x.as_str().unwrap_or_default().to_string())
            .collect()
    };
    let (a, b) = (lines("a"), lines("b"));
    let ar: Vec<&str> = a.iter().map(String::as_str).collect();
    let br: Vec<&str> = b.iter().map(String::as_str).collect();
    let mut out = case.as_object().cloned().unwrap_or_default();
    out.insert(
        "unified".into(),
        json!(unified_diff(
            &ar,
            &br,
            case["n"].as_u64().expect("n") as usize
        )),
    );
    Value::Object(out)
}

/// 사례 하나의 Rust 답 — 파이썬 답에서 입력만 남겨 다시 만든다
pub fn answer(case: &Value) -> Value {
    match case["kind"].as_str() {
        Some("body") => body_answer(case),
        Some("diff") => diff_answer(case),
        Some("difflib") => difflib_answer(case),
        other => panic!("모르는 사례 {other:?}"),
    }
}

/// 파이썬 답의 입력만 — 답 키를 뺀다
pub fn input_of(answered: &Value) -> Value {
    let mut m = answered.as_object().cloned().unwrap_or_default();
    for k in [
        "frontmatter",
        "frontmatter_lines",
        "masked",
        "headings",
        "item_blocks",
        "diff",
        "unified",
    ] {
        m.remove(k);
    }
    if let Some(Value::Array(cs)) = m.get_mut("checks") {
        for c in cs {
            if let Some(o) = c.as_object_mut() {
                o.remove("result");
            }
        }
    }
    if let Some(Value::Array(aps)) = m.get_mut("apply") {
        for a in aps {
            if let Some(o) = a.as_object_mut() {
                o.remove("ok");
                o.remove("error");
            }
        }
    }
    Value::Object(m)
}

/// 처음 다른 자리 — 같으면 None
pub fn first_difference(path: &str, want: &Value, got: &Value) -> Option<String> {
    match (want, got) {
        (Value::Object(a), Value::Object(b)) => {
            for (k, va) in a {
                match b.get(k) {
                    Some(vb) => {
                        if let Some(d) = first_difference(&format!("{path}.{k}"), va, vb) {
                            return Some(d);
                        }
                    }
                    None => return Some(format!("{path}.{k}: Rust에 없다")),
                }
            }
            b.keys()
                .find(|k| !a.contains_key(*k))
                .map(|k| format!("{path}.{k}: 파이썬에 없다"))
        }
        (Value::Array(a), Value::Array(b)) => {
            for (i, (va, vb)) in a.iter().zip(b).enumerate() {
                if let Some(d) = first_difference(&format!("{path}[{i}]"), va, vb) {
                    return Some(d);
                }
            }
            (a.len() != b.len())
                .then(|| format!("{path}: 길이 파이썬 {} · Rust {}", a.len(), b.len()))
        }
        _ => (want != got).then(|| format!("{path}: 파이썬 {want} · Rust {got}")),
    }
}
