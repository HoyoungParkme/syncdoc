//! pydantic 검증 오류 — pydantic-core 2.46.5 `src/errors`를 옮겼다 (SYNC-DOM-004 1장 compat).
//! 오류 종류·문장 틀·`loc` 꼴·`N validation errors for …` 문장이 파이썬과 바이트로 같아야 한다.

use std::fmt::Write;

use crate::compat::pyvalue::PyValue;

/// `loc`의 한 칸 — 키(문자열)나 위치(정수)
#[derive(Clone, Debug, PartialEq)]
pub enum LocItem {
    S(String),
    I(i64),
}

impl LocItem {
    /// pydantic `LocItem` Display — 점이 든 키는 백틱으로 감싼다
    fn pretty(&self) -> String {
        match self {
            LocItem::S(s) if s.contains('.') => format!("`{s}`"),
            LocItem::S(s) => s.clone(),
            LocItem::I(i) => i.to_string(),
        }
    }

    /// 파이썬 `str(x)` — FastAPI 처리기가 `".".join(str(x) for x in loc)`로 쓴다
    pub fn plain(&self) -> String {
        match self {
            LocItem::S(s) => s.clone(),
            LocItem::I(i) => i.to_string(),
        }
    }
}

impl From<&str> for LocItem {
    fn from(s: &str) -> Self {
        LocItem::S(s.to_string())
    }
}

/// 숫자 제약 값 — 문장에 `to_string`으로 들어간다(pydantic `Number`)
#[derive(Clone, Debug, PartialEq)]
pub enum Num {
    Int(i64),
    Float(f64),
}

impl Num {
    fn render(&self) -> String {
        match self {
            Num::Int(i) => i.to_string(),
            Num::Float(f) => f.to_string(),
        }
    }

    pub fn as_f64(&self) -> f64 {
        match self {
            Num::Int(i) => *i as f64,
            Num::Float(f) => *f,
        }
    }
}

/// 오류 종류 — 쓰는 것만. 이름(`type`)과 문장 틀은 pydantic-core `ErrorType` 그대로
#[derive(Clone, Debug, PartialEq)]
pub enum ErrorKind {
    Missing,
    ExtraForbidden,
    InvalidKey,
    ModelType {
        class_name: String,
    },
    ModelAttributesType,
    NoneRequired,
    GreaterThan {
        gt: Num,
    },
    GreaterThanEqual {
        ge: Num,
    },
    LessThan {
        lt: Num,
    },
    LessThanEqual {
        le: Num,
    },
    MultipleOf {
        multiple_of: Num,
    },
    FiniteNumber,
    TooShort {
        field_type: &'static str,
        min_length: usize,
        actual_length: usize,
    },
    TooLong {
        field_type: &'static str,
        max_length: usize,
        actual_length: usize,
    },
    StringType,
    StringUnicode,
    StringTooShort {
        min_length: usize,
    },
    StringTooLong {
        max_length: usize,
    },
    StringPatternMismatch {
        pattern: String,
    },
    DictType,
    ListType,
    BoolType,
    BoolParsing,
    IntType,
    IntParsing,
    IntFromFloat,
    IntParsingSize,
    FloatType,
    FloatParsing,
    LiteralError {
        expected: String,
    },
    UrlType,
    UrlParsing {
        error: String,
    },
    UrlTooLong {
        max_length: usize,
    },
    UrlScheme {
        expected_schemes: String,
    },
    RecursionLoop,
}

fn plural(n: usize) -> &'static str {
    if n == 1 { "" } else { "s" }
}

impl ErrorKind {
    /// `type` 문자열
    pub fn type_string(&self) -> &'static str {
        match self {
            ErrorKind::Missing => "missing",
            ErrorKind::ExtraForbidden => "extra_forbidden",
            ErrorKind::InvalidKey => "invalid_key",
            ErrorKind::ModelType { .. } => "model_type",
            ErrorKind::ModelAttributesType => "model_attributes_type",
            ErrorKind::NoneRequired => "none_required",
            ErrorKind::GreaterThan { .. } => "greater_than",
            ErrorKind::GreaterThanEqual { .. } => "greater_than_equal",
            ErrorKind::LessThan { .. } => "less_than",
            ErrorKind::LessThanEqual { .. } => "less_than_equal",
            ErrorKind::MultipleOf { .. } => "multiple_of",
            ErrorKind::FiniteNumber => "finite_number",
            ErrorKind::TooShort { .. } => "too_short",
            ErrorKind::TooLong { .. } => "too_long",
            ErrorKind::StringType => "string_type",
            ErrorKind::StringUnicode => "string_unicode",
            ErrorKind::StringTooShort { .. } => "string_too_short",
            ErrorKind::StringTooLong { .. } => "string_too_long",
            ErrorKind::StringPatternMismatch { .. } => "string_pattern_mismatch",
            ErrorKind::DictType => "dict_type",
            ErrorKind::ListType => "list_type",
            ErrorKind::BoolType => "bool_type",
            ErrorKind::BoolParsing => "bool_parsing",
            ErrorKind::IntType => "int_type",
            ErrorKind::IntParsing => "int_parsing",
            ErrorKind::IntFromFloat => "int_from_float",
            ErrorKind::IntParsingSize => "int_parsing_size",
            ErrorKind::FloatType => "float_type",
            ErrorKind::FloatParsing => "float_parsing",
            ErrorKind::LiteralError { .. } => "literal_error",
            ErrorKind::UrlType => "url_type",
            ErrorKind::UrlParsing { .. } => "url_parsing",
            ErrorKind::UrlTooLong { .. } => "url_too_long",
            ErrorKind::UrlScheme { .. } => "url_scheme",
            ErrorKind::RecursionLoop => "recursion_loop",
        }
    }

    /// 문장 — 파이썬 입력의 틀(`message_template_python`)
    pub fn message(&self) -> String {
        match self {
            ErrorKind::Missing => "Field required".into(),
            ErrorKind::ExtraForbidden => "Extra inputs are not permitted".into(),
            ErrorKind::InvalidKey => "Keys should be strings".into(),
            ErrorKind::ModelType { class_name } => {
                format!("Input should be a valid dictionary or instance of {class_name}")
            }
            ErrorKind::ModelAttributesType => {
                "Input should be a valid dictionary or object to extract fields from".into()
            }
            ErrorKind::NoneRequired => "Input should be None".into(),
            ErrorKind::GreaterThan { gt } => {
                format!("Input should be greater than {}", gt.render())
            }
            ErrorKind::GreaterThanEqual { ge } => {
                format!("Input should be greater than or equal to {}", ge.render())
            }
            ErrorKind::LessThan { lt } => format!("Input should be less than {}", lt.render()),
            ErrorKind::LessThanEqual { le } => {
                format!("Input should be less than or equal to {}", le.render())
            }
            ErrorKind::MultipleOf { multiple_of } => {
                format!("Input should be a multiple of {}", multiple_of.render())
            }
            ErrorKind::FiniteNumber => "Input should be a finite number".into(),
            ErrorKind::TooShort {
                field_type,
                min_length,
                actual_length,
            } => format!(
                "{field_type} should have at least {min_length} item{} after validation, not {actual_length}",
                plural(*min_length)
            ),
            ErrorKind::TooLong {
                field_type,
                max_length,
                actual_length,
            } => format!(
                "{field_type} should have at most {max_length} item{} after validation, not {actual_length}",
                plural(*max_length)
            ),
            ErrorKind::StringType => "Input should be a valid string".into(),
            ErrorKind::StringUnicode => {
                "Input should be a valid string, unable to parse raw data as a unicode string"
                    .into()
            }
            ErrorKind::StringTooShort { min_length } => format!(
                "String should have at least {min_length} character{}",
                plural(*min_length)
            ),
            ErrorKind::StringTooLong { max_length } => format!(
                "String should have at most {max_length} character{}",
                plural(*max_length)
            ),
            ErrorKind::StringPatternMismatch { pattern } => {
                format!("String should match pattern '{pattern}'")
            }
            ErrorKind::DictType => "Input should be a valid dictionary".into(),
            ErrorKind::ListType => "Input should be a valid list".into(),
            ErrorKind::BoolType => "Input should be a valid boolean".into(),
            ErrorKind::BoolParsing => {
                "Input should be a valid boolean, unable to interpret input".into()
            }
            ErrorKind::IntType => "Input should be a valid integer".into(),
            ErrorKind::IntParsing => {
                "Input should be a valid integer, unable to parse string as an integer".into()
            }
            ErrorKind::IntFromFloat => {
                "Input should be a valid integer, got a number with a fractional part".into()
            }
            ErrorKind::IntParsingSize => {
                "Unable to parse input string as an integer, exceeded maximum size".into()
            }
            ErrorKind::FloatType => "Input should be a valid number".into(),
            ErrorKind::FloatParsing => {
                "Input should be a valid number, unable to parse string as a number".into()
            }
            ErrorKind::LiteralError { expected } => format!("Input should be {expected}"),
            ErrorKind::UrlType => "URL input should be a string or URL".into(),
            ErrorKind::UrlParsing { error } => format!("Input should be a valid URL, {error}"),
            ErrorKind::UrlTooLong { max_length } => format!(
                "URL should have at most {max_length} character{}",
                plural(*max_length)
            ),
            ErrorKind::UrlScheme { expected_schemes } => {
                format!("URL scheme should be {expected_schemes}")
            }
            ErrorKind::RecursionLoop => "Recursion error - cyclic reference detected".into(),
        }
    }
}

/// 오류 한 줄 — `loc`은 바깥에서 안으로
#[derive(Clone, Debug)]
pub struct LineError {
    pub kind: ErrorKind,
    pub loc: Vec<LocItem>,
    pub input: PyValue,
}

impl LineError {
    pub fn new(kind: ErrorKind, input: &PyValue) -> Self {
        LineError {
            kind,
            loc: Vec::new(),
            input: input.clone(),
        }
    }

    /// 바깥 위치를 앞에 붙인다 (`with_outer_location`)
    pub fn outer(mut self, item: LocItem) -> Self {
        self.loc.insert(0, item);
        self
    }

    /// pydantic `PyLineError.pretty` — 위치 줄, 문장, `[type=…, input_value=…, input_type=…]`, 안내 주소
    fn pretty(&self, url_prefix: &str) -> String {
        let mut out = String::new();
        if !self.loc.is_empty() {
            let loc: Vec<String> = self.loc.iter().map(LocItem::pretty).collect();
            out.push_str(&loc.join("."));
            out.push('\n');
        }
        let _ = write!(
            out,
            "  {} [type={}, input_value=",
            self.kind.message(),
            self.kind.type_string()
        );
        out.push_str(&truncate(&self.input.safe_repr(), 50));
        let _ = write!(out, ", input_type={}]", self.input.type_name());
        let _ = write!(
            out,
            "\n    For further information visit {url_prefix}{}",
            self.kind.type_string()
        );
        out
    }
}

/// `write_truncated_to_limited_bytes` — 바이트 길이가 넘치면 앞 25·뒤 24바이트(글자 경계로 맞춘다)
fn truncate(val: &str, max_len: usize) -> String {
    if val.len() <= max_len {
        return val.to_string();
    }
    let mid = max_len.div_ceil(2);
    let mut a = mid;
    while !val.is_char_boundary(a) {
        a -= 1;
    }
    let mut b = val.len() - (mid - 1);
    while !val.is_char_boundary(b) {
        b += 1;
    }
    format!("{}...{}", &val[..a], &val[b..])
}

/// 검증 실패 — 제목(검증기 이름)과 줄들
#[derive(Clone, Debug)]
pub struct ValidationError {
    pub title: String,
    pub lines: Vec<LineError>,
}

impl ValidationError {
    /// `str(ValidationError)` — `N validation error(s) for {title}` + 줄마다 `pretty`
    pub fn display(&self, url_prefix: &str) -> String {
        let n = self.lines.len();
        let lines: Vec<String> = self.lines.iter().map(|l| l.pretty(url_prefix)).collect();
        format!(
            "{n} validation error{} for {}\n{}",
            plural(n),
            self.title,
            lines.join("\n")
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncates_like_pydantic() {
        let s = "a".repeat(60);
        assert_eq!(
            truncate(&s, 50),
            format!("{}...{}", "a".repeat(25), "a".repeat(24))
        );
        assert_eq!(truncate("short", 50), "short");
    }
}
