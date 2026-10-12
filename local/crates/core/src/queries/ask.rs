//! 묻기 — 문서·코드 그래프에서 묻고 모델이 읽기 도구로 따라 읽는다 (SYNC-MS-018 · 파이썬 판 `queries.ask_item`·`ask_code`, 카드 L14).
//! ReAct 루프는 따로 띄운 작업이 돌고 이벤트를 통로로 넘긴다 — 시작 전 실패는 `Err`(상태 코드), 뒤의 실패는
//! 통로의 `Err`(`error` 이벤트). 쓰는 것은 대화 표뿐이다

use std::collections::HashMap;
use std::sync::{Arc, LazyLock};
use std::time::Instant;

use regex::Regex;
use serde_json::{Map, Value, json};
use sqlx::{PgConnection, PgPool};
use tokio::sync::mpsc::{UnboundedSender, unbounded_channel};

use super::ask_text::{
    ASK_CODE_SYSTEM, ASK_MISSING_HINT, ASK_SYSTEM, ASK_TOOLS_JSON, ASK_WRAP_UP, READ_CODE_HINT,
};
use super::{
    by_key, code_view, diffs_of, document_list, document_view, item_chain, item_references_view,
    item_view, layers_of, next_start, title_of,
};
use crate::account::model::UserRow;
use crate::codegraph::CodeGraphService;
use crate::conversation::ConversationService;
use crate::errors::Problem;
use crate::infra::llm::Llm;
use crate::project::service::{ProjectService, ServerRepos};
use crate::pycompat::chars::{rstrip, strip};
use crate::pycompat::json::dumps;
use crate::pycompat::re::compile;
use crate::spec::SpecService;
use crate::types::{
    AskEvent, AskStream, AttachmentMeta, CodeLayer, CodeText, CodeView, ConversationView, ItemRef,
    LlmMessage, LlmStep, Progress, ToolCall, ToolResult, ToolSpec,
};

/// 도구 호출 상한 — 설정이 아니라 상수다 (사용자 결정 2026-09-22)
const ASK_MAX_CALLS: usize = 8;
/// 초 — 호출 사이에서만 본다
const ASK_TIME_LIMIT: f64 = 120.0;
/// 한 대화에서 모델에 싣는 앞 턴 수 — 파이썬 `LLM_MAX_TURNS` 기본값(설정 키는 다섯뿐)
const LLM_MAX_TURNS: i64 = 10;
/// 부르는 것·불리는 곳 각각 시작 맥락에 싣는 상한
const ASK_CODE_NEIGHBORS: usize = 20;
/// find_code 한 번에 싣는 상한 (#302)
const FIND_FUNCTIONS: usize = 30;
const FIND_CALLERS: usize = 10;
/// 이름이 여럿일 때 「없음」에 싣는 후보 상한 (#286)
const READ_CANDIDATES: usize = 10;

/// 도구 아홉 — 설명은 SYNC-API-002 도구 설명 원문 (파이썬 `_ASK_TOOLS`)
static ASK_TOOLS: LazyLock<Vec<ToolSpec>> = LazyLock::new(|| {
    let raw: Vec<Value> = serde_json::from_str(ASK_TOOLS_JSON).expect("도구 설명 JSON");
    raw.into_iter()
        .map(|t| ToolSpec {
            name: leak(t["name"].as_str().unwrap_or("")),
            description: leak(t["description"].as_str().unwrap_or("")),
            parameters: t["parameters"].clone(),
        })
        .collect()
});

fn leak(s: &str) -> &'static str {
    Box::leak(s.to_string().into_boxed_str())
}

// ── 글 채우기 · 파이썬 꼴

/// 파이썬 `str.format(**kw)` — `{이름}`을 한 번에 바꾼다(넣은 글 안의 `{…}`는 다시 안 본다)
fn fill(template: &str, kw: &[(&str, &str)]) -> String {
    let mut out = String::with_capacity(template.len());
    let mut rest = template;
    while let Some(i) = rest.find('{') {
        out.push_str(&rest[..i]);
        let after = &rest[i + 1..];
        match after.find('}') {
            Some(j) => {
                let name = &after[..j];
                match kw.iter().find(|(k, _)| *k == name) {
                    Some((_, v)) => out.push_str(v),
                    None => {
                        out.push('{');
                        out.push_str(name);
                        out.push('}');
                    }
                }
                rest = &after[j + 1..];
            }
            None => {
                out.push_str(&rest[i..]);
                rest = "";
            }
        }
    }
    out.push_str(rest);
    out
}

/// 파이썬 `str(x)` — 모델이 준 인자 값을 글자로
fn py_str(v: Option<&Value>, default: &str) -> String {
    match v {
        None => default.to_string(),
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) => "None".into(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Bool(false)) => "False".into(),
        Some(Value::Number(n)) => n.to_string(),
        Some(other) => py_repr(other),
    }
}

/// 파이썬 `repr`(목록·사전) — 글자는 작은따옴표
fn py_repr(v: &Value) -> String {
    match v {
        Value::String(s) => crate::pycompat::repr::repr(s),
        Value::Array(a) => format!("[{}]", a.iter().map(py_repr).collect::<Vec<_>>().join(", ")),
        Value::Object(m) => format!(
            "{{{}}}",
            m.iter()
                .map(|(k, v)| format!("{}: {}", crate::pycompat::repr::repr(k), py_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        other => py_str(Some(other), ""),
    }
}

/// 파이썬 `int(x or 0)` — 정수·정수 글자·실수(버림)·참거짓. 그 밖은 `internal`(파이썬 `ValueError`)
fn py_int(v: Option<&Value>) -> Result<i64, Problem> {
    let bad = || Problem::Internal {
        log: "attachment_id가 정수가 아니다".into(),
    };
    match v {
        None | Some(Value::Null) | Some(Value::Bool(false)) => Ok(0),
        Some(Value::Bool(true)) => Ok(1),
        Some(Value::Number(n)) => n
            .as_i64()
            .or_else(|| n.as_f64().map(|f| f.trunc() as i64))
            .ok_or_else(bad),
        Some(Value::String(s)) if s.is_empty() => Ok(0),
        Some(Value::String(s)) => strip(s).replace('_', "").parse().map_err(|_| bad()),
        Some(Value::Array(a)) if a.is_empty() => Ok(0),
        Some(Value::Object(o)) if o.is_empty() => Ok(0),
        Some(_) => Err(bad()),
    }
}

/// 파이썬 참거짓 — 비면 거짓
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn err(text: &str, extra: &[(&str, Value)]) -> ToolResult {
    let mut m = Map::new();
    m.insert("error".into(), Value::from(text));
    for (k, v) in extra {
        m.insert((*k).to_string(), v.clone());
    }
    ToolResult {
        target: None,
        text: dumps(&Value::Object(m), false),
    }
}

fn ok(target: Option<String>, data: &Value) -> ToolResult {
    ToolResult {
        target,
        text: dumps(data, false),
    }
}

/// 참조 하나 → 짧은 JSON (파이썬 `_ref_json`)
fn ref_json(r: &ItemRef) -> Map<String, Value> {
    let mut m = Map::new();
    if r.is_missing || (r.doc_id.is_none() && r.item_id.is_none()) {
        m.insert("raw_target".into(), Value::from(r.raw_target.as_str()));
        m.insert("note".into(), Value::from("아직 없음"));
    } else if r.item_id.is_none() {
        m.insert("doc_id".into(), Value::from(r.doc_id.clone()));
        m.insert("title".into(), Value::from(r.display_name.clone()));
    } else {
        m.insert(
            "id".into(),
            Value::from(format!(
                "{}#{}",
                r.doc_id.as_deref().unwrap_or("None"),
                r.item_id.as_deref().unwrap_or("None")
            )),
        );
        m.insert("name".into(), Value::from(r.display_name.clone()));
    }
    m
}

/// 질문 맥락의 층 표기 — `층 리포지토리 · SYNC-DOM-002 4장 · SYNC-DOM-003` (파이썬 `_layer_line`)
fn layer_line(layer: &CodeLayer) -> String {
    let mut parts = vec![format!("층 {}", layer.name)];
    for s in &layer.specs {
        let p = strip(&format!("{} {}", s.ref_.as_deref().unwrap_or(""), s.note)).to_string();
        if !p.is_empty() {
            parts.push(p);
        }
    }
    parts.join(" · ")
}

/// code_graph 도구의 JSON — 코드 탭과 같은 대조를 짧은 키로 (파이썬 `_code_view_json`)
fn code_view_json(v: &CodeView) -> Value {
    let mut out = Map::new();
    out.insert(
        "graph".into(),
        match &v.graph {
            Some(g) => json!({"commit": g.commit_hash.as_deref().unwrap_or("").chars().take(7).collect::<String>(),
                "source": g.source, "error": g.error}),
            None => Value::Null,
        },
    );
    out.insert(
        "item".into(),
        Value::from(match &v.item_id {
            Some(i) if !i.is_empty() => format!("{}#{i}", v.doc_id),
            _ => v.doc_id.clone(),
        }),
    );
    out.insert("is_ms".into(), Value::from(v.is_ms));
    out.insert("missing".into(), Value::from(v.missing));
    if let Some(f) = &v.function {
        out.insert(
            "function".into(),
            json!({
                "qual": f.qual, "file": f.file, "line": f.line, "end": f.end,
                "calls": f.calls.iter().map(|c| json!({"id": c.ms_id, "status": c.status,
                    "qual": c.qual, "file": c.file, "line": c.line})).collect::<Vec<_>>(),
                "callers": f.callers.iter().map(|c| json!({"id": c.ms_id, "qual": c.qual,
                    "file": c.file, "line": c.line})).collect::<Vec<_>>(),
            }),
        );
    }
    out.insert(
        "functions".into(),
        Value::Array(
            v.functions
                .iter()
                .map(|b| {
                    json!({"id": b.ms_id, "qual": b.qual, "file": b.file, "line": b.line,
                        "same": b.same, "code_only": b.code_only, "spec_only": b.spec_only})
                })
                .collect(),
        ),
    );
    Value::Object(out)
}

// ── 코드 찾기·읽기

/// find_code — 그래프 함수 중 이름·qual·파일이 query를 품은 것과 그 불리는 곳. 그래프가 없으면 없음 (파이썬 `_find_code`)
async fn find_code(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    query: &str,
    user: &UserRow,
) -> Result<Option<Value>, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let Some(row) = CodeGraphService { db: &mut *db }.get(project.id).await? else {
        return Ok(None);
    };
    let g = &row.graph;
    let needle = query.to_lowercase();
    let mut hits: Vec<&syncdoc_codegraph::Function> = g
        .functions
        .iter()
        .filter(|f| {
            !needle.is_empty()
                && (f.qual.to_lowercase().contains(&needle)
                    || f.name.to_lowercase().contains(&needle)
                    || f.file.to_lowercase().contains(&needle))
        })
        .collect();
    hits.sort_by(|a, b| {
        let exact = |f: &syncdoc_codegraph::Function| {
            !(f.qual.to_lowercase() == needle || f.name.to_lowercase() == needle)
        };
        (exact(a), &a.file, a.line).cmp(&(exact(b), &b.file, b.line))
    });
    let layer_of = if hits.is_empty() {
        HashMap::new()
    } else {
        layers_of(&mut *db, project.id, g).await?
    };
    let fns = by_key(g);
    let mut callers: HashMap<&str, Vec<&str>> = HashMap::new();
    for c in &g.calls {
        if fns.contains_key(c.0.as_str()) {
            let cs = callers.entry(c.1.as_str()).or_default();
            if !cs.contains(&c.0.as_str()) {
                cs.push(c.0.as_str());
            }
        }
    }
    let mut out = Vec::new();
    for f in hits.iter().take(FIND_FUNCTIONS) {
        let cs = callers.get(f.key.as_str()).cloned().unwrap_or_default();
        let mut item = Map::new();
        item.insert("qual".into(), Value::from(f.qual.as_str()));
        item.insert("file".into(), Value::from(f.file.as_str()));
        item.insert("line".into(), Value::from(f.line));
        match f.item.as_deref().filter(|i| !i.is_empty()) {
            Some(it) => {
                item.insert("item".into(), Value::from(it));
            }
            None => {
                if let Some(l) = layer_of.get(&f.key) {
                    item.insert("layer".into(), Value::from(layer_line(l)));
                }
            }
        }
        item.insert(
            "callers".into(),
            Value::Array(
                cs.iter()
                    .take(FIND_CALLERS)
                    .filter_map(|k| fns.get(k))
                    .map(|c| json!({"qual": c.qual, "file": c.file, "line": c.line}))
                    .collect(),
            ),
        );
        item.insert(
            "more_callers".into(),
            Value::from(cs.len().saturating_sub(FIND_CALLERS)),
        );
        out.push(Value::Object(item));
    }
    let mut result = Map::new();
    result.insert("query".into(), Value::from(query));
    result.insert("total".into(), Value::from(hits.len()));
    result.insert("functions".into(), Value::Array(out));
    result.insert(
        "more".into(),
        Value::from(hits.len().saturating_sub(FIND_FUNCTIONS)),
    );
    if hits.is_empty() {
        result.insert(
            "hint".into(),
            Value::from("맞는 함수가 없다 — 더 짧은 이름이나 파일 이름으로 다시 찾아라"),
        );
    }
    Ok(Some(Value::Object(result)))
}

/// `경로:줄`의 함수 — 그 줄에서 시작하는 함수, 아니면 그 줄을 품은 함수. 함수 밖이면 없음 (파이썬 `_function_at`)
fn function_at<'g>(
    functions: &'g [syncdoc_codegraph::Function],
    path: &str,
    line: i64,
) -> Option<&'g syncdoc_codegraph::Function> {
    let mut here: Vec<&syncdoc_codegraph::Function> = functions
        .iter()
        .filter(|g| g.file == path && g.line <= line)
        .collect();
    here.sort_by_key(|a| std::cmp::Reverse(a.line));
    here.into_iter().find(|g| {
        let last = g
            .end
            .filter(|e| *e != 0)
            .or_else(|| next_start(functions, g));
        last.is_none_or(|l| line <= l)
    })
}

/// 파이썬 `int()` — 유니코드 십진 숫자까지
fn decimal(s: &str) -> Option<i64> {
    let mut n: i64 = 0;
    for c in s.chars() {
        let d = crate::pycompat::chars::decimal_value(c)?;
        n = n.checked_mul(10)?.checked_add(i64::from(d))?;
    }
    Some(n)
}

static RANGE: LazyLock<Regex> = LazyLock::new(|| compile(r"^(.+?):(\d+)[-–](\d+)$"));
static AT: LazyLock<Regex> = LazyLock::new(|| compile(r"^(.+?):(\d+)$"));

/// read_code의 결과 — 본문 · 그래프 없음 · 없음(이름이 여럿이면 후보)
enum ReadCode {
    Text(CodeText),
    NoGraph,
    Missing(Option<Vec<String>>),
}

/// read_code의 target → 파일·줄 범위 → `CodeGraphService.read` (파이썬 `_read_code`)
async fn read_code(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    target: &str,
    user: &UserRow,
) -> Result<ReadCode, Problem> {
    let (project, repo) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let mut svc = CodeGraphService { db: &mut *db };
    let Some(row) = svc.get(project.id).await? else {
        return Ok(ReadCode::NoGraph);
    };
    let fns = &row.graph.functions;
    let mut f: Option<&syncdoc_codegraph::Function> = None;
    let (mut path, mut start, mut end): (String, i64, Option<i64>) = (target.to_string(), 1, None);
    if target.contains('#') {
        let spec = std::collections::BTreeMap::from([(
            target.to_string(),
            std::collections::BTreeSet::new(),
        )]);
        let d = syncdoc_codegraph::graph::compare(&row.graph, &spec);
        f = d
            .first()
            .and_then(|d| d.function.as_deref())
            .and_then(|k| fns.iter().find(|x| x.key == k));
        if f.is_none() {
            f = syncdoc_codegraph::graph::item_function(&row.graph, target);
        }
        if f.is_none() {
            return Ok(ReadCode::Missing(None));
        }
    } else {
        let mut same: Vec<&syncdoc_codegraph::Function> =
            fns.iter().filter(|x| x.qual == target).collect();
        if same.is_empty() && !target.contains('/') && !target.contains(':') {
            same = fns.iter().filter(|x| x.name == target).collect();
        }
        if same.len() > 1 {
            let cands = same
                .iter()
                .take(READ_CANDIDATES)
                .map(|x| format!("{}:{} {}", x.file, x.line, x.qual))
                .collect();
            return Ok(ReadCode::Missing(Some(cands)));
        }
        if let Some(x) = same.first() {
            f = Some(x);
        } else if let Some(m) = RANGE.captures(target)
            && let (Some(a), Some(b)) = (decimal(&m[2]), decimal(&m[3]))
        {
            (path, start, end) = (m[1].to_string(), a, Some(b));
        } else if let Some(m) = AT.captures(target)
            && let Some(a) = decimal(&m[2])
        {
            (path, start) = (m[1].to_string(), a);
            f = function_at(fns, &path, start);
        }
    }
    if let Some(f) = f {
        (path, start) = (f.file.clone(), f.line);
        end = Some(
            f.end
                .filter(|e| *e != 0)
                .or_else(|| next_start(fns, f).filter(|e| *e != 0))
                .unwrap_or(start + 59),
        );
    }
    match svc
        .read(
            &repos.git,
            project.id,
            std::path::Path::new(&repo.remote_url),
            &path,
            start,
            end,
        )
        .await
    {
        Ok(t) => Ok(ReadCode::Text(t)),
        Err(Problem::NotFound { .. }) => Ok(ReadCode::Missing(None)),
        Err(e) => Err(e),
    }
}

/// SYNC-MS-018#queries.ask_tool
///
/// 도구 하나 실행. 없음·삭제·다른 프로젝트·인자 빠짐은 예외가 아니라 `{"error": …}` 글이다 — 모델이 되짚게 한다.
/// 그 밖의 예외는 전파한다(→ error 이벤트). 소유 검사는 get_owned
pub async fn ask_tool(
    db: &mut PgConnection,
    repos: &ServerRepos,
    name: &str,
    args: &Map<String, Value>,
    code: &str,
    user: &UserRow,
    conversation_id: i32,
) -> Result<ToolResult, Problem> {
    let Some(spec) = ASK_TOOLS.iter().find(|t| t.name == name) else {
        return Ok(err(&format!("모르는 도구 {name}"), &[]));
    };
    let required: Vec<&str> = spec.parameters["required"]
        .as_array()
        .map(|a| a.iter().filter_map(Value::as_str).collect())
        .unwrap_or_default();
    let missing: Vec<&str> = required
        .iter()
        .copied()
        .filter(|k| !args.contains_key(*k))
        .collect();
    if !missing.is_empty() {
        return Ok(err(&format!("인자 {}가 없다", missing.join("·")), &[]));
    }
    let doc_id = py_str(args.get("doc_id"), "");
    let has_doc = spec.parameters["properties"].get("doc_id").is_some();
    if has_doc && doc_id.split('-').next().unwrap_or("") != code {
        // 다른 프로젝트는 소유해도 없는 것과 같다
        return Ok(err("없음", &[("doc_id", Value::from(doc_id.as_str()))]));
    }
    let item_id = py_str(args.get("item_id"), "").replace('~', "/");
    // 남의 프로젝트는 글이 아니라 not-found 전파(→ error 이벤트)
    ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let run = run_tool(
        db,
        repos,
        name,
        args,
        code,
        user,
        conversation_id,
        &doc_id,
        &item_id,
    )
    .await;
    match run {
        Err(Problem::NotFound { resource, id }) => Ok(err(
            "없음",
            &[
                ("hint", Value::from(ASK_MISSING_HINT)),
                ("resource", Value::from(resource)),
                ("id", id),
            ],
        )),
        Err(Problem::NotFoundWithItems { resource, id, .. }) => Ok(err(
            "없음",
            &[
                ("hint", Value::from(ASK_MISSING_HINT)),
                ("resource", Value::from(resource)),
                ("id", Value::from(id)),
            ],
        )),
        Err(Problem::ItemDeleted { .. }) => Ok(err(
            "삭제된 항목",
            &[
                ("doc_id", Value::from(doc_id.as_str())),
                ("item_id", Value::from(item_id.as_str())),
            ],
        )),
        other => other,
    }
}

/// `ask_tool`의 도구별 몸통 — 없음·삭제는 부르는 쪽이 글로 접는다
#[allow(clippy::too_many_arguments)]
async fn run_tool(
    db: &mut PgConnection,
    repos: &ServerRepos,
    name: &str,
    args: &Map<String, Value>,
    code: &str,
    user: &UserRow,
    conversation_id: i32,
    doc_id: &str,
    item_id: &str,
) -> Result<ToolResult, Problem> {
    let no_graph = || {
        err(
            "코드 그래프 없음",
            &[("hint", Value::from("코드를 push하면 서버가 만든다"))],
        )
    };
    match name {
        "get_item" => {
            let v = item_view(&mut *db, repos, doc_id, item_id, user).await?;
            let data = json!({"doc_id": v.doc_id, "item_id": v.item_id, "display_name": v.display_name,
                "doc_status": v.doc_status, "doc_version_no": v.doc_version_no, "body": v.body});
            Ok(ok(Some(format!("{doc_id}#{}", v.item_id)), &data))
        }
        "get_references" => {
            let r = item_references_view(&mut *db, repos, doc_id, item_id, user).await?;
            let mut status: HashMap<String, String> = HashMap::new();
            for x in &r.upstream {
                if let (None, Some(did)) =
                    (&x.item_id, x.doc_id.as_deref().filter(|d| !d.is_empty()))
                {
                    match (SpecService { db: &mut *db }).get_document(did).await {
                        Ok(d) => {
                            status.insert(did.to_string(), d.summary.status);
                        }
                        Err(Problem::NotFound { .. }) => {}
                        Err(e) => return Err(e),
                    }
                }
            }
            let up: Vec<Value> = r
                .upstream
                .iter()
                .map(|x| {
                    let mut m = ref_json(x);
                    if let Some(Value::String(d)) = m.get("doc_id").cloned() {
                        m.insert("status".into(), Value::from(status.get(&d).cloned()));
                    }
                    Value::Object(m)
                })
                .collect();
            let down: Vec<Value> = r
                .downstream
                .iter()
                .map(|x| Value::Object(ref_json(x)))
                .collect();
            Ok(ok(
                Some(format!("{doc_id}#{item_id}")),
                &json!({"upstream": up, "downstream": down}),
            ))
        }
        "item_chain" => {
            let c = item_chain(&mut *db, repos, doc_id, item_id, user).await?;
            let rows: Vec<Value> = c
                .rows
                .iter()
                .map(|row| {
                    let items: Vec<Value> = row
                        .items
                        .iter()
                        .map(|ci| {
                            let mut m = ref_json(&ci.ref_);
                            m.insert("role".into(), Value::from(ci.role.as_str()));
                            m.insert("status".into(), Value::from(ci.status.as_str()));
                            Value::Object(m)
                        })
                        .collect();
                    json!({"stage": row.stage, "doc_type": row.doc_type, "items": items})
                })
                .collect();
            Ok(ok(
                Some(format!("{doc_id}#{item_id}")),
                &json!({"item": Value::Object(ref_json(&c.item)), "rows": rows}),
            ))
        }
        "list_documents" => {
            let docs = document_list(&mut *db, repos, code, user, None, None).await?;
            let ids: Vec<i32> = docs.iter().map(|d| d.id).collect();
            let titles = SpecService { db: &mut *db }
                .describe_documents(&ids)
                .await?;
            let data: Vec<Value> = docs
                .iter()
                .map(|d| {
                    json!({"doc_id": d.doc_id, "stage": d.stage, "doc_type": d.doc_type,
                        "title": titles.get(&d.id).map_or("", |t| t.title.as_str()),
                        "status": d.status, "version_no": d.current_version_no})
                })
                .collect();
            Ok(ok(None, &Value::Array(data)))
        }
        "read_attachment" => {
            // 이 대화의 글자·PDF 첨부. 이미지·남의 첨부는 「없음」
            let att_id = py_int(args.get("attachment_id"))?;
            let mut svc = ConversationService {
                db: &mut *db,
                repos,
            };
            let text = svc.attachment_text(conversation_id, att_id).await?;
            let row = match (&text, i32::try_from(att_id)) {
                (Some(_), Ok(id)) => crate::conversation::repo::attachment(&mut *db, id).await?,
                _ => None,
            };
            match (text, row) {
                (Some(t), Some(a)) => Ok(ok(
                    Some(format!("첨부:{}", a.name)),
                    &json!({"attachment_id": att_id, "name": a.name, "mime": a.mime, "text": t}),
                )),
                _ => Ok(err(
                    "없음",
                    &[
                        ("attachment_id", Value::from(att_id)),
                        ("hint", Value::from("이미지는 붙인 질문에 이미 보였다")),
                    ],
                )),
            }
        }
        "code_graph" => {
            let v = code_view(&mut *db, repos, doc_id, Some(item_id), user).await?;
            if v.graph.is_none() {
                return Ok(no_graph());
            }
            Ok(ok(
                Some(format!("코드:{doc_id}#{item_id}")),
                &code_view_json(&v),
            ))
        }
        "find_code" => {
            let query = strip(&py_str(args.get("query"), "")).to_string();
            match find_code(&mut *db, repos, code, &query, user).await? {
                None => Ok(no_graph()),
                Some(found) => Ok(ok(Some(format!("코드검색:{query}")), &found)),
            }
        }
        "read_code" => {
            let target = strip(&py_str(args.get("target"), "")).to_string();
            match read_code(&mut *db, repos, code, &target, user).await? {
                ReadCode::NoGraph => Ok(no_graph()),
                ReadCode::Missing(cands) => {
                    let mut extra = vec![
                        ("target", Value::from(target.as_str())),
                        ("hint", Value::from(READ_CODE_HINT)),
                    ];
                    if let Some(c) = cands {
                        extra.push(("candidates", Value::from(c)));
                    }
                    Ok(err("없음", &extra))
                }
                ReadCode::Text(t) => {
                    let numbered = t
                        .text
                        .split('\n')
                        .enumerate()
                        .map(|(i, ln)| format!("{}: {ln}", t.start + i as i64))
                        .collect::<Vec<_>>()
                        .join("\n");
                    let data = json!({"path": t.path, "start": t.start, "end": t.end,
                        "commit": t.commit_hash.chars().take(7).collect::<String>(),
                        "truncated": t.truncated, "text": numbered});
                    Ok(ok(
                        Some(format!("코드:{}:{}-{}", t.path, t.start, t.end)),
                        &data,
                    ))
                }
            }
        }
        _ => {
            // get_document
            let d = document_view(&mut *db, repos, doc_id, user).await?;
            let title = title_of(&mut *db, doc_id).await?;
            let items: Vec<Value> = d
                .items
                .iter()
                .map(|i| json!({"item_id": i.item_id, "display_name": i.display_name}))
                .collect();
            Ok(ok(
                Some(doc_id.to_string()),
                &json!({"doc_id": d.summary.doc_id, "title": title, "status": d.summary.status,
                    "version_no": d.summary.current_version_no, "items": items, "body": d.body}),
            ))
        }
    }
}

// ── 답 속 참조 (#290)

/// 문서 ID → 항목 ID들(긴 것부터). 답 속 참조를 맞출 재료 (파이썬 `_ref_index`)
async fn ref_index(
    db: &mut PgConnection,
    project_id: i32,
) -> Result<HashMap<String, Vec<String>>, Problem> {
    let mut out: HashMap<String, Vec<String>> = HashMap::new();
    let briefs = SpecService { db }.list_items_by_project(project_id).await?;
    for b in briefs {
        let items = out.entry(b.doc_id).or_default();
        if let Some(i) = b.item_id.filter(|i| !i.is_empty()) {
            items.push(i);
        }
    }
    for items in out.values_mut() {
        items.sort_by_key(|x| std::cmp::Reverse(x.chars().count()));
    }
    Ok(out)
}

fn ascii_word(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_'
}

/// 맨 문서 ID 꼴 `[A-Z]{1,4}-[A-Z]+-\d{3}`이 `at`에서 시작하면 그 끝 — 앞뒤 보기는 부르는 쪽 (파이썬 `_ANS_DOC`의 가운데)
fn doc_id_at(s: &str, at: usize) -> Option<usize> {
    let mut it = s[at..].char_indices().peekable();
    let upper = |it: &mut std::iter::Peekable<std::str::CharIndices>| {
        let mut n = 0;
        while it.peek().is_some_and(|(_, c)| c.is_ascii_uppercase()) {
            it.next();
            n += 1;
        }
        n
    };
    let n = upper(&mut it);
    if !(1..=4).contains(&n) || it.next().map(|(_, c)| c) != Some('-') {
        return None;
    }
    if upper(&mut it) == 0 || it.next().map(|(_, c)| c) != Some('-') {
        return None;
    }
    for _ in 0..3 {
        match it.next() {
            Some((_, c)) if crate::pycompat::chars::is_decimal(c) => {}
            _ => return None,
        }
    }
    let end = it.peek().map_or(s.len(), |(i, _)| at + i);
    if s[end..].chars().next().is_some_and(ascii_word) {
        return None;
    }
    Some(end)
}

/// 바꾸지 않는 조각 — 코드블록 · 인라인 코드 · 이미 있는 `[[…]]` (파이썬 `_ANS_KEEP.split`, 홀수 자리가 그것)
fn keep_split(text: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut last = 0;
    let mut i = 0;
    while i < text.len() {
        let rest = &text[i..];
        let found = if let Some(r) = rest.strip_prefix("```")
            && let Some(j) = r.find("```")
        {
            Some(3 + j + 3)
        } else if let Some(r) = rest.strip_prefix('`') {
            match r.find(['`', '\n']) {
                Some(j) if r[j..].starts_with('`') => Some(1 + j + 1),
                _ => None,
            }
        } else if let Some(r) = rest.strip_prefix("[[") {
            match r.find(']') {
                Some(j) if r[j..].starts_with("]]") => Some(2 + j + 2),
                _ => None,
            }
        } else {
            None
        };
        match found {
            Some(len) => {
                out.push(&text[last..i]);
                out.push(&text[i..i + len]);
                i += len;
                last = i;
            }
            None => i += rest.chars().next().map_or(1, char::len_utf8),
        }
    }
    out.push(&text[last..]);
    out
}

/// 맨 `문서ID#항목ID` → `[[…]]`(그 문서의 가장 긴 실제 항목까지)
fn link(part: &str, index: &HashMap<String, Vec<String>>) -> String {
    let mut res = String::new();
    let mut pos = 0;
    let mut i = 0;
    while i < part.len() {
        let prev = part[..i].chars().next_back();
        let ok_before = prev.is_none_or(|c| !(ascii_word(c) || matches!(c, '#' | '/' | '[' | '-')));
        let found = if ok_before { doc_id_at(part, i) } else { None };
        let Some(mut end) = found else {
            i += part[i..].chars().next().map_or(1, char::len_utf8);
            continue;
        };
        let start = i;
        i = end; // 다음 찾기는 이 끝에서
        if start < pos {
            continue; // 앞 항목 ID가 먹은 자리
        }
        let doc = &part[start..end];
        let mut reference = doc.to_string();
        if part[end..].starts_with('#') {
            let rest = &part[end + 1..];
            let mut it = index.get(doc).and_then(|items| {
                items.iter().find(|x| {
                    rest.starts_with(x.as_str())
                        && !rest[x.len()..].chars().next().is_some_and(ascii_word)
                })
            });
            let tail;
            if it.is_none() {
                // 맞는 항목이 없다 — 영문·숫자 규칙으로 자르고 없는 참조가 된다
                let n = rest
                    .find(|c: char| !(c.is_ascii_alphanumeric() || "_./{}~-".contains(c)))
                    .unwrap_or(rest.len());
                tail = rest[..n].trim_end_matches('.').to_string();
                it = Some(&tail);
            }
            if let Some(x) = it.filter(|x| !x.is_empty()) {
                reference = format!("{doc}#{x}");
                end += 1 + x.len();
            }
        }
        res.push_str(&part[pos..start]);
        res.push_str(&format!("[[{reference}]]"));
        pos = end;
    }
    res.push_str(&part[pos..]);
    res
}

/// 답 속 맨 `문서ID#항목ID` → `[[…]]`, 없는 참조 목록 (파이썬 `_answer_links`)
fn answer_links(text: &str, index: &HashMap<String, Vec<String>>) -> (String, Vec<String>) {
    let out: String = keep_split(text)
        .into_iter()
        .enumerate()
        .map(|(i, p)| {
            if i % 2 == 1 {
                p.to_string()
            } else {
                link(p, index)
            }
        })
        .collect();
    let mut missing: Vec<String> = Vec::new();
    for (i, p) in keep_split(&out).into_iter().enumerate() {
        if i % 2 == 0 || !p.starts_with("[[") {
            continue;
        }
        let raw = &p[2..p.len() - 2];
        let (doc, it) = raw.split_once('#').unwrap_or((raw, ""));
        let absent = match index.get(doc) {
            None => true,
            Some(items) => !it.is_empty() && !items.iter().any(|x| x == it),
        };
        if !doc.is_empty() && absent && !missing.iter().any(|m| m == raw) {
            missing.push(raw.to_string());
        }
    }
    (out, missing)
}

// ── 시작 맥락

/// 시작 맥락의 [첨부] 줄 — 이름·종류·크기만 (파이썬 `_attachment_lines`)
fn attachment_lines(metas: &[AttachmentMeta]) -> String {
    if metas.is_empty() {
        return String::new();
    }
    let mut lines = vec!["[첨부]".to_string()];
    for m in metas {
        let kind = if m.mime.starts_with("image/") {
            "이미지 — 붙인 질문에 보인다"
        } else {
            "read_attachment로 읽는다"
        };
        lines.push(format!(
            "{} {} ({}, {}B) — {kind}",
            m.id, m.name, m.mime, m.size
        ));
    }
    lines.join("\n")
}

/// 시작 맥락 — 제목·상태·버전·항목 ID·이름. 본문은 안 싣는다 (파이썬 `_start_context`)
async fn start_context(
    db: &mut PgConnection,
    doc_id: &str,
    item_id: Option<&str>,
    attachments: &str,
) -> Result<String, Problem> {
    let mut spec = SpecService { db };
    let d = spec.get_document(doc_id).await?;
    let refs = spec.describe_documents(&[d.summary.id]).await?;
    let title = refs
        .get(&d.summary.id)
        .map_or_else(|| doc_id.to_string(), |r| r.title.clone());
    let mut viewing = String::new();
    if let Some(item) = item_id {
        let item = item.replace('~', "/");
        let Some(it) = d.items.iter().find(|i| i.item_id == item) else {
            return Err(Problem::NotFound {
                resource: "item".into(),
                id: Value::from(format!("{doc_id}#{item}")),
            });
        };
        viewing = rstrip(&format!(
            "[지금 보는 항목] {} {}",
            it.item_id,
            it.display_name.as_deref().unwrap_or("")
        ))
        .to_string();
    }
    let items = d
        .items
        .iter()
        .map(|i| {
            rstrip(&format!(
                "{} {}",
                i.item_id,
                i.display_name.as_deref().unwrap_or("")
            ))
            .to_string()
        })
        .collect::<Vec<_>>()
        .join("\n");
    let items = if items.is_empty() {
        "(없음)".to_string()
    } else {
        items
    };
    Ok(fill(
        ASK_SYSTEM,
        &[
            ("doc_id", doc_id),
            ("title", &title),
            ("status", &d.summary.status),
            ("version_no", &d.summary.current_version_no.to_string()),
            ("items", &items),
            ("viewing", &viewing),
            ("attachments", attachments),
        ],
    ))
}

/// ask_code의 시작 맥락 — 문서 목록·그래프 머리·고른 함수 블록. 본문은 안 싣는다 (파이썬 `_code_context`)
async fn code_context(
    db: &mut PgConnection,
    project_id: i32,
    key: Option<&str>,
    attachments: &str,
) -> Result<String, Problem> {
    let mut spec = SpecService { db: &mut *db };
    let rows = spec.list_by_project(project_id, None, None, None).await?;
    let ids: Vec<i32> = rows.iter().map(|d| d.id).collect();
    let titles = spec.describe_documents(&ids).await?;
    let docs = rows
        .iter()
        .map(|d| {
            rstrip(&format!(
                "{} {} · {}",
                d.doc_id,
                titles.get(&d.id).map_or("", |t| t.title.as_str()),
                d.status
            ))
            .to_string()
        })
        .collect::<Vec<_>>()
        .join("\n");
    let docs = if docs.is_empty() {
        "(없음)".to_string()
    } else {
        docs
    };
    let Some(row) = CodeGraphService { db: &mut *db }.get(project_id).await? else {
        if let Some(k) = key {
            return Err(Problem::NotFound {
                resource: "function".into(),
                id: Value::from(k),
            });
        }
        return Ok(fill(
            ASK_CODE_SYSTEM,
            &[
                (
                    "graph_line",
                    "[코드 그래프] 없음 — 코드를 push하면 만들어진다",
                ),
                ("docs", &docs),
                ("viewing", "[보는 것] 그래프 전체"),
                ("attachments", attachments),
            ],
        ));
    };
    let g = &row.graph;
    let graph_line = format!(
        "[코드 그래프] 커밋 {} · 함수 {} · 호출 {}",
        row.commit_hash
            .as_deref()
            .unwrap_or("")
            .chars()
            .take(7)
            .collect::<String>(),
        g.functions.len(),
        g.calls.len()
    );
    let viewing = match key {
        None => "[보는 것] 그래프 전체".to_string(),
        Some(key) => {
            let fns = by_key(g);
            let Some(f) = fns.get(key) else {
                return Err(Problem::NotFound {
                    resource: "function".into(),
                    id: Value::from(key),
                });
            };
            let diffs = diffs_of(&mut *db, project_id, g).await?;
            let mut ms_of = HashMap::new();
            for d in diffs.values() {
                if let Some(k) = d.function.as_deref() {
                    ms_of.insert(k.to_string(), d.clone());
                }
            }
            let layer_of = layers_of(&mut *db, project_id, g).await?;
            let item_of = |k: &str| -> String {
                match ms_of.get(k) {
                    None => {
                        // 대조 없는 함수 — API·UI 항목이면 그 항목만, 그것도 없으면 층
                        if let Some(it) = fns
                            .get(k)
                            .and_then(|x| x.item.as_deref())
                            .filter(|i| !i.is_empty())
                        {
                            return format!("항목 {it}");
                        }
                        layer_of
                            .get(k)
                            .map_or_else(|| "항목 없음".to_string(), layer_line)
                    }
                    Some(d) => {
                        let st = if !d.code_only.is_empty() {
                            "code_only"
                        } else if !d.spec_only.is_empty() {
                            "spec_only"
                        } else {
                            "same"
                        };
                        format!("항목 {} ({st})", d.ms_id)
                    }
                }
            };
            let line_of = |k: &str| -> String {
                let x = fns[k];
                format!("{} · {}:{} · {}", x.qual, x.file, x.line, item_of(k))
            };
            let calls: Vec<&str> = g
                .calls
                .iter()
                .filter(|c| c.0 == key && fns.contains_key(c.1.as_str()))
                .map(|c| c.1.as_str())
                .collect();
            let callers: Vec<&str> = g
                .calls
                .iter()
                .filter(|c| c.1 == key && fns.contains_key(c.0.as_str()))
                .map(|c| c.0.as_str())
                .collect();
            let end = match f.end.filter(|e| *e != 0) {
                Some(e) => format!("-{e}"),
                None => String::new(),
            };
            let mut lines = vec![format!(
                "[보는 함수] {} · {}:{}{end} · {}",
                f.qual,
                f.file,
                f.line,
                item_of(key)
            )];
            for (title, ks) in [("부르는 것", &calls), ("불리는 곳", &callers)] {
                lines.push(format!("[{title} {}]", ks.len()));
                lines.extend(ks.iter().take(ASK_CODE_NEIGHBORS).map(|k| line_of(k)));
                if ks.len() > ASK_CODE_NEIGHBORS {
                    lines.push(format!("… {}개 더", ks.len() - ASK_CODE_NEIGHBORS));
                }
            }
            lines.join("\n")
        }
    };
    Ok(fill(
        ASK_CODE_SYSTEM,
        &[
            ("graph_line", &graph_line),
            ("docs", &docs),
            ("viewing", &viewing),
            ("attachments", attachments),
        ],
    ))
}

// ── 루프

/// 루프에 넘길 것 — 따로 띄운 작업이 쥔다
struct Loop {
    pool: PgPool,
    repos: Arc<ServerRepos>,
    llm: Llm,
    user: UserRow,
    system: String,
    code: String,
    conversation_id: i32,
    turn_id: i32,
    history: Vec<LlmMessage>,
    question: String,
    images: Vec<(String, Vec<u8>)>,
    start: AskEvent,
    place: String,
}

/// 실패의 이름 — `reason`이 있으면 그것, 없으면 파이썬 예외 종류 이름
fn failure_name(p: &Problem) -> String {
    match p {
        Problem::LlmUnavailable { reason } => reason.clone(),
        Problem::NotFound { .. } | Problem::NotFoundWithItems { .. } => "NotFound".into(),
        Problem::ItemDeleted { .. } => "ItemDeleted".into(),
        Problem::LlmNotConfigured => "LlmNotConfigured".into(),
        Problem::DocumentTrashed { .. } => "DocumentTrashed".into(),
        Problem::Internal { .. } | Problem::Git { .. } => "Exception".into(),
        other => other.kind().unwrap_or("Problem").to_string(),
    }
}

/// 받는 쪽이 끊겼다 — 파이썬은 응답 작업이 취소될 때 같은 이름으로 턴을 닫는다
fn cancelled() -> Problem {
    Problem::Internal {
        log: "CancelledError".into(),
    }
}

fn send(tx: &UnboundedSender<Result<AskEvent, Problem>>, ev: AskEvent) -> Result<(), Problem> {
    tx.send(Ok(ev)).map_err(|_| cancelled())
}

/// 모델 한 번 — 글자 조각은 바로 `delta`로
async fn llm_step(
    l: &Loop,
    log: &[LlmMessage],
    tool_choice: &str,
    tx: &UnboundedSender<Result<AskEvent, Problem>>,
) -> Result<LlmStep, Problem> {
    let tx2 = tx.clone();
    let mut delta = move |s: &str| {
        let _ = tx2.send(Ok(AskEvent::Delta(s.to_string())));
    };
    let step = l
        .llm
        .step_stream(&l.system, log, &ASK_TOOLS, tool_choice, &mut delta)
        .await?;
    if tx.is_closed() {
        return Err(cancelled());
    }
    Ok(step)
}

/// ReAct 루프 — MS-008 ask_item 1~7. 답이면 (답, 본 것), 실패면 그 문제와 그때까지의 진행 줄·본 것
async fn run_loop(
    l: &Loop,
    tx: &UnboundedSender<Result<AskEvent, Problem>>,
    progress: &mut Vec<Progress>,
    reads: &mut Vec<String>,
    counts: &mut (usize, i64, i64),
    t0: Instant,
) -> Result<String, Problem> {
    let mut log = l.history.clone();
    log.push(LlmMessage::Text {
        role: "user",
        text: l.question.clone(),
        images: l.images.clone(),
    });
    loop {
        let step = llm_step(l, &log, "auto", tx).await?;
        counts.1 += step.usage.prompt_tokens;
        counts.2 += step.usage.completion_tokens;
        if step.tool_calls.is_empty() {
            return Ok(step.text.unwrap_or_default());
        }
        if let Some(t) = step.text.as_deref().filter(|t| !t.is_empty()) {
            progress.push(Progress {
                kind: "note".into(),
                text: t.to_string(),
            });
            send(tx, AskEvent::Note(t.to_string()))?;
        }
        log.push(LlmMessage::Calls {
            text: step.text.clone().unwrap_or_default(),
            tool_calls: step.tool_calls.clone(),
        });
        for call in &step.tool_calls {
            // 파이썬 `str(args.get("reason") or "").strip()`
            let reason = match call.arguments.get("reason") {
                Some(v) if truthy(v) => strip(&py_str(Some(v), "")).to_string(),
                _ => String::new(),
            };
            if !reason.is_empty() {
                progress.push(Progress {
                    kind: "note".into(),
                    text: reason.clone(),
                });
                send(tx, AskEvent::Note(reason))?;
            }
            let r = run_call(l, call).await?;
            progress.push(Progress {
                kind: "read".into(),
                text: match &r.target {
                    Some(t) => format!("{} {t}", call.name),
                    None => call.name.clone(),
                },
            });
            send(
                tx,
                AskEvent::Read {
                    tool: call.name.clone(),
                    target: r.target.clone(),
                },
            )?;
            if let Some(t) = &r.target
                && !reads.contains(t)
            {
                reads.push(t.clone());
            }
            log.push(LlmMessage::Tool {
                tool_call_id: call.id.clone(),
                text: r.text,
            });
            counts.0 += 1;
        }
        if counts.0 >= ASK_MAX_CALLS || t0.elapsed().as_secs_f64() >= ASK_TIME_LIMIT {
            log.push(LlmMessage::Text {
                role: "user",
                text: ASK_WRAP_UP.to_string(),
                images: Vec::new(),
            });
            let last = llm_step(l, &log, "none", tx).await?;
            counts.1 += last.usage.prompt_tokens;
            counts.2 += last.usage.completion_tokens;
            return match last.text.filter(|t| !t.is_empty()) {
                Some(t) => Ok(t),
                None => Err(Problem::LlmUnavailable {
                    reason: "상한 뒤에도 답이 없다".into(),
                }),
            };
        }
    }
}

/// 도구 하나 — 제 연결에서(모델을 기다리는 동안 연결을 쥐지 않는다)
async fn run_call(l: &Loop, call: &ToolCall) -> Result<ToolResult, Problem> {
    let mut c = l.pool.acquire().await?;
    ask_tool(
        &mut c,
        &l.repos,
        &call.name,
        &call.arguments,
        &l.code,
        &l.user,
        l.conversation_id,
    )
    .await
}

/// 루프를 따로 띄운다 — `start`를 먼저 넣고, 끝나면 턴을 닫고 `answer`(또는 실패)를 넣는다
fn spawn_loop(l: Loop) -> AskStream {
    let (tx, rx) = unbounded_channel();
    tokio::spawn(async move {
        let _ = tx.send(Ok(l.start.clone()));
        let t0 = Instant::now();
        let mut progress = Vec::new();
        let mut reads = Vec::new();
        let mut counts = (0usize, 0i64, 0i64);
        let result = run_loop(&l, &tx, &mut progress, &mut reads, &mut counts, t0).await;
        let answer = match result {
            Ok(a) => a,
            Err(p) => {
                // 실패도 턴으로 닫는다 — 다음 질문의 앞 대화에 안 실린다
                let name: String = match &p {
                    Problem::Internal { log } if log == "CancelledError" => log.clone(),
                    other => failure_name(other),
                };
                let name: String = name.chars().take(300).collect();
                let _ = finish(&l, None, &progress, &reads, Some(&name)).await;
                if !matches!(p, Problem::Internal { .. } | Problem::Git { .. }) {
                    let _ = tx.send(Err(p));
                }
                return;
            }
        };
        let linked = async {
            finish(&l, Some(&answer), &progress, &reads, None).await?;
            // 내보낼 때만 답 속 참조를 실제 항목과 맞춘 링크로 (#290)
            let mut c = l.pool.acquire().await?;
            let (project, _) = ProjectService {
                db: &mut c,
                repos: &l.repos,
            }
            .get_owned(&l.code, &l.user)
            .await?;
            let index = ref_index(&mut c, project.id).await?;
            Ok::<_, Problem>(answer_links(&answer, &index))
        }
        .await;
        tracing::info!(
            "ask {} conv={} user={} calls={} prompt={} completion={} elapsed={:.1}s",
            l.place,
            l.conversation_id,
            l.user.id,
            counts.0,
            counts.1,
            counts.2,
            t0.elapsed().as_secs_f64()
        );
        match linked {
            Ok((text, missing)) => {
                let _ = tx.send(Ok(AskEvent::Answer {
                    answer: text,
                    context_item_ids: reads,
                    missing_refs: missing,
                }));
            }
            Err(p) if !matches!(p, Problem::Internal { .. } | Problem::Git { .. }) => {
                let _ = tx.send(Err(p));
            }
            Err(_) => {}
        }
    });
    rx
}

/// 턴을 닫고 커밋한다
async fn finish(
    l: &Loop,
    answer: Option<&str>,
    progress: &[Progress],
    reads: &[String],
    error: Option<&str>,
) -> Result<(), Problem> {
    let mut tx = l.pool.begin().await?;
    ConversationService {
        db: &mut tx,
        repos: &l.repos,
    }
    .finish_turn(l.turn_id, answer, progress, reads, error)
    .await?;
    tx.commit().await?;
    Ok(())
}

/// 시작 전 — 대화 검사·앞 대화·턴·이 턴의 이미지·첨부 메타. 시작 맥락은 `context`가 만든다
struct Prepared {
    history: Vec<LlmMessage>,
    turn_id: i32,
    images: Vec<(String, Vec<u8>)>,
    system: String,
}

/// 대화 id — 파이썬 정수라 int4 밖이면 DB가 거절한다(500)
fn conv_id(id: i64) -> Result<i32, Problem> {
    i32::try_from(id).map_err(|_| Problem::Internal {
        log: format!("대화 id가 int4 밖이다 — {id}"),
    })
}

/// SYNC-MS-018#queries.ask_item
///
/// ReAct 루프. 쓰는 것은 대화 표뿐이다 — 질문을 받자마자 턴을 만들고 답이나 실패로 닫는다.
/// 첫 이벤트(start) 전의 오류는 `Err`(상태 코드), 뒤의 오류는 통로의 `Err`(error 이벤트)
#[allow(clippy::too_many_arguments)]
pub async fn ask_item(
    pool: &PgPool,
    repos: &ServerRepos,
    llm: &Llm,
    doc_id: &str,
    item_id: Option<&str>,
    conversation_id: i64,
    question: &str,
    attachment_ids: &[i64],
    user: &UserRow,
) -> Result<AskStream, Problem> {
    if !llm.enabled() {
        return Err(Problem::LlmNotConfigured); // 네트워크를 타기 전에 막는다
    }
    let code = doc_id.split('-').next().unwrap_or("").to_string();
    let mut tx = pool.begin().await?;
    ProjectService { db: &mut tx, repos }
        .get_owned(&code, user)
        .await?;
    let cid = conv_id(conversation_id)?;
    let p = prepare(&mut tx, repos, cid, &code, question, attachment_ids, user).await?;
    let system = start_context(&mut tx, doc_id, item_id, &p.system).await?;
    tx.commit().await?; // 턴은 스트림과 무관하게 남는다 — 답이 안 와도 실패로 닫힌다
    Ok(spawn_loop(Loop {
        pool: pool.clone(),
        repos: Arc::new(repos.clone()),
        llm: llm.clone(),
        user: user.clone(),
        system,
        code,
        conversation_id: cid,
        turn_id: p.turn_id,
        history: p.history,
        question: question.to_string(),
        images: p.images,
        start: AskEvent::Start {
            doc_id: Some(doc_id.to_string()),
            item_id: item_id.map(str::to_string),
            key: None,
        },
        place: format!("doc={doc_id} item={}", item_id.unwrap_or("None")),
    }))
}

/// 대화 검사·앞 대화·턴 만들기·이미지·[첨부] 줄 — 같은 트랜잭션 (`system`에는 첨부 줄을 담아 돌려준다)
async fn prepare(
    db: &mut PgConnection,
    repos: &ServerRepos,
    cid: i32,
    code: &str,
    question: &str,
    attachment_ids: &[i64],
    user: &UserRow,
) -> Result<Prepared, Problem> {
    let mut convs = ConversationService { db, repos };
    let view = convs.get(cid, user).await?; // 내 것이 아니면 not-found(conversation)
    if view.project_code != code {
        return Err(Problem::NotFound {
            resource: "conversation".into(),
            id: Value::from(cid),
        });
    }
    let history = convs.history(cid, LLM_MAX_TURNS).await?;
    let turn = convs.add_turn(cid, question, attachment_ids).await?;
    let images = convs.pending_images(turn.id).await?; // 이 턴의 이미지 — 메시지 파트로
    let metas: Vec<AttachmentMeta> = view
        .turns
        .iter()
        .flat_map(|t| t.attachments.iter().cloned())
        .chain(view.pending.iter().cloned())
        .collect();
    Ok(Prepared {
        history,
        turn_id: turn.id,
        images,
        system: attachment_lines(&metas),
    })
}

/// SYNC-MS-018#queries.ask_code
///
/// 코드 그래프에서 묻는다(UI-17 질문 탭). 고른 함수(key)가 시작 맥락이고 없어도 묻는다 — 그래프 전체.
/// 루프는 ask_item과 같다
#[allow(clippy::too_many_arguments)]
pub async fn ask_code(
    pool: &PgPool,
    repos: &ServerRepos,
    llm: &Llm,
    code: &str,
    key: Option<&str>,
    conversation_id: i64,
    question: &str,
    attachment_ids: &[i64],
    user: &UserRow,
) -> Result<AskStream, Problem> {
    if !llm.enabled() {
        return Err(Problem::LlmNotConfigured);
    }
    let mut tx = pool.begin().await?;
    let (project, _) = ProjectService { db: &mut tx, repos }
        .get_owned(code, user)
        .await?;
    let cid = conv_id(conversation_id)?;
    let p = prepare(&mut tx, repos, cid, code, question, attachment_ids, user).await?;
    let system = code_context(&mut tx, project.id, key, &p.system).await?;
    tx.commit().await?;
    Ok(spawn_loop(Loop {
        pool: pool.clone(),
        repos: Arc::new(repos.clone()),
        llm: llm.clone(),
        user: user.clone(),
        system,
        code: code.to_string(),
        conversation_id: cid,
        turn_id: p.turn_id,
        history: p.history,
        question: question.to_string(),
        images: p.images,
        start: AskEvent::Start {
            doc_id: None,
            item_id: None,
            key: key.map(str::to_string),
        },
        place: format!("code={code} key={}", key.unwrap_or("None")),
    }))
}

/// SYNC-MS-018#queries.conversation_view
///
/// 저장된 답은 원문이다 — 내보낼 때 답 속 맨 ID를 실제 항목과 맞춘 링크로 바꾸고 없는 참조를 싣는다
pub async fn conversation_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    conv_id: i32,
    user: &UserRow,
) -> Result<ConversationView, Problem> {
    let mut v = ConversationService {
        db: &mut *db,
        repos,
    }
    .get(conv_id, user)
    .await?;
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(&v.project_code, user)
    .await?;
    let index = ref_index(&mut *db, project.id).await?;
    for t in &mut v.turns {
        if let Some(a) = &t.answer {
            let (linked, missing) = answer_links(a, &index);
            t.answer = Some(linked);
            t.missing_refs = missing;
        }
    }
    Ok(v)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn index() -> HashMap<String, Vec<String>> {
        HashMap::from([
            (
                "SYNC-MS-007".to_string(),
                vec!["pipeline.save_pipeline".to_string()],
            ),
            (
                "SYNC-PRD-001".to_string(),
                vec!["R13".to_string(), "R1".to_string()],
            ),
        ])
    }

    #[test]
    fn answer_links_like_python() {
        let (out, missing) = answer_links(
            "SYNC-MS-007#pipeline.save_pipeline대로 · SYNC-PRD-001#R13은 · SYNC-PRD-001 · \
             `SYNC-PRD-001#R1` · [[SYNC-XX-001#a]] · SYNC-PRD-002#Z9. · xSYNC-PRD-001",
            &index(),
        );
        assert_eq!(
            out,
            "[[SYNC-MS-007#pipeline.save_pipeline]]대로 · [[SYNC-PRD-001#R13]]은 · [[SYNC-PRD-001]] · \
             `SYNC-PRD-001#R1` · [[SYNC-XX-001#a]] · [[SYNC-PRD-002#Z9]]. · xSYNC-PRD-001"
        );
        assert_eq!(missing, ["SYNC-XX-001#a", "SYNC-PRD-002#Z9"]);
        // 파이썬 `_answer_links`가 낸 답
        for (input, want, miss) in [
            (
                "```\nSYNC-PRD-001\n``` 뒤 SYNC-PRD-001#R1x",
                "```\nSYNC-PRD-001\n``` 뒤 [[SYNC-PRD-001#R1x]]",
                vec!["SYNC-PRD-001#R1x"],
            ),
            (
                "``SYNC-PRD-001`` SYNC-PRD-001#R1_a",
                "``[[SYNC-PRD-001]]`` [[SYNC-PRD-001#R1_a]]",
                vec!["SYNC-PRD-001#R1_a"],
            ),
            (
                "[[SYNC-PRD-001#R1] SYNC-PRD-001",
                "[[SYNC-PRD-001#R1] [[SYNC-PRD-001]]",
                vec![],
            ),
            (
                "ABCDE-X-001 AB-CD-0012 AB-CD-001 #SYNC-PRD-001 -SYNC-PRD-001",
                "ABCDE-X-001 AB-CD-0012 [[AB-CD-001]] #SYNC-PRD-001 -SYNC-PRD-001",
                vec!["AB-CD-001"],
            ),
            (
                "SYNC-PRD-001#R13#R1 SYNC-PRD-001#",
                "[[SYNC-PRD-001#R13]]#R1 [[SYNC-PRD-001]]#",
                vec![],
            ),
        ] {
            let (out, missing) = answer_links(input, &index());
            assert_eq!(out, want, "{input}");
            assert_eq!(missing, miss, "{input}");
        }
    }

    #[test]
    fn fill_once() {
        assert_eq!(
            fill("{a}-{b}-{c}", &[("a", "{b}"), ("b", "2")]),
            "{b}-2-{c}"
        );
    }
}
