//! 도구 부르기 — mcp 2.2.0 `MCPServer._handle_call_tool`·`Tool.run`·`FuncMetadata.pre_parse_json`을 옮겼다.
//! 인자 검증은 파이썬과 같은 문장을 낸다. 검증을 지난 도구는 그 카드가 처리기를 둔다 — 아직이면 `not-implemented`
//! (SYNC-CODE-002 L3 표, 사용자 결정 2026-10-08). 카드 L6이 `init_project`·`get_template`를, 카드 L7이
//! 읽기 넷(`list_documents`·`get_document`·`get_item`·`get_references`)과 쓰기 둘(`create_document`·`update_document`)을 열었다.

use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use num_bigint::BigInt;
use regex::Regex;
use serde_json::{Map, Value, json};
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::markdown::masked_lines;
use syncdoc_core::project::service::ProjectService;
use syncdoc_core::pycompat::chars::strip;
use syncdoc_core::pycompat::re::compile;
use syncdoc_core::queries;
use syncdoc_core::spec::{SUBTYPES, TYPES};
use syncdoc_core::types::{
    DocumentSummary, ItemRef, ProjectSummary, STAGES, Storage, py_isoformat,
};

use crate::compat::pydantic::{Failure, Opts};
use crate::compat::pyjson::{self, Depth};
use crate::compat::pyvalue::{PyDict, PyStr, PyValue};
use crate::state::AppState;
use crate::web::routes::specs::builtin;

use super::decl::decl;

/// 도구 인자의 문자열을 JSON으로 미리 읽을 때 파이썬 C 재귀가 남긴 깊이 — 파이썬 판 MCP 경로에서 잰 값
pub const ARG_JSON_DEPTH: Depth = Depth(9_987);

/// `tools/call` 결과 JSON — 늘 `CallToolResult`(오류도 `isError`로)
pub async fn call(
    state: &AppState,
    user: Option<&UserRow>,
    name: &str,
    arguments: Option<&PyValue>,
) -> String {
    let d = decl();
    let Some(tool) = d.tools.get(name) else {
        return error_result(&format!("Unknown tool: {name}"));
    };
    let args = match arguments {
        Some(PyValue::Dict(a)) => a.clone(),
        _ => PyDict::new(),
    };
    let parsed = pre_parse_json(
        &args,
        |k| tool.keys.contains(k),
        |k| tool.str_fields.contains(k),
    );
    let typed = match tool
        .validator
        .validate(&PyValue::Dict(parsed), Opts::default())
    {
        Ok(v) => v,
        Err(Failure::Invalid(e)) => {
            return error_result(&format!(
                "Error executing tool {name}: {}",
                e.display(&d.url_prefix)
            ));
        }
        Err(Failure::Exception(_)) => return error_result(&format!("Error executing tool {name}")),
    };
    let Some(user) = user else {
        // 파이썬 `_user` — 토큰 없이 닿지 않는다(인증이 먼저 막는다)
        return error_result(&problem_text(&Value::Object(problem_dict(
            &Problem::Blank {
                status: 401,
                title: "unauthorized".into(),
                detail: Some("토큰 없음".into()),
            },
        ))));
    };
    let result = match name {
        "init_project" => init_project(state, user, &typed).await,
        "get_template" => get_template(state, user, &typed).await,
        "list_documents" => list_documents(state, user, &typed).await,
        "get_document" => get_document(state, user, &typed).await,
        "get_item" => get_item(state, user, &typed).await,
        "get_references" => get_references(state, user, &typed).await,
        _ => Err(Problem::NotImplemented {
            card: tool.card.to_string(),
        }),
    };
    match result {
        Ok(v) => ok_result(&py_dumps(&v)),
        Err(p) => tool_error(name, &p),
    }
}

/// SYNC-API-002#init_project
async fn init_project(state: &AppState, user: &UserRow, a: &PyValue) -> Result<Value, Problem> {
    let code = arg_str(a, "code");
    let storage = Storage::parse(&arg_str(a, "storage")).unwrap_or(Storage::Github);
    let mut tx = state.pool.begin().await?;
    ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .init_project(
        &code,
        &arg_str(a, "name"),
        user,
        arg_bool(a, "import_existing"),
        storage,
    )
    .await?;
    tx.commit().await?;
    let mut c = state.pool.acquire().await?;
    let all = queries::project_summary(&mut c, &state.repos, user).await?;
    let summary = all
        .into_iter()
        .find(|p| p.code == code)
        .ok_or_else(|| Problem::Internal {
            log: format!("만든 프로젝트 {code}의 요약이 없다"),
        })?;
    Ok(project_json(&summary))
}

/// SYNC-API-002#list_documents
///
/// 11단계로 다시 묶는다(파이썬 `list_documents`) — `stage`가 1~11 밖이면 단계가 없다, `status`는 거르지 않고 비교만
async fn list_documents(state: &AppState, user: &UserRow, a: &PyValue) -> Result<Value, Problem> {
    let project_code = arg_str(a, "project_code");
    let stage = arg_int(a, "stage").map(|b| {
        i32::try_from(&b)
            .ok()
            .filter(|n| (1..=11).contains(n))
            .unwrap_or(0)
    });
    let status = arg_opt_str(a, "status");
    let mut c = state.pool.acquire().await?;
    let docs = queries::document_list(
        &mut c,
        &state.repos,
        &project_code,
        user,
        stage,
        status.as_deref(),
    )
    .await?;
    let mut stages = Vec::new();
    for (i, doc_type) in STAGES.iter().enumerate() {
        let n = i as i32 + 1;
        if stage.is_some_and(|s| s != n) {
            continue;
        }
        let mine: Vec<&DocumentSummary> = docs.iter().filter(|d| d.stage == Some(n)).collect();
        // 가장 낮은 상태 — 초안이 하나라도 있으면 초안
        let lowest = if mine.iter().any(|d| d.status == "draft") {
            Some("draft")
        } else if mine.is_empty() {
            None
        } else {
            Some("approved")
        };
        stages.push(json!({
            "stage": n,
            "doc_type": doc_type,
            "status": lowest,
            "doc_count": mine.len(),
            "docs": mine.iter().map(|d| summary_json(d)).collect::<Vec<_>>(),
        }));
    }
    Ok(json!({"project_code": project_code, "stages": stages}))
}

/// SYNC-API-002#get_document
///
/// 요약 + 해시·규약 오류 문장·본문·항목(각자의 미존재 참조)·이웃 — 파이썬 `get_document`의 꼴. `counts`는 비었다
async fn get_document(state: &AppState, user: &UserRow, a: &PyValue) -> Result<Value, Problem> {
    let mut c = state.pool.acquire().await?;
    let d = queries::document_view(&mut c, &state.repos, &arg_str(a, "doc_id"), user).await?;
    let mut out = summary_map(&d.summary);
    out.insert("commit_hash".into(), Value::from(d.commit_hash));
    out.insert(
        "convention_error_detail".into(),
        Value::from(d.convention_error_detail),
    );
    out.insert("body".into(), Value::from(d.body));
    out.insert(
        "items".into(),
        Value::from(
            d.items
                .iter()
                .map(|i| {
                    json!({
                        "item_id": i.item_id,
                        "display_name": i.display_name,
                        "missing_refs": i.missing_refs,
                    })
                })
                .collect::<Vec<_>>(),
        ),
    );
    out.insert("prev_doc_id".into(), Value::from(d.prev_doc_id));
    out.insert("next_doc_id".into(), Value::from(d.next_doc_id));
    Ok(Value::Object(out))
}

/// SYNC-API-002#get_item
///
/// `item_id`는 `~`를 `/`로 바꾼 것(서비스가 바꾼다)
async fn get_item(state: &AppState, user: &UserRow, a: &PyValue) -> Result<Value, Problem> {
    let mut c = state.pool.acquire().await?;
    let v = queries::item_view(
        &mut c,
        &state.repos,
        &arg_str(a, "doc_id"),
        &arg_str(a, "item_id"),
        user,
    )
    .await?;
    Ok(json!({
        "doc_id": v.doc_id,
        "item_id": v.item_id,
        "display_name": v.display_name,
        "doc_status": v.doc_status,
        "doc_version_no": v.doc_version_no,
        "body": v.body,
    }))
}

/// SYNC-API-002#get_references
async fn get_references(state: &AppState, user: &UserRow, a: &PyValue) -> Result<Value, Problem> {
    let mut c = state.pool.acquire().await?;
    let r = queries::item_references_view(
        &mut c,
        &state.repos,
        &arg_str(a, "doc_id"),
        &arg_str(a, "item_id"),
        user,
    )
    .await?;
    let refs = |xs: &[ItemRef]| -> Vec<Value> {
        xs.iter()
            .map(|x| {
                json!({
                    "doc_id": x.doc_id,
                    "item_id": x.item_id,
                    "display_name": x.display_name,
                    "raw_target": x.raw_target,
                    "is_missing": x.is_missing,
                })
            })
            .collect()
    };
    Ok(json!({
        "doc_id": r.doc_id,
        "item_id": r.item_id,
        "upstream": refs(&r.upstream),
        "downstream": refs(&r.downstream),
    }))
}

/// SYNC-API-002#get_template
async fn get_template(state: &AppState, user: &UserRow, a: &PyValue) -> Result<Value, Problem> {
    let project_code = arg_str(a, "project_code");
    let doc_type = arg_str(a, "doc_type");
    let subtype = arg_opt_str(a, "subtype");
    let Some((_, pats, secs)) = TYPES.iter().find(|(t, _, _)| *t == doc_type) else {
        return Err(not_found("doc_type", &doc_type));
    };
    let subs: Vec<&str> = SUBTYPES
        .iter()
        .filter(|(t, _, _, _)| *t == doc_type)
        .map(|(_, k, _, _)| *k)
        .collect();
    if let Some(s) = &subtype
        && !subs.contains(&s.as_str())
    {
        return Err(not_found("subtype", s)); // doc_type이 틀렸을 때와 같은 답 (API-002)
    }
    // 소유한 프로젝트만 연다 — 남의 것은 없는 것과 같다
    let mut tx = state.pool.begin().await?;
    let (_, repository) = ProjectService {
        db: &mut tx,
        repos: &state.repos,
    }
    .get_owned(&project_code, user)
    .await?;
    tx.commit().await?;
    let workdir = PathBuf::from(&repository.workdir_path);
    // 템플릿은 내장이 먼저(#94) · 서브타입 뼈대가 없으면 타입 것
    let mut name = match &subtype {
        Some(s) => format!("{doc_type}-{s}"),
        None => doc_type.clone(),
    };
    if subtype.is_some() && builtin(&format!("_templates/{name}.md")).is_none() {
        name = doc_type.clone();
    }
    let template = read_spec_file(
        state,
        &workdir,
        &format!("docs/specs/_templates/{name}.md"),
        None,
        true,
    )
    .await?;
    // 규약은 저장소의 {코드}-STD-001이 먼저, 없으면 싱크독 것 (STD-001 2.12, 사용자 결정 2026-10-08)
    let std = read_spec_file(
        state,
        &workdir,
        &format!("docs/specs/STD/{project_code}-STD-001.md"),
        Some("docs/specs/STD/SYNC-STD-001.md"),
        false,
    )
    .await?;
    let (pats, secs): (&[&str], &[&str]) = match &subtype {
        Some(s) => SUBTYPES
            .iter()
            .find(|(t, k, _, _)| *t == doc_type && k == s)
            .map(|(_, _, p, q)| (*p, *q))
            .unwrap_or((pats, secs)),
        None => (pats, secs),
    };
    let mut out = Map::new();
    out.insert("doc_type".into(), Value::from(doc_type.as_str()));
    out.insert("common_rules".into(), Value::from(section(&std, "1.")));
    out.insert(
        "type_rules".into(),
        json!({
            "item_patterns": pats,
            "required_sections": secs,
            "block_structure": block_structure(&std, &doc_type, subtype.as_deref()),
        }),
    );
    out.insert("template".into(), Value::from(template));
    out.insert("example".into(), Value::from(section(&std, "5.")));
    match &subtype {
        Some(s) => {
            out.insert("subtype".into(), Value::from(s.as_str()));
        }
        None if !subs.is_empty() => {
            out.insert("subtypes".into(), json!(subs));
        }
        None => {}
    }
    Ok(Value::Object(out))
}

/// 프로젝트 저장소의 파일, 없으면 앱에 내장된 사본 — 파이썬 `_read_spec_file`.
/// `prefer_builtin`이면 내장이 먼저, 저장소는 내장에 없을 때만
async fn read_spec_file(
    state: &AppState,
    workdir: &Path,
    path: &str,
    fallback: Option<&str>,
    prefer_builtin: bool,
) -> Result<String, Problem> {
    let local = |p: &str| builtin(p.strip_prefix("docs/specs/").unwrap_or(p));
    if prefer_builtin && let Some(t) = local(path) {
        return Ok(t);
    }
    match state.repos.git.read(workdir, path, "HEAD").await {
        Ok(t) => Ok(t),
        // 작업 사본이 없거나(OSError) 파일이 없으면(GitError) 내장 사본
        Err(Problem::Git { .. } | Problem::Internal { .. }) => [Some(path), fallback]
            .into_iter()
            .flatten()
            .find_map(local)
            .ok_or_else(|| not_found("file", path)),
        Err(other) => Err(other),
    }
}

/// `## N. 제목` 절 하나 — 다음 `## `까지. 코드블록 안 헤딩은 무시 (파이썬 `_section`)
fn section(text: &str, prefix: &str) -> String {
    let lines: Vec<&str> = text.split('\n').collect();
    let masked = masked_lines(text);
    let head = format!("## {prefix}");
    let Some(start) = masked.iter().position(|m| m.starts_with(&head)) else {
        return String::new();
    };
    let end = (start + 1..masked.len())
        .find(|&i| masked[i].starts_with("## "))
        .unwrap_or(lines.len());
    strip(&lines[start..end].join("\n")).to_string()
}

static SUB_SECTION: LazyLock<Regex> = LazyLock::new(|| compile(r"(?m)^### 2\.\d+ "));
static BOLD_HEAD: LazyLock<Regex> = LazyLock::new(|| compile(r"(?m)^\*\*([^*\n]+)\*\*\s*$"));
static BLOCK_ROW: LazyLock<Regex> = LazyLock::new(|| compile(r"(?m)^\| 항목 블록 \| (.+?) \|$"));

/// STD-001 2장 타입 표의 「항목 블록」 행 — 서브타입이면 그 굵은 머리 아래 표만 (파이썬 `_block_structure`)
fn block_structure(std: &str, doc_type: &str, subtype: Option<&str>) -> String {
    let sec = section(std, "2.");
    for chunk in SUB_SECTION.split(&sec).skip(1) {
        if !chunk.starts_with(doc_type) {
            continue;
        }
        let mut chunk = chunk;
        if let Some(sub) = subtype {
            let heads: Vec<_> = BOLD_HEAD.captures_iter(chunk).collect();
            for (i, h) in heads.iter().enumerate() {
                if h[1].contains(sub) {
                    let end = heads
                        .get(i + 1)
                        .map_or(chunk.len(), |n| n.get(0).map_or(chunk.len(), |m| m.start()));
                    let from = h.get(0).map_or(0, |m| m.end());
                    chunk = &chunk[from..end];
                    break;
                }
            }
        }
        if let Some(m) = BLOCK_ROW.captures(chunk) {
            return m[1].to_string();
        }
    }
    String::new()
}

fn not_found(resource: &str, id: &str) -> Problem {
    Problem::NotFound {
        resource: resource.to_string(),
        id: Value::from(id),
    }
}

/// 파이썬 `_project_json` — 시각은 `isoformat()`(`+00:00`)
pub fn project_json(p: &ProjectSummary) -> Value {
    json!({
        "code": p.code,
        "name": p.name,
        "storage": p.storage.as_str(),
        "remote_url": p.remote_url,
        "stages": p.stages,
        "std_docs": p.std_docs.iter().map(summary_json).collect::<Vec<_>>(),
        "counts": p.counts,
        "updated_at": p.updated_at.map(py_isoformat),
    })
}

/// 파이썬 `_author_json` — 사람은 로그인으로. 이름을 붙이지 않은 요약(프로젝트 요약의 `std_docs`)은 없음
fn author_json(d: &DocumentSummary) -> Value {
    match &d.author {
        None => Value::Null,
        Some(a) => json!({
            "kind": a.kind,
            "user": a.user.as_ref().map(|u| u.github_login.as_str()),
            "instructed_by": a.instructed_by.as_ref().map(|u| u.github_login.as_str()),
            "via": a.via,
        }),
    }
}

/// 파이썬 `_summary_json` — 시각은 `isoformat()`(`+00:00`)
fn summary_json(d: &DocumentSummary) -> Value {
    Value::Object(summary_map(d))
}

/// `_summary_json`의 키들 — `get_document`가 뒤에 더 붙인다
fn summary_map(d: &DocumentSummary) -> Map<String, Value> {
    let Value::Object(m) = json!({
        "doc_id": d.doc_id,
        "doc_type": d.doc_type,
        "stage": d.stage,
        "status": d.status,
        "version_no": d.current_version_no,
        "has_convention_error": d.has_convention_error,
        "incomplete_warnings": d.incomplete_warnings,
        "updated_at": py_isoformat(d.updated_at),
        "last_author": author_json(d),
        "counts": d.counts,
    }) else {
        return Map::new();
    };
    m
}

fn arg<'a>(v: &'a PyValue, name: &str) -> Option<&'a PyValue> {
    v.as_dict().and_then(|d| d.get(&PyStr::from(name)))
}

fn arg_str(v: &PyValue, name: &str) -> String {
    match arg(v, name) {
        Some(PyValue::Str(PyStr::Utf8(s))) => s.clone(),
        Some(PyValue::Str(s)) => s.repr(),
        _ => String::new(),
    }
}

fn arg_opt_str(v: &PyValue, name: &str) -> Option<String> {
    match arg(v, name) {
        None | Some(PyValue::None) => None,
        Some(_) => Some(arg_str(v, name)),
    }
}

/// 검증을 지난 정수 인자 — 없거나 None이면 없음
fn arg_int(v: &PyValue, name: &str) -> Option<BigInt> {
    match arg(v, name) {
        Some(PyValue::Int(i)) => Some(i.clone()),
        _ => None,
    }
}

fn arg_bool(v: &PyValue, name: &str) -> bool {
    matches!(arg(v, name), Some(PyValue::Bool(true)))
}

/// 파이썬 `Problem.to_dict()` — type·title·status·detail(비면 뺌)·확장 필드 차례
fn problem_dict(p: &Problem) -> Map<String, Value> {
    let mut m = Map::new();
    m.insert(
        "type".into(),
        Value::from(match p.kind() {
            Some(k) => format!("urn:syncdoc:{k}"),
            None => "about:blank".to_string(),
        }),
    );
    m.insert("title".into(), Value::from(p.title()));
    m.insert("status".into(), Value::from(p.status()));
    if let Some(d) = p.detail().filter(|d| !d.is_empty()) {
        m.insert("detail".into(), Value::from(d));
    }
    for (k, v) in p.extras() {
        m.insert(k.into(), v);
    }
    m
}

fn problem_text(v: &Value) -> String {
    py_dumps(v)
}

/// 처리기의 실패 — 문제(Problem)는 `_problem`의 JSON, git 실패 같은 예외는 MCP SDK의 「Error executing tool」 문장
fn tool_error(name: &str, p: &Problem) -> String {
    match p {
        Problem::Git { .. } | Problem::Internal { .. } => {
            error_result(&format!("Error executing tool {name}: {p}"))
        }
        _ => error_result(&problem_text(&Value::Object(problem_dict(p)))),
    }
}

/// 파이썬 `json.dumps(x, ensure_ascii=False)` — 기본 구분자 `, `·`: `, 키는 넣은 차례
pub fn py_dumps(v: &Value) -> String {
    match v {
        Value::Object(m) => {
            let items: Vec<String> = m
                .iter()
                .map(|(k, v)| format!("{}: {}", py_json_str(k), py_dumps(v)))
                .collect();
            format!("{{{}}}", items.join(", "))
        }
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(py_dumps).collect::<Vec<_>>().join(", ")
        ),
        Value::String(s) => py_json_str(s),
        other => other.to_string(),
    }
}

/// `pre_parse_json` — 모델 필드이고 주석이 `str`가 아닌 인자의 문자열을 JSON으로 읽어 본다.
/// 읽은 것이 str·int·float(bool 포함)면 그대로 둔다. 못 읽으면 그대로 둔다
fn pre_parse_json(
    data: &PyDict,
    is_field: impl Fn(&str) -> bool,
    is_str: impl Fn(&str) -> bool,
) -> PyDict {
    let mut out = data.clone();
    for (k, v) in data {
        let Some(key) = k.as_str() else { continue };
        if !is_field(key) || is_str(key) {
            continue;
        }
        let PyValue::Str(s) = v else { continue };
        match pyjson::loads_str(s, ARG_JSON_DEPTH) {
            Ok(PyValue::Str(_) | PyValue::Int(_) | PyValue::Float(_) | PyValue::Bool(_))
            | Err(_) => {}
            Ok(parsed) => {
                out.insert(k.clone(), parsed);
            }
        }
    }
    out
}

/// 파이썬 `json.dumps(str, ensure_ascii=False)` — 제어 글자·따옴표·역슬래시만 이스케이프
fn py_json_str(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_default()
}

/// `CallToolResult(content=[TextContent(text)])`를 판의 꼴로 — 키는 알파벳 차례, `isError`는 거짓으로 실린다
fn ok_result(text: &str) -> String {
    format!(
        "{{\"content\":[{{\"text\":{},\"type\":\"text\"}}],\"isError\":false}}",
        serde_json::to_string(text).unwrap_or_default()
    )
}

/// `CallToolResult(content=[TextContent(text)], is_error=True)`를 판의 꼴로 — 키는 알파벳 차례
fn error_result(text: &str) -> String {
    format!(
        "{{\"content\":[{{\"text\":{},\"type\":\"text\"}}],\"isError\":true}}",
        serde_json::to_string(text).unwrap_or_default()
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dumps_like_python() {
        let v = json!({"a": 1, "b": [true, null, "가\"\n"], "c": {}});
        assert_eq!(
            py_dumps(&v),
            r#"{"a": 1, "b": [true, null, "가\"\n"], "c": {}}"#
        );
    }

    #[test]
    fn section_and_block_structure_follow_std_001() {
        let std = builtin("STD/SYNC-STD-001.md").expect("내장 규약");
        assert!(section(&std, "1.").starts_with("## 1."));
        assert!(!block_structure(&std, "PRD", None).is_empty());
        assert_ne!(
            block_structure(&std, "DOM", Some("클래스")),
            block_structure(&std, "DOM", Some("도메인"))
        );
    }
}
