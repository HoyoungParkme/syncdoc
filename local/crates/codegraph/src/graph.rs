//! 줄이기·대조·층 — 파이썬 판 `graph.py`의 순수 함수 (SYNC-MS-022).

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fs;
use std::path::Path;
use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;
use serde_json::Value;
use syncdoc_pycompat::chars::{lstrip, py_splitlines, strip};
use syncdoc_pycompat::re::compile;

use crate::{Call, CallDiff, CodeGraphFailed, Function, Graph, Layer, LayerRow, LayerSpec};

/// graphify가 읽는 코드 파일 — 이것이 바뀐 커밋만 그래프를 다시 만든다 (UC-S8 1a)
pub(crate) const CODE_EXTS: [&str; 27] = [
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".scala", ".rb",
    ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".swift", ".lua", ".ex", ".exs", ".jl", ".sh",
    ".sql", ".vue", ".svelte",
];
/// 모듈 이름 대신 폴더 이름을 쓰는 파일 — `core/codegraph/service.py`의 함수는 `codegraph.x`
const PKG_STEMS: [&str; 3] = ["service", "__init__", "index"];
const CALLS_LINE: &str = "**호출하는 것**";
const LAYER_HEAD: [&str; 3] = ["경로", "층", "명세"];
const HELPER: &str = "도우미";

/// docstring 첫 줄의 항목 ID — 어느 문서든. `#` 뒤는 공백 앞까지
static ITEM_ID: LazyLock<Regex> = LazyLock::new(|| compile(r"^([A-Z][A-Z0-9]*-[A-Z]+-\d+#\S+)"));
static MS_DOC: LazyLock<Regex> = LazyLock::new(|| compile(r"^[A-Z][A-Z0-9]*-MS-\d+#"));
static TEST_FILE: LazyLock<Regex> = LazyLock::new(|| {
    compile(
        r"(^|/)(tests?|__tests__)/|(^|/)(test_[^/]*|[^/]*_test)\.py$|\.(test|spec)\.[jt]sx?$|(^|/)conftest\.py$",
    )
});
static REF: LazyLock<Regex> = LazyLock::new(|| compile(r"\[\[([^\]]+)\]\]"));
static TICK: LazyLock<Regex> = LazyLock::new(|| compile(r"`([A-Za-z_][\w.]*)"));
static BACKTICK: LazyLock<Regex> = LazyLock::new(|| compile(r"`([^`]+)`"));
static SECTION_NO: LazyLock<Regex> = LazyLock::new(|| compile(r"^[\d.]+\s*"));

// ── 파이썬 `PurePosixPath`의 몇 가지 ──

/// `parts` — `/`로 가르고 빈 조각·`.`은 버린다(절대 경로면 앞에 `/`)
pub(crate) fn parts(path: &str) -> Vec<&str> {
    let mut out = Vec::new();
    if path.starts_with('/') {
        out.push("/");
    }
    out.extend(path.split('/').filter(|p| !p.is_empty() && *p != "."));
    out
}

/// `name` — 마지막 조각(뿌리뿐이면 빈 것)
pub(crate) fn name(path: &str) -> &str {
    match parts(path).last() {
        Some(&"/") | None => "",
        Some(n) => n,
    }
}

/// `suffix`가 시작하는 자리 — `0 < i < len - 1`일 때만
fn suffix_at(name: &str) -> Option<usize> {
    let i = name.rfind('.')?;
    (i > 0 && i < name.len() - 1).then_some(i)
}

/// `stem`
pub(crate) fn stem(path: &str) -> &str {
    let n = name(path);
    match suffix_at(n) {
        Some(i) => &n[..i],
        None => n,
    }
}

/// `suffix`
pub(crate) fn suffix(path: &str) -> &str {
    let n = name(path);
    match suffix_at(n) {
        Some(i) => &n[i..],
        None => "",
    }
}

/// `parent.name`
pub(crate) fn parent_name(path: &str) -> &str {
    let ps = parts(path);
    if ps.len() < 2 {
        return "";
    }
    match ps[ps.len() - 2] {
        "/" => "",
        n => n,
    }
}

/// 테스트 코드는 구현이 아니다 — 대조에서 뺀다
pub(crate) fn is_test(file: &str) -> bool {
    TEST_FILE.is_match(file)
}

/// 노드 이름 → 함수 이름 — 앞 `.`과 뒤 `()`를 뗀다
pub(crate) fn clean(label: &str) -> String {
    let s = strip(label).trim_start_matches('.');
    s.strip_suffix("()").unwrap_or(s).to_string()
}

/// qual의 모듈 — 파일 이름, `service`·`__init__`·`index`면 폴더 이름
pub(crate) fn module(file: &str) -> String {
    let (st, parent) = (stem(file), parent_name(file));
    if PKG_STEMS.contains(&st) && !parent.is_empty() {
        parent.to_string()
    } else {
        st.to_string()
    }
}

/// docstring 첫 줄 → (item, ms). item은 어느 문서의 항목 ID든, ms는 MINISPEC일 때 같은 값
pub(crate) fn item_of(first_line: &str) -> (Option<String>, Option<String>) {
    let Some(c) = ITEM_ID.captures(strip(first_line)) else {
        return (None, None);
    };
    let item = c[1].to_string();
    let ms = MS_DOC.is_match(&item).then(|| item.clone());
    (Some(item), ms)
}

// ── JSON 값을 파이썬처럼 ──

pub(crate) fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// 파이썬 `str(v)` — 글자는 그대로
pub(crate) fn py_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        other => other.to_string(),
    }
}

fn text_of(n: &Value, key: &str) -> String {
    n.get(key).map(py_str).unwrap_or_default()
}

/// raw 노드의 (파일, 줄) — `source_file` + `source_location`의 `L` 뒤 숫자
pub(crate) fn node_key(n: &Value) -> Option<(String, i64)> {
    let file = n.get("source_file").filter(|v| truthy(Some(v)))?;
    let loc = match n.get("source_location") {
        Some(v) if truthy(Some(v)) => py_str(v),
        _ => String::new(),
    };
    let digits = loc.strip_prefix('L')?;
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    Some((py_str(file), digits.parse().ok()?))
}

/// SYNC-MS-022#codegraph.touches_code
pub fn touches_code(paths: &[String]) -> bool {
    paths.iter().any(|p| {
        if p.starts_with("docs/specs/")
            || p.starts_with("graphify-out/")
            || p.contains("/graphify-out/")
        {
            return false; // 명세·graphify 결과는 코드가 아니다
        }
        CODE_EXTS.contains(&suffix(p).to_lowercase().as_str())
    })
}

/// SYNC-MS-022#codegraph.load
///
/// 저장소에 커밋된 `graphify-out/graph.json`이 있으면 그것(`repo`), 없으면 tree-sitter로 추출(`server`)
pub fn load(src_dir: &Path) -> Result<(String, Value), CodeGraphFailed> {
    let committed = src_dir.join("graphify-out").join("graph.json");
    if committed.is_file() {
        let text = fs::read(&committed).map_err(|e| CodeGraphFailed(e.to_string()))?;
        return serde_json::from_slice(&text)
            .map(|v| ("repo".to_string(), v))
            .map_err(|_| CodeGraphFailed("graph.json 형식".into()));
    }
    Ok(("server".to_string(), crate::extract::extract(src_dir)?))
}

/// SYNC-MS-022#codegraph.reduce
///
/// 함수·메서드와 그 사이 호출 선만 남긴다. import·포함·문서·docstring·개념 노드는 버린다
pub fn reduce(raw: &Value) -> Graph {
    let mut nodes: IndexMap<String, &Value> = IndexMap::new();
    for n in raw
        .get("nodes")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(id) = n.get("id") {
            nodes.insert(py_str(id), n); // 같은 id면 마지막 것이 첫 자리에(파이썬 dict)
        }
    }
    let links: &[Value] = [raw.get("links"), raw.get("edges")]
        .into_iter()
        .flatten()
        .find(|v| truthy(Some(v)))
        .and_then(Value::as_array)
        .map_or(&[], Vec::as_slice);
    let mut owner: HashMap<String, String> = HashMap::new();
    let mut item: HashMap<String, String> = HashMap::new();
    let mut ms: HashMap<String, String> = HashMap::new();
    for e in links {
        let source = e.get("source").map(py_str).unwrap_or_default();
        let target = e.get("target").map(py_str).unwrap_or_default();
        match e.get("relation").and_then(Value::as_str) {
            Some("method") => {
                if let Some(n) = nodes.get(&source) {
                    owner.insert(target, clean(&text_of(n, "label")));
                }
            }
            Some("rationale_for") => {
                if let Some(n) = nodes.get(&source) {
                    let (it, m) = item_of(&text_of(n, "label"));
                    if let Some(it) = it {
                        item.insert(target.clone(), it);
                    }
                    if let Some(m) = m {
                        ms.insert(target, m);
                    }
                }
            }
            _ => {}
        }
    }
    let mut key_of: HashMap<String, String> = HashMap::new();
    let mut functions = Vec::new();
    let mut keys: HashSet<String> = HashSet::new();
    for (nid, n) in &nodes {
        if !truthy(n.get("_callable")) || truthy(n.get("_callable_class")) {
            continue;
        }
        let Some((file, line)) = node_key(n) else {
            continue;
        };
        if is_test(&file) {
            continue;
        }
        let key = format!("{file}:{line}");
        key_of.insert(nid.clone(), key.clone());
        if !keys.insert(key.clone()) {
            continue; // 같은 자리 둘 — 하나로 접는다
        }
        let fname = clean(&text_of(n, "label"));
        let qual = match owner.get(nid) {
            Some(cls) => format!("{cls}.{fname}"),
            None => format!("{}.{fname}", module(&file)),
        };
        functions.push(Function {
            key,
            name: fname,
            qual,
            file,
            line,
            end: None,
            item: item.get(nid).cloned(),
            ms: ms.get(nid).cloned(),
            community: None,
        });
    }
    let mut seen: HashSet<(String, String)> = HashSet::new();
    let mut calls = Vec::new();
    for e in links {
        if !matches!(
            e.get("relation").and_then(Value::as_str),
            Some("calls" | "indirect_call")
        ) {
            continue;
        }
        if e.get("confidence").and_then(Value::as_str) == Some("INFERRED") {
            continue; // 이름만 보고 추측한 선
        }
        let a = e.get("source").map(py_str).and_then(|s| key_of.get(&s));
        let b = e.get("target").map(py_str).and_then(|s| key_of.get(&s));
        if let (Some(a), Some(b)) = (a, b)
            && a != b
            && seen.insert((a.clone(), b.clone()))
        {
            calls.push(Call(a.clone(), b.clone(), "graphify".into()));
        }
    }
    let files: BTreeSet<String> = nodes
        .values()
        .filter(|n| n.get("file_type").and_then(Value::as_str) == Some("code"))
        .filter(|n| truthy(n.get("source_file")))
        .map(|n| text_of(n, "source_file"))
        .filter(|f| !is_test(f))
        .collect();
    Graph {
        functions,
        calls,
        communities: None,
        files: files.into_iter().collect(),
    }
}

/// 항목 ID의 `#` 뒤 → 항목 ID. 겹치는 이름은 모호하니 뺀다
fn short_names<'a>(ids: impl IntoIterator<Item = &'a String>) -> HashMap<String, String> {
    let mut names: HashMap<String, String> = HashMap::new();
    let mut dup: HashSet<String> = HashSet::new();
    for i in ids {
        let n = i.split_once('#').map_or("", |(_, n)| n).to_string();
        if names.contains_key(&n) {
            dup.insert(n.clone());
        }
        names.insert(n, i.clone());
    }
    for d in dup {
        names.remove(&d);
    }
    names
}

/// SYNC-MS-022#codegraph.spec_calls
///
/// 항목마다 「호출하는 것」 줄의 `[[…]]`와 백틱 이름 중 MINISPEC 항목인 것만 — 백틱 이름은 그 항목의 구현 안에서 푼다
pub fn spec_calls(
    items: &[(String, String)],
    impl_of: Option<&HashMap<String, String>>,
) -> BTreeMap<String, BTreeSet<String>> {
    let ids: HashSet<&String> = items.iter().map(|(i, _)| i).collect();
    let impl_ = |i: &str| -> Option<String> {
        impl_of.and_then(|m| m.get(i.split_once('#').map_or(i, |(d, _)| d)).cloned())
    };
    let mut groups: HashMap<Option<String>, Vec<&String>> = HashMap::new();
    for i in &ids {
        groups.entry(impl_(i)).or_default().push(i);
    }
    let names_of: HashMap<Option<String>, HashMap<String, String>> = groups
        .into_iter()
        .map(|(g, members)| (g, short_names(members)))
        .collect();
    let mut out = BTreeMap::new();
    for (ms_id, body) in items {
        let names = &names_of[&impl_(ms_id)];
        let doc = ms_id.split_once('#').map_or(ms_id.as_str(), |(d, _)| d);
        let mut found: BTreeSet<String> = BTreeSet::new();
        if let Some(line) = py_splitlines(body)
            .into_iter()
            .find(|l| l.starts_with(CALLS_LINE))
        {
            for c in REF.captures_iter(line) {
                let r = strip(&c[1]);
                let rid = if r.starts_with('#') {
                    format!("{doc}{r}")
                } else {
                    r.to_string()
                };
                if ids.contains(&rid) {
                    found.insert(rid);
                }
            }
            for c in TICK.captures_iter(line) {
                if let Some(id) = names.get(&c[1]) {
                    found.insert(id.clone());
                }
            }
        }
        found.remove(ms_id);
        out.insert(ms_id.clone(), found);
    }
    out
}

/// SYNC-MS-022#codegraph.compare
///
/// 코드 호출은 항목이 없는 함수(도우미)를 건너 항목이 있는 함수에 닿을 때까지 따라간다
pub fn compare(graph: &Graph, spec: &BTreeMap<String, BTreeSet<String>>) -> Vec<CallDiff> {
    let names = short_names(spec.keys());
    let mut fn_ms: HashMap<String, String> = HashMap::new();
    let mut ms_fn: HashMap<String, String> = HashMap::new();
    let mut by_name: IndexMap<String, Vec<String>> = IndexMap::new();
    for f in &graph.functions {
        if let Some(m) = f.ms.as_ref().filter(|m| !m.is_empty()) {
            fn_ms.insert(f.key.clone(), m.clone());
            ms_fn.entry(m.clone()).or_insert_with(|| f.key.clone());
        } else if let Some(id) = names.get(&f.qual) {
            by_name.entry(id.clone()).or_default().push(f.key.clone());
        }
    }
    for (mid, keys) in by_name {
        if !ms_fn.contains_key(&mid) && keys.len() == 1 {
            ms_fn.insert(mid.clone(), keys[0].clone());
            fn_ms.insert(keys[0].clone(), mid);
        }
    }
    let mut adj: HashMap<&str, Vec<&str>> = HashMap::new();
    for c in &graph.calls {
        adj.entry(c.0.as_str()).or_default().push(c.1.as_str());
    }
    let mut out = Vec::new();
    for (mid, want) in spec {
        let Some(key) = ms_fn.get(mid) else {
            out.push(CallDiff {
                ms_id: mid.clone(),
                function: None,
                same: Vec::new(),
                code_only: Vec::new(),
                spec_only: want.iter().cloned().collect(),
            });
            continue;
        };
        let mut code: BTreeSet<String> = BTreeSet::new();
        let mut seen: HashSet<&str> = HashSet::from([key.as_str()]);
        let mut stack: Vec<&str> = vec![key.as_str()];
        while let Some(u) = stack.pop() {
            for v in adj.get(u).into_iter().flatten() {
                if !seen.insert(v) {
                    continue;
                }
                match fn_ms.get(*v) {
                    Some(m) => {
                        code.insert(m.clone()); // 항목이 있는 함수 — 여기서 멈춘다
                    }
                    None => stack.push(v), // 도우미 — 건너 계속
                }
            }
        }
        code.remove(mid);
        out.push(CallDiff {
            ms_id: mid.clone(),
            function: Some(key.clone()),
            same: want.intersection(&code).cloned().collect(),
            code_only: code.difference(want).cloned().collect(),
            spec_only: want.difference(&code).cloned().collect(),
        });
    }
    out
}

/// SYNC-MS-022#codegraph.item_function
///
/// 화면 항목은 파일 함수 전부가 같은 item이라 파일 이름과 같은 함수로 좁히고, 없으면 (파일, 줄) 순 첫 함수
pub fn item_function<'g>(graph: &'g Graph, item_id: &str) -> Option<&'g Function> {
    let cands: Vec<&Function> = graph
        .functions
        .iter()
        .filter(|f| f.item.as_deref() == Some(item_id))
        .collect();
    let named: Vec<&Function> = cands
        .iter()
        .copied()
        .filter(|f| f.name == stem(&f.file))
        .collect();
    let pool = if named.is_empty() { cands } else { named };
    let mut best: Option<&Function> = None;
    for f in pool {
        if best.is_none_or(|b| (&f.file, f.line) < (&b.file, b.line)) {
            best = Some(f);
        }
    }
    best
}

/// SYNC-MS-022#codegraph.item_neighbors
///
/// 부르는 것·불리는 곳을 항목 있는 함수까지 — 도우미와 같은 항목의 함수는 건너 계속, 다른 항목에 닿으면 멈춘다
pub fn item_neighbors(graph: &Graph, key: &str) -> (Vec<String>, Vec<String>) {
    let by_key: HashMap<&str, &Function> = graph
        .functions
        .iter()
        .map(|f| (f.key.as_str(), f))
        .collect();
    let Some(start) = by_key.get(key) else {
        return (Vec::new(), Vec::new());
    };
    let own = start.item.as_deref();
    let mut fwd: HashMap<&str, Vec<&str>> = HashMap::new();
    let mut back: HashMap<&str, Vec<&str>> = HashMap::new();
    for c in &graph.calls {
        fwd.entry(c.0.as_str()).or_default().push(c.1.as_str());
        back.entry(c.1.as_str()).or_default().push(c.0.as_str());
    }
    let walk = |adj: &HashMap<&str, Vec<&str>>| -> Vec<String> {
        let mut found: BTreeMap<String, String> = BTreeMap::new();
        let mut seen: HashSet<&str> = HashSet::from([key]);
        let mut stack: Vec<&str> = vec![key];
        while let Some(u) = stack.pop() {
            for v in adj.get(u).into_iter().flatten() {
                if seen.contains(v) || !by_key.contains_key(v) {
                    continue;
                }
                seen.insert(v);
                match by_key[v].item.as_deref() {
                    Some(it) if !it.is_empty() && Some(it) != own => {
                        found.entry(it.to_string()).or_insert_with(|| v.to_string());
                    }
                    _ => stack.push(v),
                }
            }
        }
        found.into_values().collect()
    };
    (walk(&fwd), walk(&back))
}

fn cells(line: &str) -> Vec<String> {
    strip(line)
        .trim_matches('|')
        .split('|')
        .map(|c| strip(c).to_string())
        .collect()
}

/// SYNC-MS-022#codegraph.layer_table
///
/// 클래스 명세 「폴더 구조」 절에서 머리가 경로·층·명세인 첫 표. 표 순서가 우선순위, 코드블록 안은 표가 아니다
pub fn layer_table(body: &str) -> Vec<LayerRow> {
    let mut rows = Vec::new();
    let (mut in_sec, mut in_fence, mut in_table) = (false, false, false);
    for (i, line) in body.split('\n').enumerate() {
        if line.starts_with("```") {
            in_fence = !in_fence;
            continue;
        }
        if in_fence {
            continue;
        }
        if let Some(head) = line.strip_prefix("## ") {
            if in_table {
                break;
            }
            in_sec = SECTION_NO.replace(strip(head), "").starts_with("폴더 구조");
            continue;
        }
        if !in_sec {
            continue;
        }
        if !in_table {
            if lstrip(line).starts_with('|') && cells(line) == LAYER_HEAD {
                in_table = true;
            }
            continue;
        }
        if !lstrip(line).starts_with('|') {
            break; // 표가 끝났다
        }
        let cs = cells(line);
        if cs.len() < 3 || cs[0].chars().all(|c| matches!(c, '-' | ':' | ' ')) {
            continue; // 구분 줄
        }
        let patterns: Vec<String> = cs[0]
            .split(" · ")
            .flat_map(|part| BACKTICK.captures_iter(part).map(|c| c[1].to_string()))
            .collect();
        if patterns.is_empty() {
            continue;
        }
        let mut specs = Vec::new();
        for part in cs[2].split(" · ") {
            let m = REF.captures(part);
            let note = strip(&REF.replace_all(part, "")).to_string();
            if m.is_some() || !note.is_empty() {
                specs.push(LayerSpec {
                    ref_: m.map(|c| strip(&c[1]).to_string()),
                    note,
                });
            }
        }
        rows.push(LayerRow {
            patterns,
            name: cs[1].clone(),
            specs,
            line: i as i64 + 1,
        });
    }
    rows
}

/// 경로 꼴 → 정규식. `**`는 여러 단, `*`는 한 단(`/` 빼고). 경로 전체가 맞아야 한다.
/// 파이썬 `.`은 줄바꿈을 빼고 맞추고 `[^/]`는 줄바꿈도 맞춘다 — 그대로
fn glob(pattern: &str) -> Regex {
    let mut out = String::from("^(?:");
    let mut rest = pattern;
    while let Some(c) = rest.chars().next() {
        if let Some(r) = rest.strip_prefix("**") {
            out.push_str("[^\\n]*");
            rest = r;
        } else if c == '*' {
            out.push_str("[^/]*");
            rest = &rest[1..];
        } else {
            out.push_str(&regex::escape(&c.to_string()));
            rest = &rest[c.len_utf8()..];
        }
    }
    out.push_str(")\\z");
    Regex::new(&out).unwrap_or_else(|_| Regex::new("^\\z").expect("빈 꼴"))
}

/// SYNC-MS-022#codegraph.layers
///
/// 항목 없는 함수마다 층 — 같은 파일에 항목 있는 함수가 있으면 「도우미」, 아니면 표 위에서부터 첫 일치 줄.
/// 모든 함수와 대조해 하나도 안 맞는 줄도 돌려준다
pub fn layers(graph: &Graph, rows: &[LayerRow]) -> (HashMap<String, Layer>, Vec<LayerRow>) {
    let compiled: Vec<Vec<Regex>> = rows
        .iter()
        .map(|r| r.patterns.iter().map(|p| glob(p)).collect())
        .collect();
    let has = |f: &Function| {
        f.item.as_deref().is_some_and(|s| !s.is_empty())
            || f.ms.as_deref().is_some_and(|s| !s.is_empty())
    };
    let has_item: HashSet<&str> = graph
        .functions
        .iter()
        .filter(|f| has(f))
        .map(|f| f.file.as_str())
        .collect();
    let mut used = vec![false; rows.len()];
    let mut out = HashMap::new();
    for f in &graph.functions {
        let mut hit = None;
        for (i, pats) in compiled.iter().enumerate() {
            if pats.iter().any(|p| p.is_match(&f.file)) {
                used[i] = true;
                hit.get_or_insert(i);
            }
        }
        if has(f) {
            continue; // 항목이 먼저
        }
        if has_item.contains(f.file.as_str()) {
            out.insert(
                f.key.clone(),
                Layer {
                    name: HELPER.into(),
                    specs: Vec::new(),
                },
            );
        } else if let Some(h) = hit {
            out.insert(
                f.key.clone(),
                Layer {
                    name: rows[h].name.clone(),
                    specs: rows[h].specs.clone(),
                },
            );
        }
    }
    let unused = rows
        .iter()
        .zip(used)
        .filter(|(_, u)| !u)
        .map(|(r, _)| r.clone())
        .collect();
    (out, unused)
}
