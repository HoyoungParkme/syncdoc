//! 파이썬 문자 분류와 `str.strip()` — 생성물 표(`unicode.rs`)를 찾는다 (SYNC-DOM-004 1장 pycompat).
//! Rust 표준(`trim`·`char::is_whitespace`)은 `\x1c`~`\x1f`를 공백으로 안 보고 유니코드 판도 다르다.

use super::unicode::{DECIMAL, NON_PRINTABLE, SPACE, WORD};

/// 오름차순 구간 표에 들었나
pub fn within(table: &[(u32, u32)], cp: u32) -> bool {
    table
        .binary_search_by(|&(lo, hi)| {
            if hi < cp {
                std::cmp::Ordering::Less
            } else if lo > cp {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// 파이썬 `c.isspace()` = `re`의 `\s`
pub fn is_space(c: char) -> bool {
    within(&SPACE, u32::from(c))
}

/// 파이썬 `c.isdecimal()` = `re`의 `\d`
pub fn is_decimal(c: char) -> bool {
    within(&DECIMAL, u32::from(c))
}

/// 파이썬 `c.isalnum() or c == "_"` = `re`의 `\w`
pub fn is_word(c: char) -> bool {
    within(&WORD, u32::from(c))
}

/// 파이썬 `chr(cp).isprintable()`
pub fn is_printable(cp: u32) -> bool {
    !within(&NON_PRINTABLE, cp)
}

/// 파이썬 `s.strip()`
pub fn strip(s: &str) -> &str {
    s.trim_matches(is_space)
}

/// 파이썬 `s.lstrip()`
pub fn lstrip(s: &str) -> &str {
    s.trim_start_matches(is_space)
}

/// 파이썬 `s.rstrip()`
pub fn rstrip(s: &str) -> &str {
    s.trim_end_matches(is_space)
}

/// 파이썬 `s.splitlines()` — `\n`·`\r`·`\r\n`·`\v`·`\f`·`\x1c`~`\x1e`·`\x85`·`\u2028`·`\u2029`에서 끊는다
pub fn py_splitlines(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut it = s.char_indices().peekable();
    while let Some((i, c)) = it.next() {
        let sep = matches!(
            c,
            '\n' | '\r'
                | '\u{0b}'
                | '\u{0c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if !sep {
            continue;
        }
        out.push(&s[start..i]);
        let mut next = i + c.len_utf8();
        if c == '\r' && it.peek().is_some_and(|&(_, n)| n == '\n') {
            it.next();
            next += 1;
        }
        start = next;
    }
    if start < s.len() {
        out.push(&s[start..]);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strip_like_python() {
        assert_eq!(strip("\x1c a \u{3000}"), "a");
        assert_eq!(strip("\u{feff}a"), "\u{feff}a"); // BOM은 공백이 아니다
        assert!(is_decimal('１') && !is_decimal('²') && is_word('²') && !is_word('-'));
        assert!(!is_printable(0x0a) && is_printable(u32::from('가')));
    }

    #[test]
    fn splitlines_like_python() {
        assert_eq!(
            py_splitlines("a\nb\r\nc\rd\x1ce\u{2028}f\n"),
            ["a", "b", "c", "d", "e", "f"]
        );
        assert!(py_splitlines("").is_empty());
        assert_eq!(py_splitlines("a\n\n"), ["a", ""]);
    }
}
