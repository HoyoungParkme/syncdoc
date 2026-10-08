//! git 어댑터 — git CLI를 자식 프로세스로 (SYNC-MS-019 · SYNC-DOM-004 4.8, 카드 L6).
//! 파이썬 판 `backend/app/infra/git.py`와 같은 명령·같은 옵션. 사용자 git 설정은 막는다(MS-019 0장) —
//! 파이썬 판은 Docker 안이라 시스템·전역 설정이 없다. 같은 깨끗한 환경을 만들어 같은 결과를 낸다.

use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;

use indexmap::IndexMap;
use tokio::process::Command;

use crate::account::model::UserRow;
use crate::errors::Problem;
use crate::pycompat::chars::{py_splitlines, strip};
use crate::types::{UserKind, stage_of};

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

/// git 실행 파일과 빈 전역 설정 — 켤 때 `runtime.run`이 만든다
#[derive(Clone, Debug)]
pub struct Git {
    pub exe: PathBuf,
    pub global_config: PathBuf,
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

impl Git {
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

/// 파이썬 `OSError`의 `strerror` — Rust 문장 끝의 ` (os error N)`을 뗀다
fn strerror(e: &std::io::Error) -> String {
    let s = e.to_string();
    match s.rfind(" (os error ") {
        Some(i) => s[..i].to_string(),
        None => s,
    }
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

    /// SYNC-MS-019#Git.clone
    pub async fn clone(&self, remote: &str, workdir: &Path) -> Result<(), Problem> {
        self.run(None, &[os("clone"), os(remote), workdir.as_os_str()])
            .await?;
        self.run(
            Some(workdir),
            &[os("remote"), os("set-url"), os("origin"), os(remote)],
        )
        .await?;
        Ok(())
    }

    /// SYNC-MS-019#Git.exists
    pub async fn exists(&self, workdir: &Path, path: &str) -> Result<bool, Problem> {
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
        workdir: &Path,
        glob: &str,
        git_ref: &str,
    ) -> Result<Vec<String>, Problem> {
        let out = self
            .run(
                Some(workdir),
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
    pub async fn read(&self, workdir: &Path, path: &str, git_ref: &str) -> Result<String, Problem> {
        let spec: OsString = format!("{git_ref}:{path}").into();
        self.run(Some(workdir), &[os("show"), &spec]).await
    }
}
