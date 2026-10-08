//! 파이썬 값 — JSON을 읽은 파이썬 객체와 같은 꼴 (SYNC-DOM-004 1장 compat).
//! dict는 넣은 순서를 지키고 같은 키는 처음 자리에 마지막 값이다. 정수는 크기가 없다.
//! `repr`은 파이썬 3.12의 `repr()`과 같은 바이트를 낸다 — pydantic 오류 문장의 `input_value`가 이것이다.

use std::fmt::Write;

use indexmap::IndexMap;
use jiter::JsonValue;
use num_bigint::BigInt;

use super::printable::is_printable;

/// 파이썬 `str`. 짝 없는 서로게이트(파이썬 `json.loads`의 `"\ud800"`)가 있을 때만 `Wide`다 — 러스트 `String`에 못 담는다
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum PyStr {
    Utf8(String),
    Wide(Vec<u32>),
}

impl PyStr {
    /// 코드 포인트들 → 서로게이트가 없으면 `Utf8`
    pub fn from_code_points(cps: Vec<u32>) -> PyStr {
        if cps.iter().any(|&c| (0xD800..=0xDFFF).contains(&c)) {
            PyStr::Wide(cps)
        } else {
            PyStr::Utf8(cps.into_iter().filter_map(char::from_u32).collect())
        }
    }

    /// 러스트 문자열 — 서로게이트가 있으면 None(파이썬에서 UTF-8로 못 바꾸는 문자열)
    pub fn as_str(&self) -> Option<&str> {
        match self {
            PyStr::Utf8(s) => Some(s),
            PyStr::Wide(_) => None,
        }
    }

    /// `len(s)` — 코드 포인트 수
    pub fn char_len(&self) -> usize {
        match self {
            PyStr::Utf8(s) => s.chars().count(),
            PyStr::Wide(v) => v.len(),
        }
    }

    pub fn code_points(&self) -> Vec<u32> {
        match self {
            PyStr::Utf8(s) => s.chars().map(u32::from).collect(),
            PyStr::Wide(v) => v.clone(),
        }
    }

    /// 파이썬 `repr(s)`
    pub fn repr(&self) -> String {
        let cps = self.code_points();
        let has_single = cps.contains(&u32::from('\''));
        let has_double = cps.contains(&u32::from('"'));
        let quote = if has_single && !has_double { '"' } else { '\'' };
        let mut out = String::with_capacity(cps.len() + 2);
        out.push(quote);
        for cp in cps {
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
}

impl From<&str> for PyStr {
    fn from(s: &str) -> Self {
        PyStr::Utf8(s.to_string())
    }
}

impl From<String> for PyStr {
    fn from(s: String) -> Self {
        PyStr::Utf8(s)
    }
}

/// 파이썬 dict — 키는 늘 str(JSON에서 왔다)
pub type PyDict = IndexMap<PyStr, PyValue>;

/// JSON을 읽은 파이썬 값
#[derive(Clone, Debug, PartialEq)]
pub enum PyValue {
    None,
    Bool(bool),
    Int(BigInt),
    Float(f64),
    Str(PyStr),
    List(Vec<PyValue>),
    Dict(PyDict),
}

/// `repr`이 실패했다 — 파이썬은 4300자리를 넘는 정수를 문자열로 못 바꾼다(`int_max_str_digits`)
#[derive(Debug)]
pub struct ReprError;

/// 파이썬 3.12 `sys.int_info.default_max_str_digits`
pub const INT_MAX_STR_DIGITS: usize = 4300;

impl PyValue {
    pub fn str(s: &str) -> PyValue {
        PyValue::Str(PyStr::from(s))
    }

    /// pydantic-core가 읽은 JSON(`pydantic_core.from_json`) — jiter 값 그대로
    pub fn from_jiter(v: &JsonValue<'_>) -> PyValue {
        match v {
            JsonValue::Null => PyValue::None,
            JsonValue::Bool(b) => PyValue::Bool(*b),
            JsonValue::Int(i) => PyValue::Int(BigInt::from(*i)),
            JsonValue::BigInt(i) => PyValue::Int(i.clone()),
            JsonValue::Float(f) => PyValue::Float(*f),
            JsonValue::Str(s) => PyValue::str(s),
            JsonValue::Array(a) => PyValue::List(a.iter().map(PyValue::from_jiter).collect()),
            JsonValue::Object(o) => {
                let mut d = PyDict::new();
                for (k, v) in o.iter() {
                    d.insert(PyStr::from(k.as_ref()), PyValue::from_jiter(v));
                }
                PyValue::Dict(d)
            }
        }
    }

    /// `type(v).__qualname__`
    pub fn type_name(&self) -> &'static str {
        match self {
            PyValue::None => "NoneType",
            PyValue::Bool(_) => "bool",
            PyValue::Int(_) => "int",
            PyValue::Float(_) => "float",
            PyValue::Str(_) => "str",
            PyValue::List(_) => "list",
            PyValue::Dict(_) => "dict",
        }
    }

    pub fn is_none(&self) -> bool {
        matches!(self, PyValue::None)
    }

    pub fn as_dict(&self) -> Option<&PyDict> {
        match self {
            PyValue::Dict(d) => Some(d),
            _ => None,
        }
    }

    /// `repr(v)`
    pub fn repr(&self) -> Result<String, ReprError> {
        let mut out = String::new();
        self.write_repr(&mut out)?;
        Ok(out)
    }

    fn write_repr(&self, out: &mut String) -> Result<(), ReprError> {
        match self {
            PyValue::None => out.push_str("None"),
            PyValue::Bool(true) => out.push_str("True"),
            PyValue::Bool(false) => out.push_str("False"),
            PyValue::Int(i) => {
                let s = i.to_string();
                let digits = s.trim_start_matches('-').len();
                if digits > INT_MAX_STR_DIGITS {
                    return Err(ReprError);
                }
                out.push_str(&s);
            }
            PyValue::Float(f) => out.push_str(&float_repr(*f)),
            PyValue::Str(s) => out.push_str(&s.repr()),
            PyValue::List(items) => {
                out.push('[');
                for (i, v) in items.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    v.write_repr(out)?;
                }
                out.push(']');
            }
            PyValue::Dict(d) => {
                out.push('{');
                for (i, (k, v)) in d.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    out.push_str(&k.repr());
                    out.push_str(": ");
                    v.write_repr(out)?;
                }
                out.push('}');
            }
        }
        Ok(())
    }

    /// pydantic `safe_repr` — 실패하면 `<unprintable {type} object>`
    pub fn safe_repr(&self) -> String {
        self.repr()
            .unwrap_or_else(|_| format!("<unprintable {} object>", self.type_name()))
    }
}

/// 파이썬 `repr(float)` — 가장 짧게 되돌아오는 자릿수, `1e+16`·`1e-05` 꼴, 정수면 `.0`
pub fn float_repr(f: f64) -> String {
    if f.is_nan() {
        return "nan".to_string();
    }
    if f.is_infinite() {
        return if f > 0.0 { "inf" } else { "-inf" }.to_string();
    }
    let neg = f.is_sign_negative();
    let (digits, decpt) = shortest_digits(f.abs());
    let mut out = String::new();
    if neg {
        out.push('-');
    }
    let n = digits.len() as i32;
    if decpt <= -4 || decpt > 16 {
        out.push_str(&digits[..1]);
        if n > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        let exp = decpt - 1;
        let _ = write!(out, "e{}{:02}", if exp < 0 { '-' } else { '+' }, exp.abs());
    } else if decpt <= 0 {
        out.push_str("0.");
        out.push_str(&"0".repeat((-decpt) as usize));
        out.push_str(&digits);
    } else if decpt >= n {
        out.push_str(&digits);
        out.push_str(&"0".repeat((decpt - n) as usize));
        out.push_str(".0");
    } else {
        out.push_str(&digits[..decpt as usize]);
        out.push('.');
        out.push_str(&digits[decpt as usize..]);
    }
    out
}

/// 가장 짧은 자릿수와 소수점 자리 — 값 = 0.d1d2… × 10^decpt (파이썬 dtoa mode 0과 같다)
fn shortest_digits(f: f64) -> (String, i32) {
    if f == 0.0 {
        return ("0".to_string(), 1);
    }
    let mut buf = ryu::Buffer::new();
    let s = buf.format_finite(f);
    // ryu 꼴: "123.45", "1e16", "1.5e-5", "0.001"
    let (mant, exp) = match s.split_once('e') {
        Some((m, e)) => (m, e.parse::<i32>().unwrap_or(0)),
        None => (s, 0),
    };
    let (int_part, frac_part) = mant.split_once('.').unwrap_or((mant, ""));
    let frac_part = if frac_part == "0" { "" } else { frac_part };
    let mut digits = format!("{int_part}{frac_part}");
    let mut decpt = int_part.len() as i32 + exp;
    let lead = digits.len() - digits.trim_start_matches('0').len();
    digits.drain(..lead);
    decpt -= lead as i32;
    let trimmed = digits.trim_end_matches('0').len();
    digits.truncate(trimmed.max(1));
    (digits, decpt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn float_repr_like_python() {
        for (f, want) in [
            (1.0, "1.0"),
            (-0.0, "-0.0"),
            (0.1, "0.1"),
            (1e16, "1e+16"),
            (1234567890123456.0, "1234567890123456.0"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (1.5e-7, "1.5e-07"),
            (1e22, "1e+22"),
            (123.456, "123.456"),
            (f64::MAX, "1.7976931348623157e+308"),
            (5e-324, "5e-324"),
            (100.0, "100.0"),
            (1e15, "1000000000000000.0"),
            (12345678901234567.0, "1.2345678901234568e+16"),
        ] {
            assert_eq!(float_repr(f), want, "{f}");
        }
    }

    #[test]
    fn str_repr_like_python() {
        for (s, want) in [
            ("a", "'a'"),
            ("it's", "\"it's\""),
            ("'\"", "'\\'\"'"),
            ("a\\b", "'a\\\\b'"),
            ("\t\n\r\u{1}\u{7f}", "'\\t\\n\\r\\x01\\x7f'"),
            ("한글", "'한글'"),
            ("\u{a0}\u{ad}", "'\\xa0\\xad'"),
            ("\u{200b}", "'\\u200b'"),
            ("\u{e0001}", "'\\U000e0001'"),
        ] {
            assert_eq!(PyStr::from(s).repr(), want, "{s:?}");
        }
        assert_eq!(
            PyStr::from_code_points(vec![0x61, 0xD800]).repr(),
            "'a\\ud800'"
        );
    }

    #[test]
    fn dict_keeps_first_position_last_value() {
        let v = JsonValue::parse(br#"{"a":1,"b":2,"a":3}"#, true).unwrap();
        assert_eq!(PyValue::from_jiter(&v).repr().unwrap(), "{'a': 3, 'b': 2}");
    }
}
