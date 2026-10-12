//! 카드 L12 테스트 관점 — 코드 그래프 행(MS-022 CodeGraphService)·git 풀기(MS-019 changed_paths·archive)·
//! 그래프 만들기와 걸기(MS-017 build_code_graph·schedule_code_graph·process_commit 5a·rebuild 10)·
//! 코드 조회 넷(MS-018)과 카드 L13의 커뮤니티·코드 그래프 노드. 시험 DB · 임시 데이터 자리 · 진짜 git

mod support;

use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use sqlx::{PgConnection, PgPool};
use syncdoc_codegraph::{Call, Function, Graph};
use syncdoc_core::account::model::UserRow;
use syncdoc_core::codegraph::{CodeGraphRow, CodeGraphService};
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline;
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::queries;
use syncdoc_core::types::Storage;

const CODE: &str = "LG";

/// MINISPEC 하나 — main은 helper·other를 부른다고 적었다(other는 코드에 없다)
const MS: &str = "---\ndoc_id: LG-MS-001\ntype: MS\ntitle: MINISPEC — svc\nstatus: draft\nupstream: []\n---\n\n# MINISPEC\n\n## 1. 함수 목록\n\n## 2. 함수\n\n#### svc.main 진입\n\n**호출하는 것** [[#svc.helper]] · [[#svc.other]]\n\n#### svc.helper 도우미\n\n**호출하는 것** —\n\n#### svc.other 다른 것\n\n**호출하는 것** —\n\n## 3. 미결사항\n";

/// 코드 — main이 helper(항목)와 extra(도우미)를 부른다
const SVC: &str = "def main():\n    \"\"\"LG-MS-001#svc.main\"\"\"\n    return helper() + extra()\n\n\ndef helper():\n    \"\"\"LG-MS-001#svc.helper\"\"\"\n    return 1\n\n\ndef extra():\n    return 2\n";

struct Env {
    db: support::TestDb,
    tmp: tempfile::TempDir,
    repos: ServerRepos,
    user: UserRow,
    project_id: i32,
}

impl Env {
    fn pool(&self) -> &PgPool {
        &self.db.pool
    }

    async fn conn(&self) -> sqlx::pool::PoolConnection<sqlx::Postgres> {
        self.pool().acquire().await.expect("연결")
    }

    /// 서버 저장소 — git은 늘 여기서 돈다(카드 L19)
    fn origin(&self) -> PathBuf {
        self.repos.origins.join(format!("{CODE}.git"))
    }

    /// 서버 저장소의 다른 사본 — 밖에서 git으로 미는 사람
    fn outside(&self) -> PathBuf {
        let dir = self.tmp.path().join("outside");
        if !dir.exists() {
            let origin = self.repos.origins.join(format!("{CODE}.git"));
            git(
                self.tmp.path(),
                &[
                    "clone",
                    "-q",
                    origin.to_str().expect("경로"),
                    dir.to_str().expect("경로"),
                ],
            );
        } else {
            git(&dir, &["pull", "-q", "origin", "main"]);
        }
        dir
    }

    /// 밖에서 파일들을 커밋해 민다 → 해시
    fn push(&self, files: &[(&str, &str)], message: &str) -> String {
        let out = self.outside();
        for (path, text) in files {
            let f = out.join(path);
            std::fs::create_dir_all(f.parent().expect("부모")).expect("폴더");
            std::fs::write(f, text).expect("파일");
            git(&out, &["add", path]);
        }
        git(&out, &["commit", "-q", "-m", message]);
        git(&out, &["push", "-q", "origin", "HEAD:main"]);
        git(&out, &["rev-parse", "HEAD"])
    }

    async fn row(&self) -> Option<CodeGraphRow> {
        let mut c = self.conn().await;
        CodeGraphService { db: &mut c }
            .get(self.project_id)
            .await
            .expect("행")
    }

    /// 걸어 둔 그래프 만들기가 `ok`를 만족할 때까지 — 30초
    async fn wait_row(&self, ok: impl Fn(&CodeGraphRow) -> bool) -> CodeGraphRow {
        for _ in 0..300 {
            if let Some(r) = self.row().await
                && ok(&r)
            {
                return r;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        panic!("그래프 만들기가 끝나지 않았다");
    }

    async fn read_pending(&self) -> i64 {
        pipeline::read_pending(self.pool(), &self.repos, CODE, &self.user)
            .await
            .expect("밀린 커밋")
    }
}

async fn user(c: &mut PgConnection, login: &str) -> UserRow {
    sqlx::query_as::<_, UserRow>(
        "INSERT INTO users (github_login, display_name, kind) VALUES ($1, $1 || ' 님', 'local') \
         RETURNING id, github_login, github_user_id, display_name, github_token_encrypted, created_at, kind",
    )
    .bind(login)
    .fetch_one(c)
    .await
    .expect("사용자")
}

/// 프로젝트 하나 — 서버 저장소와 골격 커밋
async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "hoyoung").await;
    let (project, _) = ProjectService {
        db: &mut c,
        repos: &repos,
    }
    .init_project(&db.pool, CODE, "그래프 시험", &u, false, Storage::Server)
    .await
    .expect("프로젝트");
    drop(c);
    Env {
        db,
        tmp,
        repos,
        user: u,
        project_id: project.id,
    }
}

fn git(cwd: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(["-c", "user.name=밖", "-c", "user.email=out@example.com"])
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

fn function(key: &str, name: &str) -> Function {
    let (file, line) = key.rsplit_once(':').expect("key");
    Function {
        key: key.into(),
        name: name.into(),
        qual: format!("svc.{name}"),
        file: file.into(),
        line: line.parse().expect("줄"),
        end: None,
        item: None,
        ms: None,
        community: None,
    }
}

fn not_found(r: Result<impl std::fmt::Debug, Problem>) -> (String, String) {
    match r {
        Err(Problem::NotFound { resource, id }) => (resource, id.as_str().unwrap_or("").into()),
        other => panic!("not-found가 아니다: {other:?}"),
    }
}

#[tokio::test]
async fn save_replaces_one_row_and_fail_keeps_old_graph() {
    let e = env().await;
    let mut c = e.conn().await;
    let mut svc = CodeGraphService { db: &mut c };
    assert!(svc.get(e.project_id).await.expect("없음").is_none());
    // 첫 빌드부터 실패 → 빈 그래프 + 이유, 300자에서 자른다
    let long = "가".repeat(400);
    let r = svc
        .fail(e.project_id, "0123456789abcdef", &long)
        .await
        .expect("실패");
    assert_eq!(r.error.as_deref().map(|s| s.chars().count()), Some(300));
    assert!(
        r.error
            .as_deref()
            .is_some_and(|s| s.starts_with("0123456: 가"))
    );
    assert_eq!((r.commit_hash, r.source), (None, None));
    assert_eq!((r.function_count, r.call_count), (0, 0));
    assert!(r.graph.functions.is_empty());
    // 저장 둘 → 행 하나, 뒤의 것 · 앞의 error가 지워지고 개수 열이 맞다
    let g1 = Graph {
        functions: vec![function("a.py:1", "a")],
        ..Graph::default()
    };
    svc.save(e.project_id, "1111111", "server", &g1)
        .await
        .expect("저장");
    let g2 = Graph {
        functions: vec![function("a.py:1", "a"), function("a.py:5", "b")],
        calls: vec![Call("a.py:1".into(), "a.py:5".into(), "enrich".into())],
        communities: Some(Vec::new()),
        files: Vec::new(),
    };
    let r = svc
        .save(e.project_id, "2222222", "repo", &g2)
        .await
        .expect("저장");
    assert_eq!(
        (
            r.commit_hash.as_deref(),
            r.source.as_deref(),
            r.function_count,
            r.call_count,
            r.error.is_none()
        ),
        (Some("2222222"), Some("repo"), 2, 1, true)
    );
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM code_graphs")
        .fetch_one(&mut *svc.db)
        .await
        .expect("수");
    assert_eq!(n, 1);
    // 성공 뒤 실패 → 옛 그래프가 남고 error만
    svc.fail(e.project_id, "3333333", "깨졌다")
        .await
        .expect("실패");
    let r = svc.get(e.project_id).await.expect("행").expect("있다");
    assert_eq!(r.graph, g2);
    assert_eq!(r.commit_hash.as_deref(), Some("2222222"));
    assert_eq!(r.error.as_deref(), Some("3333333: 깨졌다"));
}

#[tokio::test]
async fn read_is_the_graph_commit_and_refuses_secrets_and_escapes() {
    let e = env().await;
    let lines: String = (1..=400).map(|i| format!("줄 {i}\n")).collect();
    let first = e.push(
        &[
            ("app/long.py", &lines),
            (".env", "SECRET=1\n"),
            ("id_rsa", "키\n"),
        ],
        "코드",
    );
    e.push(&[("app/long.py", "바뀜\n")], "뒤 커밋");
    let mut c = e.conn().await;
    let mut svc = CodeGraphService { db: &mut c };
    // 코드는 서버 저장소에서 읽는다(카드 L19)
    let wd = e.origin();
    // 그래프 없음 → not-found(code_graph)
    assert_eq!(
        not_found(
            svc.read(&e.repos.git, e.project_id, &wd, "app/long.py", 1, None)
                .await
        ),
        ("code_graph".into(), e.project_id.to_string())
    );
    svc.save(e.project_id, &first, "server", &Graph::default())
        .await
        .expect("저장");
    let t = svc
        .read(
            &e.repos.git,
            e.project_id,
            &wd,
            "app\\./long.py",
            10,
            Some(20),
        )
        .await
        .expect("읽기");
    assert_eq!(
        (t.path.as_str(), t.start, t.end, t.truncated),
        ("app/long.py", 10, 20, false)
    );
    assert!(t.text.starts_with("줄 10\n") && t.text.ends_with("줄 20"));
    assert_eq!(t.commit_hash, first);
    // 300줄에서 자른다 · 끝이 없으면 파일 끝까지
    let t = svc
        .read(&e.repos.git, e.project_id, &wd, "app/long.py", 0, None)
        .await
        .expect("읽기");
    assert_eq!((t.start, t.end, t.truncated), (1, 300, true));
    for bad in [
        ".env",
        "id_rsa",
        "x/secrets.yaml",
        "../x",
        "/etc/passwd",
        "",
        ".",
        "app/없음.py",
    ] {
        assert_eq!(
            not_found(
                svc.read(&e.repos.git, e.project_id, &wd, bad, 1, None)
                    .await
            ),
            ("file".into(), bad.into()),
            "{bad}"
        );
    }
}

#[tokio::test]
async fn changed_paths_and_archive_only_committed_regular_files() {
    let tmp = tempfile::tempdir().expect("임시");
    let repos = support::server_repos(tmp.path());
    let w = tmp.path().join("w");
    std::fs::create_dir_all(&w).expect("폴더");
    git(&w, &["init", "-q", "-b", "main"]);
    std::fs::write(w.join("a.py"), "def a():\n    return 1\n").expect("파일");
    std::fs::write(w.join(".gitignore"), "out/\n").expect("파일");
    git(&w, &["add", "."]);
    git(&w, &["commit", "-q", "-m", "첫"]);
    let first = git(&w, &["rev-parse", "HEAD"]);
    std::fs::create_dir_all(w.join("docs/specs/02-PRD")).expect("폴더");
    std::fs::write(w.join("docs/specs/02-PRD/X.md"), "# x\n").expect("파일");
    std::fs::write(w.join("a.py"), "def a():\n    return 2\n").expect("파일");
    #[cfg(unix)]
    std::os::unix::fs::symlink("a.py", w.join("link.py")).expect("링크");
    git(&w, &["add", "."]);
    git(&w, &["commit", "-q", "-m", "둘"]);
    let second = git(&w, &["rev-parse", "HEAD"]);
    // 코드·명세를 함께 바꾼 범위 → 둘 다
    let mut paths = repos
        .git
        .changed_paths(&w, &format!("{first}..{second}"))
        .await
        .expect("경로");
    paths.sort();
    let mut want = vec!["a.py", "docs/specs/02-PRD/X.md"];
    if cfg!(unix) {
        want.push("link.py");
    }
    want.sort();
    assert_eq!(paths, want);
    // 커밋 뒤 작업 사본을 고쳐도 커밋의 내용 · .gitignore된 것·링크는 없다
    std::fs::write(w.join("a.py"), "고친 것\n").expect("파일");
    std::fs::create_dir_all(w.join("out")).expect("폴더");
    std::fs::write(w.join("out/gen.py"), "x = 1\n").expect("파일");
    let dest = tmp.path().join("dest");
    repos.git.archive(&w, &second, &dest).await.expect("풀기");
    assert_eq!(
        std::fs::read_to_string(dest.join("a.py")).expect("a"),
        "def a():\n    return 2\n"
    );
    assert!(dest.join("docs/specs/02-PRD/X.md").is_file());
    assert!(!dest.join("out").exists());
    assert!(!dest.join("link.py").exists() && dest.join("link.py").symlink_metadata().is_err());
    assert!(!dest.join(".src.tar").exists());
}

#[tokio::test]
async fn build_from_push_follows_committed_graph_json_and_keeps_old_on_failure() {
    let e = env().await;
    let head = e.push(&[("app/svc.py", SVC)], "코드");
    // 밀린 커밋 읽기는 그래프 만들기를 따로 건다 — 여기서는 직접 부른다(받기 없음 — 서버 저장소에서 읽는다)
    pipeline::build_code_graph(e.pool(), &e.repos, CODE, &head).await;
    let r = e
        .wait_row(|r| r.commit_hash.as_deref() == Some(head.as_str()))
        .await;
    assert_eq!(r.source.as_deref(), Some("server"));
    assert!(r.error.is_none());
    let main = r
        .graph
        .functions
        .iter()
        .find(|f| f.name == "main")
        .expect("main");
    assert_eq!(
        (
            main.key.as_str(),
            main.qual.as_str(),
            main.end,
            main.item.as_deref()
        ),
        (
            "app/svc.py:1",
            "svc.main",
            Some(3),
            Some("LG-MS-001#svc.main")
        )
    );
    assert!(
        r.graph
            .calls
            .iter()
            .any(|c| (c.0.as_str(), c.1.as_str()) == ("app/svc.py:1", "app/svc.py:6"))
    );
    // 커뮤니티 — 함수마다 번호, 목록의 크기 합이 함수 수 (카드 L13)
    let groups = r.graph.communities.as_ref().expect("커뮤니티");
    assert!(!groups.is_empty());
    assert!(r.graph.functions.iter().all(|f| f.community.is_some()));
    assert_eq!(groups.iter().map(|c| c.size).sum::<i64>(), 3);
    assert_eq!(r.function_count, 3);
    // 커밋된 graph.json이 있으면 그것 — 출처 repo
    let raw = r#"{"nodes": [{"id": "f", "label": "f()", "file_type": "code", "source_file": "app/svc.py", "source_location": "L6", "_callable": true}], "links": []}"#;
    let head = e.push(&[("graphify-out/graph.json", raw)], "그래프");
    pipeline::build_code_graph(e.pool(), &e.repos, CODE, &head).await;
    let r = e.row().await.expect("행");
    assert_eq!(
        (r.source.as_deref(), r.commit_hash.as_deref()),
        (Some("repo"), Some(head.as_str()))
    );
    // 보강이 파일의 정의를 다 채운다 — 원형의 f는 helper가 된다
    assert_eq!(r.function_count, 3);
    // 깨진 graph.json → 옛 그래프를 두고 error
    let bad = e.push(&[("graphify-out/graph.json", "{깨짐")], "깨진 그래프");
    pipeline::build_code_graph(e.pool(), &e.repos, CODE, &bad).await;
    let after = e.row().await.expect("행");
    assert_eq!(after.commit_hash, r.commit_hash);
    assert_eq!(after.graph, r.graph);
    assert_eq!(after.error, Some(format!("{}: graph.json 형식", &bad[..7])));
    // 해제된 프로젝트 → 아무것도 안 한다
    pipeline::build_code_graph(e.pool(), &e.repos, "NOPE", &bad).await;
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM code_graphs")
        .fetch_one(&mut *e.conn().await)
        .await
        .expect("수");
    assert_eq!(n, 1);
}

#[tokio::test]
async fn commits_schedule_graph_when_code_changes_or_none_and_rebuild_always() {
    let e = env().await;
    // 그래프가 없으면 명세만 바뀐 커밋도 건다
    let spec = e.push(&[("docs/specs/10-MS/LG-MS-001.md", MS)], "명세");
    e.read_pending().await;
    let r = e
        .wait_row(|r| r.commit_hash.as_deref() == Some(spec.as_str()))
        .await;
    assert_eq!(r.function_count, 0);
    // 코드가 바뀐 커밋 → 다시
    let code = e.push(&[("app/svc.py", SVC)], "코드");
    e.read_pending().await;
    let r = e
        .wait_row(|r| r.commit_hash.as_deref() == Some(code.as_str()))
        .await;
    assert_eq!(r.function_count, 3);
    // 명세만 바뀐 커밋 → 그래프가 있으면 건너뛴다
    e.push(
        &[(
            "docs/specs/10-MS/LG-MS-001.md",
            &MS.replace("진입", "들어감"),
        )],
        "명세만",
    );
    e.read_pending().await;
    tokio::time::sleep(Duration::from_millis(1500)).await;
    assert_eq!(
        e.row().await.expect("행").commit_hash.as_deref(),
        Some(code.as_str())
    );
    // 재구축은 늘 다시 만든다
    let head = git(&e.outside(), &["rev-parse", "HEAD"]);
    let before = e.row().await.expect("행").built_at;
    let mut c = e.conn().await;
    pipeline::rebuild(&mut c, e.pool(), &e.repos, CODE)
        .await
        .expect("재구축");
    let r = e
        .wait_row(|r| r.built_at > before && r.commit_hash.as_deref() == Some(head.as_str()))
        .await;
    assert_eq!(r.function_count, 3);
}

#[tokio::test]
async fn scheduling_while_running_builds_the_last_once_more() {
    let e = env().await;
    let a = e.push(&[("app/a.py", "def a():\n    return 1\n")], "a");
    let b = e.push(&[("app/b.py", "def b():\n    return 2\n")], "b");
    let c = e.push(&[("app/c.py", "def c():\n    return 3\n")], "c");
    pipeline::schedule_code_graph(e.pool(), &e.repos, CODE, &a);
    pipeline::schedule_code_graph(e.pool(), &e.repos, CODE, &b);
    pipeline::schedule_code_graph(e.pool(), &e.repos, CODE, &c);
    let r = e
        .wait_row(|r| r.commit_hash.as_deref() == Some(c.as_str()))
        .await;
    assert_eq!(r.function_count, 3);
    // b는 c에 덮였다 — 한 번 더 만든 것은 마지막 것
    tokio::time::sleep(Duration::from_millis(500)).await;
    assert_eq!(
        e.row().await.expect("행").commit_hash.as_deref(),
        Some(c.as_str())
    );
}

#[tokio::test]
async fn code_queries_compare_spec_calls_with_code() {
    let e = env().await;
    let head = e.push(
        &[("docs/specs/10-MS/LG-MS-001.md", MS), ("app/svc.py", SVC)],
        "명세와 코드",
    );
    e.read_pending().await;
    let r = e
        .wait_row(|r| r.commit_hash.as_deref() == Some(head.as_str()))
        .await;
    assert_eq!(r.function_count, 3);
    let mut c = e.conn().await;
    let v = queries::code_view(&mut c, &e.repos, "LG-MS-001", Some("svc.main"), &e.user)
        .await
        .expect("코드 탭");
    assert!(v.is_ms && !v.missing);
    let f = v.function.expect("함수");
    assert_eq!((f.qual.as_str(), f.line, f.end), ("svc.main", 1, Some(3)));
    let calls: Vec<(&str, Option<&str>)> = f
        .calls
        .iter()
        .map(|r| (r.ms_id.as_str(), r.status.as_deref()))
        .collect();
    assert_eq!(
        calls,
        [
            ("LG-MS-001#svc.other", Some("spec_only")),
            ("LG-MS-001#svc.helper", Some("same"))
        ]
    );
    assert!(f.callers.is_empty());
    assert_eq!(
        v.functions
            .iter()
            .map(|b| b.ms_id.as_str())
            .collect::<Vec<_>>(),
        [
            "LG-MS-001#svc.main",
            "LG-MS-001#svc.helper",
            "LG-MS-001#svc.other"
        ]
    );
    // 코드에 없는 항목 → missing
    let v = queries::code_view(&mut c, &e.repos, "LG-MS-001", Some("svc.other"), &e.user)
        .await
        .expect("코드 탭");
    assert!(v.missing && v.function.is_none());
    // 관계도 코드 호출 — 같음·명세만
    let calls = queries::code_calls(&mut c, &e.repos, CODE, &e.user)
        .await
        .expect("호출");
    let edges: Vec<(&str, &str, &str)> = calls
        .edges
        .iter()
        .map(|x| (x.from.as_str(), x.to.as_str(), x.status.as_str()))
        .collect();
    assert_eq!(
        edges,
        [
            ("LG-MS-001#svc.main", "LG-MS-001#svc.helper", "same"),
            ("LG-MS-001#svc.main", "LG-MS-001#svc.other", "spec_only")
        ]
    );
    // 코드 보기 — 그 함수의 줄
    let t = queries::code_source(&mut c, &e.repos, "LG-MS-001", "svc.helper", &e.user)
        .await
        .expect("코드 보기");
    assert_eq!((t.path.as_str(), t.start, t.end), ("app/svc.py", 6, 8));
    assert!(t.text.starts_with("def helper():"));
    assert_eq!(
        not_found(queries::code_source(&mut c, &e.repos, "LG-MS-001", "svc.other", &e.user).await),
        ("function".into(), "LG-MS-001#svc.other".into())
    );
    // 코드 그래프의 코드 — 파일·시작 줄
    let t = queries::code_text(&mut c, &e.repos, CODE, "app/svc.py", 11, &e.user)
        .await
        .expect("코드");
    assert_eq!((t.start, t.end), (11, 12));
    assert_eq!(
        not_found(queries::code_text(&mut c, &e.repos, CODE, "app/svc.py", 2, &e.user).await),
        ("function".into(), "app/svc.py:2".into())
    );
    // 코드 그래프 노드 — 대조 상태·항목·층·커뮤니티·선 (카드 L13)
    let nodes = queries::code_nodes(&mut c, &e.repos, CODE, &e.user)
        .await
        .expect("노드");
    assert!(nodes.graph.is_some());
    let node = |name: &str| {
        nodes
            .functions
            .iter()
            .find(|n| n.name == name)
            .expect("함수")
    };
    let main = node("main");
    assert_eq!(
        (
            main.ms.as_deref(),
            main.item.as_deref(),
            main.status.as_deref(),
            main.layer.is_none()
        ),
        (
            Some("LG-MS-001#svc.main"),
            Some("LG-MS-001#svc.main"),
            Some("spec_only"),
            true
        )
    );
    assert_eq!(node("helper").status.as_deref(), Some("same"));
    let extra = node("extra");
    assert_eq!((extra.ms.as_deref(), extra.status.as_deref()), (None, None));
    assert_eq!(
        extra
            .layer
            .as_ref()
            .map(|l| (l.name.as_str(), l.specs.len())),
        Some(("도우미", 0))
    );
    assert!(!nodes.communities.is_empty());
    assert!(nodes.functions.iter().all(|f| f.community.is_some()));
    assert!(
        nodes
            .calls
            .contains(&("app/svc.py:1".to_string(), "app/svc.py:6".to_string()))
    );
    // 그래프 없음
    sqlx::query("DELETE FROM code_graphs")
        .execute(&mut *c)
        .await
        .expect("지우기");
    let v = queries::code_view(&mut c, &e.repos, "LG-MS-001", None, &e.user)
        .await
        .expect("코드 탭");
    assert!(v.graph.is_none() && v.functions.is_empty() && !v.missing);
    let nodes = queries::code_nodes(&mut c, &e.repos, CODE, &e.user)
        .await
        .expect("노드");
    assert!(nodes.graph.is_none() && nodes.functions.is_empty() && nodes.calls.is_empty());
    assert!(
        queries::code_calls(&mut c, &e.repos, CODE, &e.user)
            .await
            .expect("호출")
            .graph
            .is_none()
    );
    assert_eq!(
        not_found(queries::code_source(&mut c, &e.repos, "LG-MS-001", "svc.main", &e.user).await),
        ("code_graph".into(), CODE.into())
    );
    assert_eq!(
        not_found(queries::code_text(&mut c, &e.repos, CODE, "app/svc.py", 1, &e.user).await),
        ("code_graph".into(), CODE.into())
    );
}
