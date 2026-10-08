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
