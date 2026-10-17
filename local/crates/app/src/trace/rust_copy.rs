//! Rust 실행 기록 준비 — 작업 공간을 캐시 자리에 사본으로 뜨고(바뀐 것만) 그래프에 있는 함수의 첫머리에 도우미 호출을
//! 끼운 뒤 명령을 그 사본에서 돌린다. 원본은 고치지 않는다 (SYNC-MS-027#trace.copy_rust · view_arc native/rust.mts).
//!
//!   async fn get_user(State(state): State<AppState>, Path(id): Path<u64>) -> … {
//!   → … { use crate::syncdoc_trace::{ViaDebug as _, ViaAny as _}; let __va = crate::syncdoc_trace::enter("파일:줄", &[…]);
//!
//! 끼우는 자리는 같은 줄이라 줄 번호가 원본과 같다. 도우미 모듈은 크레이트 뿌리 끝줄에 `#[path]`로 붙인다.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use regex::Regex;

/// 함수 범위 하나 — (시작 줄, 끝 줄, 열쇠)
pub type Span = (i64, i64, String);

/// 주석(중첩)·문자열·원시 문자열·바이트 문자열·문자 리터럴을 공백으로(줄바꿈은 남긴다). 수명('a)은 남긴다.
/// 바이트 단위라 길이가 원본과 같다
pub fn mask(src: &str) -> Vec<u8> {
    let b = src.as_bytes();
    let n = b.len();
    let mut out = Vec::with_capacity(n);
    let blank = |out: &mut Vec<u8>, a: usize, z: usize| {
        out.extend(
            b[a..z]
                .iter()
                .map(|c| if *c == b'\n' { b'\n' } else { b' ' }),
        );
    };
    let word = |i: usize| i > 0 && (b[i - 1].is_ascii_alphanumeric() || b[i - 1] == b'_');
    let mut i = 0;
    while i < n {
        let c = b[i];
        let d = b.get(i + 1).copied().unwrap_or(0);
        if c == b'/' && d == b'/' {
            let end = b[i..].iter().position(|x| *x == b'\n').map_or(n, |p| i + p);
            blank(&mut out, i, end);
            i = end;
        } else if c == b'/' && d == b'*' {
            let mut depth = 1;
            let mut j = i + 2;
            while j < n && depth > 0 {
                if b[j] == b'/' && b.get(j + 1) == Some(&b'*') {
                    depth += 1;
                    j += 2;
                } else if b[j] == b'*' && b.get(j + 1) == Some(&b'/') {
                    depth -= 1;
                    j += 2;
                } else {
                    j += 1;
                }
            }
            let j = j.min(n);
            blank(&mut out, i, j);
            i = j;
        } else if (c == b'r' || (c == b'b' && d == b'r')) && !word(i) && raw_open(&b[i..]).is_some()
        {
            let (len, hashes) = raw_open(&b[i..]).unwrap_or((0, 0));
            let mut close = vec![b'"'];
            close.extend(std::iter::repeat_n(b'#', hashes));
            let from = i + len;
            let end = find(&b[from..], &close).map_or(n, |p| from + p + close.len());
            blank(&mut out, i, end);
            i = end;
        } else if c == b'"' || (c == b'b' && d == b'"' && !word(i)) {
            let mut j = i + if c == b'b' { 2 } else { 1 };
            while j < n && b[j] != b'"' {
                j += if b[j] == b'\\' { 2 } else { 1 };
            }
            let end = (j + 1).min(n);
            blank(&mut out, i, end);
            i = end;
        } else if c == b'\'' {
            match char_lit(&b[i..]) {
                Some(len) => {
                    blank(&mut out, i, i + len);
                    i += len;
                }
                None => {
                    out.push(c);
                    i += 1;
                }
            }
        } else {
            out.push(c);
            i += 1;
        }
    }
    out
}

/// `r"`·`r#"`·`br##"` 꼴의 시작 — (여는 길이, # 수)
fn raw_open(s: &[u8]) -> Option<(usize, usize)> {
    let mut k = if s.first() == Some(&b'b') { 1 } else { 0 };
    if s.get(k) != Some(&b'r') {
        return None;
    }
    k += 1;
    let mut hashes = 0;
    while s.get(k) == Some(&b'#') && hashes < 10 {
        hashes += 1;
        k += 1;
    }
    (s.get(k) == Some(&b'"')).then_some((k + 1, hashes))
}

fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
    hay.windows(needle.len()).position(|w| w == needle)
}

/// `'a'` · `'\n'` · `'\u{1F600}'` · `'\x41'`은 문자, `'a`(수명)는 아니다 — 문자면 길이
fn char_lit(s: &[u8]) -> Option<usize> {
    if s.get(1) == Some(&b'\\') {
        let rest = &s[2..];
        let body = match rest.first()? {
            b'u' if rest.get(1) == Some(&b'{') => {
                let close = rest.iter().position(|c| *c == b'}')?;
                close + 1
            }
            b'x' => 3,
            _ => 1,
        };
        return (s.get(2 + body) == Some(&b'\'')).then_some(3 + body);
    }
    // 글자 하나(UTF-8 여러 바이트일 수 있다) 뒤에 '
    let first = *s.get(1)?;
    if first == b'\'' || first == b'\n' {
        return None;
    }
    let width = match first {
        0x00..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        _ => 4,
    };
    (s.get(1 + width) == Some(&b'\'')).then_some(2 + width)
}

fn matching(code: &[u8], open: usize, a: u8, z: u8) -> Option<usize> {
    let mut depth = 0i32;
    for (i, c) in code.iter().enumerate().skip(open) {
        if *c == a {
            depth += 1;
        } else if *c == z {
            depth -= 1;
            if depth == 0 {
                return Some(i);
            }
        }
    }
    None
}

static SELF_PARAM: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(&\s*('\w+\s+)?(mut\s+)?)?(mut\s+)?self\b").expect("self"));
static NAME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b[a-z_][A-Za-z0-9_]*\b").expect("name"));
static FN: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\bfn\s+[A-Za-z_]\w*").expect("fn"));
static CONST_FN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\bconst\s+(?:unsafe\s+)?$").expect("const"));

/// 매개변수 이름 — 칸마다 맨 위 `:` 앞 패턴의 낱말(mut·ref·_ 빼고), self 포함
fn param_names(params: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut depth = 0i32;
    let mut cur = String::new();
    for ch in params.chars() {
        if "([{<".contains(ch) {
            depth += 1;
        }
        if ")]}>".contains(ch) {
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
    let mut names: Vec<String> = Vec::new();
    for p in parts {
        let t = p.trim();
        if SELF_PARAM.is_match(t) {
            names.push("self".into());
            continue;
        }
        let tb: Vec<char> = t.chars().collect();
        let mut d = 0i32;
        let mut colon = None;
        for k in 0..tb.len() {
            let c = tb[k];
            if "([{<".contains(c) {
                d += 1;
            } else if ")]}>".contains(c) {
                d -= 1;
            } else if c == ':'
                && d == 0
                && tb.get(k + 1) != Some(&':')
                && (k == 0 || tb[k - 1] != ':')
            {
                colon = Some(k);
                break;
            }
        }
        let Some(colon) = colon else { continue };
        let head: String = tb[..colon].iter().collect();
        for w in NAME.find_iter(&head) {
            if !["mut", "ref", "_"].contains(&w.as_str()) {
                names.push(w.as_str().to_string());
            }
        }
    }
    let mut seen = BTreeSet::new();
    names.retain(|n| seen.insert(n.clone()));
    names
}

fn quote(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into())
}

/// 범위의 함수 몸통 첫머리에 `enter`를 끼운다. 끼운 것이 없으면 없음
pub fn instrument(source: &str, spans: &[Span]) -> Option<String> {
    let code = mask(source);
    let text = String::from_utf8_lossy(&code).into_owned();
    let mut line_start = vec![0usize];
    for (i, c) in code.iter().enumerate() {
        if *c == b'\n' {
            line_start.push(i + 1);
        }
    }
    let mut inserts: Vec<(usize, String)> = Vec::new();
    for (line, end, id) in spans {
        let Some(&from) = usize::try_from(line - 1)
            .ok()
            .and_then(|l| line_start.get(l))
        else {
            continue;
        };
        let until = usize::try_from(*end)
            .ok()
            .and_then(|e| line_start.get(e).copied())
            .unwrap_or(code.len());
        let Some(slice) = text.get(from..until.max(from)) else {
            continue;
        };
        let Some(fm) = FN.find(slice) else { continue };
        if CONST_FN.is_match(&text[from..from + fm.start()]) {
            continue; // const fn 안에서는 부를 수 없다
        }
        let mut i = from + fm.end();
        while code.get(i).is_some_and(u8::is_ascii_whitespace) {
            i += 1;
        }
        if code.get(i) == Some(&b'<') {
            let mut d = 0i32;
            while i < code.len() {
                if code[i] == b'<' {
                    d += 1;
                } else if code[i] == b'>' && code.get(i.wrapping_sub(1)) != Some(&b'-') {
                    d -= 1;
                    if d == 0 {
                        break;
                    }
                }
                i += 1;
            }
            i += 1;
            while code.get(i).is_some_and(u8::is_ascii_whitespace) {
                i += 1;
            }
        }
        if code.get(i) != Some(&b'(') {
            continue;
        }
        let Some(close) = matching(&code, i, b'(', b')') else {
            continue;
        };
        let names = param_names(&text[i + 1..close]);
        // 반환·where 뒤 깊이 0의 첫 { — ; 가 먼저면 몸통 없음(트레이트 선언)
        let mut body = None;
        let (mut angle, mut paren) = (0i32, 0i32);
        for k in close + 1..code.len() {
            let ch = code[k];
            let prev = code.get(k.wrapping_sub(1)).copied().unwrap_or(0);
            match ch {
                b'(' | b'[' => paren += 1,
                b')' | b']' => paren -= 1,
                b'<' => angle += 1,
                b'>' if prev != b'-' && prev != b'=' => angle = (angle - 1).max(0),
                b';' if paren == 0 && angle == 0 => break,
                b'{' if paren == 0 && angle == 0 => {
                    body = Some(k);
                    break;
                }
                _ => {}
            }
        }
        let Some(body) = body else { continue };
        let args: Vec<String> = names
            .iter()
            .map(|n| format!("({}, (&crate::syncdoc_trace::W(&{n})).va())", quote(n)))
            .collect();
        let use_ = if names.is_empty() {
            String::new()
        } else {
            " #[allow(unused_imports)] use crate::syncdoc_trace::{ViaDebug as _, ViaAny as _};"
                .into()
        };
        inserts.push((
            body + 1,
            format!(
                "{use_} let __va = crate::syncdoc_trace::enter({}, &[{}]);",
                quote(id),
                args.join(", ")
            ),
        ));
    }
    if inserts.is_empty() {
        return None;
    }
    inserts.sort_by_key(|x| x.0);
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

static TOML_NAME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"(?s)\[package\][^\[]*?\bname\s*=\s*"([^"]+)""#).expect("toml"));
static LIB_NAME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"(?s)\[lib\][^\[]*?\bname\s*=\s*"([^"]+)""#).expect("toml"));
static LIB_PATH: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"(?s)\[lib\][^\[]*?\bpath\s*=\s*"([^"]+)""#).expect("toml"));
static BIN_PATH: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"(?s)\[\[bin\]\][^\[]*?\bpath\s*=\s*"([^"]+)""#).expect("toml"));
static WORKSPACE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^\[workspace\]").expect("ws"));
static PACKAGE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?m)^\[package\]").expect("pkg"));

/// cwd에서 위로 — Cargo.toml이 있는 패키지, 그 위에 `[workspace]`가 있으면 그곳이 뿌리
pub fn workspace_root(cwd: &Path) -> Option<PathBuf> {
    let (mut pkg, mut ws) = (None, None);
    let mut dir = Some(cwd);
    while let Some(d) = dir {
        let toml = d.join("Cargo.toml");
        if let Ok(text) = std::fs::read_to_string(&toml) {
            pkg.get_or_insert_with(|| d.to_path_buf());
            if WORKSPACE.is_match(&text) {
                ws = Some(d.to_path_buf());
            }
        }
        dir = d.parent();
    }
    ws.or(pkg)
}

/// 원본 → 사본(바뀐 것만) — 건너뛸 폴더 이름
fn copy_tree(from: &Path, to: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(to)?;
    for e in std::fs::read_dir(from)? {
        let e = e?;
        let name = e.file_name();
        if matches!(name.to_str(), Some("target" | ".git" | "node_modules")) {
            continue;
        }
        let (a, b) = (e.path(), to.join(&name));
        let ft = e.file_type()?;
        if ft.is_dir() {
            copy_tree(&a, &b)?;
        } else if ft.is_file() {
            let sa = std::fs::metadata(&a)?;
            let same = std::fs::metadata(&b)
                .is_ok_and(|sb| sb.len() == sa.len() && sb.modified().ok() >= sa.modified().ok());
            if !same {
                std::fs::copy(&a, &b)?;
            }
        }
    }
    Ok(())
}

fn cargo_tomls(dir: &Path, depth: usize, out: &mut Vec<PathBuf>) {
    if depth > 4 {
        return;
    }
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for e in rd.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        if name == "target" || name.starts_with('.') {
            continue;
        }
        let p = e.path();
        if e.file_type().is_ok_and(|t| t.is_dir()) {
            cargo_tomls(&p, depth + 1, out);
        } else if name == "Cargo.toml" {
            out.push(p);
        }
    }
}

/// 사본 준비의 결과 — 사본에서 돌 자리와 계측한 파일 수
pub struct Prepared {
    pub cwd: PathBuf,
    pub instrumented: usize,
}

/// SYNC-MS-027#trace.copy_rust
///
/// 작업 공간을 사본으로 뜨고(바뀐 것만), 범위의 함수에 `enter`를 끼우고, 크레이트 뿌리마다 도우미 모듈을 붙인다.
/// files는 절대 경로 → 범위. helper는 표를 채운 도우미 파일
pub fn copy_rust(
    cwd: &Path,
    files: &[(PathBuf, Vec<Span>)],
    copy: &Path,
    helper: &Path,
) -> Result<Prepared, String> {
    let root = workspace_root(cwd)
        .ok_or("Cargo.toml을 찾지 못했다 — --cwd를 Rust 패키지 폴더로 주세요")?;
    copy_tree(&root, copy).map_err(|e| format!("사본을 뜨지 못했다: {e}"))?;
    let spans_of = |f: &Path| -> Vec<Span> {
        files
            .iter()
            .find(|(p, _)| p == f)
            .map(|(_, s)| s.clone())
            .unwrap_or_default()
    };
    let fresh = |orig: &Path| -> String {
        let text = std::fs::read_to_string(orig).unwrap_or_default();
        instrument(&text, &spans_of(orig)).unwrap_or(text)
    };
    let mut instrumented = 0;
    for (file, list) in files {
        let Ok(rel) = file.strip_prefix(&root) else {
            continue;
        };
        if file.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(file) else {
            continue;
        };
        let dest = copy.join(rel);
        match instrument(&text, list) {
            Some(out) => {
                std::fs::write(&dest, out).map_err(|e| e.to_string())?;
                instrumented += 1;
            }
            // 전에 계측한 사본이 남지 않게
            None => {
                std::fs::write(&dest, text).map_err(|e| e.to_string())?;
            }
        }
    }
    if instrumented == 0 {
        return Err(
            "기록할 Rust 함수를 그래프에서 찾지 못했다 — 코드를 push해 그래프를 새로 만드세요"
                .into(),
        );
    }
    let helper_path = quote(&helper.to_string_lossy());
    let module = |vis: &str| {
        format!(
            "\n#[doc(hidden)]\n#[allow(dead_code, unused_imports)]\n#[path = {helper_path}]\n{vis}mod syncdoc_trace;\n"
        )
    };
    let mut tomls = Vec::new();
    cargo_tomls(copy, 0, &mut tomls);
    for toml in tomls {
        let Ok(text) = std::fs::read_to_string(&toml) else {
            continue;
        };
        if !PACKAGE.is_match(&text) {
            continue;
        }
        let pkg_dir = toml.parent().unwrap_or(copy).to_path_buf();
        let orig_dir = root.join(pkg_dir.strip_prefix(copy).unwrap_or(Path::new("")));
        let lib_file = pkg_dir.join(
            LIB_PATH
                .captures(&text)
                .map_or("src/lib.rs".to_string(), |m| m[1].to_string()),
        );
        let lib_name = TOML_NAME
            .captures(&text)
            .map(|m| {
                LIB_NAME
                    .captures(&text)
                    .map_or(m[1].to_string(), |l| l[1].to_string())
            })
            .map(|n| n.replace('-', "_"));
        let lib = (lib_file.is_file() && lib_name.is_some())
            .then(|| (lib_name.unwrap_or_default(), lib_file));
        let mut bins: BTreeSet<PathBuf> = BTreeSet::new();
        if pkg_dir.join("src/main.rs").is_file() {
            bins.insert(pkg_dir.join("src/main.rs"));
        }
        if let Ok(rd) = std::fs::read_dir(pkg_dir.join("src/bin")) {
            for e in rd.flatten() {
                if e.path().extension().and_then(|x| x.to_str()) == Some("rs") {
                    bins.insert(e.path());
                }
            }
        }
        for m in BIN_PATH.captures_iter(&text) {
            bins.insert(pkg_dir.join(&m[1]));
        }
        let orig_of = |f: &Path| orig_dir.join(f.strip_prefix(&pkg_dir).unwrap_or(f));
        if let Some((_, file)) = &lib {
            let body = fresh(&orig_of(file)) + &module("pub ");
            std::fs::write(file, body).map_err(|e| e.to_string())?;
        }
        for bin in bins {
            let tail = match &lib {
                Some((name, _)) => {
                    format!("\n#[allow(unused_imports)]\nuse {name}::syncdoc_trace;\n")
                }
                None => module(""),
            };
            std::fs::write(&bin, fresh(&orig_of(&bin)) + &tail).map_err(|e| e.to_string())?;
        }
    }
    Ok(Prepared {
        cwd: copy.join(cwd.strip_prefix(&root).unwrap_or(Path::new(""))),
        instrumented,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn masks_strings_comments_and_keeps_lifetimes() {
        let src = "fn a<'x>(s: &'x str) { let c = '\\n'; let r = r#\"fn b()\"#; /* fn c() */ // fn d()\n}";
        let m = String::from_utf8(mask(src)).expect("utf8");
        assert_eq!(m.len(), src.len());
        assert!(
            m.contains("<'x>") && !m.contains("fn b") && !m.contains("fn c") && !m.contains("fn d")
        );
    }

    #[test]
    fn instruments_body_start_with_params() {
        let src = "pub async fn get(State(st): State<App>, Path(id): Path<u64>, token: String) -> u64 {\n    id\n}\n\ntrait T { fn x(&self); }\n";
        let out = instrument(
            src,
            &[(1, 3, "src/a.rs:1".into()), (5, 5, "src/a.rs:5".into())],
        )
        .expect("계측");
        let first = out.lines().next().unwrap_or_default();
        assert!(first.contains("enter(\"src/a.rs:1\""));
        assert!(
            first.contains("(\"st\", ")
                && first.contains("(\"id\", ")
                && first.contains("(\"token\", ")
        );
        assert_eq!(out.lines().count(), src.lines().count()); // 줄 번호 그대로
        assert!(!out.contains("src/a.rs:5")); // 몸통 없는 트레이트 선언
    }

    #[test]
    fn param_names_skip_patterns_and_types() {
        assert_eq!(
            param_names("&mut self, mut a: u8, (b, _c): (u8, u8), Json(d): Json<X>"),
            ["self", "a", "b", "_c", "d"]
        );
    }
}
