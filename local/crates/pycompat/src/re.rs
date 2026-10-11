//! 파이썬 정규식 문자열 → `regex` (SYNC-DOM-004 1장 pycompat).
//! 명세 엔진이 쓰는 파이썬 패턴(항목 패턴 표·헤딩·참조…)을 글자 그대로 두고, `\s`·`\S`·`\d`·`\w`만
//! 파이썬 3.12 표(`unicode.rs`)의 문자 클래스로 바꿔 컴파일한다. 나머지 문법(`(?:…)`·`{m,n}`·`*?`·`[…]`)은
//! 두 엔진이 같은 뜻이다. 파이썬 `$`(끝 또는 끝 줄바꿈 앞)는 줄바꿈 없는 글에만 쓴다 — 그 글에서는 같다.
//! 룩비하인드 같은 `regex`에 없는 문법은 쓰는 쪽이 손으로 본다.

use regex::Regex;

use super::unicode::{DECIMAL, SPACE, WORD};

/// 파이썬 패턴을 컴파일한다 — 패턴은 코드에 박힌 상수라 틀리면 바로 멈춘다
pub fn compile(pattern: &str) -> Regex {
    Regex::new(&translate(pattern))
        .unwrap_or_else(|e| panic!("파이썬 패턴을 옮기지 못했다 {pattern:?}: {e}"))
}

/// `\s`·`\S`·`\d`·`\w`를 표의 문자 클래스로 — 클래스 안이면 구간만 넣는다
pub fn translate(pattern: &str) -> String {
    let mut out = String::with_capacity(pattern.len() * 4);
    let mut chars = pattern.chars().peekable();
    let mut in_class = false;
    let mut class_start = false; // 방금 `[`·`[^`를 열었다 — 여기의 `]`는 글자다
    while let Some(c) = chars.next() {
        match c {
            '\\' => {
                let Some(e) = chars.next() else {
                    out.push('\\');
                    break;
                };
                let body = match e {
                    's' | 'S' => Some(ranges(&SPACE)),
                    'd' => Some(ranges(&DECIMAL)),
                    'w' => Some(ranges(&WORD)),
                    _ => None,
                };
                match (body, in_class) {
                    (Some(b), false) if e == 'S' => {
                        out.push_str("[^");
                        out.push_str(&b);
                        out.push(']');
                    }
                    (Some(b), false) => {
                        out.push('[');
                        out.push_str(&b);
                        out.push(']');
                    }
                    (Some(b), true) if e == 'S' => {
                        out.push_str("[^");
                        out.push_str(&b);
                        out.push(']');
                    }
                    (Some(b), true) => out.push_str(&b),
                    (None, _) => {
                        out.push('\\');
                        out.push(e);
                    }
                }
                // 클래스 안 `\w-`의 `-`는 파이썬에서 글자다(구간이 될 수 없다)
                if in_class && matches!(e, 's' | 'S' | 'd' | 'w') && chars.peek() == Some(&'-') {
                    chars.next();
                    out.push_str("\\-");
                }
                class_start = false;
            }
            '[' if !in_class => {
                in_class = true;
                class_start = true;
                out.push('[');
                if chars.peek() == Some(&'^') {
                    chars.next();
                    out.push('^');
                }
            }
            ']' if in_class && !class_start => {
                in_class = false;
                out.push(']');
            }
            ']' if in_class => {
                out.push_str("\\]");
                class_start = false;
            }
            '[' => {
                // 파이썬 클래스 안의 `[`는 글자다 — regex에서는 중첩 클래스라 이스케이프한다
                out.push_str("\\[");
                class_start = false;
            }
            _ => {
                out.push(c);
                class_start = false;
            }
        }
    }
    out
}

/// 표 → `\x{lo}-\x{hi}…` — 서로게이트(regex가 못 받는다)는 뺀다
fn ranges(table: &[(u32, u32)]) -> String {
    let mut s = String::new();
    for &(lo, hi) in table {
        for (a, b) in [(lo, hi.min(0xD7FF)), (lo.max(0xE000), hi)] {
            if a > b {
                continue;
            }
            s.push_str(&format!("\\x{{{a:X}}}"));
            if b > a {
                s.push_str(&format!("-\\x{{{b:X}}}"));
            }
        }
    }
    s
}

#[cfg(test)]
mod tests {
    use super::compile;

    #[test]
    fn python_classes() {
        assert!(compile(r"^\d+$").is_match("１２"));
        assert!(!compile(r"^\d+$").is_match("²"));
        assert!(compile(r"^\S+$").is_match("a\u{feff}"));
        assert!(!compile(r"^\S+$").is_match("a\x1c"));
        assert!(compile(r"^[\w-]+$").is_match("SYNC-MS-014"));
        assert!(compile(r"^[\d.]+\s*").is_match("1.2\x1f"));
        assert!(compile(r"\[\[([^\]]+)\]\]").is_match("[[A#B]]"));
        assert!(compile(r"^(?:(GET|POST)/\S+|[a-z][a-z_]+)$").is_match("GET/api/x"));
    }
}
