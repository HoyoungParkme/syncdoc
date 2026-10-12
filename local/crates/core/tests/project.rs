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
        git: Git::new("git".into(), global),
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
    .init_project(&db.pool, "EX", "예시", &u, false, Storage::Server)
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
    // 작업 사본은 git이 아닌 폴더(카드 L19)
    assert!(!p.repos.join("EX/.git").exists());
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
    match s
        .init_project(&db.pool, "GH", "x", &u, false, Storage::Github)
        .await
    {
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
            s.init_project(&db.pool, bad, "x", &u, false, Storage::Server).await,
            Err(Problem::ProjectCodeInvalid { rule }) if rule == "^[A-Z]{1,4}$"
        ));
    }
    s.init_project(&db.pool, "DUP", "x", &u, false, Storage::Server)
        .await
        .expect("처음");
    assert!(matches!(
        s.init_project(&db.pool, "DUP", "x", &u, false, Storage::Server).await,
        Err(Problem::ProjectCodeConflict { code }) if code == "DUP"
    ));
}

#[tokio::test]
async fn delete_archives_then_recreate_asks_and_import_rebuilds() {
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
    s.init_project(&db.pool, "ARC", "보관", &u, false, Storage::Server)
        .await
        .expect("만들기");
    // 밖에서 명세 하나를 민다 — 보관본에 든다
    let out = tmp.path().join("out");
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            p.origins.join("ARC.git").to_str().expect("경로"),
            out.to_str().expect("경로"),
        ],
    );
    std::fs::write(
        out.join("docs/specs/02-PRD/ARC-PRD-001.md"),
        "---\ndoc_id: ARC-PRD-001\ntype: PRD\ntitle: 보관\nstatus: draft\n---\n# 보관\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 하나\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n",
    )
    .expect("명세");
    sh(&out, &["add", "-A"]);
    sh(
        &out,
        &[
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "spec: 밖",
        ],
    );
    sh(&out, &["push", "-q", "origin", "HEAD:main"]);
    let pushed = sh(&out, &["rev-parse", "HEAD"]);
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
        .init_project(&db.pool, "ARC", "보관", &u, false, Storage::Server)
        .await
    {
        Err(Problem::ExistingSpecs {
            doc_count,
            archived_at,
        }) => {
            assert_eq!(doc_count, 1);
            assert!(archived_at.is_some_and(|a| a.ends_with("+00:00")));
        }
        other => panic!("{other:?}"),
    }
    assert_eq!(archives(&p), kept);
    // 명세가 든 보관본을 가져오기 → 재구축(L11). 보관본이 원본으로 되살아나고 골격 커밋 없이 처리 지점이 원본 끝
    let (_, repo) = s
        .init_project(&db.pool, "ARC", "보관", &u, true, Storage::Server)
        .await
        .expect("가져오기");
    assert!(archives(&p).is_empty());
    assert_eq!(
        sh(&p.origins.join("ARC.git"), &["rev-parse", "main"]),
        pushed
    );
    assert_eq!(repo.last_processed_commit.as_deref(), Some(pushed.as_str()));
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM documents WHERE doc_id = 'ARC-PRD-001'")
        .fetch_one(&mut *s.db)
        .await
        .expect("문서");
    assert_eq!(n, 1);
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
        s.init_project(&db.pool, "LEFT", "x", &u, false, Storage::Server)
            .await,
        Err(Problem::ExistingSpecs {
            doc_count: 0,
            archived_at: Some(_)
        })
    ));
    assert_eq!(archives(&p).len(), 1);
    // 커밋 없는 보관본 + 가져오기 → 되살리고 골격 커밋
    s.init_project(&db.pool, "LEFT", "x", &u, true, Storage::Server)
        .await
        .expect("되살리기");
    assert!(archives(&p).is_empty());
    assert_eq!(
        sh(&p.origins.join("LEFT.git"), &["log", "--format=%s", "main"]),
        "chore(LEFT): init syncdoc"
    );
}

#[tokio::test]
async fn workdir_failure_leaves_nothing() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let mut p = places(tmp.path());
    // 작업 사본 자리가 파일이라 폴더를 못 만든다
    std::fs::write(tmp.path().join("notdir"), "x").expect("파일");
    p.repos = tmp.path().join("notdir");
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let r = ProjectService {
        db: &mut c,
        repos: &p,
    }
    .init_project(&db.pool, "CL", "x", &u, false, Storage::Server)
    .await;
    assert!(r.is_err());
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
    s.init_project(&db.pool, "BB", "b", &u, false, Storage::Server)
        .await
        .expect("b");
    s.init_project(&db.pool, "AA", "a", &u, false, Storage::Server)
        .await
        .expect("a");
    s.init_project(&db.pool, "OT", "o", &other, false, Storage::Server)
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

#[tokio::test]
async fn server_origin_owner_only_and_needs_the_folder() {
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
    s.init_project(&db.pool, "SO", "s", &u, false, Storage::Server)
        .await
        .expect("만들기");
    let origin = s.server_origin("SO", &u).await.expect("원본");
    assert_eq!(origin, tmp.path().join("origins/SO.git"));
    let not_found = |r: Result<PathBuf, Problem>| matches!(r, Err(Problem::NotFound { resource, id }) if resource == "project" && id == "SO");
    // 남의 것·원본 폴더가 없는 것은 없는 프로젝트와 같은 답
    assert!(not_found(s.server_origin("SO", &other).await));
    // 읽기 프로세스를 끈 뒤에 옮긴다 — 윈도는 열린 팩이 있으면 못 옮긴다(앱도 끄고 옮긴다)
    p.git.close_all().await;
    std::fs::rename(&origin, tmp.path().join("moved.git")).expect("옮기기");
    assert!(not_found(s.server_origin("SO", &u).await));
    assert!(matches!(
        s.server_origin("NOPE", &u).await,
        Err(Problem::NotFound { resource, id }) if resource == "project" && id == "NOPE"
    ));
}

const BND_DRAFT: &str = "---\ndoc_id: BND-PRD-001\ntype: PRD\ntitle: 번들\nstatus: draft\n---\n# 번들\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 하나\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n";

/// 명세 두 커밋(초안 → 상태)과 태그가 든 저장소의 번들 — 파이썬 판 시험 `_bundle`과 같은 꼴
fn bundle(tmp: &Path, branch: &str) -> Vec<u8> {
    let src = tmp.join(format!("src-{branch}"));
    sh(
        tmp,
        &["init", "-q", "-b", branch, src.to_str().expect("경로")],
    );
    let f = src.join("docs/specs/02-PRD/BND-PRD-001.md");
    std::fs::create_dir_all(f.parent().expect("위")).expect("폴더");
    let commit = |text: &str, msg: &str| {
        std::fs::write(&f, text).expect("명세");
        sh(&src, &["add", "-A"]);
        sh(
            &src,
            &[
                "-c",
                "user.name=밖",
                "-c",
                "user.email=out@example.com",
                "commit",
                "-q",
                "-m",
                msg,
            ],
        );
    };
    commit(BND_DRAFT, "spec(BND-PRD-001): 초안");
    commit(
        &BND_DRAFT.replace("status: draft", "status: approved"),
        "status(BND-PRD-001): draft → approved",
    );
    sh(&src, &["tag", "v1"]);
    let out = tmp.join(format!("{branch}.bundle"));
    sh(
        &src,
        &[
            "bundle",
            "create",
            "-q",
            out.to_str().expect("경로"),
            "--all",
        ],
    );
    std::fs::read(out).expect("번들")
}

/// L15 import_bundle — 번들의 커밋으로 서버 저장소, 재구축으로 판·상태. 골격 커밋 없음. 이름 없이 남은 원본은 보관으로
#[tokio::test]
async fn import_bundle_restores_specs_and_status_without_skeleton() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let data = bundle(tmp.path(), "main");
    let origin = p.origins.join("BND.git");
    p.git.init_bare(&origin).await.expect("남은 원본");
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    let (project, repo) = s
        .import_bundle(&db.pool, "BND", "번들", &u, &data)
        .await
        .expect("가져오기");
    assert_eq!(archives(&p).len(), 1);
    let src = tmp.path().join("src-main");
    assert_eq!(
        (project.code.as_str(), project.name.as_str()),
        ("BND", "번들")
    );
    assert_eq!(repo.storage, "server");
    assert_eq!(repo.remote_url, origin.to_string_lossy());
    for r in ["main", "v1"] {
        assert_eq!(sh(&origin, &["rev-parse", r]), sh(&src, &["rev-parse", r]));
    }
    assert_eq!(sh(&origin, &["symbolic-ref", "HEAD"]), "refs/heads/main");
    assert_eq!(
        sh(&origin, &["config", "receive.denyNonFastForwards"]),
        "true"
    );
    assert_eq!(sh(&origin, &["remote"]), "");
    assert!(!sh(&origin, &["log", "--format=%s", "main"]).contains("init syncdoc"));
    assert_eq!(
        repo.last_processed_commit.as_deref(),
        Some(sh(&origin, &["rev-parse", "main"]).as_str())
    );
    let status: String =
        sqlx::query_scalar("SELECT status FROM documents WHERE doc_id = 'BND-PRD-001'")
            .fetch_one(&mut *s.db)
            .await
            .expect("문서");
    assert_eq!(status, "approved");
}

/// UC-A1 1c2 — 번들 아님·main 없음 → bundle-invalid, 원본·작업 사본·행 없음. 코드 형식·중복
#[tokio::test]
async fn import_bundle_refuses_bad_bundles_and_leaves_nothing() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "u").await;
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    let reason = |r: Result<_, Problem>| match r {
        Err(Problem::BundleInvalid { reason }) => reason,
        other => panic!("{:?}", other.map(|_: (_, _)| ())),
    };
    assert_eq!(
        reason(
            s.import_bundle(&db.pool, "BAD", "x", &u, b"not a bundle")
                .await
        ),
        "번들 파일이 아니거나 깨졌다"
    );
    assert!(!p.origins.join("BAD.git").exists());
    let trunk = bundle(tmp.path(), "trunk");
    assert_eq!(
        reason(s.import_bundle(&db.pool, "BAD", "x", &u, &trunk).await),
        "main 가지가 없다"
    );
    assert!(!p.origins.join("BAD.git").exists() && !p.repos.join("BAD").exists());
    assert!(matches!(s.get("BAD").await, Err(Problem::NotFound { .. })));
    assert!(matches!(
        s.import_bundle(&db.pool, "bad", "x", &u, b"").await,
        Err(Problem::ProjectCodeInvalid { .. })
    ));
    s.init_project(&db.pool, "DUP", "x", &u, false, Storage::Server)
        .await
        .expect("만들기");
    assert!(matches!(
        s.import_bundle(&db.pool, "DUP", "x", &u, b"").await,
        Err(Problem::ProjectCodeConflict { .. })
    ));
}

/// L16 rehome — 다른 자리를 가리키는 행은 이 자리로, 없는 작업 사본은 다시 만들고, 원본이 없는 행은 건너뛴다
#[tokio::test]
async fn rehome_fixes_paths_and_reclones_missing_workdirs() {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시");
    let p = places(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let mut s = ProjectService {
        db: &mut c,
        repos: &p,
    };
    for code in ["RHA", "RHB", "RHC", "RHD"] {
        s.init_project(&db.pool, code, "자리", &u, false, Storage::Server)
            .await
            .expect("만들기");
    }
    assert!(
        s.rehome().await.expect("맞는 자리").is_empty(),
        "맞으면 그대로"
    );
    // RHA — 다른 데이터 자리(Docker)의 경로 · RHB — 작업 사본이 없다 · RHC — 원본이 없다
    sqlx::query(
        "UPDATE repositories SET remote_url = '/var/syncdoc/origins/RHA.git', workdir_path = '/var/syncdoc/repos/RHA' \
         WHERE project_id = (SELECT id FROM projects WHERE code = 'RHA')",
    )
    .execute(&mut *s.db)
    .await
    .unwrap();
    std::fs::remove_dir_all(p.repos.join("RHA")).unwrap();
    std::fs::remove_dir_all(p.repos.join("RHB")).unwrap();
    std::fs::remove_dir_all(p.repos.join("RHC")).unwrap();
    p.git.close_all().await; // 윈도는 열린 팩이 있으면 못 지운다
    std::fs::remove_dir_all(p.origins.join("RHC.git")).unwrap();
    // RHD — 옛 판(0.1·0.2)이 만든 clone
    std::fs::remove_dir_all(p.repos.join("RHD")).unwrap();
    sh(
        tmp.path(),
        &[
            "clone",
            "-q",
            p.origins.join("RHD.git").to_str().unwrap(),
            p.repos.join("RHD").to_str().unwrap(),
        ],
    );
    let made = s.rehome().await.expect("맞추기");
    assert_eq!(made, ["RHA", "RHB", "RHD"]);
    let (_, repo) = s.get("RHA").await.unwrap();
    assert_eq!(repo.remote_url, p.origins.join("RHA.git").to_string_lossy());
    assert_eq!(repo.workdir_path, p.repos.join("RHA").to_string_lossy());
    // 원본 main의 docs/specs 폴더 — git이 아니다(카드 L19)
    for code in ["RHB", "RHD"] {
        let w = p.repos.join(code);
        assert!(w.join("docs/specs/README.md").is_file(), "{code}");
        assert!(!w.join(".git").exists(), "{code}");
    }
    assert!(!p.repos.join("RHC").exists());
}
