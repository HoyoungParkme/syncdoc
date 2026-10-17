//! 싱크독 Rust 실행 기록 도우미 (SYNC-INFRA-001 9.9, 카드 L29) — view_arc에서 옮겼다. `syncdoc-local trace`가 계측 사본의
//! 크레이트 뿌리에 `mod syncdoc_trace;`로 넣는다(원본은 그대로).
//!
//! 계측한 함수 첫머리: `let __va = crate::syncdoc_trace::enter("파일:줄", &[("a", 값 표현)]);` — 열쇠는 그래프 함수 열쇠.
//! Guard 가 떨어질 때(함수 끝·패닉·future 취소) 끝 시각을 남긴다. 스레드별 스택으로 부모를 정하고, 라우트 함수는 언제나
//! 새 요청 기록을 연다. 기록은 SYNCDOC_TRACE_OUT/<id>.json — 기록 도구가 올린다. 표준 라이브러리만 쓴다.
#![allow(dead_code, clippy::all)]

use std::collections::HashMap;
use std::fmt::Write as _;
use std::io::Write as _;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Mutex, OnceLock};
use std::thread::{self, ThreadId};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

/// 라우트 표: (함수 열쇠, 메서드, 경로) — 기록 도구가 채운다
static ROUTES: &[(&str, &str, &str)] = &[/*VA_ROUTES*/];
/// 이름 표: (함수 열쇠, 이름) — 기록 도구가 채운다
static NAMES: &[(&str, &str)] = &[/*VA_NAMES*/];

fn name_of(id: &'static str) -> &'static str {
    NAMES.iter().find(|n| n.0 == id).map_or(id, |n| n.1)
}
const MAX_EVENTS: usize = 20000;
const MAX_FILES: usize = 300;
const SECRET: [&str; 8] = ["pass", "secret", "token", "api_key", "apikey", "authoriz", "credential", "private"];

/// 값 표현: Debug 가 있으면 그것, 없으면 타입 이름 — `(&W(&x)).va()` (두 트레이트를 같이 들여와 부른다)
pub struct W<'a, T: ?Sized>(pub &'a T);
pub trait ViaDebug {
    fn va(&self) -> String;
}
impl<'a, T: std::fmt::Debug + ?Sized> ViaDebug for W<'a, T> {
    fn va(&self) -> String {
        let mut s = String::new();
        let _ = write!(s, "{:?}", self.0);
        short(&mask(&s))
    }
}
pub trait ViaAny {
    fn va(&self) -> String;
}
impl<'a, T: ?Sized> ViaAny for &W<'a, T> {
    fn va(&self) -> String {
        let name = std::any::type_name::<T>();
        let base = name.split('<').next().unwrap_or(name);
        base.rsplit("::").next().unwrap_or(base).to_string()
    }
}

struct Ev {
    parent: i64,
    fn_: &'static str,
    args: Vec<(&'static str, String)>,
    t0: f64,
    t1: Option<f64>,
    exc: Option<&'static str>,
}

struct Rec {
    id: String,
    kind: Option<&'static str>,
    method: &'static str,
    path: &'static str,
    started_at: u128,
    start: Instant,
    events: Vec<Ev>,
    done: bool,
    truncated: bool,
}

struct Frame {
    rec: usize,
    i: usize,
}

#[derive(Default)]
struct State {
    recs: HashMap<usize, Rec>,
    stacks: HashMap<ThreadId, Vec<Frame>>,
}

static STATE: OnceLock<Mutex<State>> = OnceLock::new();
static NEXT: AtomicUsize = AtomicUsize::new(1);
static WRITE: Mutex<()> = Mutex::new(());

fn state() -> std::sync::MutexGuard<'static, State> {
    STATE
        .get_or_init(|| Mutex::new(State::default()))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
}

fn trace_dir() -> Option<String> {
    std::env::var("SYNCDOC_TRACE_OUT").ok().filter(|d| !d.is_empty())
}

fn ms(start: Instant) -> f64 {
    (start.elapsed().as_micros() / 10) as f64 / 100.0
}

/// 함수 끝에서 떨어지는 표
pub struct Guard {
    rec: usize,
    i: usize,
    tid: Option<ThreadId>,
    root: bool,
}

/// 함수 진입. 기록하지 않는 호출이면 빈 Guard
pub fn enter(id: &'static str, args: &[(&'static str, String)]) -> Guard {
    let none = Guard {
        rec: 0,
        i: 0,
        tid: None,
        root: false,
    };
    if trace_dir().is_none() {
        return none;
    }
    let tid = thread::current().id();
    let mut st = state();
    let st = &mut *st;
    let route = ROUTES.iter().find(|r| r.0 == id);
    let parent = st
        .stacks
        .get(&tid)
        .and_then(|s| s.iter().rev().find(|f| st.recs.get(&f.rec).map_or(false, |r| !r.done)))
        .map(|f| (f.rec, f.i));
    let (rec, parent_i, root) = if let Some((_, method, path)) = route {
        (open(st, method, path, None), -1, true)
    } else if let Some((rec, i)) = parent {
        (rec, i as i64, false)
    } else if std::env::var("SYNCDOC_TRACE_JOB").as_deref() == Ok("1") {
        (open(st, "JOB", name_of(id), Some("job")), -1, true)
    } else {
        return none;
    };
    let r = st.recs.get_mut(&rec).expect("기록");
    if r.events.len() >= MAX_EVENTS {
        r.truncated = true;
        return none;
    }
    let args = args
        .iter()
        .map(|(k, v)| {
            (
                *k,
                if SECRET.iter().any(|s| k.to_lowercase().contains(s)) {
                    "***".to_string()
                } else {
                    v.clone()
                },
            )
        })
        .collect();
    let t0 = ms(r.start);
    r.events.push(Ev {
        parent: parent_i,
        fn_: id,
        args,
        t0,
        t1: None,
        exc: None,
    });
    let i = r.events.len() - 1;
    st.stacks.entry(tid).or_default().push(Frame { rec, i });
    Guard {
        rec,
        i,
        tid: Some(tid),
        root,
    }
}

fn open(st: &mut State, method: &'static str, path: &'static str, kind: Option<&'static str>) -> usize {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let now = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
    st.recs.insert(
        n,
        Rec {
            id: format!("{}-{}-{}", now, std::process::id(), n),
            kind,
            method,
            path,
            started_at: now,
            start: Instant::now(),
            events: Vec::new(),
            done: false,
            truncated: false,
        },
    );
    n
}

impl Drop for Guard {
    fn drop(&mut self) {
        let Some(tid) = self.tid else { return };
        let panicking = thread::panicking();
        let finished = {
            let mut st = state();
            let st = &mut *st;
            if let Some(s) = st.stacks.get_mut(&tid) {
                if let Some(k) = s.iter().rposition(|f| f.rec == self.rec && f.i == self.i) {
                    s.remove(k);
                }
                if s.is_empty() {
                    st.stacks.remove(&tid);
                }
            }
            let Some(r) = st.recs.get_mut(&self.rec) else { return };
            let now = ms(r.start);
            if let Some(ev) = r.events.get_mut(self.i) {
                ev.t1 = Some(now);
                if panicking {
                    ev.exc = Some("panic");
                }
            }
            if self.root {
                r.done = true;
                st.recs.remove(&self.rec)
            } else {
                None
            }
        };
        if let Some(r) = finished {
            write(r, panicking);
        }
    }
}

/// 비밀 칸(password: "…", token=…)의 값을 가린다. 열쇠·구분자는 ASCII 라 바이트로 훑어도 글자 경계가 깨지지 않는다
fn mask(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    let mut last = 0;
    let mut i = 0;
    while i < b.len() {
        if b[i] == b':' || b[i] == b'=' {
            let mut start = i;
            while start > 0 && (b[start - 1].is_ascii_alphanumeric() || b[start - 1] == b'_') {
                start -= 1;
            }
            let key = s[start..i].to_ascii_lowercase();
            if !key.is_empty() && SECRET.iter().any(|w| key.contains(w)) {
                let mut end = i + 1;
                while end < b.len() && b[end] == b' ' {
                    end += 1;
                }
                if end < b.len() && b[end] == b'"' {
                    end += 1;
                    while end < b.len() && b[end] != b'"' {
                        end += if b[end] == b'\\' { 2 } else { 1 };
                    }
                    end = (end + 1).min(b.len());
                } else {
                    while end < b.len() && !matches!(b[end], b',' | b'}' | b')' | b' ') {
                        end += 1;
                    }
                }
                out.push_str(&s[last..=i]);
                out.push_str(" ***");
                last = end;
                i = end;
                continue;
            }
        }
        i += 1;
    }
    out.push_str(&s[last..]);
    out
}

fn short(s: &str) -> String {
    if s.chars().count() <= 160 {
        return s.to_string();
    }
    s.chars().take(159).collect::<String>() + "…"
}

fn quote(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn iso(millis: u128) -> String {
    // UTC ISO 8601(날짜 계산: 1970-01-01 부터 일 수 → 그레고리력)
    let secs = (millis / 1000) as i64;
    let days = secs.div_euclid(86400);
    let rem = secs.rem_euclid(86400);
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let mo = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if mo <= 2 { 1 } else { 0 };
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{m:02}:{s:02}.{:03}Z", millis % 1000)
}

fn write(mut r: Rec, panicked: bool) {
    let Some(dir) = trace_dir() else { return };
    let total = ms(r.start);
    for ev in r.events.iter_mut() {
        if ev.t1.is_none() {
            ev.t1 = Some(total);
        }
    }
    if r.kind.is_some() && r.events.len() < 2 && total < 50.0 {
        return; // 아주 작은 작업
    }
    let status = if r.kind.is_some() {
        if panicked {
            "500"
        } else {
            "200"
        }
    } else {
        "null"
    };
    let error = r.events.first().and_then(|e| e.exc).map_or("null".to_string(), quote);
    let root = r.events.iter().find(|e| e.parent == -1).map_or("null".to_string(), |e| quote(e.fn_));
    let mut events = String::from("[");
    for (i, e) in r.events.iter().enumerate() {
        if i > 0 {
            events.push(',');
        }
        let _ = write!(
            events,
            "{{\"i\":{i},\"parent\":{},\"fn\":{},\"name\":{},\"args\":{{",
            e.parent,
            quote(e.fn_),
            quote(name_of(e.fn_))
        );
        for (k, (name, v)) in e.args.iter().enumerate() {
            if k > 0 {
                events.push(',');
            }
            let _ = write!(events, "{}:{}", quote(name), quote(v));
        }
        let _ = write!(events, "}},\"t0\":{},\"t1\":{}", e.t0, e.t1.unwrap_or(total));
        if let Some(x) = e.exc {
            let _ = write!(events, ",\"exc\":{}", quote(x));
        }
        events.push('}');
    }
    events.push(']');
    let kind = r.kind.map_or(String::new(), |k| format!(",\"kind\":{}", quote(k)));
    let started = iso(r.started_at);
    let record = format!(
        "{{\"version\":1{kind},\"id\":{},\"method\":{},\"path\":{},\"query\":\"\",\"status\":{status},\"error\":{error},\"startedAt\":{},\"ms\":{total},\"truncated\":{},\"events\":{events}}}",
        quote(&r.id),
        quote(r.method),
        quote(r.path),
        quote(&started),
        r.truncated
    );
    let summary = format!(
        "{{\"id\":{}{kind},\"method\":{},\"path\":{},\"status\":{status},\"error\":{error},\"startedAt\":{},\"ms\":{total},\"calls\":{},\"root\":{root}}}\n",
        quote(&r.id),
        quote(r.method),
        quote(r.path),
        quote(&started),
        r.events.len()
    );
    let _lock = WRITE.lock().unwrap_or_else(|e| e.into_inner());
    let dir = std::path::Path::new(&dir);
    if std::fs::create_dir_all(dir).is_err() {
        return;
    }
    let tmp = dir.join(format!(".{}.tmp", r.id));
    if std::fs::write(&tmp, record).is_err() || std::fs::rename(&tmp, dir.join(format!("{}.json", r.id))).is_err() {
        eprintln!("[syncdoc] 기록을 쓰지 못했습니다");
        return;
    }
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(dir.join("index.jsonl")) {
        let _ = f.write_all(summary.as_bytes());
    }
    if let Ok(entries) = std::fs::read_dir(dir) {
        let mut names: Vec<_> = entries
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .filter(|n| n.ends_with(".json"))
            .collect();
        names.sort();
        let extra = names.len().saturating_sub(MAX_FILES);
        for n in names.into_iter().take(extra) {
            let _ = std::fs::remove_file(dir.join(n));
        }
    }
}
