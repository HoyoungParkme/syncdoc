//! SYNC-MS-013 테스트 관점 — 시험 DB · 임시 데이터 자리 · 진짜 git

mod support;

use std::path::{Path, PathBuf};
use std::process::Command;

use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::git::Git;
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::types::Storage;

fn places(tmp: &Path) -> ServerRepos {
    let global = tmp.join("gitconfig");
    std::fs::write(&global, "").expect("빈 설정");
    std::fs::create_dir_all(tmp.join("origins")).expect("origins");
    std::fs::create_dir_all(tmp.join("repos")).expect("repos");
    ServerRepos {
        git: Git {
            exe: "git".into(),
            global_config: global,
        },
        origins: tmp.join("origins"),
        repos: tmp.join("repos"),
        specs_url: "http://127.0.0.1:8010/specs".into(),
    }
}

async fn user(c: &mut PgConnection, login: &str) -> UserRow {
    sqlx::query_as::<_, UserRow>(
        "INSERT INTO users (github_login, display_name, kind) VALUES ($1, $1, 'local') \
         RETURNING id, github_login, github_user_id, display_name, github_token_encrypted, created_at, kind",
    )
    .bind(login)
    .fetch_one(c)
    .await
    .expect("사용자")
}

fn sh(cwd: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
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

fn archives(p: &ServerRepos) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(p.origins.join("_archive"))
        .map(|d| d.filter_map(Result::ok).map(|e| e.path()).collect())
        .unwrap_or_default();
    v.sort();
    v
}

#[tokio::test]
async fn init_makes_server_repo_and_skeleton_commit() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let (proj, repo) = ProjectService {
        db: &mut c,
        repos: &p,
    }
    .init_project("EX", "예시", &u, false, Storage::Server)
    .await
    .expect("만들기");
    assert_eq!((proj.code.as_str(), proj.owner_user_id), ("EX", u.id));
    let origin = p.origins.join("EX.git");
    assert_eq!(repo.remote_url, origin.to_string_lossy());
    assert_eq!(repo.storage, "server");
    assert_eq!(sh(&origin, &["symbolic-ref", "HEAD"]), "refs/heads/main");
    assert_eq!(
        sh(&origin, &["log", "--format=%s", "main"]),
        "chore(EX): init syncdoc"
    );
    assert_eq!(
        repo.last_processed_commit.as_deref(),
        Some(sh(&origin, &["rev-parse", "main"]).as_str())
    );
    assert_eq!(
        sh(&origin, &["ls-tree", "-r", "--name-only", "main"])
            .lines()
            .count(),
        14
    );
    assert!(p.repos.join("EX/docs/specs/README.md").is_file());
}

#[tokio::test]
async fn rejects_github_bad_code_and_duplicates_without_side_effects() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    match s.init_project("GH", "x", &u, false, Storage::Github).await {
        Err(Problem::StorageUnavailable { storage, enabled }) => {
            assert_eq!(
                (storage.as_str(), enabled),
                ("github", vec!["server".to_string()])
            )
        }
        other => panic!("{other:?}"),
    }
    assert!(!p.origins.join("GH.git").exists());
    for bad in ["ab", "ABCDE", "A1", ""] {
        assert!(matches!(
            s.init_project(bad, "x", &u, false, Storage::Server).await,
            Err(Problem::ProjectCodeInvalid { rule }) if rule == "^[A-Z]{1,4}$"
        ));
    }
    s.init_project("DUP", "x", &u, false, Storage::Server)
        .await
        .expect("처음");
    assert!(matches!(
        s.init_project("DUP", "x", &u, false, Storage::Server).await,
        Err(Problem::ProjectCodeConflict { code }) if code == "DUP"
    ));
}

#[tokio::test]
async fn delete_archives_then_recreate_asks_and_import_is_l11() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let other = user(&mut c, "other").await;
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    s.init_project("ARC", "보관", &u, false, Storage::Server)
        .await
        .expect("만들기");
    // 남의 것 → 없는 것과 같은 답, 아무것도 안 지워짐
    assert!(matches!(
        s.delete_project("ARC", &other).await,
        Err(Problem::NotFound { .. })
    ));
    assert!(p.origins.join("ARC.git").exists());
    s.delete_project("ARC", &u).await.expect("지우기");
    assert!(
        matches!(s.get("ARC").await, Err(Problem::NotFound { resource, .. }) if resource == "project")
    );
    assert!(!p.origins.join("ARC.git").exists() && !p.repos.join("ARC").exists());
    let kept = archives(&p);
    assert_eq!(kept.len(), 1);
    // 다시 만들기 → 보관본이 있다고 묻는다(골격뿐이라 명세 0), 아무것도 안 바뀜
    match s
        .init_project("ARC", "보관", &u, false, Storage::Server)
        .await
    {
        Err(Problem::ExistingSpecs {
            doc_count,
            archived_at,
        }) => {
            assert_eq!(doc_count, 0);
            assert!(archived_at.is_some_and(|a| a.ends_with("+00:00")));
        }
        other => panic!("{other:?}"),
    }
    assert_eq!(archives(&p), kept);
    // 명세가 든 보관본을 가져오기 → 재구축(L11). 보관본은 제자리, 행 없음
    assert!(matches!(
        s.init_project("ARC", "보관", &u, true, Storage::Server).await,
        Err(Problem::NotImplemented { card }) if card == "L11"
    ));
    assert_eq!(archives(&p), kept);
    assert!(!p.origins.join("ARC.git").exists());
    assert!(matches!(s.get("ARC").await, Err(Problem::NotFound { .. })));
}

#[tokio::test]
async fn leftover_empty_origin_is_archived_and_import_restores_it() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    p.git
        .init_bare(&p.origins.join("LEFT.git"))
        .await
        .expect("남은 원본");
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    assert!(matches!(
        s.init_project("LEFT", "x", &u, false, Storage::Server)
            .await,
        Err(Problem::ExistingSpecs {
            doc_count: 0,
            archived_at: Some(_)
        })
    ));
    assert_eq!(archives(&p).len(), 1);
    // 커밋 없는 보관본 + 가져오기 → 되살리고 골격 커밋
    s.init_project("LEFT", "x", &u, true, Storage::Server)
        .await
        .expect("되살리기");
    assert!(archives(&p).is_empty());
    assert_eq!(
        sh(&p.origins.join("LEFT.git"), &["log", "--format=%s", "main"]),
        "chore(LEFT): init syncdoc"
    );
}

#[tokio::test]
async fn clone_failure_leaves_nothing() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let mut p = places(tmp.path());
    // 작업 사본 자리가 파일이라 clone이 실패한다
    std::fs::write(tmp.path().join("notdir"), "x").expect("파일");
    p.repos = tmp.path().join("notdir");
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let r = ProjectService {
        db: &mut c,
        repos: &p,
    }
    .init_project("CL", "x", &u, false, Storage::Server)
    .await;
    assert!(matches!(r, Err(Problem::PushFailed { reason }) if reason.starts_with("clone: ")));
    assert!(!p.origins.join("CL.git").exists());
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM projects")
        .fetch_one(&mut *c)
        .await
        .expect("수");
    assert_eq!(n, 0);
}

#[tokio::test]
async fn delete_removes_rows_of_that_project_only_and_owned_listing() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let other = user(&mut c, "other").await;
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    s.init_project("BB", "b", &u, false, Storage::Server)
        .await
        .expect("b");
    s.init_project("AA", "a", &u, false, Storage::Server)
        .await
        .expect("a");
    s.init_project("OT", "o", &other, false, Storage::Server)
        .await
        .expect("o");
    let mine: Vec<String> = s
        .list_owned(&u)
        .await
        .expect("목록")
        .into_iter()
        .map(|(p, _)| p.code)
        .collect();
    assert_eq!(mine, ["AA", "BB"]);
    assert!(
        matches!(s.get_owned("OT", &u).await, Err(Problem::NotFound { resource, id }) if resource == "project" && id == "OT")
    );
    for code in ["AA", "BB"] {
        let (proj, _) = s.get(code).await.expect("있다");
        sqlx::query(
            "INSERT INTO documents (project_id, doc_id, doc_type, status, current_body, current_version_no) \
             VALUES ($1, $2, 'PRD', 'draft', 'x', 1)",
        )
        .bind(proj.id)
        .bind(format!("{code}-PRD-001"))
        .execute(&mut *s.db)
        .await
        .expect("문서");
        sqlx::query("INSERT INTO conversations (project_id, user_id, title) VALUES ($1, $2, 't')")
            .bind(proj.id)
            .bind(u.id)
            .execute(&mut *s.db)
            .await
            .expect("대화");
    }
    s.delete_project("AA", &u).await.expect("지우기");
    let docs: Vec<String> = sqlx::query_scalar("SELECT doc_id FROM documents ORDER BY doc_id")
        .fetch_all(&mut *s.db)
        .await
        .expect("문서");
    assert_eq!(docs, ["BB-PRD-001"]);
    let convs: i64 = sqlx::query_scalar("SELECT count(*) FROM conversations")
        .fetch_one(&mut *s.db)
        .await
        .expect("대화");
    assert_eq!(convs, 1);
}
