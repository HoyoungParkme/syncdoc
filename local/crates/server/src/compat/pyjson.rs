//! 파이썬 `json.loads` — CPython 3.12의 `_json.c` 스캐너를 옮겼다 (SYNC-DOM-004 1장 compat).
//! FastAPI가 요청 본문을 읽을 때(`Request.json()`)와 MCP 도구 인자를 미리 읽을 때(`pre_parse_json`) 쓴다.
//! 오류 위치(`JSONDecodeError.pos`, 글자 단위)가 파이썬과 같아야 한다 — invalid-request의 `loc`이 `body.{pos}`다.

use num_bigint::BigInt;

use super::pyvalue::{INT_MAX_STR_DIGITS, PyDict, PyStr, PyValue};

/// `json.loads`가 낸 예외
#[derive(Debug, Clone, PartialEq)]
pub enum LoadsError {
    /// `json.JSONDecodeError` — 문장과 위치(글자)
    Decode { msg: &'static str, pos: usize },
    /// 바이트를 글자로 못 바꿨다(`UnicodeDecodeError`)
    Unicode,
    /// 정수가 4300자리를 넘는다(`ValueError`)
    IntTooLong,
    /// 너무 깊다(`RecursionError`)
    Recursion,
}

/// 파이썬 C 재귀 한도 안에서 json이 쓸 수 있는 깊이 — 부르는 자리마다 다르다(쓴 만큼 빠진다)
#[derive(Clone, Copy, Debug)]
pub struct Depth(pub usize);

/// `json.loads(bytes)` — 인코딩을 찾아(BOM·0바이트 꼴) `surrogatepass`로 풀고 읽는다
pub fn loads_bytes(b: &[u8], depth: Depth) -> Result<PyValue, LoadsError> {
    let doc = decode_bytes(b).ok_or(LoadsError::Unicode)?;
    decode_doc(&doc, depth)
}

/// `json.loads(str)` — 맨 앞 BOM은 오류다
pub fn loads_str(s: &PyStr, depth: Depth) -> Result<PyValue, LoadsError> {
    let doc = s.code_points();
    if doc.first() == Some(&0xFEFF) {
        return Err(LoadsError::Decode {
            msg: "Unexpected UTF-8 BOM (decode using utf-8-sig)",
            pos: 0,
        });
    }
    decode_doc(&doc, depth)
}

fn decode_doc(doc: &[u32], depth: Depth) -> Result<PyValue, LoadsError> {
    let mut sc = Scanner {
        s: doc,
        remaining: depth.0,
    };
    let idx = skip_ws(doc, 0);
    let (v, end) = match sc.scan_once(idx) {
        Ok(r) => r,
        Err(Stop::At(pos)) => {
            return Err(LoadsError::Decode {
                msg: "Expecting value",
                pos,
            });
        }
        Err(Stop::Err(e)) => return Err(e),
    };
    let end = skip_ws(doc, end);
    if end != doc.len() {
        return Err(LoadsError::Decode {
            msg: "Extra data",
            pos: end,
        });
    }
    Ok(v)
}

fn is_ws(c: u32) -> bool {
    matches!(c, 0x20 | 0x09 | 0x0A | 0x0D)
}

fn skip_ws(s: &[u32], mut i: usize) -> usize {
    while i < s.len() && is_ws(s[i]) {
        i += 1;
    }
    i
}

/// 스캐너의 멈춤 — `StopIteration(idx)`(값이 없다)과 진짜 오류
enum Stop {
    At(usize),
    Err(LoadsError),
}

impl From<LoadsError> for Stop {
    fn from(e: LoadsError) -> Self {
        Stop::Err(e)
    }
}

fn decode_err(msg: &'static str, pos: usize) -> Stop {
    Stop::Err(LoadsError::Decode { msg, pos })
}

struct Scanner<'a> {
    s: &'a [u32],
    remaining: usize,
}

impl Scanner<'_> {
    fn at(&self, i: usize) -> Option<u32> {
        self.s.get(i).copied()
    }

    fn starts_with(&self, i: usize, lit: &str) -> bool {
        let lit: Vec<u32> = lit.chars().map(u32::from).collect();
        self.s.len() >= i + lit.len() && self.s[i..i + lit.len()] == lit[..]
    }

    /// `scan_once_unicode`
    fn scan_once(&mut self, idx: usize) -> Result<(PyValue, usize), Stop> {
        let Some(c) = self.at(idx) else {
            return Err(Stop::At(idx));
        };
        match char::from_u32(c) {
            Some('"') => {
                let (s, end) = self.scanstring(idx + 1)?;
                Ok((PyValue::Str(s), end))
            }
            Some('{') => self.nested(|sc| sc.parse_object(idx + 1)),
            Some('[') => self.nested(|sc| sc.parse_array(idx + 1)),
            Some('n') if self.starts_with(idx, "null") => Ok((PyValue::None, idx + 4)),
            Some('t') if self.starts_with(idx, "true") => Ok((PyValue::Bool(true), idx + 4)),
            Some('f') if self.starts_with(idx, "false") => Ok((PyValue::Bool(false), idx + 5)),
            Some('N') if self.starts_with(idx, "NaN") => Ok((PyValue::Float(f64::NAN), idx + 3)),
            Some('I') if self.starts_with(idx, "Infinity") => {
                Ok((PyValue::Float(f64::INFINITY), idx + 8))
            }
            Some('-') if self.starts_with(idx, "-Infinity") => {
                Ok((PyValue::Float(f64::NEG_INFINITY), idx + 9))
            }
            _ => self.match_number(idx),
        }
    }

    /// `Py_EnterRecursiveCall` — 한도를 넘으면 `RecursionError`
    fn nested(
        &mut self,
        f: impl FnOnce(&mut Self) -> Result<(PyValue, usize), Stop>,
    ) -> Result<(PyValue, usize), Stop> {
        if self.remaining == 0 {
            return Err(Stop::Err(LoadsError::Recursion));
        }
        self.remaining -= 1;
        let r = f(self);
        self.remaining += 1;
        r
    }

    /// `_match_number_unicode`
    fn match_number(&self, start: usize) -> Result<(PyValue, usize), Stop> {
        let s = self.s;
        let end_idx = s.len() as isize - 1;
        let digit = |i: usize| s.get(i).is_some_and(|&c| (0x30..=0x39).contains(&c));
        let mut idx = start;
        if s.get(idx) == Some(&u32::from('-')) {
            idx += 1;
            if idx as isize > end_idx {
                return Err(Stop::At(start));
            }
        }
        match s.get(idx).copied() {
            Some(c) if (0x31..=0x39).contains(&c) => {
                idx += 1;
                while digit(idx) {
                    idx += 1;
                }
            }
            Some(0x30) => idx += 1,
            _ => return Err(Stop::At(start)),
        }
        let mut is_float = false;
        if (idx as isize) < end_idx && s[idx] == u32::from('.') && digit(idx + 1) {
            is_float = true;
            idx += 2;
            while digit(idx) {
                idx += 1;
            }
        }
        if (idx as isize) < end_idx && (s[idx] == u32::from('e') || s[idx] == u32::from('E')) {
            let e_start = idx;
            idx += 1;
            if (idx as isize) < end_idx && (s[idx] == u32::from('-') || s[idx] == u32::from('+')) {
                idx += 1;
            }
            while digit(idx) {
                idx += 1;
            }
            if digit(idx - 1) {
                is_float = true;
            } else {
                idx = e_start;
            }
        }
        let text: String = s[start..idx]
            .iter()
            .filter_map(|&c| char::from_u32(c))
            .collect();
        if is_float {
            let f: f64 = text.parse().unwrap_or(f64::NAN);
            Ok((PyValue::Float(f), idx))
        } else {
            let digits = text.trim_start_matches('-').len();
            if digits > INT_MAX_STR_DIGITS {
                return Err(Stop::Err(LoadsError::IntTooLong));
            }
            let i: BigInt = text.parse().unwrap_or_default();
            Ok((PyValue::Int(i), idx))
        }
    }

    /// `scanstring_unicode` (strict) — `end`는 여는 따옴표 다음
    fn scanstring(&self, end: usize) -> Result<(PyStr, usize), Stop> {
        let s = self.s;
        let len = s.len();
        let begin = end - 1;
        let mut out: Vec<u32> = Vec::new();
        let mut end = end;
        loop {
            // 따옴표·역슬래시·제어 글자까지
            let mut next = end;
            let mut c = 0u32;
            while next < len {
                c = s[next];
                if c == u32::from('"') || c == u32::from('\\') {
                    break;
                }
                if c <= 0x1F {
                    return Err(decode_err("Invalid control character at", next));
                }
                next += 1;
            }
            if !(next < len && (c == u32::from('"') || c == u32::from('\\'))) {
                return Err(decode_err("Unterminated string starting at", begin));
            }
            out.extend_from_slice(&s[end..next]);
            next += 1;
            if c == u32::from('"') {
                end = next;
                break;
            }
            if next == len {
                return Err(decode_err("Unterminated string starting at", begin));
            }
            let c = s[next];
            if c != u32::from('u') {
                end = next + 1;
                let ch = match char::from_u32(c) {
                    Some('"') => '"',
                    Some('\\') => '\\',
                    Some('/') => '/',
                    Some('b') => '\u{8}',
                    Some('f') => '\u{c}',
                    Some('n') => '\n',
                    Some('r') => '\r',
                    Some('t') => '\t',
                    _ => return Err(decode_err("Invalid \\escape", end - 2)),
                };
                out.push(u32::from(ch));
            } else {
                next += 1;
                end = next + 4;
                if end >= len {
                    return Err(decode_err("Invalid \\uXXXX escape", next - 1));
                }
                let mut cp = 0u32;
                while next < end {
                    let Some(d) = hex(s[next]) else {
                        return Err(decode_err("Invalid \\uXXXX escape", end - 5));
                    };
                    cp = (cp << 4) | d;
                    next += 1;
                }
                if (0xD800..=0xDBFF).contains(&cp)
                    && end + 6 < len
                    && {
                        let a = s[next] == u32::from('\\');
                        next += 1;
                        a
                    }
                    && {
                        let b = s[next] == u32::from('u');
                        next += 1;
                        b
                    }
                {
                    let mut c2 = 0u32;
                    end += 6;
                    while next < end {
                        let Some(d) = hex(s[next]) else {
                            return Err(decode_err("Invalid \\uXXXX escape", end - 5));
                        };
                        c2 = (c2 << 4) | d;
                        next += 1;
                    }
                    if (0xDC00..=0xDFFF).contains(&c2) {
                        cp = 0x10000 + (((cp - 0xD800) << 10) | (c2 - 0xDC00));
                    } else {
                        end -= 6;
                    }
                }
                out.push(cp);
            }
        }
        Ok((PyStr::from_code_points(out), end))
    }

    /// `_parse_object_unicode`
    fn parse_object(&mut self, start: usize) -> Result<(PyValue, usize), Stop> {
        let s = self.s;
        let len = s.len();
        let mut d = PyDict::new();
        let mut idx = skip_ws(s, start);
        if idx < len && s[idx] == u32::from('}') {
            return Ok((PyValue::Dict(d), idx + 1));
        }
        loop {
            if idx >= len || s[idx] != u32::from('"') {
                return Err(decode_err(
                    "Expecting property name enclosed in double quotes",
                    idx,
                ));
            }
            let (key, after) = self.scanstring(idx + 1)?;
            idx = skip_ws(s, after);
            if idx >= len || s[idx] != u32::from(':') {
                return Err(decode_err("Expecting ':' delimiter", idx));
            }
            idx = skip_ws(s, idx + 1);
            let (val, after) = match self.scan_once(idx) {
                Ok(r) => r,
                Err(Stop::At(p)) => return Err(decode_err("Expecting value", p)),
                Err(e) => return Err(e),
            };
            d.insert(key, val);
            idx = skip_ws(s, after);
            if idx < len && s[idx] == u32::from('}') {
                return Ok((PyValue::Dict(d), idx + 1));
            }
            if idx >= len || s[idx] != u32::from(',') {
                return Err(decode_err("Expecting ',' delimiter", idx));
            }
            idx = skip_ws(s, idx + 1);
        }
    }

    /// `_parse_array_unicode`
    fn parse_array(&mut self, start: usize) -> Result<(PyValue, usize), Stop> {
        let s = self.s;
        let len = s.len();
        let mut items = Vec::new();
        let mut idx = skip_ws(s, start);
        if idx < len && s[idx] == u32::from(']') {
            return Ok((PyValue::List(items), idx + 1));
        }
        loop {
            let (val, after) = match self.scan_once(idx) {
                Ok(r) => r,
                Err(Stop::At(p)) => return Err(decode_err("Expecting value", p)),
                Err(e) => return Err(e),
            };
            items.push(val);
            idx = skip_ws(s, after);
            if idx < len && s[idx] == u32::from(']') {
                return Ok((PyValue::List(items), idx + 1));
            }
            if idx >= len || s[idx] != u32::from(',') {
                return Err(decode_err("Expecting ',' delimiter", idx));
            }
            idx = skip_ws(s, idx + 1);
        }
    }
}

fn hex(c: u32) -> Option<u32> {
    char::from_u32(c).and_then(|c| c.to_digit(16))
}

/// `json.detect_encoding` + `bytes.decode(enc, 'surrogatepass')` — 실패하면 None
fn decode_bytes(b: &[u8]) -> Option<Vec<u32>> {
    const BOM8: &[u8] = &[0xEF, 0xBB, 0xBF];
    if b.starts_with(&[0x00, 0x00, 0xFE, 0xFF]) || b.starts_with(&[0xFF, 0xFE, 0x00, 0x00]) {
        return decode_utf32(b, None);
    }
    if b.starts_with(&[0xFE, 0xFF]) || b.starts_with(&[0xFF, 0xFE]) {
        return decode_utf16(b, None);
    }
    if b.starts_with(BOM8) {
        return decode_utf8(&b[3..]);
    }
    if b.len() >= 4 {
        if b[0] == 0 {
            return if b[1] != 0 {
                decode_utf16(b, Some(true))
            } else {
                decode_utf32(b, Some(true))
            };
        }
        if b[1] == 0 {
            return if b[2] != 0 || b[3] != 0 {
                decode_utf16(b, Some(false))
            } else {
                decode_utf32(b, Some(false))
            };
        }
    } else if b.len() == 2 {
        if b[0] == 0 {
            return decode_utf16(b, Some(true));
        }
        if b[1] == 0 {
            return decode_utf16(b, Some(false));
        }
    }
    decode_utf8(b)
}

/// UTF-8 + `surrogatepass` — 서로게이트를 담은 3바이트(ED A0..BF ..)도 받는다
fn decode_utf8(b: &[u8]) -> Option<Vec<u32>> {
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        let c = b[i];
        let cont = |j: usize| b.get(j).is_some_and(|&x| (0x80..=0xBF).contains(&x));
        if c < 0x80 {
            out.push(u32::from(c));
            i += 1;
        } else if (0xC2..=0xDF).contains(&c) && cont(i + 1) {
            out.push((u32::from(c & 0x1F) << 6) | u32::from(b[i + 1] & 0x3F));
            i += 2;
        } else if (0xE0..=0xEF).contains(&c) && cont(i + 1) && cont(i + 2) {
            let cp = (u32::from(c & 0x0F) << 12)
                | (u32::from(b[i + 1] & 0x3F) << 6)
                | u32::from(b[i + 2] & 0x3F);
            if cp < 0x800 {
                return None; // 너무 긴 꼴
            }
            out.push(cp);
            i += 3;
        } else if (0xF0..=0xF4).contains(&c) && cont(i + 1) && cont(i + 2) && cont(i + 3) {
            let cp = (u32::from(c & 0x07) << 18)
                | (u32::from(b[i + 1] & 0x3F) << 12)
                | (u32::from(b[i + 2] & 0x3F) << 6)
                | u32::from(b[i + 3] & 0x3F);
            if !(0x10000..=0x10FFFF).contains(&cp) {
                return None;
            }
            out.push(cp);
            i += 4;
        } else {
            return None;
        }
    }
    Some(out)
}

/// UTF-16 + `surrogatepass`. `big`이 None이면 BOM으로 정하고 BOM을 뺀다
fn decode_utf16(b: &[u8], big: Option<bool>) -> Option<Vec<u32>> {
    let (big, body) = match big {
        Some(be) => (be, b),
        None => (b[0] == 0xFE, &b[2..]),
    };
    if body.len() % 2 != 0 {
        return None;
    }
    let units: Vec<u32> = body
        .chunks(2)
        .map(|p| {
            if big {
                u32::from(u16::from_be_bytes([p[0], p[1]]))
            } else {
                u32::from(u16::from_le_bytes([p[0], p[1]]))
            }
        })
        .collect();
    let mut out = Vec::with_capacity(units.len());
    let mut i = 0;
    while i < units.len() {
        let u = units[i];
        if (0xD800..=0xDBFF).contains(&u)
            && units
                .get(i + 1)
                .is_some_and(|&v| (0xDC00..=0xDFFF).contains(&v))
        {
            out.push(0x10000 + (((u - 0xD800) << 10) | (units[i + 1] - 0xDC00)));
            i += 2;
        } else {
            out.push(u);
            i += 1;
        }
    }
    Some(out)
}

/// UTF-32 + `surrogatepass`. `big`이 None이면 BOM으로 정하고 BOM을 뺀다
fn decode_utf32(b: &[u8], big: Option<bool>) -> Option<Vec<u32>> {
    let (big, body) = match big {
        Some(be) => (be, b),
        None => (b[0] == 0x00, &b[4..]),
    };
    if body.len() % 4 != 0 {
        return None;
    }
    let mut out = Vec::with_capacity(body.len() / 4);
    for p in body.chunks(4) {
        let cp = if big {
            u32::from_be_bytes([p[0], p[1], p[2], p[3]])
        } else {
            u32::from_le_bytes([p[0], p[1], p[2], p[3]])
        };
        if cp > 0x10FFFF {
            return None;
        }
        out.push(cp);
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pos(s: &str) -> (Option<String>, Option<(&'static str, usize)>) {
        match loads_str(&PyStr::from(s), Depth(9997)) {
            Ok(v) => (Some(v.repr().unwrap()), None),
            Err(LoadsError::Decode { msg, pos }) => (None, Some((msg, pos))),
            Err(e) => panic!("{e:?}"),
        }
    }

    #[test]
    fn errors_where_python_puts_them() {
        for (s, msg, at) in [
            ("\"\\q\"", "Invalid \\escape", 1),
            ("\"abc", "Unterminated string starting at", 0),
            ("\"a\\", "Unterminated string starting at", 0),
            ("\"\\u12\"", "Invalid \\uXXXX escape", 2),
            ("\"\\u12G4\"", "Invalid \\uXXXX escape", 2),
            ("\"\\ud800\\u\"", "Invalid \\uXXXX escape", 8),
            ("\"\\ud800\\uZZZZ\"", "Invalid \\uXXXX escape", 8),
            ("\"\u{1}\"", "Invalid control character at", 1),
            (
                "{\"a\":1,}",
                "Expecting property name enclosed in double quotes",
                7,
            ),
            ("[1,]", "Expecting value", 3),
            (
                "{,}",
                "Expecting property name enclosed in double quotes",
                1,
            ),
            ("{\"a\" 1}", "Expecting ':' delimiter", 5),
            ("[1 2]", "Expecting ',' delimiter", 3),
            ("1.", "Extra data", 1),
            ("1.e5", "Extra data", 1),
            ("1e", "Extra data", 1),
            ("1e+", "Extra data", 1),
            ("-", "Expecting value", 0),
            ("00", "Extra data", 1),
            ("tru", "Expecting value", 0),
            (" ", "Expecting value", 1),
            ("", "Expecting value", 0),
            ("[", "Expecting value", 1),
            ("{", "Expecting property name enclosed in double quotes", 1),
            ("{\"a\":", "Expecting value", 5),
            ("1 2", "Extra data", 2),
            (
                "\u{feff}1",
                "Unexpected UTF-8 BOM (decode using utf-8-sig)",
                0,
            ),
            ("-Inf", "Expecting value", 0),
            ("٣", "Expecting value", 0),
            ("[1,2,", "Expecting value", 5),
            ("\"a\"b", "Extra data", 3),
        ] {
            assert_eq!(pos(s), (None, Some((msg, at))), "{s:?}");
        }
    }

    #[test]
    fn values_like_python() {
        for (s, want) in [
            ("\"\\ud800\"", "'\\ud800'"),
            ("\"\\ud800\\u0041\"", "'\\ud800A'"),
            ("\"\\ud83d\\ude00\"", "'😀'"),
            ("-0", "0"),
            ("-Infinity", "-inf"),
            ("1E5", "100000.0"),
            ("{\"a\":1,\"a\":2}", "{'a': 2}"),
            ("[1, 2.5, true, null, \"x\"]", "[1, 2.5, True, None, 'x']"),
        ] {
            assert_eq!(pos(s), (Some(want.to_string()), None), "{s:?}");
        }
    }

    #[test]
    fn bytes_find_their_encoding() {
        let d = Depth(9997);
        assert!(loads_bytes(b"\xef\xbb\xbf{\"a\":1}", d).is_ok());
        assert_eq!(
            loads_bytes(b"\xff\xfe1\x00", d).unwrap().repr().unwrap(),
            "1"
        );
        let le: Vec<u8> = "{\"a\":\"é\"}"
            .encode_utf16()
            .flat_map(|u| u.to_le_bytes())
            .collect();
        assert_eq!(loads_bytes(&le, d).unwrap().repr().unwrap(), "{'a': 'é'}");
        assert_eq!(loads_bytes(b"\x80", d), Err(LoadsError::Unicode));
        assert_eq!(loads_bytes(b"\"\xc3\"", d), Err(LoadsError::Unicode));
        assert_eq!(
            loads_bytes(b"\"\xed\xa0\x80\"", d).unwrap().repr().unwrap(),
            "'\\ud800'"
        );
        assert_eq!(
            loads_bytes(b"\x00\x001\x00", d),
            Err(LoadsError::Decode {
                msg: "Expecting value",
                pos: 0
            })
        );
    }

    #[test]
    fn limits() {
        let deep = format!("{}{}", "[".repeat(5), "]".repeat(5));
        assert!(loads_str(&PyStr::from(deep.as_str()), Depth(5)).is_ok());
        assert_eq!(
            loads_str(&PyStr::from(deep.as_str()), Depth(4)),
            Err(LoadsError::Recursion)
        );
        assert_eq!(
            loads_str(&PyStr::from("1".repeat(4301).as_str()), Depth(9)),
            Err(LoadsError::IntTooLong)
        );
    }
}
