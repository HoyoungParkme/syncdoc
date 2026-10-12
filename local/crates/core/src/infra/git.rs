//! git 어댑터 — git CLI를 자식 프로세스로 (SYNC-MS-019 · SYNC-DOM-004 4.8, 카드 L6).
//! 파이썬 판 `backend/app/infra/git.py`와 같은 명령·같은 옵션. 사용자 git 설정은 막는다(MS-019 0장) —
//! 파이썬 판은 Docker 안이라 시스템·전역 설정이 없다. 같은 깨끗한 환경을 만들어 같은 결과를 낸다.
//! 프로세스를 적게(카드 L19) — 작업 사본은 git이 아닌 폴더, git은 늘 서버 저장소에서 돈다. 커밋은
//! `fast-import` 하나, 읽기는 저장소마다 오래 사는 `cat-file --batch` 하나다(MS-019 0장).

use std::collections::HashMap;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::sync::{Arc, Mutex};

use indexmap::IndexMap;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};

use crate::account::model::UserRow;
use crate::errors::Problem;
use crate::pycompat::chars::{py_splitlines, strip};
use crate::types::{ChangedFile, Commit, UserKind, stage_of};

/// push가 거부되면 다시 미는 수 — INFRA 5.2 `PUSH_RETRIES` 기본값
pub const PUSH_RETRIES: usize = 3;

/// 모든 git 앞에 — 한글 경로를 따옴표 없이(#349), 줄바꿈·서명·자격 도우미 끔, 앱이 만든 저장소는 다 연다
const ISOLATE: [&str; 10] = [
    "-c",
    "core.quotepath=false",
    "-c",
    "core.autocrlf=false",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "credential.helper=",
    "-c",
    "safe.directory=*",
];

/// 서버 저장소의 받기 규칙 — 이력을 되감거나 가지를 지우는 push와 깨진 객체를 받지 않는다
const RECEIVE_RULES: [&str; 3] = [
    "receive.denyNonFastForwards",
    "receive.denyDeletes",
    "receive.fsckObjects",
];

/// 골격의 디렉터리 — 11단계와 단계 밖 `STD`
const SPEC_TYPES: [&str; 12] = [
    "RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE", "STD",
];

/// 저장소 README 자리
const README_PATH: &str = "docs/specs/README.md";

/// 새 저장소의 `docs/specs/README.md` — 파이썬 `_readme()`와 글자 하나 다르지 않다. `{SPECS_URL}`이 규약 주소
const README: &str = r#"# docs/specs — 명세 원본

싱크독 명세 체인 11단계 + STD. 쓰는 법은 아래 셋이다.

- [명세 작성 규약 SYNC-STD-001]({SPECS_URL}/STD/SYNC-STD-001.md) — 필수 절과 항목 ID 형식은 그 2장
- [개발 규약 SYNC-STD-004]({SPECS_URL}/STD/SYNC-STD-004.md)
- [타입별 뼈대 `_templates/`]({SPECS_URL}/_templates)

**이 저장소에는 규약·템플릿 사본을 두지 않는다.** 규약이 바뀌면 위 링크 끝이 바뀐다.
에이전트는 싱크독 MCP의 `get_template`으로 타입별 뼈대와 규약을 받는다.

**위에서 아래로 읽는다.** 디렉터리 번호가 그 순서다.

| # | 디렉터리 | 무엇 |
|---|---|---|
| 1 | `01-RFQ` | 요청 — 무엇을 원하나 |
| 2 | `02-PRD` | 제품 요구사항 |
| 3 | `03-SCN` | 사용자 시나리오 |
| 4 | `04-UC` | 유스케이스 |
| 5 | `05-INFRA` | 인프라·제약 |
| 6 | `06-DOM` | 도메인 모델 · **클래스 명세** · ERD·DD (문서 셋 — **한 번에 쓰지 않는다.** 아래) |
| 7 | `07-UI` | 화면 설계 · 와이어프레임 |
| 8 | `08-API` | REST · MCP 도구 |
| 9 | `09-SEQ` | 시퀀스 |
| 10 | `10-MS` | MINISPEC — 함수 단위 |
| 11 | `11-CODE` | 구현 슬라이스 카드 |
| — | `STD` | 작성 규약·뷰 규약·개발 규약 (단계 밖 — 싱크독 저장소에 있다) |

- 경로 `docs/specs/{NN-TYPE}/{doc_id}.md` · 문서 ID `{프로젝트코드}-{TYPE}-{NNN}`
- 상태(`status`)는 frontmatter가 진실. 변경은 싱크독 웹에서만
- 첨부는 `assets/` — 문서에서는 문서 폴더 기준 상대 경로(`../assets/x.png`)
- 화면(UI) 배치는 디자인 도구 산출물(스타일까지 든 자기 완결 html)을 그대로 넣는다(규약 2.7)
- 커밋·PR에 에이전트 표시(Co-Authored-By 등)를 남기지 않는다. 작성자는 사람의 계정이다
- **문서 하나를 만들거나 고치면 멈춘다.** 사람이 웹에서 읽고 「다음」이라고 한 뒤에 다음 문서.
  단계가 아니라 문서가 단위다(규약 1.8)
- DOM 셋은 순서가 있다. 도메인 모델은 6에서, 클래스 명세는 8 API 뒤에 돌아와서,
  ERD는 클래스 명세 뒤에(규약 2.6)
"#;

/// git 실행 파일·전역 설정·저장소마다 오래 사는 읽기 프로세스 — 켤 때 `runtime.run`이 [`Git::new`]로 만든다.
/// 복제하면 읽기 프로세스 지도를 함께 쓴다
#[derive(Clone, Debug)]
pub struct Git {
    pub exe: PathBuf,
    pub global_config: PathBuf,
    readers: Readers,
}

/// [`Git::commit`]이 쓸 것
#[derive(Clone, Copy)]
struct Change<'a> {
    message: &'a str,
    user: &'a UserRow,
    files: &'a IndexMap<String, String>,
    delete: &'a [String],
}

/// [`Git::commit`]의 결과 — 새 해시와 그 부모(바뀐 것이 없으면 둘이 같다)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Committed {
    pub hash: String,
    pub parent: Option<String>,
}

/// 저장소(서버 저장소 자리)마다 `git cat-file --batch` 하나 — 쓰는 동안 그 자리를 잠근다
#[derive(Clone, Default)]
struct Readers(Arc<Mutex<HashMap<PathBuf, Slot>>>);

type Slot = Arc<tokio::sync::Mutex<Option<Batch>>>;

impl std::fmt::Debug for Readers {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let n = self.0.lock().map(|m| m.len()).unwrap_or(0);
        write!(f, "Readers({n})")
    }
}

impl Readers {
    fn slot(&self, repo: &Path) -> Slot {
        let mut map = self
            .0
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        Arc::clone(map.entry(repo.to_path_buf()).or_default())
    }

    fn take(&self, repo: &Path) -> Option<Slot> {
        self.0
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .remove(repo)
    }

    fn repos(&self) -> Vec<PathBuf> {
        self.0
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .keys()
            .cloned()
            .collect()
    }
}

/// 읽기 프로세스 하나 — 이름 한 줄을 넣고 `<oid> <type> <size>` 머리와 내용을 읽는다
struct Batch {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

/// 읽기 프로세스에 물은 객체
struct Obj {
    oid: String,
    kind: String,
    data: Vec<u8>,
}

/// 읽기 프로세스의 답 — 있다 · 없다 · 프로세스가 답하지 못했다(부르는 쪽이 원래 명령으로)
enum Lookup {
    Found(Obj),
    Missing,
    Broken,
}

impl Batch {
    async fn ask(&mut self, name: &str) -> std::io::Result<Lookup> {
        self.stdin.write_all(format!("{name}\n").as_bytes()).await?;
        self.stdin.flush().await?;
        let mut line = Vec::new();
        let n = self.stdout.read_until(b'\n', &mut line).await?;
        if n == 0 || line.last() != Some(&b'\n') {
            return Err(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                "git cat-file --batch가 끝났다",
            ));
        }
        line.pop();
        let head = String::from_utf8_lossy(&line).into_owned();
        if head == format!("{name} missing") || head == format!("{name} ambiguous") {
            return Ok(Lookup::Missing);
        }
        let mut it = head.split(' ');
        let (oid, kind, size) = (it.next(), it.next(), it.next());
        let (Some(oid), Some(kind), Some(size)) = (oid, kind, size.and_then(|s| s.parse().ok()))
        else {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("git cat-file --batch 머리를 못 읽었다: {head}"),
            ));
        };
        let mut data = vec![0; size];
        self.stdout.read_exact(&mut data).await?;
        let mut lf = [0u8; 1];
        self.stdout.read_exact(&mut lf).await?;
        Ok(Lookup::Found(Obj {
            oid: oid.to_string(),
            kind: kind.to_string(),
            data,
        }))
    }
}

/// git `strbuf_stripspace`(주석 없이) — `git commit -m`이 메시지에 하는 정리. 줄 끝 공백(` `·`\t`·`\r`·`\n`)을
/// 걷고, 빈 줄은 앞뒤를 버리고 사이의 여럿을 하나로, 줄마다 끝에 `\n`
fn stripspace(msg: &str) -> String {
    let mut out = String::new();
    let mut empties = 0;
    for line in msg.split_inclusive('\n') {
        let kept = line.trim_end_matches([' ', '\t', '\n', '\r']);
        if kept.is_empty() {
            empties += 1;
            continue;
        }
        if empties > 0 && !out.is_empty() {
            out.push('\n');
        }
        empties = 0;
        out.push_str(kept);
        out.push('\n');
    }
    out
}

/// git `strbuf_addstr_without_crud` — 본인 줄의 이름·메일에서 앞뒤 군더더기를 걷고 안의 `\n`·`<`·`>`를 뺀다
fn without_crud(s: &str) -> String {
    let crud =
        |c: char| (c as u32) <= 32 || matches!(c, ',' | ':' | ';' | '<' | '>' | '"' | '\\' | '\'');
    s.trim_matches(crud)
        .chars()
        .filter(|c| !matches!(c, '\n' | '<' | '>'))
        .collect()
}

/// git의 현지 시각 꼴 `{초} ±HHMM` — 지금
fn git_now() -> String {
    let now = jiff::Zoned::now();
    let off = now.offset().seconds();
    let sign = if off < 0 { '-' } else { '+' };
    let off = off.abs();
    format!(
        "{} {sign}{:02}{:02}",
        now.timestamp().as_second(),
        off / 3600,
        off % 3600 / 60
    )
}

/// fast-import의 경로 — `"`·`\`·줄바꿈·제어 글자가 있거나 `"`로 시작하면 C 꼴로 따옴
fn fi_path(path: &str) -> String {
    if !path
        .chars()
        .any(|c| c == '"' || c == '\\' || c.is_control())
    {
        return path.to_string();
    }
    let mut out = String::from("\"");
    for c in path.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => {
                for b in c.to_string().bytes() {
                    out.push_str(&format!("\\{b:03o}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// 파이썬 `git add -- p`가 경로를 다듬는 것 — `/`로 가르고 빈 조각·`.`을 버리고 `..`는 앞 조각을 지운다
fn normal_path(path: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for p in path.split('/') {
        match p {
            "" | "." => {}
            ".." => {
                parts.pop();
            }
            p => parts.push(p),
        }
    }
    parts.join("/")
}

/// 트리 객체에서 이름의 모드 — 줄마다 `{모드} {이름}\0{oid 바이트}`
fn tree_mode(tree: &[u8], name: &str, oid_bytes: usize) -> Option<String> {
    let mut i = 0;
    while i < tree.len() {
        let sp = i + tree[i..].iter().position(|&b| b == b' ')?;
        let nul = sp + 1 + tree[sp + 1..].iter().position(|&b| b == 0)?;
        if &tree[sp + 1..nul] == name.as_bytes() {
            return Some(String::from_utf8_lossy(&tree[i..sp]).into_owned());
        }
        i = nul + 1 + oid_bytes;
    }
    None
}

/// 끝 코드·표준 출력·표준 오류
struct Out {
    code: i32,
    stdout: String,
    stderr: String,
}

fn os(s: &str) -> &OsStr {
    OsStr::new(s)
}

/// 파이썬 `GitError`의 명령 — `git` + 인자를 빈칸으로
fn cmd_text(args: &[&OsStr]) -> String {
    let mut s = String::from("git");
    for a in args {
        s.push(' ');
        s.push_str(&a.to_string_lossy());
    }
    s
}

/// 커밋 작성자 → 아이디 — noreply 메일이면 앞부분(ID+ 접두어를 뗀다), 아니면 이름 (파이썬 `_login_of`)
fn login_of(name: &str, email: &str) -> String {
    if email.ends_with("@users.noreply.github.com") {
        let local = email.split('@').next().unwrap_or("");
        return local.rsplit('+').next().unwrap_or("").to_string();
    }
    name.to_string()
}

/// 「제목\n본문」 → 본문이 있으면 `제목\n\n본문`(걷어서), 없으면 제목 (파이썬 `_message`)
fn commit_message(subject_body: &str) -> String {
    let (subject, body) = subject_body.split_once('\n').unwrap_or((subject_body, ""));
    let body = strip(body);
    if body.is_empty() {
        subject.to_string()
    } else {
        format!("{subject}\n\n{body}")
    }
}

/// 파이썬 `PurePosixPath(p).parts` — `/`로 가르고 빈 조각·`.`은 버린다(절대 경로면 앞에 `/`)
fn posix_parts(path: &str) -> Vec<&str> {
    let mut out: Vec<&str> = Vec::new();
    if path.starts_with('/') {
        out.push("/");
    }
    out.extend(path.split('/').filter(|p| !p.is_empty() && *p != "."));
    out
}

fn is_hash(s: &str) -> bool {
    s.len() == 40
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl Git {
    /// SYNC-MS-019#Git.new
    pub fn new(exe: PathBuf, global_config: PathBuf) -> Git {
        Git {
            exe,
            global_config,
            readers: Readers::default(),
        }
    }

    fn command(&self, cwd: Option<&Path>, args: &[&OsStr]) -> Command {
        let mut c = Command::new(&self.exe);
        c.args(ISOLATE)
            .args(args)
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", &self.global_config)
            .env("GIT_TERMINAL_PROMPT", "0")
            .env("LC_ALL", "C")
            .env("LANGUAGE", "C")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        if let Some(d) = cwd {
            c.current_dir(d);
        }
        #[cfg(windows)]
        c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW — 창 없는 실행 파일에서 콘솔이 번쩍이지 않게
        c
    }

    /// 실패해도 돌려준다 — 끝 코드를 보는 자리(파이썬 `_exec`)
    async fn exec(&self, cwd: Option<&Path>, args: &[&OsStr]) -> Result<Out, Problem> {
        let out = self
            .command(cwd, args)
            .output()
            .await
            .map_err(|e| Problem::Internal {
                log: format!("{}을 못 돌렸다 — {e}", cmd_text(args)),
            })?;
        let stdout = String::from_utf8(out.stdout).map_err(|e| Problem::Internal {
            log: format!("{}의 출력이 UTF-8이 아니다 — {e}", cmd_text(args)),
        })?;
        Ok(Out {
            code: out.status.code().unwrap_or(-1),
            stdout,
            stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
        })
    }

    /// git 입구의 자식 — 본문을 표준 입력으로 넣는 일과 출력을 읽는 일을 동시에(차례로 하면 파이프가 찬다).
    /// 끝 코드와 상관없이 표준 출력을 돌려준다 — http-backend도 응답을 보낸 뒤에야 끝 코드를 본다
    async fn pipe(
        &self,
        args: &[&OsStr],
        input: Vec<u8>,
        protocol: Option<&str>,
    ) -> Result<Vec<u8>, Problem> {
        let mut c = self.command(None, args);
        c.stdin(Stdio::piped());
        if let Some(p) = protocol {
            c.env("GIT_PROTOCOL", p);
        }
        let mut child = c.spawn().map_err(|e| Problem::Internal {
            log: format!("{}을 못 돌렸다 — {e}", cmd_text(args)),
        })?;
        let mut stdin = child.stdin.take();
        let feed = tokio::spawn(async move {
            if let Some(w) = stdin.as_mut() {
                use tokio::io::AsyncWriteExt;
                // 자식이 먼저 끝났으면(거절 등) 그 답은 표준 출력에 있다
                let _ = w.write_all(&input).await;
                let _ = w.shutdown().await;
            }
        });
        let out = child
            .wait_with_output()
            .await
            .map_err(|e| Problem::Internal {
                log: format!("{}을 기다리지 못했다 — {e}", cmd_text(args)),
            })?;
        let _ = feed.await;
        if !out.status.success() {
            tracing::warn!(
                "{} 끝 코드 {:?} — {}",
                cmd_text(args),
                out.status.code(),
                String::from_utf8_lossy(&out.stderr)
            );
        }
        Ok(out.stdout)
    }

    /// 끝 코드가 0이 아니면 `Problem::Git`(파이썬 `_run`)
    async fn run(&self, cwd: Option<&Path>, args: &[&OsStr]) -> Result<String, Problem> {
        let o = self.exec(cwd, args).await?;
        if o.code != 0 {
            return Err(Problem::Git {
                cmd: cmd_text(args),
                stderr: o.stderr,
            });
        }
        Ok(o.stdout)
    }

    /// 저장소의 읽기 프로세스를 띄운다 — 저장소 자리가 없으면 `Problem::Internal`
    fn spawn_batch(&self, repo: &Path) -> Result<Batch, Problem> {
        let args = [os("cat-file"), os("--batch")];
        let mut c = self.command(Some(repo), &args);
        c.stdin(Stdio::piped()).stderr(Stdio::null());
        let mut child = c.spawn().map_err(|e| Problem::Internal {
            log: format!("{}을 못 돌렸다 — {e}", cmd_text(&args)),
        })?;
        let (Some(stdin), Some(stdout)) = (child.stdin.take(), child.stdout.take()) else {
            return Err(Problem::Internal {
                log: "git cat-file --batch의 파이프가 없다".into(),
            });
        };
        Ok(Batch {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        })
    }

    /// 읽기 프로세스에 묻는다(MS-019 0장) — 죽었으면 한 번 다시 띄운다. 그래도 답이 없으면 `Broken`
    async fn lookup(&self, repo: &Path, name: &str) -> Result<Lookup, Problem> {
        if name.contains(['\n', '\0']) {
            return Ok(Lookup::Broken);
        }
        let slot = self.readers.slot(repo);
        let mut guard = slot.lock().await;
        for _ in 0..2 {
            if guard.is_none() {
                *guard = Some(self.spawn_batch(repo)?);
            }
            let Some(batch) = guard.as_mut() else {
                break;
            };
            match batch.ask(name).await {
                Ok(answer) => return Ok(answer),
                Err(e) => {
                    tracing::debug!("git cat-file --batch({}) — {e}", repo.display());
                    *guard = None;
                }
            }
        }
        Ok(Lookup::Broken)
    }

    /// `{rev}:{path}`의 블롭 oid — 없으면 `None`(다른 꼴도)
    async fn blob_oid(
        &self,
        repo: &Path,
        rev: &str,
        path: &str,
    ) -> Result<Option<String>, Problem> {
        Ok(match self.lookup(repo, &format!("{rev}:{path}")).await? {
            Lookup::Found(o) if o.kind == "blob" => Some(o.oid),
            _ => None,
        })
    }

    /// `{rev}`에서 경로의 모드 — 그 폴더 트리를 읽는다. 없으면 `None`
    async fn mode_of(&self, repo: &Path, rev: &str, path: &str) -> Result<Option<String>, Problem> {
        let (dir, name) = path.rsplit_once('/').unwrap_or(("", path));
        Ok(match self.lookup(repo, &format!("{rev}:{dir}")).await? {
            Lookup::Found(t) if t.kind == "tree" => tree_mode(&t.data, name, t.oid.len() / 2),
            _ => None,
        })
    }
}

/// `Git.archive`의 풀기 — 보통 파일·폴더만, 저장소 안 경로만 (파이썬 `extractall(filter="data")` 대신)
fn untar(tar: &Path, dest: &Path) -> Result<(), Problem> {
    let mut a = tar::Archive::new(fs::File::open(tar)?);
    for entry in a.entries()? {
        let mut e = entry?;
        let kind = e.header().entry_type();
        if !(kind.is_file() || kind.is_dir()) {
            continue;
        }
        let path = e.path()?.into_owned();
        let inside = path
            .components()
            .all(|c| matches!(c, Component::Normal(_) | Component::CurDir));
        if !inside {
            continue;
        }
        let to = dest.join(&path);
        if kind.is_dir() {
            fs::create_dir_all(&to)?;
        } else {
            if let Some(parent) = to.parent() {
                fs::create_dir_all(parent)?;
            }
            e.unpack(&to)?;
        }
    }
    Ok(())
}

/// 파이썬 `PurePosixPath(p).match(glob)` — 뒤에서부터 조각마다 맞춘다. 조각 안에서 `*`는 아무 글자들, `?`는 한 글자
fn path_match(path: &str, glob: &str) -> bool {
    let parts: Vec<&str> = path
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    let pats: Vec<&str> = glob
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    if pats.is_empty() || pats.len() > parts.len() {
        return false;
    }
    parts.iter().rev().zip(pats.iter().rev()).all(|(p, g)| {
        fnmatch(
            &p.chars().collect::<Vec<_>>(),
            &g.chars().collect::<Vec<_>>(),
        )
    })
}

fn fnmatch(s: &[char], p: &[char]) -> bool {
    match p.split_first() {
        None => s.is_empty(),
        Some(('*', rest)) => (0..=s.len()).any(|i| fnmatch(&s[i..], rest)),
        Some(('?', rest)) => !s.is_empty() && fnmatch(&s[1..], rest),
        Some((c, rest)) => s.first() == Some(c) && fnmatch(&s[1..], rest),
    }
}

/// 파이썬 `Path.resolve()`(엄격하지 않게) — 있는 조각의 심볼릭 링크를 풀고 `..`를 접는다
fn resolve(p: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for comp in p.components() {
        match comp {
            Component::Prefix(_) | Component::RootDir => out.push(comp.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            Component::Normal(n) => {
                out.push(n);
                if fs::symlink_metadata(&out).is_ok_and(|m| m.file_type().is_symlink())
                    && let Ok(real) = fs::canonicalize(&out)
                {
                    out = real;
                }
            }
        }
    }
    out
}

/// 쓰거나 지울 경로가 작업 사본 안이고 `.git` 조각이 없나 (MS-009 commit_push 3)
fn inside(workdir: &Path, rel: &str) -> bool {
    if rel.is_empty() || rel.split('/').any(|p| p == ".git") {
        return false;
    }
    let root = resolve(&std::path::absolute(workdir).unwrap_or_else(|_| workdir.to_path_buf()));
    let target = resolve(&root.join(rel));
    target == root || target.starts_with(&root)
}

fn push_failed(reason: impl Into<String>) -> Problem {
    Problem::PushFailed {
        reason: reason.into(),
    }
}

impl Git {
    /// SYNC-MS-019#Git.init_bare
    pub async fn init_bare(&self, path: &Path) -> Result<(), Problem> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        self.run(
            None,
            &[
                os("init"),
                os("-q"),
                os("--bare"),
                os("--initial-branch=main"),
                path.as_os_str(),
            ],
        )
        .await?;
        for key in RECEIVE_RULES {
            self.run(Some(path), &[os("config"), os(key), os("true")])
                .await?;
        }
        Ok(())
    }

    /// SYNC-MS-019#Git.exists
    pub async fn exists(&self, origin: &Path, path: &str) -> Result<bool, Problem> {
        match self.lookup(origin, &format!("HEAD:{path}")).await? {
            Lookup::Found(_) => Ok(true),
            Lookup::Missing => Ok(false),
            Lookup::Broken => self.exists_spawn(origin, path).await,
        }
    }

    /// 읽기 프로세스가 답하지 못할 때 — 파이썬 판의 두 명령 그대로(저장소가 아니면 `Problem::Git`)
    async fn exists_spawn(&self, workdir: &Path, path: &str) -> Result<bool, Problem> {
        // HEAD 없음을 stderr 문구로 가리지 않는다(#349) — 가리키는 커밋이 없으면 조용히 끝 코드 1
        let head = [
            os("rev-parse"),
            os("--verify"),
            os("--quiet"),
            os("HEAD^{commit}"),
        ];
        let o = self.exec(Some(workdir), &head).await?;
        if o.code == 1 {
            return Ok(false);
        }
        if o.code != 0 {
            return Err(Problem::Git {
                cmd: cmd_text(&head),
                stderr: o.stderr,
            });
        }
        let out = self
            .run(
                Some(workdir),
                &[os("ls-tree"), os("HEAD"), os("--"), os(path)],
            )
            .await?;
        Ok(!strip(&out).is_empty())
    }

    /// SYNC-MS-019#Git.list
    pub async fn list(
        &self,
        origin: &Path,
        glob: &str,
        git_ref: &str,
    ) -> Result<Vec<String>, Problem> {
        let out = self
            .run(
                Some(origin),
                &[
                    os("ls-tree"),
                    os("-r"),
                    os("--name-only"),
                    os(git_ref),
                    os("--"),
                    os("docs/specs"),
                ],
            )
            .await?;
        // 명세가 아닌 것은 뺀다 — 템플릿·첨부 (MS-009 list, #40)
        Ok(py_splitlines(&out)
            .into_iter()
            .filter(|p| {
                path_match(p, glob) && !p.split('/').any(|x| x == "_templates" || x == "assets")
            })
            .map(str::to_string)
            .collect())
    }

    /// SYNC-MS-019#Git.read
    ///
    /// 읽기 프로세스에 묻고, 블롭이 아니면(없다·트리·답 없음) 그때만 `git show`를 띄워 같은 답·같은 오류 문장
    pub async fn read(&self, origin: &Path, path: &str, git_ref: &str) -> Result<String, Problem> {
        let spec = format!("{git_ref}:{path}");
        if let Lookup::Found(o) = self.lookup(origin, &spec).await?
            && o.kind == "blob"
        {
            return String::from_utf8(o.data).map_err(|e| Problem::Internal {
                log: format!("git show {spec}의 출력이 UTF-8이 아니다 — {e}"),
            });
        }
        let spec: OsString = spec.into();
        self.run(Some(origin), &[os("show"), &spec]).await
    }

    /// SYNC-MS-019#Git.commit
    ///
    /// 서버 저장소 main 위에 `fast-import` 하나로 — `git commit`과 같은 객체(본인 줄·시각·메시지 정리).
    /// 저장 도중 밖에서 같은 파일을 밀었으면 합치지 않고 `conflict`(파이썬 판은 rebase — 계약 밖)
    pub async fn commit(
        &self,
        origin: &Path,
        workdir: &Path,
        message: &str,
        user: &UserRow,
        files: &IndexMap<String, String>,
        delete: &[String],
    ) -> Result<Committed, Problem> {
        // 3. 부모 = 서버 저장소의 main 끝(빈 저장소면 없음)
        let parent = self.head(origin).await?;
        let change = Change {
            message,
            user,
            files,
            delete,
        };
        self.commit_from(origin, workdir, parent, &change).await
    }

    /// `commit` 1·2·4~9 — 부모를 받는다(시험이 사이에 밖에서 민 것을 흉내 낸다)
    async fn commit_from(
        &self,
        origin: &Path,
        workdir: &Path,
        parent: Option<String>,
        change: &Change<'_>,
    ) -> Result<Committed, Problem> {
        let Change {
            message,
            user,
            files,
            delete,
        } = *change;
        let mut parent = parent;
        // 1. 경로 가드 — 아무것도 쓰기 전에 (MS-009 commit_push 3과 같은 문장)
        for p in files.keys().chain(delete.iter()) {
            if !inside(workdir, p) {
                return Err(push_failed(format!("작업 사본 밖 경로: {p}")));
            }
        }
        // 파이썬 판은 이런 글자를 명령줄에 넘기지 못해 예외다
        let texts = [
            message,
            user.display_name.as_str(),
            user.github_login.as_str(),
        ];
        if texts
            .iter()
            .chain(files.keys().map(String::as_str).collect::<Vec<_>>().iter())
            .chain(delete.iter().map(String::as_str).collect::<Vec<_>>().iter())
            .any(|t| t.contains('\0'))
        {
            return Err(Problem::Internal {
                log: "git 인자에 NUL이 있다".into(),
            });
        }
        let changes: Vec<(String, Option<&String>)> = files
            .iter()
            .map(|(p, body)| (normal_path(p), Some(body)))
            .chain(delete.iter().map(|p| (normal_path(p), None)))
            .collect();
        let domain = if user.kind == UserKind::Local.as_str() {
            "syncdoc.local"
        } else {
            "users.noreply.github.com"
        };
        let name = without_crud(&user.display_name);
        let email = without_crud(&format!("{}@{domain}", user.github_login));
        let mut last_err = String::new();
        for _ in 0..=PUSH_RETRIES {
            // 4. 바뀐 것이 없으면 커밋 없이 (파이썬 `diff --cached --quiet`)
            let mut changed = false;
            let mut modes: Vec<String> = Vec::with_capacity(changes.len());
            for (path, body) in &changes {
                let have = match parent.as_deref() {
                    Some(rev) => self.blob_oid(origin, rev, path).await?,
                    None => None,
                };
                let mode = match (parent.as_deref(), &have) {
                    (Some(rev), Some(_)) => self.mode_of(origin, rev, path).await?,
                    _ => None,
                };
                modes.push(match mode.as_deref() {
                    Some("100755") => "100755".to_string(),
                    _ => "100644".to_string(),
                });
                changed |= match (body, &have, parent.as_deref()) {
                    (None, None, _) => false,
                    (None, Some(_), _) => true,
                    (Some(_), None, _) => true,
                    (Some(body), Some(_), Some(rev)) => {
                        self.read_blob(origin, rev, path).await? != body.as_bytes()
                    }
                    (Some(_), Some(_), None) => true,
                };
            }
            if !changed {
                let Some(hash) = parent.clone() else {
                    // 빈 저장소에 아무것도 없다 — 파이썬 판의 `rev-parse HEAD`가 실패한다
                    return Err(Problem::Git {
                        cmd: "git rev-parse HEAD".into(),
                        stderr: "fatal: ambiguous argument 'HEAD': unknown revision".into(),
                    });
                };
                return Ok(Committed { hash, parent });
            }
            // 2. 메시지 — 커밋할 것이 있을 때만 (파이썬 판은 빈 메시지면 `git commit`이 실패한다)
            let msg = stripspace(message);
            if msg.is_empty() || name.is_empty() {
                return Err(Problem::Git {
                    cmd: "git commit -q -m".into(),
                    stderr: "Aborting commit due to empty commit message.\n".into(),
                });
            }
            let who = format!("{name} <{email}> {}", git_now());
            let mut stream: Vec<u8> = Vec::new();
            stream.extend(
                format!("commit refs/heads/main\nmark :1\nauthor {who}\ncommitter {who}\n").bytes(),
            );
            stream.extend(format!("data {}\n", msg.len()).bytes());
            stream.extend(msg.bytes());
            stream.push(b'\n');
            if let Some(p) = parent.as_deref() {
                stream.extend(format!("from {p}\n").bytes());
            }
            for ((path, body), mode) in changes.iter().zip(&modes) {
                match body {
                    Some(body) => {
                        stream.extend(
                            format!("M {mode} inline {}\ndata {}\n", fi_path(path), body.len())
                                .bytes(),
                        );
                        stream.extend(body.bytes());
                        stream.push(b'\n');
                    }
                    None => stream.extend(format!("D {}\n", fi_path(path)).bytes()),
                }
            }
            stream.extend(b"\nget-mark :1\ndone\n");
            let (code, out, err) = self.fast_import(origin, stream).await?;
            if code == 0 {
                let hash = strip(&out).to_string();
                self.write_folder(workdir, &changes);
                return Ok(Committed { hash, parent });
            }
            last_err = err;
            // 7. 거부 — 사이에 밖에서 밀었으면 같은 경로가 바뀌었나 본다
            let now = self.head(origin).await?;
            if now == parent {
                break;
            }
            for (path, _) in &changes {
                let before = match parent.as_deref() {
                    Some(rev) => self.blob_oid(origin, rev, path).await?,
                    None => None,
                };
                let after = match now.as_deref() {
                    Some(rev) => self.blob_oid(origin, rev, path).await?,
                    None => None,
                };
                if before != after {
                    return Err(push_failed("conflict"));
                }
            }
            parent = now;
        }
        Err(push_failed(strip(&last_err).to_string()))
    }

    /// 블롭 내용 그대로 — 없으면 빈 것
    async fn read_blob(&self, repo: &Path, rev: &str, path: &str) -> Result<Vec<u8>, Problem> {
        Ok(match self.lookup(repo, &format!("{rev}:{path}")).await? {
            Lookup::Found(o) if o.kind == "blob" => o.data,
            _ => Vec::new(),
        })
    }

    /// `git fast-import --quiet --done`에 한 번에 넣는다 — 끝 코드·표준 출력·표준 오류
    async fn fast_import(
        &self,
        origin: &Path,
        stream: Vec<u8>,
    ) -> Result<(i32, String, String), Problem> {
        let args = [os("fast-import"), os("--quiet"), os("--done")];
        let mut c = self.command(Some(origin), &args);
        c.stdin(Stdio::piped());
        let mut child = c.spawn().map_err(|e| Problem::Internal {
            log: format!("{}을 못 돌렸다 — {e}", cmd_text(&args)),
        })?;
        let mut stdin = child.stdin.take();
        let feed = tokio::spawn(async move {
            if let Some(w) = stdin.as_mut() {
                let _ = w.write_all(&stream).await;
                let _ = w.shutdown().await;
            }
        });
        let out = child
            .wait_with_output()
            .await
            .map_err(|e| Problem::Internal {
                log: format!("{}을 기다리지 못했다 — {e}", cmd_text(&args)),
            })?;
        let _ = feed.await;
        Ok((
            out.status.code().unwrap_or(-1),
            String::from_utf8_lossy(&out.stdout).into_owned(),
            String::from_utf8_lossy(&out.stderr).into_owned(),
        ))
    }

    /// 작업 사본 폴더에 `docs/specs/` 아래의 쓴 것·지운 것을 — 폴더가 있을 때만, 실패는 로그만(첨부 파일 읽기만 쓴다)
    fn write_folder(&self, workdir: &Path, changes: &[(String, Option<&String>)]) {
        if !workdir.is_dir() {
            return;
        }
        for (path, body) in changes {
            if !path.starts_with("docs/specs/") {
                continue;
            }
            let f = workdir.join(path);
            let done = match body {
                Some(body) => f
                    .parent()
                    .map_or(Ok(()), fs::create_dir_all)
                    .and_then(|()| fs::write(&f, body.as_bytes())),
                None => match fs::remove_file(&f) {
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
                    other => other,
                },
            };
            if let Err(e) = done {
                tracing::warn!("작업 사본 폴더 {} — {e}", f.display());
            }
        }
    }

    /// SYNC-MS-019#Git.init_specs
    pub fn init_specs(specs_url: &str) -> IndexMap<String, String> {
        let mut files = IndexMap::new();
        for t in SPEC_TYPES {
            let dir = match stage_of(t) {
                Some(n) => format!("{n:02}-{t}"),
                None => t.to_string(),
            };
            files.insert(format!("docs/specs/{dir}/.gitkeep"), String::new());
        }
        files.insert("docs/specs/assets/.gitkeep".to_string(), String::new());
        files.insert(
            README_PATH.to_string(),
            README.replace("{SPECS_URL}", specs_url.trim_end_matches('/')),
        );
        files
    }

    /// SYNC-MS-019#Git.head
    ///
    /// 서버 저장소의 `refs/heads/main` — 빈 저장소면 `None`. 받지 않는다(작업 사본이 git이 아니다)
    pub async fn head(&self, origin: &Path) -> Result<Option<String>, Problem> {
        match self.lookup(origin, "refs/heads/main").await? {
            Lookup::Found(o) if o.kind == "commit" => Ok(Some(o.oid)),
            Lookup::Found(_) | Lookup::Missing => Ok(None),
            Lookup::Broken => {
                let args = [
                    os("rev-parse"),
                    os("--verify"),
                    os("--quiet"),
                    os("refs/heads/main"),
                ];
                let o = self.exec(Some(origin), &args).await?;
                match o.code {
                    0 => Ok(Some(strip(&o.stdout).to_string())),
                    1 => Ok(None),
                    _ => Err(Problem::Git {
                        cmd: cmd_text(&args),
                        stderr: o.stderr,
                    }),
                }
            }
        }
    }

    /// SYNC-MS-019#Git.rev_list_count
    pub async fn rev_list_count(&self, origin: &Path, range: &str) -> Result<i64, Problem> {
        let out = self
            .run(Some(origin), &[os("rev-list"), os("--count"), os(range)])
            .await?;
        strip(&out).parse().map_err(|_| Problem::Internal {
            log: format!("git rev-list --count {range}의 출력이 수가 아니다: {out}"),
        })
    }

    /// SYNC-MS-019#Git.changed_files
    ///
    /// 커밋은 최신부터 — 경로마다 처음 본 것(가장 최근)만. 이름 바꾸기는 새 경로의 `M`으로 접고 옛 경로는 막는다(#31)
    pub async fn changed_files(
        &self,
        origin: &Path,
        range: &str,
        prefix: &str,
    ) -> Result<Vec<ChangedFile>, Problem> {
        let out = self
            .run(
                Some(origin),
                &[
                    os("log"),
                    os("--name-status"),
                    os("--format=%H%x00%an%x00%ae%x00%s%n%b%x00"),
                    os(range),
                    os("--"),
                    os(prefix),
                ],
            )
            .await?;
        // 막힌 옛 경로는 None — 더 앞선 커밋의 같은 경로를 막는다
        let mut seen: std::collections::BTreeMap<String, Option<ChangedFile>> =
            std::collections::BTreeMap::new();
        let tokens: Vec<&str> = out.split('\0').collect();
        let mut hash = strip(tokens[0]).to_string();
        let mut i = 4;
        while i < tokens.len() {
            let (an, ae, msg) = (tokens[i - 3], tokens[i - 2], tokens[i - 1]);
            let lines: Vec<&str> = tokens[i].split('\n').collect();
            let last = strip(lines.last().copied().unwrap_or(""));
            let next_hash = if is_hash(last) {
                last.to_string()
            } else {
                String::new()
            };
            for line in &lines {
                if !line.contains('\t') {
                    continue;
                }
                let mut cols = line.split('\t');
                let mut status = cols.next().unwrap_or("").to_string();
                let paths: Vec<&str> = cols.collect();
                let path = paths.last().copied().unwrap_or("");
                if status.starts_with('R') && paths.len() == 2 {
                    seen.entry(paths[0].to_string()).or_insert(None);
                    status = "M".to_string();
                }
                let parts = posix_parts(path);
                if parts.contains(&"_templates")
                    || parts.contains(&"assets")
                    || parts.len() <= 3
                    || seen.contains_key(path)
                {
                    continue;
                }
                seen.insert(
                    path.to_string(),
                    Some(ChangedFile {
                        path: path.to_string(),
                        status: status.chars().next().map(String::from).unwrap_or_default(),
                        commit_hash: hash.clone(),
                        author_login: login_of(an, ae),
                        message: commit_message(msg),
                        author_email: ae.to_string(),
                    }),
                );
            }
            hash = next_hash;
            i += 4;
        }
        Ok(seen.into_values().flatten().collect())
    }

    /// SYNC-MS-019#Git.log
    ///
    /// `--follow`는 `--reverse`와 함께 쓰지 못한다 — 받아서 뒤집는다(#39). 지운 커밋은 뺀다(#325).
    /// 커밋 경계는 앞쪽 구분자 `%x1e` — `--name-only`가 메시지 뒤에 빈 줄과 그때의 경로를 붙인다
    pub async fn log(&self, origin: &Path, path: &str) -> Result<Vec<Commit>, Problem> {
        let out = self
            .run(
                Some(origin),
                &[
                    os("log"),
                    os("--follow"),
                    os("--diff-filter=d"),
                    os("--name-only"),
                    os("--format=%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%s%n%b"),
                    os("--"),
                    os(path),
                ],
            )
            .await?;
        let mut commits = Vec::new();
        for block in out.split('\u{1e}').skip(1) {
            let mut f = block.splitn(5, '\u{1f}');
            let (h, an, ae, date, rest) = (
                f.next().unwrap_or(""),
                f.next().unwrap_or(""),
                f.next().unwrap_or(""),
                f.next().unwrap_or(""),
                f.next().unwrap_or(""),
            );
            let lines: Vec<&str> = rest.trim_end_matches('\n').split('\n').collect();
            let (at_path, msg) = match lines.split_last() {
                Some((last, head)) => (*last, head.join("\n")),
                None => ("", String::new()),
            };
            let date =
                time::OffsetDateTime::parse(date, &time::format_description::well_known::Rfc3339)
                    .map_err(|e| Problem::Internal {
                    log: format!("git log 시각을 못 읽었다 {date:?} — {e}"),
                })?;
            commits.push(Commit {
                hash: h.to_string(),
                login: login_of(an, ae),
                date,
                message: commit_message(msg.trim_matches('\n')),
                email: ae.to_string(),
                path: at_path.to_string(),
            });
        }
        commits.reverse();
        Ok(commits)
    }

    /// SYNC-MS-019#Git.changed_paths
    ///
    /// 범위에서 바뀐 경로 전부 — `changed_files`와 달리 명세 밖도 거르지 않는다. 코드가 바뀌었는지(커밋 처리 5a)만 본다
    pub async fn changed_paths(&self, origin: &Path, range: &str) -> Result<Vec<String>, Problem> {
        let out = self
            .run(Some(origin), &[os("diff"), os("--name-only"), os(range)])
            .await?;
        Ok(py_splitlines(&out)
            .into_iter()
            .filter(|l| !strip(l).is_empty())
            .map(str::to_string)
            .collect())
    }

    /// SYNC-MS-019#Git.archive
    ///
    /// 커밋된 파일만 `dest`에 푼다 — .gitignore된 산출물이 섞이지 않는다(INFRA 4.3).
    /// 보통 파일과 폴더만 — 링크는 따라가지도 만들지도 않고, 절대 경로·`..` 조각은 버린다
    pub async fn archive(&self, origin: &Path, commit: &str, dest: &Path) -> Result<(), Problem> {
        self.unpack(origin, commit, None, dest).await
    }

    /// `git archive`를 `dest`에 푼다 — `only`가 있으면 그 경로만
    async fn unpack(
        &self,
        origin: &Path,
        commit: &str,
        only: Option<&str>,
        dest: &Path,
    ) -> Result<(), Problem> {
        fs::create_dir_all(dest)?;
        let tar = dest.join(".src.tar");
        let mut args = vec![
            os("archive"),
            os("--format=tar"),
            os("-o"),
            tar.as_os_str(),
            os(commit),
        ];
        if let Some(path) = only {
            args.push(os(path));
        }
        self.run(Some(origin), &args).await?;
        let (from, to) = (tar.clone(), dest.to_path_buf());
        let done = tokio::task::spawn_blocking(move || untar(&from, &to))
            .await
            .map_err(|e| Problem::Internal {
                log: format!("tar 풀기가 멈췄다 — {e}"),
            });
        let _ = fs::remove_file(&tar);
        done?
    }

    /// SYNC-MS-019#Git.clone_bare
    ///
    /// 번들을 서버 저장소로 통째로 — 가지·태그가 해시 그대로. 원격을 지우고 HEAD를 main으로, 받기 규칙은 init_bare와 같다
    pub async fn clone_bare(&self, source: &str, path: &Path) -> Result<(), Problem> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        self.run(
            None,
            &[
                os("clone"),
                os("-q"),
                os("--bare"),
                os(source),
                path.as_os_str(),
            ],
        )
        .await?;
        let at = Some(path);
        self.run(at, &[os("remote"), os("remove"), os("origin")])
            .await?;
        self.run(at, &[os("symbolic-ref"), os("HEAD"), os("refs/heads/main")])
            .await?;
        for key in RECEIVE_RULES {
            self.run(at, &[os("config"), os(key), os("true")]).await?;
        }
        Ok(())
    }

    /// SYNC-MS-019#Git.mirror
    ///
    /// 백업의 서버 저장소 사진(L16) — 켠 채로 떠도 참조와 객체가 맞게 upload-pack을 거친다(`--no-local`).
    /// 원격을 지우고 HEAD를 원본대로, 받기 규칙은 init_bare와 같다
    pub async fn mirror(&self, source: &Path, dest: &Path) -> Result<(), Problem> {
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }
        let head = self
            .run(Some(source), &[os("symbolic-ref"), os("HEAD")])
            .await
            .map(|h| strip(&h).to_string())
            .unwrap_or_else(|_| "refs/heads/main".to_string());
        self.run(
            None,
            &[
                os("clone"),
                os("--mirror"),
                os("--no-local"),
                os("-q"),
                source.as_os_str(),
                dest.as_os_str(),
            ],
        )
        .await?;
        let at = Some(dest);
        self.run(at, &[os("remote"), os("remove"), os("origin")])
            .await?;
        self.run(at, &[os("symbolic-ref"), os("HEAD"), os(&head)])
            .await?;
        for key in RECEIVE_RULES {
            self.run(at, &[os("config"), os(key), os("true")]).await?;
        }
        Ok(())
    }

    /// SYNC-MS-019#Git.sync_readme
    ///
    /// 재구축 위임이 저장소에 쓰는 유일한 것 — 같으면 커밋이 생기지 않는다
    pub async fn sync_readme(
        &self,
        origin: &Path,
        workdir: &Path,
        user: &UserRow,
        code: &str,
        specs_url: &str,
    ) -> Result<Option<String>, Problem> {
        let mut files = Self::init_specs(specs_url);
        let want = files.shift_remove(README_PATH).unwrap_or_default();
        let have = self
            .read(origin, README_PATH, "refs/heads/main")
            .await
            .unwrap_or_default(); // README가 없는 저장소
        if have == want {
            return Ok(None);
        }
        let message = format!("chore({code}): README를 싱크독 규약 링크로");
        let one = IndexMap::from([(README_PATH.to_string(), want)]);
        Ok(Some(
            self.commit(origin, workdir, &message, user, &one, &[])
                .await?
                .hash,
        ))
    }

    /// SYNC-MS-019#Git.materialize
    ///
    /// 작업 사본 폴더 = 커밋의 `docs/specs/`(카드 L19) — 지우고 다시 푼다. 옛 판의 clone(`.git`)도 이것으로 바뀐다
    pub async fn materialize(
        &self,
        origin: &Path,
        commit: &str,
        workdir: &Path,
    ) -> Result<(), Problem> {
        if workdir.exists() {
            fs::remove_dir_all(workdir)?;
        }
        fs::create_dir_all(workdir)?;
        if let Lookup::Missing = self.lookup(origin, &format!("{commit}:docs/specs")).await? {
            return Ok(());
        }
        self.unpack(origin, commit, Some("docs/specs"), workdir)
            .await
    }

    /// SYNC-MS-019#Git.close
    ///
    /// 그 저장소의 읽기 프로세스를 끝내고 기다린다 — 윈도는 열린 팩 파일이 있으면 폴더를 옮기지도 지우지도 못한다
    pub async fn close(&self, origin: &Path) {
        let Some(slot) = self.readers.take(origin) else {
            return;
        };
        let mut guard = slot.lock().await;
        if let Some(mut batch) = guard.take() {
            drop(batch.stdin);
            let _ = batch.child.start_kill();
            let _ = batch.child.wait().await;
        }
    }

    /// SYNC-MS-019#Git.close_all
    pub async fn close_all(&self) {
        for origin in self.readers.repos() {
            self.close(&origin).await;
        }
    }

    /// SYNC-MS-019#Git.gc
    ///
    /// 전역 설정의 `gc.auto=0`을 이 한 번만 git 기본 문턱으로 — 쌓인 것이 문턱 아래면 아무것도 하지 않는다
    pub async fn gc(&self, origin: &Path) -> Result<(), Problem> {
        self.close(origin).await;
        self.run(
            Some(origin),
            &[
                os("-c"),
                os("gc.auto=6700"),
                os("-c"),
                os("gc.autoPackLimit=50"),
                os("-c"),
                os("gc.autoDetach=false"),
                os("gc"),
                os("--auto"),
                os("--quiet"),
            ],
        )
        .await?;
        Ok(())
    }

    /// SYNC-MS-019#Git.advertise_refs
    ///
    /// http-backend `get_info_refs` 그대로 — v2가 아니면 앞에 `# service=…` pkt-line과 flush
    pub async fn advertise_refs(
        &self,
        origin: &Path,
        service: &str,
        protocol: Option<&str>,
    ) -> Result<Vec<u8>, Problem> {
        let mut out = Vec::new();
        if protocol_version(protocol) != 2 {
            let line = format!("# service={service}\n");
            out.extend(format!("{:04x}{line}0000", line.len() + 4).into_bytes());
        }
        let sub = service.strip_prefix("git-").unwrap_or(service);
        let o: &OsStr = origin.as_os_str();
        out.extend(
            self.pipe(
                &[os(sub), os("--stateless-rpc"), os("--advertise-refs"), o],
                Vec::new(),
                protocol,
            )
            .await?,
        );
        Ok(out)
    }

    /// SYNC-MS-019#Git.service_rpc
    ///
    /// 본문은 부른 쪽이 다 받아(gzip이면 풀어) 넘긴다. 되감기·지우기 거절은 받기 규칙이 git 프로토콜 응답 안에서 한다
    pub async fn service_rpc(
        &self,
        origin: &Path,
        service: &str,
        body: Vec<u8>,
        protocol: Option<&str>,
    ) -> Result<Vec<u8>, Problem> {
        let sub = service.strip_prefix("git-").unwrap_or(service);
        let o: &OsStr = origin.as_os_str();
        self.pipe(&[os(sub), os("--stateless-rpc"), o], body, protocol)
            .await
    }
}

/// git `determine_protocol_version_server` — `:`로 나눈 `version=` 값 가운데 가장 큰 것(`0`·`1`·`2`만 센다)
fn protocol_version(protocol: Option<&str>) -> u8 {
    protocol
        .unwrap_or("")
        .split(':')
        .filter_map(|item| match item.strip_prefix("version=")? {
            "0" => Some(0),
            "1" => Some(1),
            "2" => Some(2),
            _ => None,
        })
        .max()
        .unwrap_or(0)
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn isolates_user_git_config() {
        let g = Git::new("git".into(), "/tmp/empty-gitconfig".into());
        let c = g.command(None, &[os("status")]);
        let std = c.as_std();
        let args: Vec<_> = std
            .get_args()
            .map(|a| a.to_string_lossy().into_owned())
            .collect();
        assert_eq!(&args[..10], ISOLATE.map(str::to_string).as_slice());
        assert_eq!(args.last().map(String::as_str), Some("status"));
        let envs: Vec<(String, Option<String>)> = std
            .get_envs()
            .map(|(k, v)| {
                (
                    k.to_string_lossy().into_owned(),
                    v.map(|v| v.to_string_lossy().into_owned()),
                )
            })
            .collect();
        for (k, v) in [
            ("GIT_CONFIG_NOSYSTEM", "1"),
            ("GIT_CONFIG_GLOBAL", "/tmp/empty-gitconfig"),
            ("GIT_TERMINAL_PROMPT", "0"),
            ("LC_ALL", "C"),
        ] {
            assert!(envs.contains(&(k.to_string(), Some(v.to_string()))), "{k}");
        }
    }

    #[test]
    fn glob_like_pure_posix_path_match() {
        assert!(path_match("docs/specs/02-PRD/x.md", "docs/specs/*/*.md"));
        assert!(path_match("docs/specs/02-PRD/한글.md", "docs/specs/*/*.md"));
        assert!(!path_match(
            "docs/specs/02-PRD/sub/x.md",
            "docs/specs/*/*.md"
        ));
        assert!(!path_match("docs/specs/README.md", "docs/specs/*/*.md"));
        assert!(path_match("docs/specs/a/.md", "docs/specs/*/*.md"));
        assert!(!path_match("docs/specs/a/x.mdx", "docs/specs/*/*.md"));
    }

    fn sh(cwd: &Path, args: &[&str]) -> String {
        let out = std::process::Command::new("git")
            .args([
                "-c",
                "user.name=o",
                "-c",
                "user.email=o@x",
                "-c",
                "gc.auto=0",
            ])
            .args(args)
            .current_dir(cwd)
            .output()
            .expect("git");
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        String::from_utf8_lossy(&out.stdout).trim().to_string()
    }

    fn user() -> UserRow {
        UserRow {
            id: 1,
            github_login: "local".into(),
            github_user_id: None,
            display_name: "로컬".into(),
            github_token_encrypted: None,
            created_at: time::OffsetDateTime::now_utc(),
            kind: "local".into(),
        }
    }

    /// 서버 저장소에 a·b를 두고, 우리가 부모를 읽은 뒤 밖에서 `outside`를 민 상태를 만든다
    async fn raced(tmp: &Path, outside: &str) -> (Git, PathBuf, PathBuf, String) {
        let g = Git::new("git".into(), tmp.join("gitconfig"));
        std::fs::write(tmp.join("gitconfig"), "").expect("설정");
        let (origin, work) = (tmp.join("o.git"), tmp.join("w"));
        g.init_bare(&origin).await.expect("init");
        std::fs::create_dir_all(&work).expect("폴더");
        let two = IndexMap::from([
            ("a.md".to_string(), "1\n".to_string()),
            ("b.md".to_string(), "1\n".to_string()),
        ]);
        let base = g
            .commit(&origin, &work, "base", &user(), &two, &[])
            .await
            .expect("base")
            .hash;
        let other = tmp.join("other");
        sh(
            tmp,
            &[
                "clone",
                "-q",
                origin.to_str().expect("경로"),
                other.to_str().expect("경로"),
            ],
        );
        std::fs::write(other.join(outside), "theirs\n").expect("쓰기");
        sh(&other, &["commit", "-qam", "race"]);
        sh(&other, &["push", "-q", "origin", "HEAD:main"]);
        (g, origin, work, base)
    }

    #[tokio::test]
    async fn commit_from_stale_parent_lands_on_top_when_other_file_changed() {
        let tmp = tempfile::tempdir().expect("임시");
        let (g, origin, work, base) = raced(tmp.path(), "b.md").await;
        let theirs = sh(&origin, &["rev-parse", "main"]);
        let mine = IndexMap::from([("a.md".to_string(), "mine\n".to_string())]);
        let u = user();
        let change = Change {
            message: "mine",
            user: &u,
            files: &mine,
            delete: &[],
        };
        let made = g
            .commit_from(&origin, &work, Some(base), &change)
            .await
            .expect("그 위에");
        assert_eq!(made.parent.as_deref(), Some(theirs.as_str()));
        assert_eq!(sh(&origin, &["rev-parse", "main"]), made.hash);
        assert_eq!(
            sh(&origin, &["log", "--format=%s", "-3", "main"]),
            "mine\nrace\nbase"
        );
        assert_eq!(sh(&origin, &["show", "main:b.md"]), "theirs");
    }

    #[tokio::test]
    async fn commit_from_stale_parent_conflicts_on_the_same_file() {
        let tmp = tempfile::tempdir().expect("임시");
        let (g, origin, work, base) = raced(tmp.path(), "a.md").await;
        let theirs = sh(&origin, &["rev-parse", "main"]);
        let mine = IndexMap::from([("a.md".to_string(), "mine\n".to_string())]);
        let u = user();
        let change = Change {
            message: "mine",
            user: &u,
            files: &mine,
            delete: &[],
        };
        let r = g.commit_from(&origin, &work, Some(base), &change).await;
        assert!(matches!(r, Err(Problem::PushFailed { reason }) if reason == "conflict"));
        assert_eq!(sh(&origin, &["rev-parse", "main"]), theirs);
    }

    #[test]
    fn stripspace_like_git_commit_m() {
        assert_eq!(stripspace("제목"), "제목\n");
        assert_eq!(
            stripspace("\n\n제목  \t\r\n\n\n\n본문 \n\n"),
            "제목\n\n본문\n"
        );
        assert_eq!(stripspace("a\r\nb"), "a\nb\n");
        assert_eq!(stripspace("  \n\t\n"), "");
        assert_eq!(stripspace("\u{b}a"), "\u{b}a\n"); // git의 공백에 \v·\f는 없다
    }

    #[test]
    fn ident_without_crud_and_fast_import_paths() {
        assert_eq!(without_crud(" <로컬>, "), "로컬");
        assert_eq!(without_crud("a<b>c"), "abc");
        assert_eq!(
            fi_path("docs/specs/한글 이름.md"),
            "docs/specs/한글 이름.md"
        );
        assert_eq!(fi_path("a\"b"), "\"a\\\"b\"");
        assert_eq!(fi_path("a\nb"), "\"a\\nb\"");
        assert_eq!(normal_path("./a//b/../c"), "a/c");
        let tree = [
            b"100644 a.md\0".as_slice(),
            &[1u8; 20],
            b"100755 run.sh\0",
            &[2u8; 20],
        ]
        .concat();
        assert_eq!(tree_mode(&tree, "run.sh", 20).as_deref(), Some("100755"));
        assert_eq!(tree_mode(&tree, "a.md", 20).as_deref(), Some("100644"));
        assert_eq!(tree_mode(&tree, "b", 20), None);
    }
}
