//! 흐름 보기의 더하기 — 코드 그래프 값에 흐름 키를 더한다 (SYNC-MS-026, 카드 L22~L24).
//! 파이썬 판 `core/codegraph/flow.py`와 같은 처리·같은 결과(바이트)다. 흐름 키는 `Graph` 구조체가 아니라 직렬화한
//! 그래프 값에 더한다 — 줄이기의 `files`(이름 목록)와 흐름의 `files`(객체 목록)가 이름이 같아서다(MS-026 0장).

use std::path::Path;

use regex::Regex;
use serde_json::{Map, Value, json};
use tree_sitter::{Node, Parser, Tree};

use syncdoc_pycompat::chars::{is_space, strip};

use crate::graph::{CODE_EXTS, is_test};
use crate::{infra, routes, steps};

/// 모든 흐름 함수가 건너뛰는 폴더 (MS-024 0장) — 이름이 `.`으로 시작하는 폴더도
pub(crate) const SKIP_DIRS: [&str; 12] = [
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "out",
    "venv",
    ".venv",
    "__pycache__",
    "site-packages",
    "coverage",
    "graphify-out",
];
const LABEL_MAX: usize = 70;
const BOM: &[u8] = b"\xef\xbb\xbf";

// ---------------------------------------------------------------- 공용 도우미

/// 파일을 읽어 BOM을 떼고 UTF-8인지 본다. 못 읽거나 UTF-8이 아니면 없음
pub(crate) fn read(src_dir: &Path, file: &str) -> Option<Vec<u8>> {
    let mut src = std::fs::read(src_dir.join(file)).ok()?;
    if src.starts_with(BOM) {
        src.drain(..BOM.len());
    }
    std::str::from_utf8(&src).ok()?;
    Some(src)
}

pub(crate) fn ts_parse(file: &str, src: &[u8]) -> Option<Tree> {
    let lang = if file.ends_with(".tsx") || file.ends_with(".jsx") {
        tree_sitter_typescript::LANGUAGE_TSX
    } else {
        tree_sitter_typescript::LANGUAGE_TYPESCRIPT
    };
    let mut p = Parser::new();
    p.set_language(&lang.into()).ok()?;
    p.parse(src, None)
}

pub(crate) fn rs_parse(src: &[u8]) -> Option<Tree> {
    let mut p = Parser::new();
    p.set_language(&tree_sitter_rust::LANGUAGE.into()).ok()?;
    p.parse(src, None)
}

/// 노드의 글자 — 못 읽는 바이트는 대체 문자(파이썬 `decode(errors="replace")`)
pub(crate) fn text(n: Node, src: &[u8]) -> String {
    String::from_utf8_lossy(&src[n.start_byte()..n.end_byte()]).into_owned()
}

pub(crate) fn children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.children(&mut c).collect()
}

pub(crate) fn named_children<'t>(n: Node<'t>) -> Vec<Node<'t>> {
    let mut c = n.walk();
    n.named_children(&mut c).collect()
}

/// 앞차례 깊이 우선 — 파이썬 판 `_walk`(스택에 자식을 거꾸로)와 같은 차례
pub(crate) fn walk(root: Node) -> Vec<Node> {
    let mut out = Vec::new();
    let mut stack = vec![root];
    while let Some(n) = stack.pop() {
        out.push(n);
        let mut kids = children(n);
        kids.reverse();
        stack.extend(kids);
    }
    out
}

/// 괄호로만 싼 식 → 안쪽 식 (MS-024 steps 6)
pub(crate) fn unparen(mut n: Node) -> Node {
    while n.kind() == "parenthesized_expression" {
        let inner: Vec<Node> = named_children(n)
            .into_iter()
            .filter(|c| c.kind() != "comment")
            .collect();
        if inner.len() != 1 {
            break;
        }
        n = inner[0];
    }
    n
}

/// 공백 묶음을 한 칸으로 · 앞뒤 자르기 · `.` 앞뒤 한 칸 지우기 · 70자 넘으면 69자 + `…` (MS-024 steps 6)
pub(crate) fn label(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    let mut in_ws = false;
    for c in raw.chars() {
        if is_space(c) {
            if !in_ws {
                out.push(' ');
            }
            in_ws = true;
        } else {
            out.push(c);
            in_ws = false;
        }
    }
    let s = strip(&out).replace(" .", ".").replace(". ", ".");
    if s.chars().count() <= LABEL_MAX {
        s
    } else {
        let mut t: String = s.chars().take(LABEL_MAX - 1).collect();
        t.push('…');
        t
    }
}

/// 파이썬 `re.ASCII` 꼴 → regex crate 꼴 — `\w`·`\d`·`\s`를 ASCII 묶음으로 (MS-026 0장)
pub(crate) fn ascii(pattern: &str, ignore_case: bool) -> Regex {
    let mut out = String::with_capacity(pattern.len() + 16);
    let mut in_class = false;
    let mut chars = pattern.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' {
            let Some(&n) = chars.peek() else {
                out.push(c);
                continue;
            };
            chars.next();
            let set = match n {
                'w' => Some("0-9A-Za-z_"),
                'd' => Some("0-9"),
                's' => Some("\\t\\n\\x0B\\x0C\\r "),
                _ => None,
            };
            match set {
                Some(s) if in_class => out.push_str(s),
                Some(s) => {
                    out.push('[');
                    out.push_str(s);
                    out.push(']');
                }
                None => {
                    out.push('\\');
                    out.push(n);
                }
            }
            continue;
        }
        if c == '[' && !in_class {
            in_class = true;
        } else if c == ']' && in_class {
            in_class = false;
        }
        out.push(c);
    }
    let flags = if ignore_case { "(?i)" } else { "" };
    Regex::new(&format!("{flags}{out}")).expect("흐름 정규식")
}

/// 파일 확장자의 세 갈래 — 파이썬 `py` · TS/JS `ts` · Rust `rs`
pub(crate) fn lang_of(file: &str) -> Option<&'static str> {
    if file.ends_with(".py") {
        Some("py")
    } else if [".ts", ".tsx", ".js", ".jsx", ".mjs"]
        .iter()
        .any(|e| file.ends_with(e))
    {
        Some("ts")
    } else if file.ends_with(".rs") {
        Some("rs")
    } else {
        None
    }
}

/// src_dir 아래 파일의 '/' 경로 — 건너뛰는 폴더 빼고, 링크를 따르지 않는다
pub(crate) fn walk_files(src_dir: &Path) -> Vec<String> {
    let mut out = Vec::new();
    let mut stack = vec![(src_dir.to_path_buf(), String::new())];
    while let Some((dir, rel)) = stack.pop() {
        let Ok(rd) = std::fs::read_dir(&dir) else {
            continue;
        };
        for e in rd.flatten() {
            let Ok(ft) = e.file_type() else { continue };
            let name = e.file_name().to_string_lossy().into_owned();
            let r = if rel.is_empty() {
                name.clone()
            } else {
                format!("{rel}/{name}")
            };
            if ft.is_dir() {
                if !name.starts_with('.') && !SKIP_DIRS.contains(&name.as_str()) {
                    stack.push((e.path(), r));
                }
            } else if ft.is_file() {
                out.push(r);
            }
        }
    }
    out
}

fn loc(data: &[u8]) -> i64 {
    if data.is_empty() {
        return 0;
    }
    let n = data.iter().filter(|b| **b == b'\n').count() as i64;
    if data.ends_with(b"\n") { n } else { n + 1 }
}

/// SYNC-MS-026#flow.files
///
/// 저장소의 코드 파일 전부 — `{path, lang, loc}`, 경로 바이트 순. 테스트 파일은 뺀다.
pub fn files(src_dir: &Path) -> Vec<Value> {
    let mut paths: Vec<String> = walk_files(src_dir)
        .into_iter()
        .filter(|p| {
            let ext = match p.rfind('.') {
                Some(i) if !p[i..].contains('/') => p[i..].to_lowercase(),
                _ => String::new(),
            };
            CODE_EXTS.contains(&ext.as_str()) && !is_test(p)
        })
        .collect();
    paths.sort();
    paths
        .into_iter()
        .filter_map(|p| {
            let data = std::fs::read(src_dir.join(&p)).ok()?;
            let ext = p[p.rfind('.').unwrap_or(0)..].to_lowercase();
            let lang = match ext.as_str() {
                ".py" => "python".to_string(),
                ".ts" | ".tsx" => "typescript".to_string(),
                ".js" | ".jsx" | ".mjs" => "javascript".to_string(),
                ".rs" => "rust".to_string(),
                e => e.trim_start_matches('.').to_string(),
            };
            Some(json!({"path": p, "lang": lang, "loc": loc(&data)}))
        })
        .collect()
}

fn functions_mut(graph: &mut Value) -> Vec<&mut Map<String, Value>> {
    graph
        .get_mut("functions")
        .and_then(Value::as_array_mut)
        .map(|a| a.iter_mut().filter_map(Value::as_object_mut).collect())
        .unwrap_or_default()
}

/// SYNC-MS-026#flow.extend
///
/// 파일 목록 → 실행 단위 → 호출 순서 → 라우트 → 화면 요청 → 장비 차례로 더하고, 대상도 장비도 없는 호출을 지운다.
pub fn extend(src_dir: &Path, graph: &mut Value) {
    let Some(obj) = graph.as_object_mut() else {
        return;
    };
    obj.insert("files".into(), Value::Array(files(src_dir)));
    obj.insert("units".into(), Value::Array(infra::units(src_dir)));
    let idents = steps::steps(src_dir, graph);
    routes::routes(src_dir, graph);
    let http = routes::http_links(src_dir, graph);
    if let Some(o) = graph.as_object_mut() {
        o.insert("http".into(), Value::Array(http));
    }
    infra::infra(src_dir, graph, &idents);
    for f in functions_mut(graph) {
        f.entry("route").or_insert(Value::Null);
        let kept: Vec<Value> = f
            .get("steps")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter(|st| {
                        st["k"] != "call" || st.get("to").is_some() || st.get("infra").is_some()
                    })
                    .cloned()
                    .collect()
            })
            .unwrap_or_default();
        f.insert("steps".into(), Value::Array(kept));
    }
}
