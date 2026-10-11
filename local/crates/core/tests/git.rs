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
    std::fs::write(&global, "").expect("빈 설정");
    Git {
        exe: "git".into(),
        global_config: global,
    }
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

/// 시험이 직접 부르는 git — 작성자를 붙인다
fn sh(cwd: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(["-c", "user.name=seed", "-c", "user.email=seed@example.com"])
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

/// 서버 저장소 + 작업 사본
async fn setup(tmp: &Path) -> (Git, PathBuf, PathBuf) {
    let g = git_for(tmp);
    let origin = tmp.join("origins/X.git");
    let work = tmp.join("repos/X");
    g.init_bare(&origin).await.expect("init_bare");
    g.clone(origin.to_str().expect("경로"), &work)
        .await
        .expect("clone");
    (g, origin, work)
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
    let (g, _, work) = setup(tmp.path()).await;
    assert!(!g.exists(&work, "docs/specs").await.expect("빈 저장소"));
    let u = local_user();
    g.commit_push(
        &work,
        "first",
        &u,
        &files(&[("docs/specs/02-PRD/a.md", "x\n")]),
        &[],
    )
    .await
    .expect("push");
    assert!(g.exists(&work, "docs/specs").await.expect("있다"));
    std::fs::create_dir_all(work.join("docs/specs/04-UC")).expect("폴더");
    std::fs::write(work.join("docs/specs/04-UC/x.md"), "uncommitted").expect("파일");
    assert!(
        !g.exists(&work, "docs/specs/04-UC")
            .await
            .expect("작업 사본만")
    );
    std::fs::create_dir_all(tmp.path().join("plain")).expect("폴더");
    assert!(matches!(
        g.exists(&tmp.path().join("plain"), "docs").await,
        Err(Problem::Git { .. })
    ));
}

#[tokio::test]
async fn commit_push_first_commit_identity_and_noop() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let h = g
        .commit_push(
            &work,
            "chore(X): init syncdoc",
            &u,
            &Git::init_specs("http://127.0.0.1:8010/specs"),
            &[],
        )
        .await
        .expect("push");
    assert_eq!(sh(&origin, &["rev-parse", "main"]), h);
    assert_eq!(
        sh(&origin, &["log", "-1", "--format=%an <%ae> %s"]),
        "로컬 <local@syncdoc.local> chore(X): init syncdoc"
    );
    let listed = sh(&origin, &["ls-tree", "-r", "--name-only", "main"]);
    assert_eq!(listed.lines().count(), 14);
    assert!(!listed.contains("_templates"));
    // 같은 내용 → 커밋 없음
    let again = g
        .commit_push(
            &work,
            "noop",
            &u,
            &files(&[(
                "docs/specs/README.md",
                &std::fs::read_to_string(work.join("docs/specs/README.md")).expect("README"),
            )]),
            &[],
        )
        .await
        .expect("noop");
    assert_eq!(again, h);
}

#[tokio::test]
async fn list_and_read() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, _, work) = setup(tmp.path()).await;
    let u = local_user();
    let mut fs = Git::init_specs("http://x/specs");
    fs.insert("docs/specs/02-PRD/한글-문서.md".into(), "가\r\n나\n".into());
    fs.insert("docs/specs/02-PRD/sub/deep.md".into(), "x".into());
    fs.insert("docs/specs/_templates/PRD.md".into(), "x".into());
    fs.insert("docs/specs/assets/a.md".into(), "x".into());
    g.commit_push(&work, "m", &u, &fs, &[]).await.expect("push");
    let got = g
        .list(&work, "docs/specs/*/*.md", "HEAD")
        .await
        .expect("list");
    assert_eq!(got, ["docs/specs/02-PRD/한글-문서.md"]);
    assert_eq!(
        g.read(&work, "docs/specs/02-PRD/한글-문서.md", "HEAD")
            .await
            .expect("read"),
        "가\r\n나\n"
    );
    assert!(matches!(
        g.read(&work, "docs/specs/none.md", "HEAD").await,
        Err(Problem::Git { .. })
    ));
}

/// push 직전에 다른 사본이 원격을 한 번 앞서게 한다 — 우리 push가 거부되어 rebase 길을 탄다
#[cfg(unix)]
fn race_hook(work: &Path, other: &Path, file: &str, content: &str) {
    use std::os::unix::fs::PermissionsExt;
    let mark = other.join(".raced");
    let hook = work.join(".git/hooks/pre-push");
    let script = format!(
        "#!/bin/sh\nunset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE\nif [ ! -f '{m}' ]; then touch '{m}'; cd '{o}' && printf '{c}' > '{f}' && git -c user.name=o -c user.email=o@x commit -qam race && git push -q origin HEAD:main; fi\n",
        m = mark.display(),
        o = other.display(),
        c = content,
        f = file
    );
    std::fs::write(&hook, script).expect("훅");
    std::fs::set_permissions(&hook, std::fs::Permissions::from_mode(0o755)).expect("권한");
}

#[cfg(unix)]
#[tokio::test]
async fn commit_push_rebases_when_rejected() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    g.commit_push(
        &work,
        "base",
        &u,
        &files(&[("a.md", "1\n"), ("b.md", "1\n")]),
        &[],
    )
    .await
    .expect("base");
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
    race_hook(&work, &other, "b.md", "2\\n");
    let h = g
        .commit_push(&work, "mine", &u, &files(&[("a.md", "2\n")]), &[])
        .await
        .expect("rebase");
    assert_eq!(sh(&origin, &["rev-parse", "main"]), h);
    assert_eq!(
        sh(&origin, &["log", "--format=%s", "-3", "main"]),
        "mine\nrace\nbase"
    );
}

#[cfg(unix)]
#[tokio::test]
async fn commit_push_conflict_restores_workdir() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    g.commit_push(&work, "base", &u, &files(&[("a.md", "1\n")]), &[])
        .await
        .expect("base");
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
    race_hook(&work, &other, "a.md", "theirs\\n");
    let r = g
        .commit_push(&work, "mine", &u, &files(&[("a.md", "mine\n")]), &[])
        .await;
    assert!(matches!(r, Err(Problem::PushFailed { reason }) if reason == "conflict"));
    assert_eq!(
        std::fs::read_to_string(work.join("a.md")).expect("a"),
        "theirs\n"
    );
    assert_eq!(sh(&work, &["status", "--porcelain"]), "");
}

#[tokio::test]
async fn commit_push_writes_on_top_of_remote() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    g.commit_push(
        &work,
        "base",
        &u,
        &files(&[("a.md", "1\n"), ("b.md", "1\n")]),
        &[],
    )
    .await
    .expect("base");
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
    std::fs::write(other.join("b.md"), "2\n").expect("쓰기");
    sh(&other, &["commit", "-qam", "theirs"]);
    sh(&other, &["push", "-q", "origin", "HEAD:main"]);
    // 다른 파일 → fetch 뒤 reset 위에 쓰므로 그대로 성공
    let h = g
        .commit_push(&work, "mine", &u, &files(&[("a.md", "2\n")]), &[])
        .await
        .expect("race");
    assert_eq!(sh(&origin, &["rev-parse", "main"]), h);
    assert_eq!(
        std::fs::read_to_string(work.join("b.md")).expect("b"),
        "2\n"
    );
}

#[tokio::test]
async fn path_guard_rejects_before_writing() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, _, work) = setup(tmp.path()).await;
    let u = local_user();
    for bad in [
        ".git/hooks/pre-commit",
        "../escape.md",
        "a/../../escape.md",
        "",
    ] {
        let r = g
            .commit_push(&work, "m", &u, &files(&[(bad, "x")]), &[])
            .await;
        assert!(matches!(r, Err(Problem::PushFailed { .. })), "{bad}");
    }
    assert!(!tmp.path().join("repos/escape.md").exists());
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(tmp.path(), work.join("out")).expect("링크");
        let r = g
            .commit_push(&work, "m", &u, &files(&[("out/x.md", "x")]), &[])
            .await;
        assert!(
            matches!(r, Err(Problem::PushFailed { reason }) if reason.starts_with("작업 사본 밖 경로"))
        );
    }
}

#[tokio::test]
async fn clone_of_missing_remote_is_git_error() {
    let tmp = tempfile::tempdir().expect("임시");
    let g = git_for(tmp.path());
    let r = g
        .clone(
            tmp.path().join("nope.git").to_str().expect("경로"),
            &tmp.path().join("w"),
        )
        .await;
    assert!(matches!(r, Err(Problem::Git { cmd, .. }) if cmd.starts_with("git clone ")));
}

#[tokio::test]
async fn fetch_sees_outside_push_without_touching_workdir_and_counts_range() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    // 빈 원격 — origin/main이 없다
    assert!(matches!(g.fetch(&work).await, Err(Problem::Git { .. })));
    let first = g
        .commit_push(&work, "첫", &local_user(), &files(&[("a.md", "a")]), &[])
        .await
        .expect("첫 커밋");
    assert_eq!(g.fetch(&work).await.expect("fetch"), first);
    // 밖에서 민 커밋 → 그 해시, 작업 사본 HEAD는 그대로
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
    std::fs::write(other.join("b.md"), "b").expect("파일");
    sh(&other, &["add", "b.md"]);
    sh(&other, &["commit", "-q", "-m", "밖"]);
    sh(&other, &["push", "-q", "origin", "HEAD:main"]);
    let outside = sh(&other, &["rev-parse", "HEAD"]);
    assert_eq!(g.fetch(&work).await.expect("fetch"), outside);
    assert_eq!(sh(&work, &["rev-parse", "HEAD"]), first);
    let range = format!("{first}..{outside}");
    assert_eq!(g.rev_list_count(&work, &range).await.expect("수"), 1);
    assert_eq!(
        g.rev_list_count(&work, &format!("{first}..{first}"))
            .await
            .expect("수"),
        0
    );
    assert!(matches!(
        g.rev_list_count(&work, "0123456789abcdef0123456789abcdef01234567..HEAD")
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
    g.commit_push(
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("push");
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
    g.commit_push(
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("push");
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
        .commit_push(&work, "first", &u, &files(&[("a.txt", "a\n")]), &[])
        .await
        .expect("push");
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
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
    let head = g.fetch(&work).await.expect("fetch");
    assert_eq!(head, c4);
    let got = g
        .changed_files(&work, &format!("{base}..{head}"), "docs/specs/")
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
        .changed_files(&work, &format!("{base}..{c2}"), "docs/specs/")
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
    g.commit_push(
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("push");
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
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
    g.fetch(&work).await.expect("fetch");
    sh(&work, &["checkout", "-q", "origin/main"]);
    let got = g.log(&work, new).await.expect("이력");
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
        g.read(&work, &c.path, &c.hash).await.expect("읽힌다");
    }
    assert!(
        g.log(&work, "docs/specs/02-PRD/없음.md")
            .await
            .expect("빈")
            .is_empty()
    );
}

#[tokio::test]
async fn checkout_force_drops_local_edits() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, _, work) = setup(tmp.path()).await;
    g.commit_push(
        &work,
        "first",
        &local_user(),
        &files(&[("a.txt", "a\n")]),
        &[],
    )
    .await
    .expect("push");
    g.fetch(&work).await.expect("fetch"); // push는 추적 참조를 고치지 않는다 — 재구축도 받고 나서 돌린다
    std::fs::write(work.join("a.txt"), "고침\n").expect("고침");
    g.checkout(&work, "origin/main").await.expect("checkout");
    assert_eq!(
        std::fs::read_to_string(work.join("a.txt")).expect("읽기"),
        "a\n"
    );
    assert!(matches!(
        g.checkout(&work, "없는-가지").await,
        Err(Problem::Git { .. })
    ));
}

#[tokio::test]
async fn sync_readme_only_when_different() {
    let tmp = tempfile::tempdir().expect("임시");
    let (g, origin, work) = setup(tmp.path()).await;
    let u = local_user();
    let url = "http://127.0.0.1:8010/specs";
    g.commit_push(&work, "init", &u, &Git::init_specs(url), &[])
        .await
        .expect("push");
    assert_eq!(
        g.sync_readme(&work, &u, "X", url).await.expect("같다"),
        None
    );
    let other = tmp.path().join("other");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            other.to_str().expect("경로"),
        ],
    );
    put(&other, "docs/specs/README.md", "옛 README\n");
    push_as(&other, "a", "a@x", "README 고침");
    let hash = g
        .sync_readme(&work, &u, "X", url)
        .await
        .expect("다르다")
        .expect("커밋");
    assert_eq!(
        sh(&origin, &["log", "-1", "--format=%s"]),
        "chore(X): README를 싱크독 규약 링크로"
    );
    assert_eq!(sh(&origin, &["rev-parse", "main"]), hash);
    assert_eq!(
        g.sync_readme(&work, &u, "X", url).await.expect("이제 같다"),
        None
    );
    // README가 없는 저장소 — 만든다
    sh(&other, &["pull", "-q", "origin", "main"]);
    sh(&other, &["rm", "-q", "docs/specs/README.md"]);
    push_as(&other, "a", "a@x", "README 지움");
    assert!(
        g.sync_readme(&work, &u, "X", url)
            .await
            .expect("없다")
            .is_some()
    );
}
