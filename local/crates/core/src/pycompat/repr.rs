//! 파이썬 3.12의 `repr(str)` (SYNC-DOM-004 1장 pycompat).
//! 따옴표는 `'`, 글에 `'`만 있으면 `"` · 인쇄 못 하는 글자는 `\xNN`·`\uNNNN`·`\UNNNNNNNN`.
//! 서버의 `compat::pyvalue`(짝 없는 서로게이트가 있는 글)도 코드 포인트로 이것을 부른다.

use std::fmt::Write;

use super::chars::is_printable;

/// 파이썬 `repr(s)`
pub fn repr(s: &str) -> String {
    repr_code_points(&s.chars().map(u32::from).collect::<Vec<_>>())
}

/// 코드 포인트들의 `repr` — 서로게이트(`0xD800`~`0xDFFF`)도 받는다
pub fn repr_code_points(cps: &[u32]) -> String {
    let has_single = cps.contains(&u32::from('\''));
    let has_double = cps.contains(&u32::from('"'));
    let quote = if has_single && !has_double { '"' } else { '\'' };
    let mut out = String::with_capacity(cps.len() + 2);
    out.push(quote);
    for &cp in cps {
        match cp {
            c if c == u32::from(quote) || c == u32::from('\\') => {
                out.push('\\');
                out.push(char::from_u32(c).unwrap_or('?'));
            }
            0x09 => out.push_str("\\t"),
            0x0A => out.push_str("\\n"),
            0x0D => out.push_str("\\r"),
            c if c < 0x20 || c == 0x7F => {
                let _ = write!(out, "\\x{c:02x}");
            }
            c if c < 0x7F => out.push(char::from_u32(c).unwrap_or('?')),
            c if is_printable(c) && char::from_u32(c).is_some() => {
                out.push(char::from_u32(c).unwrap_or('?'));
            }
            c if c <= 0xFF => {
                let _ = write!(out, "\\x{c:02x}");
            }
            c if c <= 0xFFFF => {
                let _ = write!(out, "\\u{c:04x}");
            }
            c => {
                let _ = write!(out, "\\U{c:08x}");
            }
        }
    }
    out.push(quote);
    out
}

#[cfg(test)]
mod tests {
    use super::repr;

    #[test]
    fn like_python() {
        assert_eq!(repr("ab"), "'ab'");
        assert_eq!(repr("it's"), "\"it's\"");
        assert_eq!(repr("a'\""), "'a\\'\"'");
        assert_eq!(repr("\x1c\u{a0}\u{feff}가"), "'\\x1c\\xa0\\ufeff가'");
    }
}
