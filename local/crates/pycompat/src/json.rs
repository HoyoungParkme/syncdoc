//! 파이썬 `json.dumps(x, ensure_ascii=…)` — 기본 구분자 `, `·`: `, 키는 넣은 차례 (카드 L14).
//! 질문 도구의 결과·SSE 프레임·모델에 보내는 도구 인자(`ensure_ascii=True`)가 파이썬 판과 같은 글자가 되게 쓴다.
//! 수는 받은 글자 그대로다(`serde_json`의 `arbitrary_precision`) — 파이썬이 다시 쓰는 실수 꼴은 옮기지 않는다

use serde_json::Value;

/// 파이썬 `json.dumps(s)`의 글자 하나 — `ensure_ascii`면 공백~`~` 밖을 `\uXXXX`로(BMP 밖은 대리 쌍)
pub fn dumps_str(s: &str, ensure_ascii: bool) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c if ensure_ascii && !(' '..='~').contains(&c) => {
                let mut buf = [0u16; 2];
                for unit in c.encode_utf16(&mut buf) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// 파이썬 `json.dumps(v, ensure_ascii=…)`
pub fn dumps(v: &Value, ensure_ascii: bool) -> String {
    match v {
        Value::Object(m) => {
            let items: Vec<String> = m
                .iter()
                .map(|(k, v)| format!("{}: {}", dumps_str(k, ensure_ascii), dumps(v, ensure_ascii)))
                .collect();
            format!("{{{}}}", items.join(", "))
        }
        Value::Array(a) => format!(
            "[{}]",
            a.iter()
                .map(|x| dumps(x, ensure_ascii))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::String(s) => dumps_str(s, ensure_ascii),
        Value::Bool(true) => "true".into(),
        Value::Bool(false) => "false".into(),
        Value::Null => "null".into(),
        Value::Number(n) => n.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dumps_like_python() {
        let v: Value =
            serde_json::from_str(r#"{"a": [1, true, null], "b": "가\"\n\u007f😀", "c": {}}"#)
                .expect("JSON");
        assert_eq!(
            dumps(&v, false),
            "{\"a\": [1, true, null], \"b\": \"가\\\"\\n\u{7f}😀\", \"c\": {}}"
        );
        assert_eq!(
            dumps(&v, true),
            r#"{"a": [1, true, null], "b": "\uac00\"\n\u007f\ud83d\ude00", "c": {}}"#
        );
    }
}
