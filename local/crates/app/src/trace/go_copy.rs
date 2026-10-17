//! Go 실행 기록 준비 (SYNC-MS-027#trace.go_overlay, 카드 L34) — view_arc `native/go.mts`를 옮겼다.
//! 그래프에 있는 함수의 첫머리에 도우미 호출을 끼운 사본과 도우미 패키지(`<모듈>/syncdoctrace`)를 캐시 자리에 쓰고,
//! `GOFLAGS=-overlay=<겹침 JSON>`으로 빌드가 원본 대신 그것을 보게 한다. 원본은 고치지 않는다.
//!
//! ```text
//! func (s *Service) Find(id string) (*User, error) {
//! → func (s *Service) Find(id string) (*User, error) { defer syncdoctrace.Exit(syncdoctrace.Enter("svc/user.go:12", "id", id));
//! ```
//! 끼우는 자리는 같은 줄이라 줄 번호(패닉 위치·디버거)가 원본과 같다. import도 package 줄 끝에 붙인다.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};

use regex::Regex;
use serde_json::json;

use super::rust_copy::Span;

const HELPER: &str = "syncdoctrace";

/// 주석·문자열·룬·원시 문자열을 공백으로(줄바꿈은 남겨 자리 그대로). 바이트로 훑는다 — 구분자는 ASCII라 글자 경계가 안 깨진다
pub fn mask(src: &str) -> Vec<u8> {
    let s = src.as_bytes();
    let n = s.len();
    let mut out = Vec::with_capacity(n);
    let blank = |out: &mut Vec<u8>, a: usize, b: usize| {
        out.extend(
            s[a..b]
                .iter()
                .map(|&c| if c == b'\n' { b'\n' } else { b' ' }),
        );
    };
    let find = |from: usize, pat: &[u8]| -> Option<usize> {
        s.get(from..)?
            .windows(pat.len())
            .position(|w| w == pat)
            .map(|p| p + from)
    };
    let mut i = 0;
    while i < n {
        let c = s[i];
        let d = s.get(i + 1).copied();
        if c == b'/' && d == Some(b'/') {
            let end = find(i, b"\n").unwrap_or(n);
            blank(&mut out, i, end);
            i = end;
        } else if c == b'/' && d == Some(b'*') {
            let end = find(i + 2, b"*/").map_or(n, |e| e + 2);
            blank(&mut out, i, end);
            i = end;
        } else if c == b'`' {
            let end = find(i + 1, b"`").map_or(n, |e| e + 1);
            blank(&mut out, i, end);
            i = end;
        } else if c == b'"' || c == b'\'' {
            let mut j = i + 1;
            while j < n && s[j] != c && s[j] != b'\n' {
                j += if s[j] == b'\\' { 2 } else { 1 };
            }
            let end = n.min(j + 1);
            blank(&mut out, i, end);
            i = j + 1;
        } else {
            out.push(c);
            i += 1;
        }
    }
    out.truncate(n);
    out
}

fn enter(id: &str, names: &[String]) -> String {
    let q = |s: &str| serde_json::to_string(s).unwrap_or_default();
    let kv: Vec<String> = names.iter().map(|n| format!("{}, {n}", q(n))).collect();
    let tail = if kv.is_empty() {
        String::new()
    } else {
        format!(", {}", kv.join(", "))
    };
    format!(" defer {HELPER}.Exit({HELPER}.Enter({}{tail}));", q(id))
}

/// 여는 괄호에서 짝 닫는 괄호 자리
fn matching(code: &[u8], open: usize, a: u8, b: u8) -> Option<usize> {
    let mut depth = 0i32;
    for (i, &c) in code.iter().enumerate().skip(open) {
        if c == a {
            depth += 1;
        } else if c == b {
            depth -= 1;
            if depth == 0 {
                return Some(i);
            }
        }
    }
    None
}

fn is_ident(w: &str) -> bool {
    let mut cs = w.chars();
    cs.next()
        .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
        && cs.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// 매개변수 이름 — 이름이 하나라도 있으면 각 칸의 첫 낱말(`a, b int`의 a 포함), 없으면 이름 없음. `_`는 뺀다
fn param_names(params: &str) -> Vec<String> {
    let mut parts: Vec<String> = Vec::new();
    let mut depth = 0i32;
    let mut cur = String::new();
    for ch in params.chars() {
        if "([{".contains(ch) {
            depth += 1;
        }
        if ")]}".contains(ch) {
            depth -= 1;
        }
        if ch == ',' && depth == 0 {
            parts.push(std::mem::take(&mut cur));
        } else {
            cur.push(ch);
        }
    }
    if !cur.trim().is_empty() {
        parts.push(cur);
    }
    let words: Vec<Vec<&str>> = parts
        .iter()
        .map(|p| p.split_whitespace().collect())
        .collect();
    if !words.iter().any(|w| w.len() > 1) {
        return Vec::new();
    }
    words
        .iter()
        .filter_map(|w| w.first())
        .filter(|n| is_ident(n) && **n != "_")
        .map(|n| (*n).to_string())
        .collect()
}

/// SYNC-MS-027#trace.instrument_go
///
/// 범위의 함수 몸통 첫머리에 Enter·Exit를 끼운다. 라우트 함수 안의 핸들러 함수 리터럴(요청·응답·프레임워크 문맥을 받는 것)에도
/// 같은 열쇠로 끼운다 — 등록 때 핸들러를 돌려주는 함수는 그 안 리터럴이 실제 요청을 받는다. 끼운 것이 없으면 없음
pub fn instrument_go(
    source: &str,
    spans: &[Span],
    import_path: &str,
    routes: &HashSet<String>,
) -> Option<String> {
    let handler =
        Regex::new(r"\bhttp\.ResponseWriter\b|\*http\.Request\b|\*gin\.Context\b|\becho\.Context\b|\*fiber\.Ctx\b")
            .expect("handler");
    let fn_kw = Regex::new(r"\bfunc\b").expect("func");
    let lit_re = Regex::new(r"\bfunc\s*\(").expect("lit");
    let cont = Regex::new(r"[,(]\s*$").expect("cont");
    let typed = Regex::new(r"\b(struct|interface)\s*$").expect("typed");
    let pkg_re = Regex::new(r"(?m)^[ \t]*package[ \t]+\w+").expect("package");
    let code = mask(source);
    let text = |a: usize, b: usize| String::from_utf8_lossy(&code[a..b]).into_owned();
    let mut line_start = vec![0usize];
    for (i, &c) in code.iter().enumerate() {
        if c == b'\n' {
            line_start.push(i + 1);
        }
    }
    let mut inserts: Vec<(usize, String)> = Vec::new();
    for (line, _, id) in spans {
        let Some(&from) = usize::try_from(*line - 1)
            .ok()
            .and_then(|l| line_start.get(l))
        else {
            continue;
        };
        let line_end = code[from..]
            .iter()
            .position(|&c| c == b'\n')
            .map_or(code.len(), |p| from + p);
        let Some(fn_at) = fn_kw.find(&text(from, line_end)).map(|m| m.start()) else {
            continue;
        };
        let mut i = from + fn_at + 4;
        let skip_ws = |i: &mut usize| {
            while *i < code.len() && matches!(code[*i], b' ' | b'\t') {
                *i += 1;
            }
        };
        skip_ws(&mut i);
        if code.get(i) == Some(&b'(') {
            // 받는 쪽 (s *Service)
            let Some(close) = matching(&code, i, b'(', b')') else {
                continue;
            };
            i = close + 1;
            skip_ws(&mut i);
        }
        while i < code.len() && (code[i].is_ascii_alphanumeric() || code[i] == b'_') {
            i += 1;
        }
        skip_ws(&mut i);
        if code.get(i) == Some(&b'[') {
            let Some(close) = matching(&code, i, b'[', b']') else {
                continue;
            };
            i = close + 1;
            skip_ws(&mut i);
        }
        if code.get(i) != Some(&b'(') {
            continue;
        }
        let Some(p_close) = matching(&code, i, b'(', b')') else {
            continue;
        };
        let names = param_names(&text(i + 1, p_close));
        // 결과 뒤 깊이 0의 첫 { (struct{…}·interface{…} 결과 타입은 건너뛴다)
        let mut depth = 0i32;
        let mut body = None;
        let mut k = p_close + 1;
        while k < code.len() {
            let ch = code[k];
            if ch == b'(' || ch == b'[' {
                depth += 1;
            } else if ch == b')' || ch == b']' {
                depth -= 1;
            } else if depth == 0 && ch == b'\n' && !cont.is_match(&text(p_close + 1, k)) {
                break; // 몸통 없는 선언
            } else if depth == 0 && ch == b'{' {
                if typed.is_match(&text(p_close + 1, k)) {
                    let Some(close) = matching(&code, k, b'{', b'}') else {
                        break;
                    };
                    k = close + 1;
                    continue;
                }
                body = Some(k);
                break;
            }
            k += 1;
        }
        let Some(body) = body else { continue };
        inserts.push((body + 1, enter(id, &names)));
        if !routes.contains(id) {
            continue;
        }
        let end = matching(&code, body, b'{', b'}').unwrap_or(code.len());
        let inner = text(body + 1, end);
        for lit in lit_re.find_iter(&inner) {
            let open = body + 1 + lit.end() - 1;
            let Some(close) = matching(&code, open, b'(', b')') else {
                continue;
            };
            if !handler.is_match(&source[open..close]) {
                continue;
            }
            let Some(brace) = code[close..]
                .iter()
                .position(|&c| c == b'{')
                .map(|p| close + p)
            else {
                continue;
            };
            if code[close + 1..brace].contains(&b'\n') {
                continue;
            }
            inserts.push((brace + 1, enter(id, &param_names(&text(open + 1, close)))));
        }
    }
    if inserts.is_empty() {
        return None;
    }
    let pkg_end = pkg_re.find(&text(0, code.len()))?.end();
    inserts.push((
        pkg_end,
        format!(
            "; import {HELPER} {}",
            serde_json::to_string(import_path).unwrap_or_default()
        ),
    ));
    inserts.sort_by_key(|(p, _)| *p);
    let mut out = String::with_capacity(source.len() + inserts.len() * 80);
    let mut at = 0;
    for (pos, t) in inserts {
        out.push_str(&source[at..pos]);
        out.push_str(&t);
        at = pos;
    }
    out.push_str(&source[at..]);
    Some(out)
}

/// 파일에서 위로 가장 가까운 go.mod — (모듈 뿌리, 모듈 경로)
fn module_of(
    file: &Path,
    cache: &mut HashMap<PathBuf, Option<(PathBuf, String)>>,
) -> Option<(PathBuf, String)> {
    let dir = file.parent()?.to_path_buf();
    if let Some(hit) = cache.get(&dir) {
        return hit.clone();
    }
    let mut found = std::fs::read_to_string(dir.join("go.mod"))
        .ok()
        .and_then(|t| {
            t.lines().find_map(|l| {
                l.strip_prefix("module")
                    .filter(|r| r.starts_with([' ', '\t']))
                    .and_then(|r| r.split_whitespace().next())
                    .map(|m| (dir.clone(), m.to_string()))
            })
        });
    if found.is_none() && dir.parent().is_some() {
        found = module_of(&dir, cache);
    }
    cache.insert(dir, found.clone());
    found
}

/// 겹침 준비 결과 — 겹침 JSON 자리와 계측한 파일 수
pub struct Overlay {
    pub json: PathBuf,
    pub instrumented: usize,
}

/// SYNC-MS-027#trace.go_overlay
///
/// 범위의 `.go`(테스트 빼고)를 계측한 사본과 모듈마다 도우미 패키지를 `out`에 쓰고 겹침 JSON(`{"Replace": {원본: 사본}}`)을 만든다
pub fn go_overlay(
    files: &[(PathBuf, Vec<Span>)],
    routes: &HashSet<String>,
    helper_src: &str,
    out: &Path,
) -> Result<Overlay, String> {
    let _ = std::fs::remove_dir_all(out);
    let mut replace: BTreeMap<String, String> = BTreeMap::new();
    let mut mods: HashMap<PathBuf, Option<(PathBuf, String)>> = HashMap::new();
    let mut helpers: Vec<PathBuf> = Vec::new();
    let mut instrumented = 0;
    for (file, spans) in files {
        let name = file.to_string_lossy();
        if !name.ends_with(".go") || name.ends_with("_test.go") {
            continue;
        }
        let Some((root, module)) = module_of(file, &mut mods) else {
            continue;
        };
        let Ok(text) = std::fs::read_to_string(file) else {
            continue;
        };
        let Some(result) = instrument_go(&text, spans, &format!("{module}/{HELPER}"), routes)
        else {
            continue;
        };
        let rel: PathBuf = file
            .components()
            .filter(|c| matches!(c, std::path::Component::Normal(_)))
            .collect();
        let copy = out.join("files").join(rel);
        std::fs::create_dir_all(copy.parent().unwrap_or(out)).map_err(|e| e.to_string())?;
        std::fs::write(&copy, result).map_err(|e| e.to_string())?;
        replace.insert(name.into_owned(), copy.to_string_lossy().into_owned());
        instrumented += 1;
        if !helpers.contains(&root) {
            helpers.push(root.clone());
            let helper = out
                .join("helpers")
                .join(helpers.len().to_string())
                .join(format!("{HELPER}.go"));
            std::fs::create_dir_all(helper.parent().unwrap_or(out)).map_err(|e| e.to_string())?;
            std::fs::write(&helper, helper_src).map_err(|e| e.to_string())?;
            replace.insert(
                root.join(HELPER)
                    .join(format!("{HELPER}.go"))
                    .to_string_lossy()
                    .into_owned(),
                helper.to_string_lossy().into_owned(),
            );
        }
    }
    if instrumented == 0 {
        return Err(
            "기록할 Go 함수를 그래프에서 찾지 못했다 — 코드를 push해 그래프를 다시 만드세요".into(),
        );
    }
    let json_path = out.join("overlay.json");
    std::fs::write(
        &json_path,
        serde_json::to_string_pretty(&json!({ "Replace": replace })).unwrap_or_default(),
    )
    .map_err(|e| e.to_string())?;
    Ok(Overlay {
        json: json_path,
        instrumented,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const SRC: &str = "package main\n\nimport \"net/http\"\n\n// 주석 func x() {\nfunc (s *Server) hello(w http.ResponseWriter, r *http.Request) {\n\tw.Write([]byte(\"}\"))\n}\n\nfunc pair(a, b int) (int, error) {\n\treturn a + b, nil\n}\n\nfunc routes() http.Handler {\n\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {\n\t})\n}\n\ntype I interface {\n\tM() int\n}\n\nfunc gen[T any](x T) struct{ v T } {\n\treturn struct{ v T }{x}\n}\n";

    #[test]
    fn masks_strings_comments_and_keeps_length() {
        let m = mask("a := \"x{\" // }\nb := `}\n` + 'c'\n");
        assert_eq!(m.len(), "a := \"x{\" // }\nb := `}\n` + 'c'\n".len());
        let t = String::from_utf8(m).expect("utf8");
        assert!(!t.contains('{') && !t.contains('}'));
        assert_eq!(t.matches('\n').count(), 3);
    }

    #[test]
    fn instruments_bodies_on_the_same_line() {
        let spans: Vec<Span> = vec![
            (6, 8, "main.go:6".into()),
            (10, 12, "main.go:10".into()),
            (14, 17, "main.go:14".into()),
            (23, 25, "main.go:23".into()),
        ];
        let routes: HashSet<String> = ["main.go:14".to_string()].into_iter().collect();
        let out = instrument_go(SRC, &spans, "ex.com/m/syncdoctrace", &routes).expect("계측");
        assert_eq!(out.lines().count(), SRC.lines().count()); // 줄 수 그대로
        let line = |n: usize| out.lines().nth(n - 1).unwrap_or_default().to_string();
        assert!(line(1).ends_with("package main; import syncdoctrace \"ex.com/m/syncdoctrace\""));
        assert!(line(6).ends_with(
            r#"{ defer syncdoctrace.Exit(syncdoctrace.Enter("main.go:6", "w", w, "r", r));"#
        ));
        assert!(line(10).contains(r#"Enter("main.go:10", "a", a, "b", b)"#));
        assert!(
            line(14).ends_with(r#"{ defer syncdoctrace.Exit(syncdoctrace.Enter("main.go:14"));"#)
        );
        assert!(line(15).contains(r#"Enter("main.go:14", "w", w, "r", r)"#)); // 라우트 안 핸들러 리터럴
        assert!(line(23).contains(r#"Enter("main.go:23", "x", x)"#)); // 제네릭·struct 결과
        assert!(!out.contains("주석 func x() { defer")); // 주석 안은 아니다
        assert!(!line(20).contains("Enter")); // 인터페이스 메서드
    }

    #[test]
    fn param_names_need_a_type() {
        assert_eq!(param_names("a, b int"), ["a", "b"]);
        assert!(param_names("int, string").is_empty());
        assert_eq!(param_names("_ int, f func(int) error"), ["f"]);
    }
}
