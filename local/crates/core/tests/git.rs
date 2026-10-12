//! SYNC-MS-019 테스트 관점 — 임시 자리의 진짜 git

use std::path::{Path, PathBuf};
use std::process::Command;

use indexmap::IndexMap;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::git::Git;
use time::OffsetDateTime;

fn git_for(tmp: &Path) -> Git {
    let global = tmp.join("gitconfig");
    std::fs::write(&global, "[gc]\n\tauto = 0\n[maintenance]\n\tauto = false\n").expect("설정");
    Git::new("git".into(), global)
}

fn local_user() -> UserRow {
    UserRow {
        id: 1,
        github_login: "local".into(),
        github_user_id: None,
        display_name: "로컬".into(),
        github_token_encrypted: None,
        created_at: OffsetDateTime::now_utc(),
        kind: "local".into(),
    }
}

/// 시험이 직접 부르는 git — 작성자를 붙인다. 자동 gc는 끈다(뒤에서 돌며 `gc.pid`를 쥐면 시험의 gc가 건너뛴다)
fn sh(cwd: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(["-c", "user.name=seed", "-c", "user.email=seed@example.com"])
        .args(["-c", "gc.auto=0", "-c", "maintenance.auto=false"])
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("git");
    assert!(
        out.status.success(),
        "{args:?}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

fn files(pairs: &[(&str, &str)]) -> IndexMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
}

/// 서버 저장소 + 작업 사본 폴더(git이 아니다 — 카드 L19)
async fn setup(tmp: &Path) -> (Git, PathBuf, PathBuf) {
    let g = git_for(tmp);
    let origin = tmp.join("origins/X.git");
    let work = tmp.join("repos/X");
    g.init_bare(&origin).await.expect("init_bare");
    std::fs::create_dir_all(&work).expect("폴더");
    (g, origin, work)
}

/// 서버 저장소를 받은 다른 사본 — 밖에서 미는 사람
fn outside(tmp: &Path, origin: &Path) -> PathBuf {
    let other = tmp.join("other");
    if !other.exists() {
        sh(
            tmp,
            &[
                "clone",
                "-q",
                origin.to_str().expect("경로"),
                other.to_str().expect("경로"),
            ],
        );
    } else {
        sh(&other, &["pull", "-q", "origin", "main"]);
    }
    other
}

#[tokio::test]
async fn init_bare_main_and_receive_rules() {
    let tmp = tempfile::tempdir().expect("임시");
    let (_, origin, _) = setup(tmp.path()).await;
    assert_eq!(sh(&origin, &["symbolic-ref", "HEAD"]), "refs/heads/main");
    for key in [
        "receive.denyNonFastForwards",
        "receive.denyDeletes",
        "receive.fsckObjects",
    ] {
        assert_eq!(sh(&origin, &["config", key]), "true");
    }
}

#[tokio::test]
async fn exists_empty_committed_and_not_a_repo() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    assert!(!g.exists(&origin, "docs/specs").await.expect("빈 저장소"));
    let u = local_user();
    g.commit(
        &origin,
        &work,
        "first",
        &u,
        &files(&[("docs/specs/02-PRD/a.md", "x\n")]),
        &[],
    )
    .await
    .expect("커밋");
    assert!(g.exists(&origin, "docs/specs").await.expect("있다"));
    // 폴더에만 있는 것은 커밋된 것이 아니다
    std::fs::create_dir_all(work.join("docs/specs/04-UC")).expect("폴더");
    std::fs::write(work.join("docs/specs/04-UC/x.md"), "uncommitted").expect("파일");
    assert!(!g.exists(&origin, "docs/specs/04-UC").await.expect("폴더만"));
    std::fs::create_dir_all(tmp.path().join("plain")).expect("폴더");
    assert!(matches!(
        g.exists(&tmp.path().join("plain"), "docs").await,
        Err(Problem::Git { .. })
    ));
}

#[tokio::test]
async fn commit_first_commit_identity_folder_and_noop() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let mut fs = Git::init_specs("http://127.0.0.1:8010/specs");
    fs.insert("src/main.rs".into(), "fn main() {}\n".into());
    let made = g
        .commit(&origin, &work, "chore(X): init syncdoc", &u, &fs, &[])
        .await
        .expect("커밋");
    assert_eq!(made.parent, None);
    assert_eq!(sh(&origin, &["rev-parse", "main"]), made.hash);
    assert_eq!(
        sh(&origin, &["log", "-1", "--format=%an <%ae> %s"]),
        "로컬 <local@syncdoc.local> chore(X): init syncdoc"
    );
    let listed = sh(&origin, &["ls-tree", "-r", "--name-only", "main"]);
    assert_eq!(listed.lines().count(), 15);
    // 폴더에는 docs/specs만 — 첨부 파일 읽기만 쓴다
    assert!(work.join("docs/specs/README.md").is_file());
    assert!(work.join("docs/specs/assets/.gitkeep").is_file());
    assert!(!work.join("src").exists());
    assert!(!work.join(".git").exists());
    // 같은 내용 → 커밋 없음, 빈 메시지라도
    let again = g
        .commit(
            &origin,
            &work,
            " \n",
            &u,
            &files(&[(
                "docs/specs/README.md",
                &std::fs::read_to_string(work.join("docs/specs/README.md")).expect("README"),
            )]),
            &[],
        )
        .await
        .expect("noop");
    assert_eq!(again.hash, made.hash);
    assert_eq!(again.parent.as_deref(), Some(made.hash.as_str()));
    // 바뀐 것이 있는데 빈 메시지 → git commit처럼 실패, main 그대로
    let r = g
        .commit(&origin, &work, "  \n\t", &u, &files(&[("a.md", "x")]), &[])
        .await;
    assert!(matches!(r, Err(Problem::Git { .. })), "{r:?}");
    assert_eq!(sh(&origin, &["rev-parse", "main"]), made.hash);
    // 지우기 — 폴더에서도
    let gone = g
        .commit(
            &origin,
            &work,
            "지움",
            &u,
            &IndexMap::new(),
            &["docs/specs/README.md".to_string()],
        )
        .await
        .expect("지우기");
    assert_eq!(gone.parent.as_deref(), Some(made.hash.as_str()));
    assert!(!work.join("docs/specs/README.md").exists());
    assert!(!sh(&origin, &["ls-tree", "-r", "--name-only", "main"]).contains("README"));
}

/// 우리 커밋을 `git commit`으로 다시 만든다 — 같은 부모·파일·본인·시각이면 해시가 같아야 한다
fn recommit(
    tmp: &Path,
    origin: &Path,
    ours: &str,
    files: &[(&str, &str)],
    message: &str,
) -> String {
    let clone = tmp.join(format!("re-{}", &ours[..8]));
    sh(
        tmp,
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            clone.to_str().expect("경로"),
        ],
    );
    sh(&clone, &["checkout", "-q", &format!("{ours}^")]);
    for (p, body) in files {
        let f = clone.join(p);
        std::fs::create_dir_all(f.parent().expect("부모")).expect("폴더");
        std::fs::write(&f, body).expect("파일");
        sh(&clone, &["add", "--", p]);
    }
    let raw = sh(origin, &["cat-file", "-p", ours]);
    let ident = |who: &str| {
        let line = raw
            .lines()
            .find(|l| l.starts_with(who))
            .expect("본인 줄")
            .to_string();
        let gt = line.rfind('>').expect(">");
        (
            line[who.len() + 1..=gt].to_string(),
            line[gt + 2..].to_string(),
        )
    };
    let (author, date) = ident("author");
    let (name, email) = author.split_once(" <").expect("이름");
    let out = Command::new("git")
        .args([
            "-c",
            &format!("user.name={name}"),
            "-c",
            &format!("user.email={}", email.trim_end_matches('>')),
            "-c",
            "core.autocrlf=false",
            "commit",
            "-q",
            "-m",
            message,
        ])
        .env("GIT_AUTHOR_DATE", &date)
        .env("GIT_COMMITTER_DATE", &date)
        .current_dir(&clone)
        .output()
        .expect("git commit");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    sh(&clone, &["rev-parse", "HEAD"])
}

#[tokio::test]
async fn commit_bytes_match_git_commit() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let mut u = local_user();
    let base = g
        .commit(&origin, &work, "base", &u, &files(&[("a.md", "0\n")]), &[])
        .await
        .expect("base");
    assert!(base.parent.is_none());
    let messages = [
        "spec(X-PRD-001): 초안",
        "제목\n\n본문  \n\n\n둘째 문단\t\n",
        "\n\n  앞뒤 빈 줄\r\n\r\n끝  ",
        "끝 줄바꿈 없음",
        "여러\n줄\n\n\n\n모음\n\n",
    ];
    for (i, m) in messages.iter().enumerate() {
        if i == 3 {
            u.display_name = " <로컬>, ".into(); // git처럼 군더더기를 걷는다
        }
        let body = format!("가\r\n나 {i}\n");
        let fs = [
            ("a.md", body.as_str()),
            ("docs/specs/02-PRD/새 문서.md", "새\n"),
        ];
        let made = g
            .commit(&origin, &work, m, &u, &files(&fs), &[])
            .await
            .expect("커밋");
        assert_eq!(
            recommit(tmp.path(), &origin, &made.hash, &fs, m),
            made.hash,
            "{m:?}"
        );
    }
    // 현지 오프셋 — git이 지금 쓰는 것과 같다
    let ours = sh(
        &origin,
        &["log", "-1", "--format=%ad", "--date=raw", "main"],
    );
    let theirs = sh(tmp.path(), &["var", "GIT_COMMITTER_IDENT"]);
    assert_eq!(ours.rsplit(' ').next(), theirs.rsplit(' ').next());
}

#[cfg(unix)]
#[tokio::test]
async fn commit_keeps_executable_mode() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    g.commit(
        &origin,
        &work,
        "base",
        &u,
        &files(&[("run.sh", "echo 1\n")]),
        &[],
    )
    .await
    .expect("base");
    let other = outside(tmp.path(), &origin);
    sh(&other, &["update-index", "--chmod=+x", "run.sh"]);
    sh(&other, &["commit", "-qm", "x"]);
    sh(&other, &["push", "-q", "origin", "HEAD:main"]);
    g.commit(
        &origin,
        &work,
        "고침",
        &u,
        &files(&[("run.sh", "echo 2\n"), ("new.sh", "n\n")]),
        &[],
    )
    .await
    .expect("고침");
    let tree = sh(&origin, &["ls-tree", "main"]);
    assert!(
        tree.lines()
            .any(|l| l.starts_with("100755") && l.ends_with("run.sh")),
        "{tree}"
    );
    assert!(
        tree.lines()
            .any(|l| l.starts_with("100644") && l.ends_with("new.sh")),
        "{tree}"
    );
}

#[tokio::test]
async fn list_read_and_reader_sees_later_commits() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let mut fs = Git::init_specs("http://x/specs");
    fs.insert("docs/specs/02-PRD/한글-문서.md".into(), "가\r\n나\n".into());
    fs.insert("docs/specs/02-PRD/sub/deep.md".into(), "x".into());
    fs.insert("docs/specs/_templates/PRD.md".into(), "x".into());
    fs.insert("docs/specs/assets/a.md".into(), "x".into());
    g.commit(&origin, &work, "m", &u, &fs, &[])
        .await
        .expect("커밋");
    let got = g
        .list(&origin, "docs/specs/*/*.md", "HEAD")
        .await
        .expect("list");
    assert_eq!(got, ["docs/specs/02-PRD/한글-문서.md"]);
    assert_eq!(
        g.read(&origin, "docs/specs/02-PRD/한글-문서.md", "HEAD")
            .await
            .expect("read"),
        "가\r\n나\n"
    );
    let missing = g.read(&origin, "docs/specs/none.md", "HEAD").await;
    assert!(
        matches!(&missing, Err(Problem::Git { cmd, stderr }) if cmd == "git show HEAD:docs/specs/none.md" && stderr.contains("does not exist")),
        "{missing:?}"
    );
    // 읽기 프로세스를 띄운 뒤 밖에서 민 커밋 — main도 내용도 본다
    let other = outside(tmp.path(), &origin);
    std::fs::write(other.join("later.md"), "나중\n").expect("파일");
    sh(&other, &["add", "later.md"]);
    sh(&other, &["commit", "-qm", "나중"]);
    sh(&other, &["push", "-q", "origin", "HEAD:main"]);
    let later = sh(&other, &["rev-parse", "HEAD"]);
    assert_eq!(
        g.head(&origin).await.expect("head").as_deref(),
        Some(later.as_str())
    );
    assert_eq!(
        g.read(&origin, "later.md", "refs/heads/main")
            .await
            .expect("읽기"),
        "나중\n"
    );
    // 끈 뒤에도 다시 띄워 읽는다
    g.close(&origin).await;
    assert_eq!(
        g.read(&origin, "later.md", &later).await.expect("다시"),
        "나중\n"
    );
    // 저장소 자리가 없으면 Internal
    assert!(matches!(
        g.read(&tmp.path().join("none.git"), "a", "HEAD").await,
        Err(Problem::Internal { .. })
    ));
}

#[tokio::test]
async fn path_guard_rejects_before_writing() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    for bad in [
        ".git/hooks/pre-commit",
        "../escape.md",
        "a/../../escape.md",
        "",
    ] {
        let r = g
            .commit(&origin, &work, "m", &u, &files(&[(bad, "x")]), &[])
            .await;
        assert!(matches!(r, Err(Problem::PushFailed { .. })), "{bad}");
    }
    assert!(!tmp.path().join("repos/escape.md").exists());
    assert_eq!(g.head(&origin).await.expect("head"), None);
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(tmp.path(), work.join("out")).expect("링크");
        let r = g
            .commit(&origin, &work, "m", &u, &files(&[("out/x.md", "x")]), &[])
            .await;
        assert!(
            matches!(r, Err(Problem::PushFailed { reason }) if reason.starts_with("작업 사본 밖 경로"))
        );
    }
}

#[tokio::test]
async fn head_and_rev_list_count_on_the_server_repo() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    assert_eq!(g.head(&origin).await.expect("빈"), None);
    let first = g
        .commit(
            &origin,
            &work,
            "첫",
            &local_user(),
            &files(&[("a.md", "a")]),
            &[],
        )
        .await
        .expect("첫 커밋")
        .hash;
    assert_eq!(
        g.head(&origin).await.expect("head").as_deref(),
        Some(first.as_str())
    );
    let other = outside(tmp.path(), &origin);
    std::fs::write(other.join("b.md"), "b").expect("파일");
    sh(&other, &["add", "b.md"]);
    sh(&other, &["commit", "-q", "-m", "밖"]);
    sh(&other, &["push", "-q", "origin", "HEAD:main"]);
    let outside_head = sh(&other, &["rev-parse", "HEAD"]);
    assert_eq!(
        g.head(&origin).await.expect("head").as_deref(),
        Some(outside_head.as_str())
    );
    let range = format!("{first}..{outside_head}");
    assert_eq!(g.rev_list_count(&origin, &range).await.expect("수"), 1);
    assert_eq!(
        g.rev_list_count(&origin, &format!("{first}..{first}"))
            .await
            .expect("수"),
        0
    );
    assert!(matches!(
        g.rev_list_count(&origin, "0123456789abcdef0123456789abcdef01234567..HEAD")
            .await,
        Err(Problem::Git { .. })
    ));
}

/// pkt-line 머리 넷을 건너 한 줄씩 — 광고를 읽는다
fn pkt_lines(mut b: &[u8]) -> Vec<String> {
    let mut out = Vec::new();
    while b.len() >= 4 {
        let n =
            usize::from_str_radix(std::str::from_utf8(&b[..4]).expect("길이"), 16).expect("길이");
        if n < 4 {
            out.push(format!("{n:04x}"));
            b = &b[4..];
            continue;
        }
        out.push(String::from_utf8_lossy(&b[4..n]).into_owned());
        b = &b[n..];
    }
    out
}

#[tokio::test]
async fn advertise_refs_service_line_unless_v2() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    // 빈 저장소 — 서비스 줄 + flush, 참조 없음(capabilities^{})
    let empty = g
        .advertise_refs(&origin, "git-upload-pack", None)
        .await
        .expect("광고");
    let lines = pkt_lines(&empty);
    assert_eq!(lines[..2], ["# service=git-upload-pack\n", "0000"]);
    assert!(lines[2].starts_with("0000000000000000000000000000000000000000 capabilities^{}"));
    g.commit(
        &origin,
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("커밋");
    let head = sh(&origin, &["rev-parse", "main"]);
    for service in ["git-upload-pack", "git-receive-pack"] {
        let out = g
            .advertise_refs(&origin, service, None)
            .await
            .expect("광고");
        let lines = pkt_lines(&out);
        assert_eq!(lines[0], format!("# service={service}\n"));
        assert!(
            lines
                .iter()
                .any(|l| l.starts_with(&format!("{head} refs/heads/main"))),
            "{lines:?}"
        );
    }
    // v2 — 서비스 줄 없이 `version 2`
    for proto in ["version=2", "version=1:version=2", "x=y:version=2"] {
        let out = g
            .advertise_refs(&origin, "git-upload-pack", Some(proto))
            .await
            .expect("광고");
        assert!(out.starts_with(b"000eversion 2\n"), "{proto}");
    }
    // v2가 아니다 — git이 세지 않는 값
    for proto in ["version=20", "xversion=2", "version=1", "version=", ""] {
        let out = g
            .advertise_refs(&origin, "git-upload-pack", Some(proto))
            .await
            .expect("광고");
        assert!(
            out.starts_with(b"001e# service=git-upload-pack\n0000"),
            "{proto}"
        );
    }
}

#[tokio::test]
async fn service_rpc_ls_refs_and_flush_only() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    g.commit(
        &origin,
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("커밋");
    // 빈 요청(flush만) — 아무것도 원하지 않는다, 답도 비었다
    let out = g
        .service_rpc(&origin, "git-upload-pack", b"0000".to_vec(), None)
        .await
        .expect("rpc");
    assert!(out.is_empty(), "{out:?}");
    // v2 ls-refs — main이 보인다
    let req = b"0014command=ls-refs\n00010009peel\n0000".to_vec();
    let out = g
        .service_rpc(&origin, "git-upload-pack", req, Some("version=2"))
        .await
        .expect("rpc");
    let head = sh(&origin, &["rev-parse", "main"]);
    assert!(
        pkt_lines(&out).contains(&format!("{head} refs/heads/main\n")),
        "{:?}",
        pkt_lines(&out)
    );
}

/// 다른 사본에서 작성자를 정해 커밋하고 민다
fn push_as(dir: &Path, name: &str, email: &str, message: &str) -> String {
    let out = Command::new("git")
        .args([
            "-c",
            &format!("user.name={name}"),
            "-c",
            &format!("user.email={email}"),
        ])
        .args(["commit", "-q", "-m", message])
        .current_dir(dir)
        .output()
        .expect("git");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    sh(dir, &["push", "-q", "origin", "HEAD:main"]);
    sh(dir, &["rev-parse", "HEAD"])
}

fn put(dir: &Path, path: &str, text: &str) {
    let f = dir.join(path);
    std::fs::create_dir_all(f.parent().expect("부모")).expect("폴더");
    std::fs::write(f, text).expect("파일");
    sh(dir, &["add", path]);
}

#[tokio::test]
async fn changed_files_latest_per_path_renames_and_skips() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let base = g
        .commit(
            &origin,
            &work,
            "first",
            &u,
            &files(&[("a.txt", "a\n")]),
            &[],
        )
        .await
        .expect("커밋")
        .hash;
    let other = outside(tmp.path(), &origin);
    put(&other, "docs/specs/02-PRD/X-PRD-001.md", "v1\n");
    put(&other, "docs/specs/README.md", "r\n");
    put(&other, "docs/specs/assets/a.png", "p");
    put(&other, "docs/specs/_templates/t.md", "t\n");
    push_as(&other, "홍 길동", "hong@example.com", "spec: 첫");
    put(&other, "docs/specs/02-PRD/X-PRD-001.md", "v2\n");
    put(&other, "docs/specs/03-SCN/X-SCN-001.md", "s\n");
    let c2 = push_as(
        &other,
        "Octo Cat",
        "123+octo@users.noreply.github.com",
        "spec: 둘\n\n  본문 줄  \n",
    );
    sh(
        &other,
        &[
            "mv",
            "docs/specs/03-SCN/X-SCN-001.md",
            "docs/specs/03-SCN/X-SCN-002.md",
        ],
    );
    let c3 = push_as(&other, "a", "a@x", "옮김");
    sh(&other, &["rm", "-q", "docs/specs/02-PRD/X-PRD-001.md"]);
    let c4 = push_as(&other, "b", "b@x", "지움");
    let head = g.head(&origin).await.expect("head").expect("main");
    assert_eq!(head, c4);
    let got = g
        .changed_files(&origin, &format!("{base}..{head}"), "docs/specs/")
        .await
        .expect("바뀐 파일");
    let brief: Vec<(&str, &str, &str)> = got
        .iter()
        .map(|f| (f.path.as_str(), f.status.as_str(), f.commit_hash.as_str()))
        .collect();
    assert_eq!(
        brief,
        [
            ("docs/specs/02-PRD/X-PRD-001.md", "D", c4.as_str()),
            ("docs/specs/03-SCN/X-SCN-002.md", "M", c3.as_str()),
        ]
    );
    // 범위를 c2까지로 — 여러 줄 메시지·noreply 아이디
    let got = g
        .changed_files(&origin, &format!("{base}..{c2}"), "docs/specs/")
        .await
        .expect("바뀐 파일");
    let scn = got
        .iter()
        .find(|f| f.path.ends_with("X-SCN-001.md"))
        .expect("SCN");
    assert_eq!(scn.message, "spec: 둘\n\n본문 줄");
    assert_eq!(
        (scn.author_login.as_str(), scn.author_email.as_str()),
        ("octo", "123+octo@users.noreply.github.com")
    );
    let prd = got
        .iter()
        .find(|f| f.path.ends_with("X-PRD-001.md"))
        .expect("PRD");
    assert_eq!(
        (prd.status.as_str(), prd.commit_hash.as_str()),
        ("M", c2.as_str())
    );
    assert_eq!(got.len(), 2);
}

#[tokio::test]
async fn log_oldest_first_follows_renames_and_skips_deletions() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    g.commit(
        &origin,
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("커밋");
    let other = outside(tmp.path(), &origin);
    let (old, new) = (
        "docs/specs/DOM/X-DOM-001.md",
        "docs/specs/06-DOM/X-DOM-001.md",
    );
    put(&other, old, "v1\n");
    push_as(&other, "a", "a@x", "spec: 초안\n\n둘째 줄\n\n셋째");
    put(&other, old, "v2\n");
    push_as(&other, "a", "9+octo@users.noreply.github.com", "spec: 수정");
    std::fs::create_dir_all(other.join("docs/specs/06-DOM")).expect("폴더");
    sh(&other, &["mv", old, new]);
    push_as(&other, "a", "a@x", "옮김");
    sh(&other, &["rm", "-q", new]);
    push_as(&other, "a", "a@x", "trash(X-DOM-001)");
    put(&other, new, "v3\n");
    push_as(&other, "a", "a@x", "다시");
    let got = g.log(&origin, new).await.expect("이력");
    let brief: Vec<(&str, &str)> = got
        .iter()
        .map(|c| (c.message.as_str(), c.path.as_str()))
        .collect();
    assert_eq!(
        brief,
        [
            ("spec: 초안\n\n둘째 줄\n\n셋째", old),
            ("spec: 수정", old),
            ("옮김", new),
            ("다시", new),
        ]
    );
    assert_eq!(got[1].login, "octo");
    for c in &got {
        g.read(&origin, &c.path, &c.hash).await.expect("읽힌다");
    }
    assert!(
        g.log(&origin, "docs/specs/02-PRD/없음.md")
            .await
            .expect("빈")
            .is_empty()
    );
}

#[tokio::test]
async fn materialize_writes_only_docs_specs_and_replaces_old_clone() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let code_only = g
        .commit(
            &origin,
            &work,
            "코드",
            &u,
            &files(&[("src/a.rs", "a\n")]),
            &[],
        )
        .await
        .expect("커밋")
        .hash;
    // docs/specs가 없는 커밋 → 빈 폴더
    g.materialize(&origin, &code_only, &work).await.expect("빈");
    assert_eq!(std::fs::read_dir(&work).expect("폴더").count(), 0);
    let head = g
        .commit(
            &origin,
            &work,
            "명세",
            &u,
            &files(&[
                ("docs/specs/02-PRD/X.md", "p\n"),
                ("docs/specs/assets/x.png", "png"),
            ]),
            &[],
        )
        .await
        .expect("커밋")
        .hash;
    // 옛 판의 clone(.git이 있는 폴더) → .git 없이 다시
    std::fs::create_dir_all(work.join(".git")).expect(".git");
    std::fs::write(work.join("stale.md"), "옛").expect("파일");
    g.materialize(&origin, &head, &work).await.expect("다시");
    assert!(!work.join(".git").exists());
    assert!(!work.join("stale.md").exists());
    assert!(!work.join("src").exists());
    assert_eq!(
        std::fs::read_to_string(work.join("docs/specs/02-PRD/X.md")).expect("p"),
        "p\n"
    );
    assert_eq!(
        std::fs::read(work.join("docs/specs/assets/x.png")).expect("png"),
        b"png"
    );
}

#[tokio::test]
async fn close_lets_the_repo_move_and_reads_reopen() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    g.commit(
        &origin,
        &work,
        "a",
        &local_user(),
        &files(&[("a.md", "a")]),
        &[],
    )
    .await
    .expect("커밋");
    let copy = g.clone();
    assert_eq!(copy.read(&origin, "a.md", "HEAD").await.expect("읽기"), "a");
    // 복제본이 띄운 것도 원본의 close_all이 끈다 — 끈 뒤 폴더를 옮길 수 있다(윈도는 열린 팩이 있으면 못 한다)
    g.close_all().await;
    let moved = tmp.path().join("origins/_archive/X-1.git");
    std::fs::create_dir_all(moved.parent().expect("부모")).expect("폴더");
    std::fs::rename(&origin, &moved).expect("옮기기");
    assert_eq!(g.read(&moved, "a.md", "HEAD").await.expect("다시"), "a");
    g.close(&moved).await;
}

#[tokio::test]
async fn gc_packs_loose_objects_over_the_threshold() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    // 작은 커밋마다 fast-import는 낱낱의 객체로 쓴다(fastimport.unpackLimit) — 문턱(6700)을 넉넉히 넘게 쌓는다.
    // gc --auto는 objects/17 하나로 어림한다(256배)
    let tree = tmp.path().join("tree");
    for i in 0..12000 {
        let d = tree.join(format!("d{}", i % 70));
        std::fs::create_dir_all(&d).expect("폴더");
        std::fs::write(d.join(format!("{i}.md")), format!("{i}\n")).expect("파일");
    }
    let (gd, wt) = (
        format!("--git-dir={}", origin.display()),
        format!("--work-tree={}", tree.display()),
    );
    sh(tmp.path(), &[&gd, &wt, "add", "-A"]);
    sh(tmp.path(), &[&gd, &wt, "commit", "-q", "-m", "많이"]);
    let loose = || {
        std::fs::read_dir(origin.join("objects"))
            .expect("객체")
            .flatten()
            .filter(|e| e.file_name().len() == 2)
            .map(|e| std::fs::read_dir(e.path()).map_or(0, Iterator::count))
            .sum::<usize>()
    };
    let before = loose();
    assert!(before > 11000, "{before}");
    let head = sh(&origin, &["rev-parse", "main"]);
    assert_eq!(
        g.read(&origin, "d0/0.md", "HEAD").await.expect("읽기"),
        "0\n"
    );
    g.gc(&origin).await.expect("gc"); // 읽기 프로세스를 끄고 돈다
    assert!(loose() < 100, "{before} → {}", loose());
    assert_eq!(sh(&origin, &["rev-parse", "main"]), head);
    assert_eq!(
        g.read(&origin, "d69/11969.md", "HEAD").await.expect("읽기"),
        "11969\n"
    );
    // 쌓인 것이 없으면 아무것도 안 한다
    let packs = std::fs::read_dir(origin.join("objects/pack"))
        .expect("팩")
        .count();
    g.gc(&origin).await.expect("다시");
    assert_eq!(
        std::fs::read_dir(origin.join("objects/pack"))
            .expect("팩")
            .count(),
        packs
    );
    let _ = work;
}

#[tokio::test]
async fn sync_readme_only_when_different() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let url = "http://127.0.0.1:8010/specs";
    g.commit(&origin, &work, "init", &u, &Git::init_specs(url), &[])
        .await
        .expect("커밋");
    assert_eq!(
        g.sync_readme(&origin, &work, &u, "X", url)
            .await
            .expect("같다"),
        None
    );
    let other = outside(tmp.path(), &origin);
    put(&other, "docs/specs/README.md", "옛 README\n");
    push_as(&other, "a", "a@x", "README 고침");
    let hash = g
        .sync_readme(&origin, &work, &u, "X", url)
        .await
        .expect("다르다")
        .expect("커밋");
    assert_eq!(
        sh(&origin, &["log", "-1", "--format=%s"]),
        "chore(X): README를 싱크독 규약 링크로"
    );
    assert_eq!(sh(&origin, &["rev-parse", "main"]), hash);
    assert!(
        std::fs::read_to_string(work.join("docs/specs/README.md"))
            .expect("폴더")
            .contains(url)
    );
    assert_eq!(
        g.sync_readme(&origin, &work, &u, "X", url)
            .await
            .expect("이제 같다"),
        None
    );
    // README가 없는 저장소 — 만든다
    sh(&other, &["pull", "-q", "origin", "main"]);
    sh(&other, &["rm", "-q", "docs/specs/README.md"]);
    push_as(&other, "a", "a@x", "README 지움");
    assert!(
        g.sync_readme(&origin, &work, &u, "X", url)
            .await
            .expect("없다")
            .is_some()
    );
}

/// L15 clone_bare — 번들의 가지·태그가 해시 그대로, 원격 없음·HEAD main·받기 규칙. 번들이 아니면 `Problem::Git`
#[tokio::test]
async fn clone_bare_from_bundle_keeps_hashes_without_remote() {
    let tmp = tempfile::tempdir().expect("임시");
    let g = git_for(tmp.path());
    let src = tmp.path().join("src");
    sh(
        tmp.path(),
        &["init", "-q", "-b", "main", src.to_str().expect("경로")],
    );
    std::fs::write(src.join("a.md"), "하나\n").expect("파일");
    sh(&src, &["add", "-A"]);
    sh(&src, &["commit", "-q", "-m", "하나"]);
    sh(&src, &["tag", "v1"]);
    sh(&src, &["branch", "side"]);
    let bundle = tmp.path().join("x.bundle");
    sh(
        &src,
        &[
            "bundle",
            "create",
            "-q",
            bundle.to_str().expect("경로"),
            "--all",
        ],
    );
    let origin = tmp.path().join("origins/B.git");
    g.clone_bare(bundle.to_str().expect("경로"), &origin)
        .await
        .expect("복제");
    for r in ["main", "v1", "side"] {
        assert_eq!(sh(&origin, &["rev-parse", r]), sh(&src, &["rev-parse", r]));
    }
    assert_eq!(sh(&origin, &["remote"]), "");
    assert_eq!(sh(&origin, &["symbolic-ref", "HEAD"]), "refs/heads/main");
    for key in [
        "receive.denyNonFastForwards",
        "receive.denyDeletes",
        "receive.fsckObjects",
    ] {
        assert_eq!(sh(&origin, &["config", key]), "true");
    }
    let junk = tmp.path().join("junk.bundle");
    std::fs::write(&junk, b"not a bundle").expect("쓰레기");
    assert!(matches!(
        g.clone_bare(
            junk.to_str().expect("경로"),
            &tmp.path().join("origins/J.git")
        )
        .await,
        Err(Problem::Git { .. })
    ));
}

/// L16 mirror — 백업 사진: 가지·태그 해시·HEAD가 원본과 같고 원격이 없다. 빈 저장소도
#[tokio::test]
async fn mirror_copies_refs_without_remote() {
    let tmp = tempfile::tempdir().expect("임시");
    let g = git_for(tmp.path());
    let origin = tmp.path().join("origins/M.git");
    g.init_bare(&origin).await.expect("원본");
    let work = tmp.path().join("w");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().unwrap(),
            work.to_str().unwrap(),
        ],
    );
    std::fs::write(work.join("a.md"), "하나\n").unwrap();
    sh(&work, &["add", "-A"]);
    sh(&work, &["commit", "-q", "-m", "하나"]);
    sh(&work, &["tag", "v1"]);
    sh(
        &work,
        &[
            "push",
            "-q",
            "origin",
            "HEAD:main",
            "v1",
            "HEAD:refs/heads/side",
        ],
    );
    let dest = tmp.path().join("snap/origins/M.git");
    g.mirror(&origin, &dest).await.expect("거울");
    for r in ["main", "v1", "side"] {
        assert_eq!(sh(&dest, &["rev-parse", r]), sh(&origin, &["rev-parse", r]));
    }
    assert_eq!(sh(&dest, &["remote"]), "");
    assert_eq!(sh(&dest, &["symbolic-ref", "HEAD"]), "refs/heads/main");
    assert_eq!(sh(&dest, &["config", "receive.denyDeletes"]), "true");
    let empty = tmp.path().join("origins/E.git");
    g.init_bare(&empty).await.expect("빈 원본");
    let edest = tmp.path().join("snap/origins/E.git");
    g.mirror(&empty, &edest).await.expect("빈 거울");
    assert_eq!(sh(&edest, &["symbolic-ref", "HEAD"]), "refs/heads/main");
}
