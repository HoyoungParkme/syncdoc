//! git 입구 — 카드 L10 (SYNC-MS-019 advertise_refs·service_rpc · SYNC-MS-013 server_origin · SYNC-API-001 git 셋).
//! 진짜 git 클라이언트로 서버에 clone·push한다(시험 DB · 임시 자리).

#[path = "../../core/tests/support/mod.rs"]
mod support;

use std::path::Path;
use std::process::Command;

use syncdoc_core::account::service::AccountService;
use syncdoc_core::project::service::ProjectService;
use syncdoc_core::types::Storage;
use syncdoc_server::app;
use syncdoc_server::state::AppState;

/// 시험이 부르는 git — 사용자 설정 없이, 작성자를 붙여
fn git(cwd: &Path, global: &Path, args: &[&str]) -> (bool, String) {
    let out = Command::new("git")
        .args(["-c", "user.name=t", "-c", "user.email=t@t"])
        .args(args)
        .current_dir(cwd)
        .env("GIT_CONFIG_GLOBAL", global)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_TERMINAL_PROMPT", "0")
        .output()
        .expect("git");
    (
        out.status.success(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

#[tokio::test]
async fn real_git_clones_and_pushes_through_the_entrance() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut tx = db.pool.begin().await.expect("트랜잭션");
    let user = AccountService { db: &mut tx }
        .ensure_local_user("local", "로컬")
        .await
        .expect("사용자");
    let raw = AccountService { db: &mut tx }
        .issue_token(&user, "git")
        .await
        .expect("토큰")
        .raw;
    ProjectService {
        db: &mut tx,
        repos: &repos,
    }
    .init_project(&db.pool, "LG", "깃", &user, false, Storage::Server)
    .await
    .expect("프로젝트");
    tx.commit().await.expect("커밋");
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("묶기");
    let port = listener.local_addr().expect("포트").port();
    let state = AppState {
        pool: db.pool.clone(),
        local_login: "local".into(),
        local_name: "로컬".into(),
        llm_enabled: false,
        repos: std::sync::Arc::new(repos),
        public_netloc: format!("127.0.0.1:{port}"),
    };
    let server = tokio::spawn(async move {
        axum::serve(listener, app(state)).await.expect("서빙");
    });
    let global = tmp.path().join("client-gitconfig");
    std::fs::write(&global, "").expect("빈 설정");
    let url = format!("http://x:{raw}@127.0.0.1:{port}/git/LG.git");
    let (url2, g, t) = (url.clone(), global.clone(), tmp.path().to_path_buf());
    // git 클라이언트는 막히는 프로세스 — 서버가 같은 런타임에서 돌도록 따로 띄운다
    let checks = tokio::task::spawn_blocking(move || {
        let work = t.join("clone");
        let (ok, log) = git(
            &t,
            &g,
            &["clone", "-q", &url2, work.to_str().expect("경로")],
        );
        assert!(ok, "clone: {log}");
        assert!(work.join("docs/specs/README.md").is_file());
        // main에 코드를 민다
        std::fs::create_dir_all(work.join("src")).expect("src");
        std::fs::write(work.join("src/a.py"), "def f():\n    return 1\n").expect("코드");
        git(&work, &g, &["add", "src/a.py"]);
        git(&work, &g, &["commit", "-q", "-m", "코드"]);
        let (ok, log) = git(&work, &g, &["push", "-q", "origin", "main"]);
        assert!(ok, "push: {log}");
        // 다른 가지는 받는다
        let (ok, log) = git(&work, &g, &["push", "-q", "origin", "main:topic"]);
        assert!(ok, "가지 push: {log}");
        // 되감기·지우기는 받지 않는다
        git(&work, &g, &["reset", "-q", "--hard", "HEAD~1"]);
        std::fs::write(work.join("b.txt"), "b").expect("파일");
        git(&work, &g, &["add", "b.txt"]);
        git(&work, &g, &["commit", "-q", "-m", "갈라짐"]);
        let (ok, _) = git(&work, &g, &["push", "-q", "--force", "origin", "main"]);
        assert!(!ok, "되감는 push가 들어갔다");
        let (ok, _) = git(&work, &g, &["push", "-q", "origin", ":topic"]);
        assert!(!ok, "지우는 push가 들어갔다");
        // 틀린 토큰은 git이 다시 묻는다(프롬프트를 끄면 실패)
        let bad = url2.replace(&raw, "syncdoc_pat_wrong");
        let (ok, log) = git(&t, &g, &["ls-remote", &bad]);
        assert!(!ok, "틀린 토큰: {log}");
        // 남의 것·없는 프로젝트는 없는 것과 같다
        let none = url2.replace("LG.git", "NOPE.git");
        let (ok, _) = git(&t, &g, &["ls-remote", &none]);
        assert!(!ok);
        // 다시 받으면 민 코드가 있다
        let again = t.join("again");
        let (ok, log) = git(
            &t,
            &g,
            &["clone", "-q", &url2, again.to_str().expect("경로")],
        );
        assert!(ok, "다시 clone: {log}");
        assert!(again.join("src/a.py").is_file());
    });
    let r = checks.await;
    server.abort();
    r.expect("git 시험");
    let origin = tmp.path().join("origins/LG.git");
    let (_, heads) = git(
        &origin,
        &global,
        &["for-each-ref", "--format=%(refname)", "refs/heads"],
    );
    assert_eq!(heads.trim(), "refs/heads/main\nrefs/heads/topic");
}
