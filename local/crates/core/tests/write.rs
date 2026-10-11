//! SYNC-MS-017(L9)·MS-014(L9)·MS-015 inbound_of_document 테스트 관점 — 시험 DB · 임시 데이터 자리 · 진짜 git.
//! 상태 바꾸기·되돌리기·휴지통 넣기·되살리기·완전 삭제

mod support;

use std::path::Path;
use std::process::Command;

use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline::{self, SaveInput};
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::reference::service::ReferenceService;
use syncdoc_core::spec::SpecService;
use syncdoc_core::types::{Author, AuthorKind, DocStatus, Entry, Storage};

const CODE: &str = "LW";

/// 경고 없는 PRD(필수 절이 다 있다)
const PRD: &str = "# 쓰기 시험\n\n## 1. 목표\n\n#### G1 목표\n한 줄.\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명.\n\n#### R2 둘째 기능\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n";
const SCN: &str = "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LW-PRD-001]\n---\n# 시나리오\n\n## 1. 페르소나\n\n#### P1 사람\n누구.\n\n## 2. 시나리오\n\n#### S1 첫 흐름\n근거: [[LW-PRD-001#R1]] · [[LW-PRD-001#R2]]\n\n## 3. 대응표\n";

struct Env {
    db: support::TestDb,
    _tmp: tempfile::TempDir,
    repos: ServerRepos,
    user: UserRow,
}

impl Env {
    fn agent(&self) -> Author {
        Author {
            kind: AuthorKind::Agent,
            user: self.user.clone(),
            instructed_by: Some(self.user.clone()),
            via: Entry::Mcp,
        }
    }

    fn human(&self, via: Entry) -> Author {
        Author {
            kind: AuthorKind::Human,
            user: self.user.clone(),
            instructed_by: None,
            via,
        }
    }

    async fn create(&self, doc_type: &str, body: &str) {
        pipeline::save_pipeline(
            &self.db.pool,
            &self.repos,
            SaveInput {
                entry: Entry::Mcp,
                doc_id: None,
                doc_type: Some(doc_type.into()),
                body: body.into(),
                expected_version: None,
                project_code: Some(CODE.into()),
                author: self.agent(),
                message: format!("{doc_type} 만들기"),
                confirm_item_deletion: false,
                reason: None,
                restore: false,
                read_first: true,
            },
        )
        .await
        .expect("만들기");
    }

    async fn update(&self, doc_id: &str, body: &str, expected: i64) {
        pipeline::save_pipeline(
            &self.db.pool,
            &self.repos,
            SaveInput {
                entry: Entry::Mcp,
                doc_id: Some(doc_id.into()),
                doc_type: None,
                body: body.into(),
                expected_version: Some(expected),
                project_code: None,
                author: self.agent(),
                message: "고침".into(),
                confirm_item_deletion: true,
                reason: None,
                restore: false,
                read_first: true,
            },
        )
        .await
        .expect("고치기");
    }

    async fn conn(&self) -> sqlx::pool::PoolConnection<sqlx::Postgres> {
        self.db.pool.acquire().await.expect("연결")
    }

    async fn body(&self, doc_id: &str) -> String {
        let mut c = self.conn().await;
        SpecService { db: &mut c }
            .get_document(doc_id)
            .await
            .expect("문서")
            .body
    }

    fn origin(&self) -> std::path::PathBuf {
        self.repos.origins.join(format!("{CODE}.git"))
    }
}

fn git(cwd: &Path, args: &[&str]) -> (bool, String) {
    let out = Command::new("git")
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("git");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).trim().to_string(),
    )
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

async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut tx = db.pool.begin().await.expect("트랜잭션");
    let u = user(&mut tx, "writer").await;
    ProjectService {
        db: &mut tx,
        repos: &repos,
    }
    .init_project(CODE, "쓰기 시험", &u, false, Storage::Server)
    .await
    .expect("프로젝트");
    tx.commit().await.expect("커밋");
    let e = Env {
        db,
        _tmp: tmp,
        repos,
        user: u,
    };
    e.create("PRD", PRD).await;
    e
}

async fn count(c: &mut PgConnection, sql: &str) -> i64 {
    sqlx::query_scalar::<_, i64>(sqlx::AssertSqlSafe(sql.to_string()))
        .fetch_one(c)
        .await
        .expect(sql)
}

#[tokio::test]
async fn change_status_approves_blocks_and_toggles_back() {
    let e = env().await;
    let d = pipeline::change_status(
        &e.db.pool,
        &e.repos,
        "LW-PRD-001",
        DocStatus::Approved,
        &e.human(Entry::WebStatus),
        Some("다 읽음"),
    )
    .await
    .expect("완료로");
    assert_eq!(d.summary.status, "approved");
    assert_eq!(d.summary.current_version_no, 1);
    let (_, file) = git(
        &e.origin(),
        &["show", "main:docs/specs/02-PRD/LW-PRD-001.md"],
    );
    assert!(file.contains("status: approved\n"));
    let (_, msg) = git(&e.origin(), &["log", "-1", "--format=%B", "main"]);
    assert_eq!(msg, "status(LW-PRD-001): draft → approved\n\n다 읽음");
    let mut c = e.conn().await;
    let row: (String, String, Option<String>, bool) = sqlx::query_as(
        "SELECT to_status, via, reason, commit_hash IS NOT NULL FROM status_changes",
    )
    .fetch_one(&mut *c)
    .await
    .expect("상태 변경");
    assert_eq!(
        row,
        (
            "approved".into(),
            "web".into(),
            Some("다 읽음".into()),
            true
        )
    );
    assert_eq!(count(&mut c, "SELECT count(*) FROM versions").await, 1);
    drop(c);
    // 같은 상태 → 커밋 없음
    let (_, before) = git(&e.origin(), &["rev-parse", "main"]);
    pipeline::change_status(
        &e.db.pool,
        &e.repos,
        "LW-PRD-001",
        DocStatus::Approved,
        &e.agent(),
        None,
    )
    .await
    .expect("그대로");
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]).1, before);
    // 내리기는 막지 않는다 — 에이전트면 via=mcp
    pipeline::change_status(
        &e.db.pool,
        &e.repos,
        "LW-PRD-001",
        DocStatus::Draft,
        &e.agent(),
        None,
    )
    .await
    .expect("초안으로");
    let mut c = e.conn().await;
    assert_eq!(
        count(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE via = 'mcp'"
        )
        .await,
        1
    );
    drop(c);
    // 끊어진 참조가 있는 문서 → status-blocked(ref.missing)
    e.create(
        "SCN",
        &SCN.replace("[[LW-PRD-001#R2]]", "[[LW-PRD-009#R1]]"),
    )
    .await;
    match pipeline::change_status(
        &e.db.pool,
        &e.repos,
        "LW-SCN-001",
        DocStatus::Approved,
        &e.agent(),
        None,
    )
    .await
    {
        Err(Problem::StatusBlocked { warnings, .. }) => {
            assert!(
                warnings.contains(&"ref.missing: LW-PRD-009#R1".to_string()),
                "{warnings:?}"
            );
        }
        other => panic!("{other:?}"),
    }
}

#[tokio::test]
async fn revert_writes_the_old_body_as_a_new_version() {
    let e = env().await;
    let v1 = e.body("LW-PRD-001").await;
    e.update("LW-PRD-001", &v1.replace("설명.", "고친 설명."), 1)
        .await;
    let r = pipeline::revert(&e.db.pool, &e.repos, "LW-PRD-001", 1, &e.user, false)
        .await
        .expect("되돌리기");
    assert_eq!((r.version_no, r.next_step), (3, None));
    assert_eq!(e.body("LW-PRD-001").await, v1);
    assert!(matches!(
        pipeline::revert(&e.db.pool, &e.repos, "LW-PRD-001", 3, &e.user, false).await,
        Err(Problem::AlreadyCurrent)
    ));
    assert!(matches!(
        pipeline::revert(&e.db.pool, &e.repos, "LW-PRD-001", 9, &e.user, false).await,
        Err(Problem::NotFound { resource, .. }) if resource == "version"
    ));
    let mut c = e.conn().await;
    let via: String =
        sqlx::query_scalar("SELECT via || ':' || author_kind FROM versions WHERE version_no = 3")
            .fetch_one(&mut *c)
            .await
            .expect("판");
    assert_eq!(via, "web:human");
}

#[tokio::test]
async fn trash_restore_and_purge_round_trip() {
    let e = env().await;
    e.create("SCN", SCN).await;
    let before = e.body("LW-PRD-001").await;
    // 확인 없이 → 끊어질 것을 담아 묻는다
    match pipeline::trash_document(&e.db.pool, &e.repos, "LW-PRD-001", &e.agent(), false).await {
        Err(Problem::DocumentDeletionNeedsConfirm {
            title,
            version_count,
            inbound_refs,
            ..
        }) => {
            assert_eq!((title.as_str(), version_count), ("쓰기 시험", 1));
            assert_eq!(
                inbound_refs,
                ["LW-SCN-001", "LW-SCN-001#S1", "LW-SCN-001#S1"]
            );
        }
        other => panic!("{other:?}"),
    }
    let t = pipeline::trash_document(&e.db.pool, &e.repos, "LW-PRD-001", &e.agent(), true)
        .await
        .expect("휴지통");
    assert_eq!(t.broken_refs, 2);
    assert_eq!(
        t.next_step,
        "LW-PRD-001 휴지통에 넣음 — 끊어진 참조 2. 사람에게 알리고 멈춘다"
    );
    assert!(
        !git(
            &e.origin(),
            &["cat-file", "-e", "main:docs/specs/02-PRD/LW-PRD-001.md"]
        )
        .0
    );
    let mut c = e.conn().await;
    assert_eq!(
        count(
            &mut c,
            r#"SELECT count(*) FROM "references" WHERE is_missing"#
        )
        .await,
        2
    );
    let last: Option<String> = sqlx::query_scalar("SELECT last_processed_commit FROM repositories")
        .fetch_one(&mut *c)
        .await
        .expect("처리 지점");
    assert_eq!(last.as_deref(), Some(t.commit_hash.as_str()));
    drop(c);
    assert!(matches!(
        pipeline::trash_document(&e.db.pool, &e.repos, "LW-PRD-001", &e.agent(), true).await,
        Err(Problem::DocumentTrashed { .. })
    ));
    assert!(matches!(
        pipeline::change_status(
            &e.db.pool,
            &e.repos,
            "LW-PRD-001",
            DocStatus::Approved,
            &e.agent(),
            None
        )
        .await,
        Err(Problem::DocumentTrashed { .. })
    ));
    // 완전 삭제는 남이 아직 가리키면 안 된다 — 미존재는 안 센다(SCN의 upstream 문서 참조는 남아 있다)
    match pipeline::purge_document(
        &e.db.pool,
        &e.repos,
        "LW-PRD-001",
        &e.human(Entry::WebStatus),
    )
    .await
    {
        Err(Problem::DocumentHasHistory { inbound_refs }) => {
            assert_eq!(inbound_refs, ["LW-SCN-001"])
        }
        other => panic!("{other:?}"),
    }
    // 되살리기 → 직전 내용으로 새 판, 끊긴 참조가 다시 이어진다
    let r = pipeline::restore_document(&e.db.pool, &e.repos, "LW-PRD-001", &e.agent())
        .await
        .expect("되살리기");
    assert_eq!(r.version_no, 2);
    assert!(r.next_step.is_some());
    assert_eq!(e.body("LW-PRD-001").await, before);
    let mut c = e.conn().await;
    assert_eq!(
        count(
            &mut c,
            r#"SELECT count(*) FROM "references" WHERE is_missing"#
        )
        .await,
        0
    );
    assert_eq!(
        count(&mut c, "SELECT count(*) FROM items WHERE is_deleted").await,
        0
    );
    drop(c);
    assert!(matches!(
        pipeline::restore_document(&e.db.pool, &e.repos, "LW-PRD-001", &e.agent()).await,
        Err(Problem::DocumentNotTrashed)
    ));
    assert!(matches!(
        pipeline::purge_document(
            &e.db.pool,
            &e.repos,
            "LW-PRD-001",
            &e.human(Entry::WebStatus)
        )
        .await,
        Err(Problem::DocumentNotTrashed)
    ));
    // SCN을 넣고 지운다 — 아무도 안 가리킨다. 그 번호는 다시 발급된다
    pipeline::trash_document(&e.db.pool, &e.repos, "LW-SCN-001", &e.agent(), true)
        .await
        .expect("휴지통");
    pipeline::purge_document(
        &e.db.pool,
        &e.repos,
        "LW-SCN-001",
        &e.human(Entry::WebStatus),
    )
    .await
    .expect("완전 삭제");
    let mut c = e.conn().await;
    assert_eq!(
        count(
            &mut c,
            "SELECT count(*) FROM documents WHERE doc_id = 'LW-SCN-001'"
        )
        .await,
        0
    );
    let pid: i32 = sqlx::query_scalar("SELECT id FROM projects")
        .fetch_one(&mut *c)
        .await
        .expect("프로젝트");
    assert_eq!(
        SpecService { db: &mut c }
            .issue_doc_id(pid, CODE, "SCN")
            .await
            .expect("발급"),
        "LW-SCN-001"
    );
    let prd: i32 = sqlx::query_scalar("SELECT id FROM documents WHERE doc_id = 'LW-PRD-001'")
        .fetch_one(&mut *c)
        .await
        .expect("PRD");
    assert!(
        ReferenceService { db: &mut c }
            .inbound_of_document(prd)
            .await
            .expect("들어오는 것")
            .is_empty()
    );
}
