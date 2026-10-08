//! pydantic-core 스키마 — 파이썬 판이 내보낸 core schema(JSON)를 검증기 나무로 (SYNC-DOM-004 1장 compat).
//! 내보내기는 `cargo xtask mcp-tools`가 한다. 쓰는 종류만 받고 모르는 종류는 읽을 때 실패한다 —
//! 파이썬이 새 종류를 쓰기 시작하면 조용히 넘기지 않고 여기서 멈춘다.

use std::collections::HashMap;

use serde_json::Value;

use super::errors::Num;
use crate::compat::pyvalue::{PyDict, PyStr, PyValue};

/// 모델·typed-dict의 남는 키 다루기
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Extra {
    Ignore,
    Allow,
    Forbid,
}

/// 숫자 제약
#[derive(Clone, Debug, Default)]
pub struct NumC {
    pub gt: Option<Num>,
    pub ge: Option<Num>,
    pub lt: Option<Num>,
    pub le: Option<Num>,
    pub multiple_of: Option<Num>,
}

impl NumC {
    fn any(&self) -> bool {
        self.gt.is_some()
            || self.ge.is_some()
            || self.lt.is_some()
            || self.le.is_some()
            || self.multiple_of.is_some()
    }
}

/// 모델 필드 하나
#[derive(Clone, Debug)]
pub struct Field {
    pub name: String,
    /// `validation_alias` — 없으면 이름으로 찾는다
    pub alias: Option<String>,
    pub node: Node,
    /// typed-dict 필드만 — 없어도 되나
    pub required: bool,
}

/// `model-fields`·`typed-dict` 공통
#[derive(Clone, Debug)]
pub struct Fields {
    pub fields: Vec<Field>,
    pub model_name: String,
    pub extra: Extra,
    pub extras: Option<Box<Node>>,
    pub strict: bool,
    pub loc_by_alias: bool,
    pub by_alias: Option<bool>,
    pub by_name: Option<bool>,
    pub typed_dict: bool,
}

/// `default`의 실패 처리
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum OnError {
    Raise,
    Omit,
    Default,
}

/// 검증기 나무의 마디
#[derive(Clone, Debug)]
pub enum Node {
    Any,
    None,
    Bool {
        strict: bool,
    },
    Int {
        strict: bool,
        c: NumC,
    },
    Float {
        strict: bool,
        allow_inf_nan: bool,
        c: NumC,
    },
    Str {
        strict: bool,
        min_length: Option<usize>,
        max_length: Option<usize>,
        /// pydantic-core 기본 엔진(rust-regex)과 같은 `regex` crate — `is_match`(어디든 맞으면)
        pattern: Option<(String, regex::Regex)>,
    },
    Literal {
        expected: Vec<PyValue>,
        repr: String,
        name: String,
    },
    List {
        items: Box<Node>,
        strict: bool,
        min_length: Option<usize>,
        max_length: Option<usize>,
    },
    Dict {
        keys: Box<Node>,
        values: Box<Node>,
        strict: bool,
        min_length: Option<usize>,
        max_length: Option<usize>,
    },
    Nullable(Box<Node>),
    Default {
        inner: Box<Node>,
        default: Option<PyValue>,
        on_error: OnError,
        validate_default: bool,
    },
    Union {
        choices: Vec<(Node, Option<String>)>,
        left_to_right: bool,
    },
    Model {
        class_name: String,
        fields: Box<Fields>,
    },
    Fields(Box<Fields>),
    Ref(String),
    Url {
        strict: bool,
        max_length: Option<usize>,
        allowed: Option<(Vec<String>, String)>,
        host_required: bool,
        name: String,
    },
    /// pydantic `_BaseUrl`의 wrap 검증 — 문자열 입력에는 안쪽 url 검증과 같다
    UrlWrap(Box<Node>),
}

/// 읽은 스키마 — 뿌리와 정의들(`definitions`·`definition-ref`)
#[derive(Clone, Debug)]
pub struct Compiled {
    pub root: Node,
    pub defs: HashMap<String, Node>,
    /// 오류 제목 — 검증기 `title`(`N validation errors for {title}`)
    pub title: String,
}

/// 읽기 실패 — 내보낸 스키마가 이 옮김이 모르는 꼴이다
#[derive(Debug)]
pub struct SchemaError(pub String);

/// 물려받는 config
#[derive(Clone, Debug, Default)]
struct Config {
    strict: Option<bool>,
    extra: Option<Extra>,
    by_alias: Option<bool>,
    by_name: Option<bool>,
    loc_by_alias: Option<bool>,
    str_max_length: Option<usize>,
    str_min_length: Option<usize>,
    allow_inf_nan: Option<bool>,
}

impl Config {
    fn from_value(v: Option<&Value>) -> Config {
        let Some(v) = v else {
            return Config::default();
        };
        let b = |k: &str| v.get(k).and_then(Value::as_bool);
        let u = |k: &str| v.get(k).and_then(Value::as_u64).map(|n| n as usize);
        Config {
            strict: b("strict"),
            extra: v
                .get("extra_fields_behavior")
                .and_then(Value::as_str)
                .and_then(extra_of),
            by_alias: b("validate_by_alias"),
            by_name: b("validate_by_name"),
            loc_by_alias: b("loc_by_alias"),
            str_max_length: u("str_max_length"),
            str_min_length: u("str_min_length"),
            allow_inf_nan: b("allow_inf_nan"),
        }
    }
}

fn extra_of(s: &str) -> Option<Extra> {
    match s {
        "ignore" => Some(Extra::Ignore),
        "allow" => Some(Extra::Allow),
        "forbid" => Some(Extra::Forbid),
        _ => None,
    }
}

/// JSON 값 → 파이썬 값 (스키마의 기본값·Literal 값)
pub fn py_of_json(v: &Value) -> PyValue {
    match v {
        Value::Null => PyValue::None,
        Value::Bool(b) => PyValue::Bool(*b),
        Value::Number(n) => {
            if let Ok(i) = n.to_string().parse::<num_bigint::BigInt>() {
                PyValue::Int(i)
            } else {
                PyValue::Float(n.as_f64().unwrap_or(f64::NAN))
            }
        }
        Value::String(s) => PyValue::str(s),
        Value::Array(a) => PyValue::List(a.iter().map(py_of_json).collect()),
        Value::Object(o) => {
            let mut d = PyDict::new();
            for (k, v) in o {
                d.insert(PyStr::from(k.as_str()), py_of_json(v));
            }
            PyValue::Dict(d)
        }
    }
}

fn num_of(v: Option<&Value>) -> Option<Num> {
    let v = v?;
    if let Some(i) = v.as_i64() {
        Some(Num::Int(i))
    } else {
        v.as_f64().map(Num::Float)
    }
}

/// Literal 값들의 `repr` → `'a', 'b' or 'c'`와 이름 `literal['a','b','c']`
pub fn literal_texts(base: &str, reprs: &[String]) -> (String, String) {
    let name = format!("{base}[{}]", reprs.join(","));
    let repr = match reprs.split_last() {
        Some((last, [])) => last.clone(),
        Some((last, rest)) => format!("{} or {last}", rest.join(", ")),
        None => String::new(),
    };
    (repr, name)
}

/// 내보낸 core schema를 읽는다
pub fn compile(schema: &Value, title: &str) -> Result<Compiled, SchemaError> {
    let mut defs = HashMap::new();
    let root = build(schema, &Config::default(), &mut defs)?;
    Ok(Compiled {
        root,
        defs,
        title: title.to_string(),
    })
}

fn build(s: &Value, cfg: &Config, defs: &mut HashMap<String, Node>) -> Result<Node, SchemaError> {
    let ty = s
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| SchemaError(format!("type 없음: {s}")))?;
    let strict = s
        .get("strict")
        .and_then(Value::as_bool)
        .or(cfg.strict)
        .unwrap_or(false);
    let usize_of = |k: &str| s.get(k).and_then(Value::as_u64).map(|n| n as usize);
    let node = match ty {
        "any" => Node::Any,
        "none" => Node::None,
        "bool" => Node::Bool { strict },
        "int" => {
            let c = NumC {
                gt: num_of(s.get("gt")),
                ge: num_of(s.get("ge")),
                lt: num_of(s.get("lt")),
                le: num_of(s.get("le")),
                multiple_of: num_of(s.get("multiple_of")),
            };
            Node::Int { strict, c }
        }
        "float" => {
            let c = NumC {
                gt: num_of(s.get("gt")),
                ge: num_of(s.get("ge")),
                lt: num_of(s.get("lt")),
                le: num_of(s.get("le")),
                multiple_of: num_of(s.get("multiple_of")),
            };
            Node::Float {
                strict,
                allow_inf_nan: s
                    .get("allow_inf_nan")
                    .and_then(Value::as_bool)
                    .or(cfg.allow_inf_nan)
                    .unwrap_or(true),
                c,
            }
        }
        "str" => {
            for k in [
                "strip_whitespace",
                "to_lower",
                "to_upper",
                "coerce_numbers_to_str",
            ] {
                if s.get(k)
                    .is_some_and(|v| !v.is_null() && v != &Value::Bool(false))
                {
                    return Err(SchemaError(format!("str {k}는 옮기지 않았다")));
                }
            }
            let pattern = match s.get("pattern").and_then(Value::as_str) {
                Some(p) => Some((
                    p.to_string(),
                    regex::Regex::new(p).map_err(|e| SchemaError(format!("pattern {p}: {e}")))?,
                )),
                None => None,
            };
            Node::Str {
                strict,
                min_length: usize_of("min_length").or(cfg.str_min_length),
                max_length: usize_of("max_length").or(cfg.str_max_length),
                pattern,
            }
        }
        "literal" => {
            let expected: Vec<PyValue> = s
                .get("expected")
                .and_then(Value::as_array)
                .ok_or_else(|| SchemaError("literal expected 없음".into()))?
                .iter()
                .map(py_of_json)
                .collect();
            let reprs: Vec<String> = expected.iter().map(PyValue::safe_repr).collect();
            let (repr, name) = literal_texts("literal", &reprs);
            Node::Literal {
                expected,
                repr,
                name,
            }
        }
        "list" => Node::List {
            items: Box::new(match s.get("items_schema") {
                Some(i) => build(i, cfg, defs)?,
                None => Node::Any,
            }),
            strict,
            min_length: usize_of("min_length"),
            max_length: usize_of("max_length"),
        },
        "dict" => Node::Dict {
            keys: Box::new(match s.get("keys_schema") {
                Some(i) => build(i, cfg, defs)?,
                None => Node::Any,
            }),
            values: Box::new(match s.get("values_schema") {
                Some(i) => build(i, cfg, defs)?,
                None => Node::Any,
            }),
            strict,
            min_length: usize_of("min_length"),
            max_length: usize_of("max_length"),
        },
        "nullable" => Node::Nullable(Box::new(build(req(s, "schema")?, cfg, defs)?)),
        "default" => {
            if s.get("default_factory").is_some() {
                return Err(SchemaError("default_factory는 옮기지 않았다".into()));
            }
            Node::Default {
                inner: Box::new(build(req(s, "schema")?, cfg, defs)?),
                default: s.get("default").map(py_of_json),
                on_error: match s.get("on_error").and_then(Value::as_str) {
                    Some("omit") => OnError::Omit,
                    Some("default") => OnError::Default,
                    _ => OnError::Raise,
                },
                validate_default: s
                    .get("validate_default")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
            }
        }
        "union" => {
            if s.get("custom_error_type").is_some() {
                return Err(SchemaError("union custom_error는 옮기지 않았다".into()));
            }
            let mut choices = Vec::new();
            for c in s
                .get("choices")
                .and_then(Value::as_array)
                .ok_or_else(|| SchemaError("union choices 없음".into()))?
            {
                // (schema, label) 짝이면 label
                if let Some(pair) = c.as_array() {
                    let node = build(&pair[0], cfg, defs)?;
                    let label = pair.get(1).and_then(Value::as_str).map(str::to_string);
                    choices.push((node, label));
                } else {
                    choices.push((build(c, cfg, defs)?, None));
                }
            }
            let auto_collapse = s
                .get("auto_collapse")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            if choices.len() == 1 && auto_collapse {
                return Ok(choices.remove(0).0);
            }
            Node::Union {
                choices,
                left_to_right: s.get("mode").and_then(Value::as_str) == Some("left_to_right"),
            }
        }
        "model" => {
            for k in ["custom_init", "root_model", "post_init"] {
                if s.get(k)
                    .is_some_and(|v| v != &Value::Bool(false) && !v.is_null())
                {
                    return Err(SchemaError(format!("model {k}는 옮기지 않았다")));
                }
            }
            let class_name = s
                .get("cls")
                .and_then(Value::as_str)
                .unwrap_or("Model")
                .to_string();
            let model_cfg = Config::from_value(s.get("config"));
            let inner = req(s, "schema")?;
            let fields = build_fields(inner, &model_cfg, defs, false)?;
            Node::Model {
                class_name,
                fields: Box::new(fields),
            }
        }
        "model-fields" => Node::Fields(Box::new(build_fields(s, cfg, defs, false)?)),
        "typed-dict" => {
            let td_cfg = match s.get("config") {
                Some(c) => Config::from_value(Some(c)),
                None => cfg.clone(),
            };
            Node::Fields(Box::new(build_fields(s, &td_cfg, defs, true)?))
        }
        "definitions" => {
            for d in s
                .get("definitions")
                .and_then(Value::as_array)
                .ok_or_else(|| SchemaError("definitions 없음".into()))?
            {
                let r = d
                    .get("ref")
                    .and_then(Value::as_str)
                    .ok_or_else(|| SchemaError("definition ref 없음".into()))?
                    .to_string();
                let node = build(d, cfg, defs)?;
                defs.insert(r, node);
            }
            build(req(s, "schema")?, cfg, defs)?
        }
        "definition-ref" => Node::Ref(
            s.get("schema_ref")
                .and_then(Value::as_str)
                .ok_or_else(|| SchemaError("schema_ref 없음".into()))?
                .to_string(),
        ),
        "url" => {
            let allowed = match s.get("allowed_schemes").and_then(Value::as_array) {
                Some(list) => {
                    let names: Vec<String> = list
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::to_string)
                        .collect();
                    let reprs: Vec<String> = names
                        .iter()
                        .map(|n| PyStr::from(n.as_str()).repr())
                        .collect();
                    let (repr, _) = literal_texts("url", &reprs);
                    Some((names, repr))
                }
                None => None,
            };
            let name = match &allowed {
                Some((names, _)) => {
                    let reprs: Vec<String> = names
                        .iter()
                        .map(|n| PyStr::from(n.as_str()).repr())
                        .collect();
                    literal_texts("url", &reprs).1
                }
                None => "url".to_string(),
            };
            Node::Url {
                strict,
                max_length: usize_of("max_length"),
                allowed,
                host_required: s
                    .get("host_required")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                name,
            }
        }
        "function-wrap" => {
            let fname = s
                .get("function")
                .and_then(|f| f.get("function"))
                .and_then(|f| f.get("<fn>"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if fname != "_BaseUrl.__get_pydantic_core_schema__.<locals>.wrap_val" {
                return Err(SchemaError(format!(
                    "function-wrap {fname}는 옮기지 않았다"
                )));
            }
            Node::UrlWrap(Box::new(build(req(s, "schema")?, cfg, defs)?))
        }
        other => return Err(SchemaError(format!("모르는 종류 {other}"))),
    };
    // 제약이 있는 숫자는 이름이 다르다 (constrained-int …) — 이름은 Node::name이 정한다
    if let Node::Int { c, .. } | Node::Float { c, .. } = &node {
        let _ = c.any();
    }
    if let Some(r) = s.get("ref").and_then(Value::as_str)
        && ty != "definitions"
    {
        defs.entry(r.to_string()).or_insert_with(|| node.clone());
    }
    Ok(node)
}

fn req<'a>(s: &'a Value, k: &str) -> Result<&'a Value, SchemaError> {
    s.get(k).ok_or_else(|| {
        SchemaError(format!(
            "{k} 없음: {}",
            s.get("type").unwrap_or(&Value::Null)
        ))
    })
}

fn build_fields(
    s: &Value,
    cfg: &Config,
    defs: &mut HashMap<String, Node>,
    typed_dict: bool,
) -> Result<Fields, SchemaError> {
    let mut fields = Vec::new();
    let total = s.get("total").and_then(Value::as_bool).unwrap_or(true);
    if let Some(obj) = s.get("fields").and_then(Value::as_object) {
        for (name, f) in obj {
            let alias = match f.get("validation_alias") {
                Some(Value::String(a)) => Some(a.clone()),
                Some(Value::Null) | None => None,
                Some(other) => {
                    return Err(SchemaError(format!(
                        "validation_alias 꼴 {other}는 옮기지 않았다"
                    )));
                }
            };
            let node = build(req(f, "schema")?, cfg, defs)?;
            let required = f.get("required").and_then(Value::as_bool).unwrap_or(total);
            fields.push(Field {
                name: name.clone(),
                alias,
                node,
                required,
            });
        }
    }
    let extra = s
        .get("extra_behavior")
        .and_then(Value::as_str)
        .and_then(extra_of)
        .or(cfg.extra)
        .unwrap_or(Extra::Ignore);
    let extras = match s.get("extras_schema") {
        Some(e) if extra == Extra::Allow => Some(Box::new(build(e, cfg, defs)?)),
        _ => None,
    };
    let model_name = if typed_dict {
        s.get("cls")
            .and_then(Value::as_str)
            .unwrap_or("typed-dict")
            .to_string()
    } else {
        s.get("model_name")
            .and_then(Value::as_str)
            .unwrap_or("Model")
            .to_string()
    };
    Ok(Fields {
        fields,
        model_name,
        extra,
        extras,
        strict: s
            .get("strict")
            .and_then(Value::as_bool)
            .or(cfg.strict)
            .unwrap_or(false),
        loc_by_alias: cfg.loc_by_alias.unwrap_or(true),
        by_alias: cfg.by_alias,
        by_name: cfg.by_name,
        typed_dict,
    })
}

impl Node {
    /// pydantic `get_name` — union 오류의 `loc` 이름표
    pub fn name(&self, defs: &HashMap<String, Node>) -> String {
        match self {
            Node::Any => "any".into(),
            Node::None => "none".into(),
            Node::Bool { .. } => "bool".into(),
            Node::Int { c, .. } => if c.any() { "constrained-int" } else { "int" }.into(),
            Node::Float { c, .. } => if c.any() {
                "constrained-float"
            } else {
                "float"
            }
            .into(),
            Node::Str {
                min_length,
                max_length,
                ..
            } => {
                if min_length.is_some() || max_length.is_some() {
                    "constrained-str".into()
                } else {
                    "str".into()
                }
            }
            Node::Literal { name, .. } => name.clone(),
            Node::List { items, .. } => format!("list[{}]", items.name(defs)),
            Node::Dict { keys, values, .. } => {
                format!("dict[{},{}]", keys.name(defs), values.name(defs))
            }
            Node::Nullable(i) => format!("nullable[{}]", i.name(defs)),
            Node::Default { inner, .. } => format!("default[{}]", inner.name(defs)),
            Node::Union { choices, .. } => {
                let labels: Vec<String> = choices
                    .iter()
                    .map(|(n, l)| l.clone().unwrap_or_else(|| n.name(defs)))
                    .collect();
                format!("union[{}]", labels.join(","))
            }
            Node::Model { class_name, .. } => class_name.clone(),
            Node::Fields(f) => {
                if f.typed_dict {
                    f.model_name.clone()
                } else {
                    "model-fields".into()
                }
            }
            Node::Ref(r) => defs.get(r).map_or_else(|| "...".into(), |n| n.name(defs)),
            Node::Url { name, .. } => name.clone(),
            Node::UrlWrap(i) => format!("function-wrap[wrap_val({})]", i.name(defs)),
        }
    }
}
