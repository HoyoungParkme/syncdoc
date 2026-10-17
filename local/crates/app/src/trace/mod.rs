//! 기록 도구 — `syncdoc-local trace`·`trace-web` 하위 명령 (SYNC-INFRA-001 9.9 · SYNC-MS-027, 카드 L29).
//! 사용자 프로그램을 기록기와 함께 띄우고, 기록을 개인 토큰으로 서버(두 판 어느 쪽이든)에 올린다. 서버(앱)를 켜지 않는다.
//! 기록기(Python·Node·브라우저·Rust 도우미)는 실행 파일에 담겨 있다가 임시 폴더에 풀린다. view_arc `trace.mts`를 옮겼다.

mod rust_copy;

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

use clap::Parser;
use rust_embed::RustEmbed;
use serde_json::{Map, Value, json};

pub use rust_copy::{copy_rust, instrument as instrument_rust, mask as mask_rust};

#[derive(RustEmbed)]
#[folder = "$CARGO_MANIFEST_DIR/tracers"]
struct Tracers;

/// Node 기록기가 쓰는 TypeScript 파서 — 화면 빌드와 같은 판(`frontend/node_modules/typescript`)
#[derive(RustEmbed)]
#[folder = "$CARGO_MANIFEST_DIR/../../../frontend/node_modules/typescript"]
#[include = "package.json"]
#[include = "lib/typescript.js"]
struct TypeScript;

const MAX_EVENTS: usize = 20000;
const MAX_BYTES: usize = 4 * 1024 * 1024;

/// `syncdoc-local trace` — 서버·작업을 실행 기록을 켠 채 띄운다
#[derive(Parser, Debug)]
#[command(
    name = "syncdoc-local trace",
    about = "서버·작업을 실행 기록을 켠 채 띄우고 기록을 싱크독에 올린다"
)]
pub struct TraceArgs {
    /// 싱크독 서버 주소 — 예) https://syncdoc.example.org · http://127.0.0.1:8010
    #[arg(long)]
    pub to: String,
    /// 프로젝트 코드
    #[arg(long)]
    pub project: String,
    /// 웹 요청이 아닌 작업(봇·배치)도 기록한다
    #[arg(long)]
    pub job: bool,
    /// 띄울 폴더(기본: 지금 폴더)
    #[arg(long)]
    pub cwd: Option<PathBuf>,
    /// 띄울 명령 — `--` 뒤에
    #[arg(last = true, required = true)]
    pub command: Vec<String>,
}

/// `syncdoc-local trace-web` — 화면 개발 서버 앞에 프록시를 열어 브라우저 기록을 올린다
#[derive(Parser, Debug)]
#[command(
    name = "syncdoc-local trace-web",
    about = "화면 개발 서버 앞에 프록시를 열어 브라우저 실행 기록을 싱크독에 올린다"
)]
pub struct WebArgs {
    #[arg(long)]
    pub to: String,
    #[arg(long)]
    pub project: String,
    /// 화면 개발 서버 주소
    #[arg(long, default_value = "http://localhost:5173")]
    pub target: String,
    /// 프록시 포트 — 앱을 여기서 연다
    #[arg(long, default_value_t = 3124)]
    pub port: u16,
    /// 저장소 폴더(기본: 지금 폴더)
    #[arg(long)]
    pub cwd: Option<PathBuf>,
}

/// 첫 인자가 `trace`·`trace-web`이면 기록 도구로 돈다
pub fn requested() -> Option<String> {
    std::env::args()
        .nth(1)
        .filter(|a| a == "trace" || a == "trace-web")
}

/// 기록 도구 진입 — 윈도 릴리즈 실행 파일은 콘솔 없이 뜨므로 부른 터미널의 콘솔에 붙는다
pub fn main(which: &str) -> ExitCode {
    attach_console();
    let rt = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(rt) => rt,
        Err(e) => {
            eprintln!("[syncdoc] 시작하지 못했다: {e}");
            return ExitCode::FAILURE;
        }
    };
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    if which == "trace" {
        match TraceArgs::try_parse_from(args) {
            Ok(a) => rt.block_on(run(a)),
            Err(e) => {
                let _ = e.print();
                ExitCode::from(2)
            }
        }
    } else {
        match WebArgs::try_parse_from(args) {
            Ok(a) => rt.block_on(proxy(a)),
            Err(e) => {
                let _ = e.print();
                ExitCode::from(2)
            }
        }
    }
}

#[cfg(windows)]
fn attach_console() {
    use windows_sys::Win32::System::Console::{ATTACH_PARENT_PROCESS, AttachConsole};
    // SAFETY: 부모 콘솔에 붙는 것뿐 — 실패하면(콘솔 없음) 그대로 둔다
    #[allow(unsafe_code)]
    unsafe {
        AttachConsole(ATTACH_PARENT_PROCESS);
    }
}

#[cfg(not(windows))]
fn attach_console() {}

fn say(line: &str) {
    eprintln!("[syncdoc] {line}");
}

/// 사용자 프로그램의 언어 — 기록기를 붙이는 방법이 다르다
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Lang {
    Python,
    Node,
    Rust,
}

/// SYNC-MS-027#trace.detect
///
/// 띄울 명령의 낱말(경로를 뗀 이름)로 — cargo → Rust, 파이썬 실행기 → Python, node·npm 따위 → Node. 모르면 없음
pub fn detect(command: &[String]) -> Option<Lang> {
    let words: Vec<String> = command
        .iter()
        .flat_map(|c| {
            c.split([' ', ';', '&', '|'])
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .map(|w| {
            let base = w.rsplit(['/', '\\']).next().unwrap_or(&w).to_string();
            base.strip_suffix(".exe")
                .map(str::to_string)
                .unwrap_or(base)
        })
        .collect();
    let any = |names: &[&str]| words.iter().any(|w| names.contains(&w.as_str()));
    if any(&["cargo"]) {
        Some(Lang::Rust)
    } else if any(&[
        "python",
        "python3",
        "py",
        "uv",
        "uvicorn",
        "gunicorn",
        "flask",
        "celery",
        "manage.py",
        "hypercorn",
        "fastapi",
        "poetry",
        "pipenv",
    ]) || words.iter().any(|w| w.starts_with("python3."))
    {
        Some(Lang::Python)
    } else if any(&[
        "node", "npm", "npx", "pnpm", "yarn", "tsx", "ts-node", "next", "nodemon", "bun",
    ]) {
        Some(Lang::Node)
    } else {
        None
    }
}

/// 풀어 둔 기록기 자리
pub struct Kit {
    pub dir: PathBuf,
}

impl Kit {
    pub fn python(&self) -> PathBuf {
        self.dir.join("python")
    }
    pub fn node(&self) -> PathBuf {
        self.dir.join("node")
    }
    pub fn rust_helper(&self) -> PathBuf {
        self.dir.join("rust").join("syncdoc_trace.rs")
    }
}

/// SYNC-MS-027#trace.unpack
///
/// 담아 둔 기록기를 폴더에 푼다 — Node의 TypeScript 파서는 `node/node_modules/typescript`로
pub fn unpack(dir: &Path) -> std::io::Result<Kit> {
    for name in Tracers::iter() {
        let Some(f) = Tracers::get(&name) else {
            continue;
        };
        let p = dir.join(name.as_ref());
        std::fs::create_dir_all(p.parent().unwrap_or(dir))?;
        std::fs::write(p, f.data)?;
    }
    for name in TypeScript::iter() {
        let Some(f) = TypeScript::get(&name) else {
            continue;
        };
        let p = dir
            .join("node")
            .join("node_modules")
            .join("typescript")
            .join(name.as_ref());
        std::fs::create_dir_all(p.parent().unwrap_or(dir))?;
        std::fs::write(p, f.data)?;
    }
    Ok(Kit {
        dir: dir.to_path_buf(),
    })
}

/// 저장소 뿌리 — git이면 맨 위, 아니면 그 폴더. 그래프의 경로가 여기 기준이다
fn repo_root(cwd: &Path) -> PathBuf {
    std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(cwd)
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| PathBuf::from(String::from_utf8_lossy(&o.stdout).trim()))
        .unwrap_or_else(|| cwd.to_path_buf())
}

fn head_commit(root: &Path) -> Option<String> {
    std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(root)
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .filter(|h| h.len() == 40)
}

fn token() -> Result<String, String> {
    if let Ok(t) = std::env::var("SYNCDOC_TOKEN")
        && !t.trim().is_empty()
    {
        return Ok(t.trim().to_string());
    }
    rpassword::prompt_password("싱크독 개인 토큰(UI-13에서 발급): ")
        .map(|t| t.trim().to_string())
        .map_err(|e| format!("토큰을 읽지 못했다: {e}"))
}

fn base(to: &str) -> String {
    to.trim_end_matches('/').to_string()
}

/// SYNC-MS-027#trace.fetch_spans
///
/// 서버에서 기록할 함수 범위·라우트·장비 주소와 그래프 커밋을 받는다(개인 토큰)
pub async fn fetch_spans(
    client: &reqwest::Client,
    to: &str,
    project: &str,
    token: &str,
) -> Result<Value, String> {
    let url = format!("{}/api/projects/{project}/trace-spans", base(to));
    let res = client
        .get(&url)
        .bearer_auth(token)
        .send()
        .await
        .map_err(|e| format!("서버에 닿지 못했다({url}): {e}"))?;
    let status = res.status();
    let body: Value = res
        .bytes()
        .await
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or(Value::Null);
    match status.as_u16() {
        200 => Ok(body),
        401 => Err("토큰이 틀렸거나 폐기됐다 — UI-13에서 새로 발급하세요".into()),
        404 => Err(format!("프로젝트 {project}가 없거나 내 것이 아니다")),
        s => Err(format!(
            "서버가 {s}로 답했다: {}",
            body.get("detail").and_then(Value::as_str).unwrap_or("")
        )),
    }
}

/// 범위 파일 — 기록기들이 읽는 꼴. files는 절대 경로 → [[시작 줄, 끝 줄, 열쇠]]
pub struct SpanTable {
    pub json: Value,
    pub files: Vec<(PathBuf, Vec<rust_copy::Span>)>,
    pub routes: Vec<(String, String, String)>,
    pub names: Vec<(String, String)>,
}

/// SYNC-MS-027#trace.span_table
///
/// 서버의 범위를 기록기의 꼴로 — 파일별 범위·라우트 열쇠·이름·장비 주소(호스트:포트 → 종류)·화면용 이름 표
pub fn span_table(spans: &Value, root: &Path) -> SpanTable {
    let mut files: BTreeMap<PathBuf, Vec<rust_copy::Span>> = BTreeMap::new();
    let mut routes = Vec::new();
    let mut names = Vec::new();
    let mut by_name: BTreeMap<String, Map<String, Value>> = BTreeMap::new();
    for s in spans["spans"].as_array().into_iter().flatten() {
        let text = |k: &str| s[k].as_str().unwrap_or_default().to_string();
        let (key, file, name, qual) = (text("key"), text("file"), text("name"), text("qual"));
        let (line, end) = (
            s["line"].as_i64().unwrap_or(0),
            s["end"].as_i64().unwrap_or(0),
        );
        let abs = file
            .split('/')
            .fold(root.to_path_buf(), |p, part| p.join(part));
        files.entry(abs).or_default().push((line, end, key.clone()));
        if let Some(r) = s["route"].as_object() {
            let m = |k: &str| {
                r.get(k)
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string()
            };
            routes.push((key.clone(), m("method"), m("path")));
        }
        names.push((key.clone(), name.clone()));
        let table = by_name.entry(file.clone()).or_default();
        let mut add = |n: String| {
            if !n.is_empty() {
                table.entry(n).or_insert_with(|| Value::from(key.as_str()));
            }
        };
        add(name.clone());
        // 메서드는 `클래스.이름`으로도 — qual의 끝 두 칸
        let segs: Vec<&str> = qual.rsplitn(3, '.').collect();
        if segs.len() >= 2 {
            add(format!("{}.{}", segs[1], segs[0]));
        }
    }
    let mut hosts = Map::new();
    for n in spans["infra"].as_array().into_iter().flatten() {
        let (Some(host), Some(kind)) = (n["host"].as_str(), n["kind"].as_str()) else {
            continue;
        };
        if matches!(kind, "backend" | "browser") {
            continue;
        }
        let k = match kind {
            "db" => "db",
            "cache" => "redis",
            "storage" => "s3",
            _ => "http",
        };
        hosts.insert(host.to_string(), Value::from(k));
    }
    let json = json!({
        "files": files.iter().map(|(p, s)| (p.to_string_lossy().into_owned(), json!(s.iter().map(|(a, b, k)| json!([a, b, k])).collect::<Vec<_>>()))).collect::<Map<String, Value>>(),
        "routes": routes.iter().map(|r| r.0.clone()).collect::<Vec<_>>(),
        "names": names.iter().map(|(k, n)| (k.clone(), Value::from(n.as_str()))).collect::<Map<String, Value>>(),
        "hosts": hosts,
        "byName": by_name.into_iter().map(|(f, m)| (f, Value::Object(m))).collect::<Map<String, Value>>(),
    });
    SpanTable {
        json,
        files: files.into_iter().collect(),
        routes,
        names,
    }
}

/// SYNC-MS-027#trace.env_for
///
/// 띄울 프로그램에 줄 환경 변수 — 공통 셋, Python은 PYTHONPATH 앞에 기록기, Node는 NODE_OPTIONS에 로더
pub fn env_for(
    lang: Lang,
    kit: &Kit,
    spans: &Path,
    out: &Path,
    root: &Path,
    job: bool,
) -> Vec<(String, String)> {
    let mut env = vec![
        (
            "SYNCDOC_TRACE_OUT".to_string(),
            out.to_string_lossy().into_owned(),
        ),
        (
            "SYNCDOC_TRACE_SPANS".to_string(),
            spans.to_string_lossy().into_owned(),
        ),
        (
            "SYNCDOC_TRACE_ROOT".to_string(),
            root.to_string_lossy().into_owned(),
        ),
    ];
    if job {
        env.push(("SYNCDOC_TRACE_JOB".into(), "1".into()));
    }
    if matches!(lang, Lang::Python | Lang::Node) {
        let sep = if cfg!(windows) { ";" } else { ":" };
        let py = kit.python().to_string_lossy().into_owned();
        let pythonpath = match std::env::var("PYTHONPATH") {
            Ok(old) if !old.is_empty() => format!("{py}{sep}{old}"),
            _ => py,
        };
        env.push(("PYTHONPATH".into(), pythonpath));
        let loader = file_url(&kit.node().join("node-tracer.mjs"));
        let node_options = match std::env::var("NODE_OPTIONS") {
            Ok(old) if !old.is_empty() => format!("--import={loader} {old}"),
            _ => format!("--import={loader}"),
        };
        env.push(("NODE_OPTIONS".into(), node_options));
    }
    env
}

/// 파일 경로 → `file://` 주소(윈도 드라이브 글자도)
fn file_url(p: &Path) -> String {
    let s = p.to_string_lossy().replace('\\', "/");
    let s = if s.starts_with('/') {
        s
    } else {
        format!("/{s}")
    };
    let mut out = String::from("file://");
    for b in s.bytes() {
        if b.is_ascii_alphanumeric() || b"/-_.~:".contains(&b) {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

/// SYNC-MS-027#trace.normalize
///
/// 기록기마다 조금씩 다른 꼴을 서버의 TraceRecord에 맞춘다 — kind 기본 back · method 10자 · path 500자 · id 64자 ·
/// ms는 0 이상 정수 · 작업 사본 커밋 · 사건 2만 개 · 본문 4MB(넘으면 사건을 덜고 truncated)
pub fn normalize(record: &mut Value, commit: Option<&str>) {
    let Some(r) = record.as_object_mut() else {
        return;
    };
    let cut = |v: Option<&Value>, n: usize| {
        v.and_then(Value::as_str)
            .map(|s| s.chars().take(n).collect::<String>())
    };
    let kind = r
        .get("kind")
        .and_then(Value::as_str)
        .filter(|k| matches!(*k, "back" | "front" | "job"))
        .unwrap_or("back")
        .to_string();
    r.insert("version".into(), json!(1));
    let method = cut(r.get("method"), 10)
        .filter(|m| !m.is_empty())
        .unwrap_or_else(|| {
            if kind == "job" {
                "JOB".into()
            } else {
                "GET".into()
            }
        });
    r.insert("method".into(), json!(method));
    r.insert("kind".into(), json!(kind));
    r.insert(
        "path".into(),
        json!(cut(r.get("path"), 500).unwrap_or_default()),
    );
    r.insert("id".into(), json!(cut(r.get("id"), 64).unwrap_or_default()));
    let ms = r
        .get("ms")
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
        .max(0.0)
        .round() as i64;
    r.insert("ms".into(), json!(ms));
    if !r.get("status").is_some_and(|s| s.is_i64() || s.is_null()) {
        let s = r.get("status").and_then(Value::as_f64).map(|f| f as i64);
        r.insert("status".into(), json!(s));
    }
    for k in ["error", "query", "page"] {
        if r.get(k).is_some_and(|v| !v.is_string() && !v.is_null()) {
            r.insert(k.into(), Value::Null);
        }
    }
    r.insert("commit".into(), json!(commit));
    let truncated = r.get("truncated").and_then(Value::as_bool).unwrap_or(false);
    r.insert("truncated".into(), json!(truncated));
    if let Some(Value::Array(events)) = r.get_mut("events")
        && events.len() > MAX_EVENTS
    {
        events.truncate(MAX_EVENTS);
        r.insert("truncated".into(), json!(true));
    }
    while serde_json::to_vec(&*r).map_or(0, |b| b.len()) > MAX_BYTES {
        let Some(Value::Array(events)) = r.get_mut("events") else {
            break;
        };
        let keep = events.len() / 2;
        events.truncate(keep);
        r.insert("truncated".into(), json!(true));
        if keep == 0 {
            break;
        }
    }
}

/// SYNC-MS-027#trace.send
///
/// 기록 하나를 올린다 — 실패하면 세 번 더(1·2·4초 뒤). 같은 기록을 다시 보내도 서버에는 하나다
pub async fn send(
    client: &reqwest::Client,
    to: &str,
    project: &str,
    token: &str,
    record: &Value,
) -> Result<u16, String> {
    let url = format!("{}/api/projects/{project}/traces", base(to));
    let mut last = String::new();
    for wait in [0u64, 1, 2, 4] {
        if wait > 0 {
            tokio::time::sleep(Duration::from_secs(wait)).await;
        }
        let req = client
            .post(&url)
            .bearer_auth(token)
            .header(reqwest::header::CONTENT_TYPE, "application/json")
            .body(serde_json::to_vec(record).unwrap_or_default());
        match req.send().await {
            Ok(res) if res.status().is_success() => return Ok(res.status().as_u16()),
            // 꼴이 틀렸거나 남의 것이면 다시 보내도 같다
            Ok(res) if matches!(res.status().as_u16(), 401 | 404 | 413 | 422) => {
                let code = res.status().as_u16();
                let body: Value = res
                    .bytes()
                    .await
                    .ok()
                    .and_then(|b| serde_json::from_slice(&b).ok())
                    .unwrap_or(Value::Null);
                return Err(format!(
                    "{code} {}",
                    body.get("detail").and_then(Value::as_str).unwrap_or("")
                ));
            }
            Ok(res) => last = format!("{}", res.status()),
            Err(e) => last = e.to_string(),
        }
    }
    Err(last)
}

/// SYNC-MS-027#trace.watch
///
/// 기록 폴더의 새 기록(`*.json`)을 맞춰 올리고 지운다. 한 번 훑고 올린 수를 돌려준다
pub async fn watch(
    client: &reqwest::Client,
    out: &Path,
    to: &str,
    project: &str,
    token: &str,
    commit: Option<&str>,
) -> usize {
    let Ok(rd) = std::fs::read_dir(out) else {
        return 0;
    };
    let mut names: Vec<PathBuf> = rd
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            p.extension().and_then(|e| e.to_str()) == Some("json")
                && !p
                    .file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| n.starts_with('.'))
        })
        .collect();
    names.sort();
    let mut sent = 0;
    for p in names {
        let Ok(text) = std::fs::read_to_string(&p) else {
            continue;
        };
        let _ = std::fs::remove_file(&p);
        let Ok(mut record) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        normalize(&mut record, commit);
        let label = format!(
            "{} {}",
            record["method"].as_str().unwrap_or(""),
            record["path"].as_str().unwrap_or("")
        );
        match send(client, to, project, token, &record).await {
            Ok(_) => {
                sent += 1;
                say(&format!(
                    "기록 올림 — {label} (사건 {})",
                    record["events"].as_array().map_or(0, Vec::len)
                ));
            }
            Err(e) => say(&format!("기록을 올리지 못해 버렸다 — {label}: {e}")),
        }
    }
    sent
}

/// 공통 준비 — 토큰·범위·저장소 뿌리·커밋 비교
struct Prepared {
    client: reqwest::Client,
    token: String,
    spans: Value,
    root: PathBuf,
    commit: Option<String>,
}

async fn prepare(to: &str, project: &str, cwd: &Path) -> Result<Prepared, String> {
    let token = token()?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;
    let spans = fetch_spans(&client, to, project, &token).await?;
    let Some(graph_commit) = spans["commit_hash"].as_str().map(str::to_string) else {
        return Err(format!(
            "프로젝트 {project}의 코드 그래프가 없다 — 코드를 먼저 push하세요"
        ));
    };
    let root = repo_root(cwd);
    let commit = head_commit(&root);
    if commit.as_deref() != Some(graph_commit.as_str()) {
        say(&format!(
            "작업 사본({})이 그래프의 커밋({})과 다르다 — 함수 자리가 어긋날 수 있다",
            commit.as_deref().map_or("git 아님", |c| &c[..7]),
            &graph_commit[..graph_commit.len().min(7)]
        ));
    }
    Ok(Prepared {
        client,
        token,
        spans,
        root,
        commit,
    })
}

/// SYNC-MS-027#trace.run
///
/// 준비(토큰·범위·커밋) → 언어 알아보기 → 기록기 풀기·범위 파일 → (Rust면 사본 계측) → 띄우기 → 기록 폴더를 지켜보며
/// 올리기 → 끝나면 남은 기록을 올리고 임시 폴더를 지운다. Ctrl+C는 프로그램에 넘긴다
pub async fn run(args: TraceArgs) -> ExitCode {
    let cwd = args
        .cwd
        .clone()
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| PathBuf::from("."));
    let Some(lang) = detect(&args.command) else {
        say(
            "띄울 명령의 언어를 모른다 — Python(uv·python·uvicorn…)·Node(npm·node·tsx…)·Rust(cargo)만 기록한다",
        );
        return ExitCode::from(2);
    };
    let p = match prepare(&args.to, &args.project, &cwd).await {
        Ok(p) => p,
        Err(e) => {
            say(&e);
            return ExitCode::from(2);
        }
    };
    let tmp = match tempfile::Builder::new().prefix("syncdoc-trace-").tempdir() {
        Ok(t) => t,
        Err(e) => {
            say(&format!("임시 폴더를 만들지 못했다: {e}"));
            return ExitCode::FAILURE;
        }
    };
    let kit = match unpack(&tmp.path().join("kit")) {
        Ok(k) => k,
        Err(e) => {
            say(&format!("기록기를 풀지 못했다: {e}"));
            return ExitCode::FAILURE;
        }
    };
    let out = tmp.path().join("out");
    let _ = std::fs::create_dir_all(&out);
    let table = span_table(&p.spans, &p.root);
    let spans_path = tmp.path().join("spans.json");
    if let Err(e) = std::fs::write(&spans_path, table.json.to_string()) {
        say(&format!("범위 파일을 쓰지 못했다: {e}"));
        return ExitCode::FAILURE;
    }
    let mut env = env_for(lang, &kit, &spans_path, &out, &p.root, args.job);
    let mut run_cwd = cwd.clone();
    if lang == Lang::Rust {
        match rust_setup(&kit, &table, &cwd, &p.root) {
            Ok((dir, target, n)) => {
                say(&format!(
                    "Rust 파일 {n}개를 계측한 사본에서 띄운다 — 원본은 그대로 ({})",
                    dir.display()
                ));
                run_cwd = dir;
                env.push((
                    "CARGO_TARGET_DIR".into(),
                    target.to_string_lossy().into_owned(),
                ));
            }
            Err(e) => {
                say(&e);
                return ExitCode::from(2);
            }
        }
    }
    say(&format!(
        "{} 실행 기록 → {} 프로젝트 {}",
        match lang {
            Lang::Python => "Python",
            Lang::Node => "Node",
            Lang::Rust => "Rust",
        },
        base(&args.to),
        args.project
    ));
    say(&format!(
        "{}에서 띄운다: {}",
        run_cwd.display(),
        args.command.join(" ")
    ));
    let mut cmd = tokio::process::Command::new(&args.command[0]);
    cmd.args(&args.command[1..]).current_dir(&run_cwd).envs(env);
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            say(&format!("띄우지 못했다: {e}"));
            return ExitCode::FAILURE;
        }
    };
    let code = loop {
        tokio::select! {
            st = child.wait() => break st.ok().and_then(|s| s.code()).unwrap_or(1),
            // Ctrl+C는 같은 터미널의 프로그램이 받는다 — 도구는 끝나기를 기다린다
            _ = tokio::signal::ctrl_c() => {}
            _ = tokio::time::sleep(Duration::from_millis(400)) => {
                watch(&p.client, &out, &args.to, &args.project, &p.token, p.commit.as_deref()).await;
            }
        }
    };
    tokio::time::sleep(Duration::from_millis(300)).await;
    watch(
        &p.client,
        &out,
        &args.to,
        &args.project,
        &p.token,
        p.commit.as_deref(),
    )
    .await;
    drop(tmp);
    ExitCode::from(u8::try_from(code).unwrap_or(1))
}

/// Rust 사본 — 사본과 빌드 폴더는 캐시 자리에 두고 다시 쓴다(매번 처음부터 빌드하지 않게)
fn rust_setup(
    kit: &Kit,
    table: &SpanTable,
    cwd: &Path,
    root: &Path,
) -> Result<(PathBuf, PathBuf, usize), String> {
    let cache = directories::ProjectDirs::from("", "", "syncdoc-local")
        .map(|d| d.cache_dir().to_path_buf())
        .unwrap_or_else(std::env::temp_dir)
        .join("trace");
    let id = {
        use std::hash::{Hash, Hasher};
        let mut h = std::collections::hash_map::DefaultHasher::new();
        root.hash(&mut h);
        format!("{:016x}", h.finish())
    };
    let helper_src = std::fs::read_to_string(kit.rust_helper()).map_err(|e| e.to_string())?;
    let q = |s: &str| serde_json::to_string(s).unwrap_or_default();
    let routes: Vec<String> = table
        .routes
        .iter()
        .map(|(k, m, p)| format!("({}, {}, {})", q(k), q(m), q(p)))
        .collect();
    let names: Vec<String> = table
        .names
        .iter()
        .map(|(k, n)| format!("({}, {})", q(k), q(n)))
        .collect();
    let helper = cache.join(format!("{id}-helper")).join("syncdoc_trace.rs");
    std::fs::create_dir_all(helper.parent().unwrap_or(&cache)).map_err(|e| e.to_string())?;
    std::fs::write(
        &helper,
        helper_src
            .replace("/*VA_ROUTES*/", &routes.join(", "))
            .replace("/*VA_NAMES*/", &names.join(", ")),
    )
    .map_err(|e| e.to_string())?;
    if which("cargo").is_none() {
        return Err("Rust 실행 기록에는 cargo가 필요하다 — https://rustup.rs".into());
    }
    let prepared = copy_rust(
        cwd,
        &table.files,
        &cache.join(format!("{id}-copy")),
        &helper,
    )?;
    Ok((
        prepared.cwd,
        cache.join(format!("{id}-target")),
        prepared.instrumented,
    ))
}

fn which(cmd: &str) -> Option<PathBuf> {
    let exts: &[&str] = if cfg!(windows) {
        &[".exe", ".cmd", ""]
    } else {
        &[""]
    };
    std::env::split_paths(&std::env::var_os("PATH")?).find_map(|d| {
        exts.iter()
            .map(|e| d.join(format!("{cmd}{e}")))
            .find(|p| p.is_file())
    })
}

/// SYNC-MS-027#trace.proxy
///
/// `trace-web` — Node 프록시(web-proxy.mjs)를 띄워 화면 모듈을 계측하고, 브라우저가 보낸 기록을 올린다
pub async fn proxy(args: WebArgs) -> ExitCode {
    let cwd = args
        .cwd
        .clone()
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| PathBuf::from("."));
    let Some(node) = which("node") else {
        say("화면 기록에는 Node.js가 필요하다 — https://nodejs.org");
        return ExitCode::from(2);
    };
    let p = match prepare(&args.to, &args.project, &cwd).await {
        Ok(p) => p,
        Err(e) => {
            say(&e);
            return ExitCode::from(2);
        }
    };
    let Ok(tmp) = tempfile::Builder::new().prefix("syncdoc-trace-").tempdir() else {
        say("임시 폴더를 만들지 못했다");
        return ExitCode::FAILURE;
    };
    let kit = match unpack(&tmp.path().join("kit")) {
        Ok(k) => k,
        Err(e) => {
            say(&format!("기록기를 풀지 못했다: {e}"));
            return ExitCode::FAILURE;
        }
    };
    let out = tmp.path().join("out");
    let _ = std::fs::create_dir_all(&out);
    let table = span_table(&p.spans, &p.root);
    let spans_path = tmp.path().join("spans.json");
    if std::fs::write(&spans_path, table.json.to_string()).is_err() {
        return ExitCode::FAILURE;
    }
    let mut child = match tokio::process::Command::new(node)
        .arg(kit.node().join("web-proxy.mjs"))
        .env("SYNCDOC_TRACE_OUT", &out)
        .env("SYNCDOC_TRACE_SPANS", &spans_path)
        .env("SYNCDOC_TRACE_TARGET", &args.target)
        .env("SYNCDOC_TRACE_PORT", args.port.to_string())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            say(&format!("프록시를 띄우지 못했다: {e}"));
            return ExitCode::FAILURE;
        }
    };
    let code = loop {
        tokio::select! {
            st = child.wait() => break st.ok().and_then(|s| s.code()).unwrap_or(0),
            _ = tokio::signal::ctrl_c() => {}
            _ = tokio::time::sleep(Duration::from_millis(400)) => {
                watch(&p.client, &out, &args.to, &args.project, &p.token, p.commit.as_deref()).await;
            }
        }
    };
    watch(
        &p.client,
        &out,
        &args.to,
        &args.project,
        &p.token,
        p.commit.as_deref(),
    )
    .await;
    drop(tmp);
    ExitCode::from(u8::try_from(code).unwrap_or(1))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_language_from_command_words() {
        let c = |s: &str| s.split(' ').map(str::to_string).collect::<Vec<_>>();
        assert_eq!(
            detect(&c("uv run uvicorn app.main:app")),
            Some(Lang::Python)
        );
        assert_eq!(
            detect(&c("/usr/bin/python3 manage.py runserver")),
            Some(Lang::Python)
        );
        assert_eq!(detect(&c("npm run dev")), Some(Lang::Node));
        assert_eq!(detect(&c("cargo run -p svc")), Some(Lang::Rust));
        assert_eq!(detect(&c("./server")), None);
    }

    #[test]
    fn normalize_fits_trace_record() {
        let mut r = json!({"id": "x".repeat(80), "method": "", "path": "/a", "ms": 12.6, "startedAt": "2026-10-17T00:00:00Z",
            "truncated": false, "events": [{"i": 0, "parent": -1, "fn": "a.py:1", "t0": 0}]});
        normalize(&mut r, Some(&"a".repeat(40)));
        assert_eq!(
            (r["kind"].as_str(), r["method"].as_str(), r["ms"].as_i64()),
            (Some("back"), Some("GET"), Some(13))
        );
        assert_eq!(r["id"].as_str().map(str::len), Some(64));
        assert_eq!(r["commit"].as_str().map(str::len), Some(40));
        let mut job = json!({"kind": "job", "method": "JOB", "path": "x", "ms": 1, "events": []});
        normalize(&mut job, None);
        assert_eq!(
            (job["method"].as_str(), job["commit"].is_null()),
            (Some("JOB"), true)
        );
    }

    #[test]
    fn span_table_keys_files_routes_and_hosts() {
        let spans = json!({"commit_hash": "c", "spans": [
            {"key": "app/a.py:3", "file": "app/a.py", "line": 3, "end": 9, "name": "read", "qual": "a.read", "route": {"method": "GET", "path": "/x"}},
            {"key": "web/p.tsx:2", "file": "web/p.tsx", "line": 2, "end": 5, "name": "load", "qual": "p.Api.load", "route": null}],
            "infra": [{"id": "infra:db", "kind": "db", "host": "db:5432"}, {"id": "infra:server:a", "kind": "backend", "host": "localhost:8000"}]});
        let t = span_table(&spans, Path::new("/r"));
        assert_eq!(t.json["routes"], json!(["app/a.py:3"]));
        assert_eq!(t.json["hosts"], json!({"db:5432": "db"}));
        assert_eq!(
            t.json["byName"]["web/p.tsx"]["Api.load"],
            json!("web/p.tsx:2")
        );
        assert!(
            t.json["files"]
                .as_object()
                .is_some_and(|f| f.keys().any(|k| k.ends_with("a.py")))
        );
        assert_eq!(t.names[1], ("web/p.tsx:2".to_string(), "load".to_string()));
    }

    #[test]
    fn unpacks_tracers_with_typescript() {
        let tmp = tempfile::tempdir().expect("임시");
        let kit = unpack(tmp.path()).expect("풀기");
        assert!(kit.python().join("sitecustomize.py").is_file());
        assert!(kit.node().join("node-tracer.mjs").is_file());
        assert!(
            kit.node()
                .join("node_modules/typescript/lib/typescript.js")
                .is_file()
        );
        assert!(kit.rust_helper().is_file());
    }
}
