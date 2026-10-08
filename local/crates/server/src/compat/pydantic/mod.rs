//! pydantic 검증 — 파이썬 판이 내보낸 core schema를 읽어 같은 규칙으로 검증하고 같은 오류 문장을 낸다
//! (SYNC-DOM-004 1장 compat · 사용자 결정 2026-10-08 「검증 문장까지 바이트로」).

pub mod errors;
pub mod schema;
pub mod validate;

use serde_json::Value;

pub use errors::{ErrorKind, LineError, LocItem, ValidationError};
pub use schema::SchemaError;

use crate::compat::pyvalue::PyValue;
use schema::Compiled;
use validate::{Ctx, State, ValError};

/// `model_validate`·`validate_python`의 덮어쓰기 인자
#[derive(Clone, Copy, Debug, Default)]
pub struct Opts {
    pub by_alias: Option<bool>,
    pub by_name: Option<bool>,
    pub strict: Option<bool>,
}

/// 검증 실패
#[derive(Debug)]
pub enum Failure {
    /// `pydantic.ValidationError`
    Invalid(ValidationError),
    /// 그 밖의 파이썬 예외 — 부르는 쪽이 `except ValidationError`로 못 잡는다
    Exception(String),
}

/// 읽어 둔 검증기 하나 (`SchemaValidator`)
#[derive(Clone, Debug)]
pub struct Validator {
    compiled: Compiled,
}

impl Validator {
    pub fn new(schema: &Value, title: &str) -> Result<Self, SchemaError> {
        Ok(Validator {
            compiled: schema::compile(schema, title)?,
        })
    }

    pub fn title(&self) -> &str {
        &self.compiled.title
    }

    pub fn validate(&self, input: &PyValue, opts: Opts) -> Result<PyValue, Failure> {
        self.run(input, opts, |root, input, ctx, st| {
            validate::validate(root, input, ctx, st)
        })
    }

    /// 뿌리가 smart union이면 고른 갈래 번호도 — JSON-RPC 봉투가 요청·알림·응답·오류 가운데 무엇인지
    pub fn validate_union(&self, input: &PyValue, opts: Opts) -> Result<(usize, PyValue), Failure> {
        self.run(input, opts, |root, input, ctx, st| match root {
            schema::Node::Union { choices, .. } => {
                validate::validate_smart(choices, input, ctx, st)
            }
            other => validate::validate(other, input, ctx, st).map(|v| (0, v)),
        })
    }

    fn run<T>(
        &self,
        input: &PyValue,
        opts: Opts,
        f: impl FnOnce(&schema::Node, &PyValue, &Ctx<'_>, &mut State) -> Result<T, ValError>,
    ) -> Result<T, Failure> {
        let ctx = Ctx {
            defs: &self.compiled.defs,
        };
        let mut st = State {
            by_alias: opts.by_alias,
            by_name: opts.by_name,
            strict: opts.strict,
            ..State::default()
        };
        match f(&self.compiled.root, input, &ctx, &mut st) {
            Ok(v) => Ok(v),
            Err(ValError::Lines(lines)) => Err(Failure::Invalid(ValidationError {
                title: self.compiled.title.clone(),
                lines,
            })),
            // 맨 위의 Omit은 파이썬에서 SchemaError — 여기 스키마에서는 나오지 않는다
            Err(ValError::Omit) => Err(Failure::Exception("Uncaught Omit error".into())),
            Err(ValError::Exception(e)) => Err(Failure::Exception(e)),
        }
    }
}
