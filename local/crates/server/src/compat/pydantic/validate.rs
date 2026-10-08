//! pydantic lax 검증 — pydantic-core 2.46.5의 `validators/*`·`input/input_python.rs`·`input/shared.rs`를 옮겼다.
//! 입력은 파이썬 객체(JSON을 읽은 것)다. smart union이 고르는 기준(exactness·fields_set)까지 같게 쓴다.

use std::collections::HashMap;

use jiter::{JsonErrorType, NumberInt};
use num_bigint::BigInt;
use num_traits::{ToPrimitive, Zero};

use super::errors::{ErrorKind, LineError, LocItem, Num};
use super::schema::{Extra, Fields, Node, NumC, OnError};
use crate::compat::pyvalue::{PyDict, PyStr, PyValue};

/// 얼마나 딱 맞았나 — smart union이 고른다
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Exactness {
    Lax,
    Strict,
    Exact,
}

/// 검증 상태 (`ValidationState`) — union 안에서만 exactness를 본다
#[derive(Clone, Debug, Default)]
pub struct State {
    pub exactness: Option<Exactness>,
    pub fields_set_count: Option<usize>,
    /// `model_validate(by_name=…)`·`by_alias` — 부를 때 덮어쓴다
    pub by_alias: Option<bool>,
    pub by_name: Option<bool>,
    pub strict: Option<bool>,
}

impl State {
    fn floor(&mut self, e: Exactness) {
        match self.exactness {
            None | Some(Exactness::Lax) => {}
            Some(Exactness::Strict) => {
                if e == Exactness::Lax {
                    self.exactness = Some(Exactness::Lax);
                }
            }
            Some(Exactness::Exact) => self.exactness = Some(e),
        }
    }

    fn add_fields_set(&mut self, n: usize) {
        *self.fields_set_count.get_or_insert(0) += n;
    }

    fn strict_or(&self, d: bool) -> bool {
        self.strict.unwrap_or(d)
    }
}

/// 검증 실패
#[derive(Debug)]
pub enum ValError {
    Lines(Vec<LineError>),
    Omit,
    /// 검증 오류가 아닌 파이썬 예외(서로게이트 문자열을 UTF-8로 못 바꿈 등) — `ValidationError`로 잡히지 않는다
    Exception(String),
}

type VResult = Result<PyValue, ValError>;

fn err(kind: ErrorKind, input: &PyValue) -> ValError {
    ValError::Lines(vec![LineError::new(kind, input)])
}

/// 서로게이트가 든 문자열을 UTF-8로 읽어야 할 때 (`py_string_str` → `string_unicode`)
fn unicode_err(input: &PyValue) -> ValError {
    err(ErrorKind::StringUnicode, input)
}

/// 정의 표
pub struct Ctx<'a> {
    pub defs: &'a HashMap<String, Node>,
}

pub fn validate(node: &Node, input: &PyValue, ctx: &Ctx<'_>, st: &mut State) -> VResult {
    match node {
        Node::Any => {
            st.floor(Exactness::Strict);
            Ok(input.clone())
        }
        Node::None => match input {
            PyValue::None => Ok(PyValue::None),
            _ => Err(err(ErrorKind::NoneRequired, input)),
        },
        Node::Bool { strict } => {
            let (b, e) = validate_bool(input, st.strict_or(*strict))?;
            st.floor(e);
            Ok(PyValue::Bool(b))
        }
        Node::Int { strict, c } => {
            let (i, e) = validate_int(input, st.strict_or(*strict))?;
            st.floor(e);
            check_int(&i, c, input)?;
            Ok(PyValue::Int(i))
        }
        Node::Float {
            strict,
            allow_inf_nan,
            c,
        } => {
            let (f, e) = validate_float(input, st.strict_or(*strict))?;
            st.floor(e);
            if !allow_inf_nan && !f.is_finite() {
                return Err(err(ErrorKind::FiniteNumber, input));
            }
            check_float(f, c, input)?;
            Ok(PyValue::Float(f))
        }
        Node::Str {
            strict,
            min_length,
            max_length,
            pattern,
        } => {
            let s = match input {
                PyValue::Str(s) => s.clone(),
                _ => {
                    let _ = strict;
                    return Err(err(ErrorKind::StringType, input));
                }
            };
            st.floor(Exactness::Exact);
            if min_length.is_some() || max_length.is_some() {
                if s.as_str().is_none() {
                    return Err(unicode_err(input));
                }
                let len = s.char_len();
                if let Some(min) = min_length
                    && len < *min
                {
                    return Err(err(ErrorKind::StringTooShort { min_length: *min }, input));
                }
                if let Some(max) = max_length
                    && len > *max
                {
                    return Err(err(ErrorKind::StringTooLong { max_length: *max }, input));
                }
            }
            // pydantic-core 차례 — 길이 다음 패턴
            if let Some((p, re)) = pattern {
                let Some(text) = s.as_str() else {
                    return Err(unicode_err(input));
                };
                if !re.is_match(text) {
                    return Err(err(
                        ErrorKind::StringPatternMismatch { pattern: p.clone() },
                        input,
                    ));
                }
            }
            Ok(PyValue::Str(s))
        }
        Node::Literal { expected, repr, .. } => {
            if let PyValue::Str(PyStr::Wide(_)) = input
                && expected.iter().any(|e| matches!(e, PyValue::Str(_)))
            {
                return Err(unicode_err(input));
            }
            match expected.iter().find(|e| py_eq(e, input)) {
                Some(v) => Ok(v.clone()),
                None => Err(err(
                    ErrorKind::LiteralError {
                        expected: repr.clone(),
                    },
                    input,
                )),
            }
        }
        Node::List {
            items,
            strict,
            min_length,
            max_length,
        } => {
            let PyValue::List(list) = input else {
                let _ = strict;
                return Err(err(ErrorKind::ListType, input));
            };
            st.floor(Exactness::Exact);
            let mut out = Vec::with_capacity(list.len());
            let mut errors = Vec::new();
            for (i, item) in list.iter().enumerate() {
                match validate(items, item, ctx, st) {
                    Ok(v) => out.push(v),
                    Err(ValError::Lines(ls)) => {
                        errors.extend(ls.into_iter().map(|l| l.outer(LocItem::I(i as i64))));
                    }
                    Err(ValError::Omit) => {}
                    Err(e) => return Err(e),
                }
            }
            if !errors.is_empty() {
                return Err(ValError::Lines(errors));
            }
            let n = out.len();
            if let Some(min) = min_length
                && n < *min
            {
                return Err(err(
                    ErrorKind::TooShort {
                        field_type: "List",
                        min_length: *min,
                        actual_length: n,
                    },
                    input,
                ));
            }
            if let Some(max) = max_length
                && n > *max
            {
                return Err(err(
                    ErrorKind::TooLong {
                        field_type: "List",
                        max_length: *max,
                        actual_length: n,
                    },
                    input,
                ));
            }
            Ok(PyValue::List(out))
        }
        Node::Dict {
            keys,
            values,
            min_length,
            max_length,
            ..
        } => {
            let PyValue::Dict(d) = input else {
                return Err(err(ErrorKind::DictType, input));
            };
            let mut out = PyDict::new();
            let mut errors = Vec::new();
            for (k, v) in d {
                let key_in = PyValue::Str(k.clone());
                let key_loc = LocItem::S(lossy(k));
                let out_key = match validate(keys, &key_in, ctx, st) {
                    Ok(PyValue::Str(s)) => Some(s),
                    Ok(_) => Some(k.clone()),
                    Err(ValError::Lines(ls)) => {
                        for l in ls {
                            errors.push(l.outer(LocItem::S("[key]".into())).outer(key_loc.clone()));
                        }
                        None
                    }
                    Err(ValError::Omit) => continue,
                    Err(e) => return Err(e),
                };
                let out_val = match validate(values, v, ctx, st) {
                    Ok(v) => v,
                    Err(ValError::Lines(ls)) => {
                        errors.extend(ls.into_iter().map(|l| l.outer(key_loc.clone())));
                        continue;
                    }
                    Err(ValError::Omit) => continue,
                    Err(e) => return Err(e),
                };
                if let Some(k) = out_key {
                    out.insert(k, out_val);
                }
            }
            if !errors.is_empty() {
                return Err(ValError::Lines(errors));
            }
            let n = out.len();
            if let Some(min) = min_length
                && n < *min
            {
                return Err(err(
                    ErrorKind::TooShort {
                        field_type: "Dictionary",
                        min_length: *min,
                        actual_length: n,
                    },
                    input,
                ));
            }
            if let Some(max) = max_length
                && n > *max
            {
                return Err(err(
                    ErrorKind::TooLong {
                        field_type: "Dictionary",
                        max_length: *max,
                        actual_length: n,
                    },
                    input,
                ));
            }
            Ok(PyValue::Dict(out))
        }
        Node::Nullable(inner) => match input {
            PyValue::None => Ok(PyValue::None),
            _ => validate(inner, input, ctx, st),
        },
        Node::Default {
            inner,
            default,
            on_error,
            ..
        } => match validate(inner, input, ctx, st) {
            Ok(v) => Ok(v),
            Err(ValError::Lines(ls)) => match on_error {
                OnError::Raise => Err(ValError::Lines(ls)),
                OnError::Omit => Err(ValError::Omit),
                OnError::Default => default.clone().ok_or(ValError::Lines(ls)),
            },
            Err(e) => Err(e),
        },
        Node::Union {
            choices,
            left_to_right,
        } => {
            if *left_to_right {
                validate_left_to_right(choices, input, ctx, st)
            } else {
                validate_smart(choices, input, ctx, st).map(|(_, v)| v)
            }
        }
        Node::Model { fields, class_name } => {
            if let PyValue::Dict(_) = input {
                st.floor(Exactness::Strict);
            }
            validate_fields(fields, input, ctx, st, Some(class_name))
        }
        Node::Fields(f) => validate_fields(f, input, ctx, st, None),
        Node::Ref(r) => match ctx.defs.get(r) {
            Some(n) => validate(n, input, ctx, st),
            None => Err(ValError::Exception(format!("정의 {r} 없음"))),
        },
        Node::Url {
            strict,
            max_length,
            allowed,
            host_required,
            ..
        } => {
            let s = match input {
                PyValue::Str(PyStr::Utf8(s)) => s.clone(),
                PyValue::Str(PyStr::Wide(_)) => return Err(unicode_err(input)),
                _ => return Err(err(ErrorKind::UrlType, input)),
            };
            let _ = strict;
            if let Some(max) = max_length
                && s.len() > *max
            {
                return Err(err(ErrorKind::UrlTooLong { max_length: *max }, input));
            }
            if s.is_empty() {
                return Err(err(
                    ErrorKind::UrlParsing {
                        error: "input is empty".into(),
                    },
                    input,
                ));
            }
            let url = match url::Url::parse(&s) {
                Ok(u) => u,
                Err(e) => {
                    return Err(err(
                        ErrorKind::UrlParsing {
                            error: e.to_string(),
                        },
                        input,
                    ));
                }
            };
            if let Some((names, repr)) = allowed
                && !names.iter().any(|n| n == url.scheme())
            {
                return Err(err(
                    ErrorKind::UrlScheme {
                        expected_schemes: repr.clone(),
                    },
                    input,
                ));
            }
            if *host_required && !url.has_host() {
                return Err(err(
                    ErrorKind::UrlParsing {
                        error: url::ParseError::EmptyHost.to_string(),
                    },
                    input,
                ));
            }
            st.floor(Exactness::Lax);
            Ok(PyValue::str(url.as_str()))
        }
        Node::UrlWrap(inner) => validate(inner, input, ctx, st),
    }
}

/// 기본값 — 없으면 None (`default_value`)
fn default_value(node: &Node, ctx: &Ctx<'_>) -> Option<PyValue> {
    match node {
        Node::Default { default, .. } => default.clone(),
        Node::Ref(r) => ctx.defs.get(r).and_then(|n| default_value(n, ctx)),
        _ => None,
    }
}

/// smart union — 고른 갈래의 번호와 값
pub fn validate_smart(
    choices: &[(Node, Option<String>)],
    input: &PyValue,
    ctx: &Ctx<'_>,
    st: &mut State,
) -> Result<(usize, PyValue), ValError> {
    let old_exactness = st.exactness;
    let old_fields = st.fields_set_count;
    let mut errors: Vec<(String, Vec<LineError>)> = Vec::new();
    let mut should_omit = false;
    let mut best: Option<(usize, PyValue, Exactness, Option<usize>)> = None;
    for (idx, (choice, label)) in choices.iter().enumerate() {
        st.exactness = Some(Exactness::Exact);
        st.fields_set_count = None;
        match validate(choice, input, ctx, st) {
            Ok(v) => match (st.exactness, st.fields_set_count) {
                (Some(Exactness::Exact), None) => {
                    st.exactness = old_exactness;
                    st.fields_set_count = old_fields;
                    return Ok((idx, v));
                }
                (e, n) => {
                    let new_e = e.unwrap_or(Exactness::Lax);
                    let better =
                        best.as_ref()
                            .is_none_or(|(_, _, cur_e, cur_n)| match (*cur_n, n) {
                                (Some(cur), Some(new)) if cur != new => cur < new,
                                _ => *cur_e < new_e,
                            });
                    if better {
                        best = Some((idx, v, new_e, n));
                    }
                }
            },
            Err(ValError::Omit) => {
                if best.is_none() {
                    should_omit = true;
                }
            }
            Err(ValError::Lines(ls)) => {
                if best.is_none() {
                    let name = label.clone().unwrap_or_else(|| choice.name(ctx.defs));
                    errors.push((name, ls));
                }
            }
            Err(e) => return Err(e),
        }
    }
    st.exactness = old_exactness;
    st.fields_set_count = old_fields;
    if let Some((idx, v, e, n)) = best {
        st.floor(e);
        if let Some(n) = n {
            st.add_fields_set(n);
        }
        return Ok((idx, v));
    }
    if should_omit {
        return Err(ValError::Omit);
    }
    Err(union_errors(errors))
}

fn validate_left_to_right(
    choices: &[(Node, Option<String>)],
    input: &PyValue,
    ctx: &Ctx<'_>,
    st: &mut State,
) -> VResult {
    let mut errors = Vec::new();
    for (choice, label) in choices {
        match validate(choice, input, ctx, st) {
            Err(ValError::Lines(ls)) => {
                let name = label.clone().unwrap_or_else(|| choice.name(ctx.defs));
                errors.push((name, ls));
            }
            other => return other,
        }
    }
    Err(union_errors(errors))
}

fn union_errors(errors: Vec<(String, Vec<LineError>)>) -> ValError {
    ValError::Lines(
        errors
            .into_iter()
            .flat_map(|(name, ls)| {
                ls.into_iter()
                    .map(move |l| l.outer(LocItem::S(name.clone())))
            })
            .collect(),
    )
}

/// `model-fields`·`typed-dict` — 사전에서 키(별칭 먼저)로 찾아 검증한다
fn validate_fields(
    f: &Fields,
    input: &PyValue,
    ctx: &Ctx<'_>,
    st: &mut State,
    _class: Option<&String>,
) -> VResult {
    let PyValue::Dict(d) = input else {
        let kind = if f.typed_dict {
            ErrorKind::DictType
        } else {
            ErrorKind::ModelType {
                class_name: f.model_name.clone(),
            }
        };
        return Err(err(kind, input));
    };
    let by_alias = st.by_alias.or(f.by_alias).unwrap_or(true);
    let by_name = st.by_name.or(f.by_name).unwrap_or(false);
    let mut out = PyDict::new();
    let mut errors: Vec<LineError> = Vec::new();
    let mut used: Option<Vec<String>> = if f.extra == Extra::Ignore {
        None
    } else {
        Some(Vec::new())
    };
    let mut fields_set = 0usize;
    for field in &f.fields {
        // lookup_paths — 별칭(있고 by_alias면), 이름(별칭이 없거나 by_name이면)
        let mut paths: Vec<&str> = Vec::new();
        if by_alias && let Some(a) = &field.alias {
            paths.push(a);
        }
        if field.alias.is_none() || by_name {
            paths.push(&field.name);
        }
        let found = paths
            .iter()
            .find_map(|p| d.get(&PyStr::from(*p)).map(|v| (*p, v)));
        if let Some((key, value)) = found {
            if let Some(used) = used.as_mut() {
                used.push(key.to_string());
            }
            match validate(&field.node, value, ctx, st) {
                Ok(v) => {
                    out.insert(PyStr::from(field.name.as_str()), v);
                    fields_set += 1;
                }
                Err(ValError::Omit) => {}
                Err(ValError::Lines(ls)) => {
                    let loc = if f.loc_by_alias {
                        key
                    } else {
                        field.name.as_str()
                    };
                    errors.extend(ls.into_iter().map(|l| l.outer(LocItem::S(loc.to_string()))));
                }
                Err(e) => return Err(e),
            }
            continue;
        }
        match default_value(&field.node, ctx) {
            Some(v) => {
                out.insert(PyStr::from(field.name.as_str()), v);
            }
            None => {
                if f.typed_dict && !field.required {
                    continue;
                }
                let loc = match (&field.alias, f.loc_by_alias && by_alias) {
                    (Some(a), true) => a.clone(),
                    _ => field.name.clone(),
                };
                errors.push(LineError::new(ErrorKind::Missing, input).outer(LocItem::S(loc)));
            }
        }
    }
    if f.typed_dict {
        st.add_fields_set(fields_set);
    }
    if let Some(used) = used {
        for (k, v) in d {
            let ks = k.as_str().map(str::to_string);
            if ks.as_ref().is_some_and(|ks| used.iter().any(|u| u == ks)) {
                continue;
            }
            match f.extra {
                Extra::Forbid => errors
                    .push(LineError::new(ErrorKind::ExtraForbidden, v).outer(LocItem::S(lossy(k)))),
                Extra::Ignore => {}
                Extra::Allow => match &f.extras {
                    Some(ev) => match validate(ev, v, ctx, st) {
                        Ok(v) => {
                            out.insert(k.clone(), v);
                        }
                        Err(ValError::Lines(ls)) => {
                            errors.extend(ls.into_iter().map(|l| l.outer(LocItem::S(lossy(k)))));
                        }
                        Err(ValError::Omit) => {}
                        Err(e) => return Err(e),
                    },
                    None => {
                        out.insert(k.clone(), v.clone());
                    }
                },
            }
        }
    }
    if !errors.is_empty() {
        return Err(ValError::Lines(errors));
    }
    if !f.typed_dict {
        st.add_fields_set(fields_set);
    }
    Ok(PyValue::Dict(out))
}

/// `PyString.to_string_lossy` — 서로게이트는 U+FFFD
fn lossy(s: &PyStr) -> String {
    match s {
        PyStr::Utf8(s) => s.clone(),
        PyStr::Wide(v) => v
            .iter()
            .map(|&c| char::from_u32(c).unwrap_or('\u{FFFD}'))
            .collect(),
    }
}

/// 파이썬 `==` — 수는 bool·int·float를 가로질러 값으로, 나머지는 같은 종류끼리
pub fn py_eq(a: &PyValue, b: &PyValue) -> bool {
    fn num(v: &PyValue) -> Option<(Option<BigInt>, f64)> {
        match v {
            PyValue::Bool(b) => Some((Some(BigInt::from(u8::from(*b))), f64::from(u8::from(*b)))),
            PyValue::Int(i) => Some((Some(i.clone()), i.to_f64().unwrap_or(f64::NAN))),
            PyValue::Float(f) => Some((None, *f)),
            _ => None,
        }
    }
    match (a, b) {
        (PyValue::None, PyValue::None) => true,
        (PyValue::Str(x), PyValue::Str(y)) => x == y,
        _ => match (num(a), num(b)) {
            (Some((Some(x), _)), Some((Some(y), _))) => x == y,
            (Some((xi, xf)), Some((yi, yf))) => {
                // int와 float — float가 정수이고 int와 같아야 한다
                let (i, f) = match (xi, yi) {
                    (Some(i), None) => (i, yf),
                    (None, Some(i)) => (i, xf),
                    _ => return xf == yf,
                };
                f.is_finite() && f.fract() == 0.0 && BigInt::from_f64_exact(f) == Some(i)
            }
            _ => false,
        },
    }
}

trait FromF64Exact {
    fn from_f64_exact(f: f64) -> Option<BigInt>;
}

impl FromF64Exact for BigInt {
    fn from_f64_exact(f: f64) -> Option<BigInt> {
        num_traits::FromPrimitive::from_f64(f)
    }
}

// ---- 기본형 (input_python.rs · shared.rs) ----

fn py_str_str<'a>(s: &'a PyStr, input: &PyValue) -> Result<&'a str, ValError> {
    s.as_str().ok_or_else(|| unicode_err(input))
}

fn validate_bool(input: &PyValue, strict: bool) -> Result<(bool, Exactness), ValError> {
    match input {
        PyValue::Bool(b) => return Ok((*b, Exactness::Exact)),
        _ if strict => {}
        PyValue::Str(s) => {
            return str_as_bool(py_str_str(s, input)?, input).map(|b| (b, Exactness::Lax));
        }
        PyValue::Int(i) => {
            if let Some(i) = i.to_i64() {
                return int_as_bool(i, input).map(|b| (b, Exactness::Lax));
            }
            if let Some(f) = int_to_f64(i)
                && let Ok(i) = float_as_int(f, input)
            {
                return match i.to_i64() {
                    Some(0) => Ok((false, Exactness::Lax)),
                    Some(1) => Ok((true, Exactness::Lax)),
                    _ => Err(err(ErrorKind::BoolParsing, input)),
                };
            }
        }
        PyValue::Float(f) => {
            if let Ok(i) = float_as_int(*f, input) {
                return match i.to_i64() {
                    Some(0) => Ok((false, Exactness::Lax)),
                    Some(1) => Ok((true, Exactness::Lax)),
                    _ => Err(err(ErrorKind::BoolParsing, input)),
                };
            }
        }
        _ => {}
    }
    Err(err(ErrorKind::BoolType, input))
}

fn validate_int(input: &PyValue, strict: bool) -> Result<(BigInt, Exactness), ValError> {
    match input {
        PyValue::Int(i) => Ok((i.clone(), Exactness::Exact)),
        PyValue::Bool(b) => {
            if strict {
                Err(err(ErrorKind::IntType, input))
            } else {
                Ok((BigInt::from(u8::from(*b)), Exactness::Lax))
            }
        }
        _ if strict => Err(err(ErrorKind::IntType, input)),
        PyValue::Str(s) => str_as_int(py_str_str(s, input)?, input).map(|i| (i, Exactness::Lax)),
        PyValue::Float(f) => float_as_int(*f, input).map(|i| (i, Exactness::Lax)),
        _ => Err(err(ErrorKind::IntType, input)),
    }
}

fn validate_float(input: &PyValue, strict: bool) -> Result<(f64, Exactness), ValError> {
    match input {
        PyValue::Float(f) => Ok((*f, Exactness::Exact)),
        PyValue::Str(s) if !strict => {
            str_as_float(py_str_str(s, input)?, input).map(|f| (f, Exactness::Lax))
        }
        PyValue::Int(i) => match int_to_f64(i) {
            Some(f) => Ok((f, Exactness::Strict)),
            None => Err(err(ErrorKind::FloatType, input)),
        },
        PyValue::Bool(b) => {
            if strict {
                Err(err(ErrorKind::FloatType, input))
            } else {
                Ok((f64::from(u8::from(*b)), Exactness::Lax))
            }
        }
        _ => Err(err(ErrorKind::FloatType, input)),
    }
}

/// 파이썬 `float(int)` — 너무 크면 OverflowError(None)
fn int_to_f64(i: &BigInt) -> Option<f64> {
    let f = i.to_f64()?;
    f.is_finite().then_some(f)
}

fn str_as_bool(s: &str, input: &PyValue) -> Result<bool, ValError> {
    let l = s.to_ascii_lowercase();
    if s == "0" || matches!(l.as_str(), "f" | "n" | "no" | "off" | "false") {
        Ok(false)
    } else if s == "1" || matches!(l.as_str(), "t" | "y" | "on" | "yes" | "true") {
        Ok(true)
    } else {
        Err(err(ErrorKind::BoolParsing, input))
    }
}

fn int_as_bool(i: i64, input: &PyValue) -> Result<bool, ValError> {
    match i {
        0 => Ok(false),
        1 => Ok(true),
        _ => Err(err(ErrorKind::BoolParsing, input)),
    }
}

fn number_int(b: &[u8]) -> Result<BigInt, JsonErrorType> {
    match NumberInt::try_from(b) {
        Ok(NumberInt::Int(i)) => Ok(BigInt::from(i)),
        Ok(NumberInt::BigInt(i)) => Ok(i),
        Err(e) => Err(e.error_type),
    }
}

fn str_as_int(s: &str, input: &PyValue) -> Result<BigInt, ValError> {
    match number_int(s.as_bytes()) {
        Ok(i) => return Ok(i),
        Err(JsonErrorType::NumberOutOfRange) => {
            return Err(err(ErrorKind::IntParsingSize, input));
        }
        Err(_) => {}
    }
    match clean_int_str(s) {
        Some(c) => number_int(c.as_bytes()).map_err(|_| err(ErrorKind::IntParsing, input)),
        None => Err(err(ErrorKind::IntParsing, input)),
    }
}

fn str_as_float(s: &str, input: &PyValue) -> Result<f64, ValError> {
    if let Ok(f) = s.trim().parse::<f64>() {
        return Ok(f);
    }
    match strip_underscores(s).and_then(|x| x.parse::<f64>().ok()) {
        Some(f) => Ok(f),
        None => Err(err(ErrorKind::FloatParsing, input)),
    }
}

fn strip_underscores(s: &str) -> Option<String> {
    if s.starts_with('_') || s.ends_with('_') || !s.contains('_') || s.contains("__") {
        None
    } else {
        Some(s.replace('_', ""))
    }
}

fn clean_int_str(s: &str) -> Option<String> {
    let len_before = s.len();
    let mut s = s.trim();
    if let Some(suffix) = s.strip_prefix('+') {
        if suffix.starts_with('-') {
            return None;
        }
        s = suffix;
    }
    let mut neg = false;
    if let Some(suffix) = s.strip_prefix('-') {
        if suffix.starts_with('-') || suffix.starts_with('+') {
            return None;
        }
        neg = true;
        s = suffix;
    }
    s = strip_leading_zeros(s)?;
    if let Some(i) = s.find('.') {
        let dec = &s[i + 1..];
        if !dec.is_empty() && dec.chars().all(|c| c == '0') {
            s = &s[..i];
        }
    }
    if let Some(stripped) = strip_underscores(s) {
        return Some(if neg {
            format!("-{stripped}")
        } else {
            stripped
        });
    }
    if len_before == s.len() {
        return None;
    }
    Some(if neg { format!("-{s}") } else { s.to_string() })
}

fn strip_leading_zeros(s: &str) -> Option<&str> {
    let mut it = s.char_indices();
    match it.next() {
        Some((_, '0')) => {}
        Some((_, c)) if ('1'..='9').contains(&c) || c == '-' => return Some(s),
        _ => return None,
    }
    for (i, c) in it {
        match c {
            '0' | '_' => {}
            '1'..='9' | '-' => return Some(&s[i..]),
            '.' => return Some(&s[i - 1..]),
            _ => return None,
        }
    }
    Some(&s[s.len() - 1..])
}

fn float_as_int(f: f64, input: &PyValue) -> Result<BigInt, ValError> {
    if f.is_infinite() || f.is_nan() {
        Err(err(ErrorKind::FiniteNumber, input))
    } else if f % 1.0 != 0.0 {
        Err(err(ErrorKind::IntFromFloat, input))
    } else if (i64::MIN as f64) < f && f < (i64::MAX as f64) {
        Ok(BigInt::from(f as i64))
    } else {
        Err(err(ErrorKind::IntParsingSize, input))
    }
}

/// 제약 — multiple_of·le·lt·ge·gt 차례 (ConstrainedIntValidator)
fn check_int(i: &BigInt, c: &NumC, input: &PyValue) -> Result<(), ValError> {
    let as_f = || i.to_f64().unwrap_or(f64::NAN);
    let cmp = |n: &Num| -> std::cmp::Ordering {
        match n {
            Num::Int(x) => i.cmp(&BigInt::from(*x)),
            Num::Float(x) => as_f().partial_cmp(x).unwrap_or(std::cmp::Ordering::Equal),
        }
    };
    if let Some(m) = &c.multiple_of {
        let ok = match m {
            Num::Int(x) => *x != 0 && (i % BigInt::from(*x)).is_zero(),
            Num::Float(x) => as_f() % x == 0.0,
        };
        if !ok {
            return Err(err(
                ErrorKind::MultipleOf {
                    multiple_of: m.clone(),
                },
                input,
            ));
        }
    }
    if let Some(le) = &c.le
        && cmp(le) == std::cmp::Ordering::Greater
    {
        return Err(err(ErrorKind::LessThanEqual { le: le.clone() }, input));
    }
    if let Some(lt) = &c.lt
        && cmp(lt) != std::cmp::Ordering::Less
    {
        return Err(err(ErrorKind::LessThan { lt: lt.clone() }, input));
    }
    if let Some(ge) = &c.ge
        && cmp(ge) == std::cmp::Ordering::Less
    {
        return Err(err(ErrorKind::GreaterThanEqual { ge: ge.clone() }, input));
    }
    if let Some(gt) = &c.gt
        && cmp(gt) != std::cmp::Ordering::Greater
    {
        return Err(err(ErrorKind::GreaterThan { gt: gt.clone() }, input));
    }
    Ok(())
}

fn check_float(f: f64, c: &NumC, input: &PyValue) -> Result<(), ValError> {
    use std::cmp::Ordering::{Equal, Greater, Less};
    if let Some(m) = &c.multiple_of {
        let r = f / m.as_f64();
        if (r - r.round()).abs() > 1e-9 {
            return Err(err(
                ErrorKind::MultipleOf {
                    multiple_of: m.clone(),
                },
                input,
            ));
        }
    }
    if let Some(le) = &c.le
        && !matches!(f.partial_cmp(&le.as_f64()), Some(Less | Equal))
    {
        return Err(err(ErrorKind::LessThanEqual { le: le.clone() }, input));
    }
    if let Some(lt) = &c.lt
        && f.partial_cmp(&lt.as_f64()) != Some(Less)
    {
        return Err(err(ErrorKind::LessThan { lt: lt.clone() }, input));
    }
    if let Some(ge) = &c.ge
        && !matches!(f.partial_cmp(&ge.as_f64()), Some(Greater | Equal))
    {
        return Err(err(ErrorKind::GreaterThanEqual { ge: ge.clone() }, input));
    }
    if let Some(gt) = &c.gt
        && f.partial_cmp(&gt.as_f64()) != Some(Greater)
    {
        return Err(err(ErrorKind::GreaterThan { gt: gt.clone() }, input));
    }
    Ok(())
}
