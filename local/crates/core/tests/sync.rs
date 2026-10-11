//! 카드 L11 테스트 관점 — 서버 저장소에 민 것이 문서가 된다(MS-017 process_commit·rebuild·upload_code·catch_up,
//! MS-014 save의 재구축·상태 커밋 갈래, MS-013 동기화·재구축 위임). 시험 DB · 임시 데이터 자리 · 진짜 git

mod support;

use std::path::{Path, PathBuf};
use std::process::Command;

use sqlx::{PgConnection, PgPool};
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline::{self, SaveInput};
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::spec::SpecService;
use syncdoc_core::types::{Author, AuthorKind, DocStatus, Entry, SaveResult, Storage};

const CODE: &str = "LS";

/// 항목 둘(R1·R2)인 PRD — frontmatter 없이 보내면 서버가 채운다
const PRD: &str = "# 따라잡기 시험\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명.\n\n#### R2 둘째 기능\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n";

struct Env {
    db: support::TestDb,
    tmp: tempfile::TempDir,
    repos: ServerRepos,
    user: UserRow,
}

impl Env {
    fn pool(&self) -> &PgPool {
        &self.db.pool
    }

    fn workdir(&self) -> PathBuf {
        self.repos.repos.join(CODE)
    }

    fn origin(&self) -> PathBuf {
        self.repos.origins.join(format!("{CODE}.git"))
    }

    fn author(&self, via: Entry) -> Author {
        Author {
            kind: AuthorKind::Agent,
            user: self.user.clone(),
            instructed_by: Some(self.user.clone()),
            via,
        }
    }

    async fn create(&self, doc_type: &str, body: &str) -> SaveResult {
        pipeline::save_pipeline(
            self.pool(),
            &self.repos,
            SaveInput {
                entry: Entry::Mcp,
                doc_id: None,
                doc_type: Some(doc_type.into()),
                body: body.into(),
                expected_version: None,
                project_code: Some(CODE.into()),
                author: self.author(Entry::Mcp),
                message: format!("{doc_type} 만들기"),
                confirm_item_deletion: false,
                reason: None,
                restore: false,
                read_first: true,
            },
        )
        .await
        .expect("만들기")
    }

    async fn conn(&self) -> sqlx::pool::PoolConnection<sqlx::Postgres> {
        self.pool().acquire().await.expect("연결")
    }

    /// 서버 저장소의 다른 사본 — 밖에서 git으로 미는 사람
    fn outside(&self) -> PathBuf {
        let dir = self.tmp.path().join("outside");
        if !dir.exists() {
            git(
                self.tmp.path(),
                &[
                    "clone",
                    "-q",
                    self.origin().to_str().expect("경로"),
                    dir.to_str().expect("경로"),
                ],
            );
        } else {
            git(&dir, &["pull", "-q", "origin", "main"]);
        }
        dir
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

/// 프로젝트 하나 — 서버 저장소와 골격 커밋(처리 지점이 그 커밋)
async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut tx = db.pool.begin().await.expect("트랜잭션");
    let u = user(&mut tx, "hoyoung").await;
    ProjectService {
        db: &mut tx,
        repos: &repos,
    }
    .init_project(CODE, "따라잡기 시험", &u, false, Storage::Server)
    .await
    .expect("프로젝트");
    tx.commit().await.expect("커밋");
    Env {
        db,
        tmp,
        repos,
        user: u,
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

async fn scalar_i64(c: &mut PgConnection, sql: &str) -> i64 {
    sqlx::query_scalar::<_, i64>(sqlx::AssertSqlSafe(sql.to_string()))
        .fetch_one(c)
        .await
        .expect(sql)
}

#[tokio::test]
async fn save_rebuild_numbers_by_remaining_versions_and_github_demotion_hash() {
    let e = env().await;
    let r = e.create("PRD", PRD).await;
    pipeline::change_status(
        e.pool(),
        &e.repos,
        &r.doc_id,
        DocStatus::Approved,
        &e.author(Entry::WebStatus),
        None,
    )
    .await
    .expect("완료로");
    let mut c = e.conn().await;
    let mut spec = SpecService { db: &mut c };
    let doc = spec.get_document(&r.doc_id).await.expect("문서");
    let github = e.author(Entry::Github);
    let vr = spec
        .validate(&doc.body, "PRD", Entry::Github, None)
        .await
        .expect("검증");
    // github이 완료 그대로 고치고 파이프라인이 강등 커밋을 민 것 — 그 해시의 상태 변경 행
    let body = doc.body.replace("설명.", "고친 설명.");
    let v = spec
        .save(
            &doc,
            &body,
            "c0ffee",
            &github,
            "밖",
            &[],
            &vr,
            false,
            Some("d00d"),
        )
        .await
        .expect("저장");
    assert_eq!(v.version_no, 2);
    let doc = spec.get_document(&r.doc_id).await.expect("문서");
    assert_eq!(doc.summary.status, "draft");
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE commit_hash = 'd00d' AND reason = '본문 수정으로 자동 강등'"
        )
        .await,
        1
    );
    // 재구축 번호 — 남은 판 수 + 1(현재 판이 아니다)
    sqlx::query("DELETE FROM versions WHERE version_no = 2")
        .execute(&mut *c)
        .await
        .expect("지우기");
    let mut spec = SpecService { db: &mut c };
    let doc = spec.get_document(&r.doc_id).await.expect("문서");
    let v = spec
        .save(&doc, &body, "beef", &github, "재구축", &[], &vr, true, None)
        .await
        .expect("저장");
    assert_eq!(v.version_no, 2);
}

#[tokio::test]
async fn mark_deleted_keeps_row_drafts_and_deletes_items() {
    let e = env().await;
    let r = e.create("PRD", PRD).await;
    let mut c = e.conn().await;
    let mut spec = SpecService { db: &mut c };
    let doc = spec.get_document(&r.doc_id).await.expect("문서");
    let pks = spec
        .mark_deleted(&doc, "abc123", &e.author(Entry::Github))
        .await
        .expect("삭제 반영");
    assert_eq!(pks.len(), 2);
    let doc = spec.get_document(&r.doc_id).await.expect("행은 남는다");
    assert_eq!(doc.summary.status, "draft");
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM documents WHERE has_convention_error AND convention_error_detail = 'file.deleted: abc123'"
        )
        .await,
        1
    );
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM items WHERE NOT is_deleted").await,
        0
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE reason = '파일 삭제됨' AND commit_hash = 'abc123' AND to_status = 'draft'"
        )
        .await,
        1
    );
}

#[tokio::test]
async fn clear_index_drops_versions_and_commit_status_rows_only() {
    let e = env().await;
    let r = e.create("PRD", PRD).await;
    pipeline::change_status(
        e.pool(),
        &e.repos,
        &r.doc_id,
        DocStatus::Approved,
        &e.author(Entry::WebStatus),
        None,
    )
    .await
    .expect("완료로");
    let mut c = e.conn().await;
    sqlx::query(
        "INSERT INTO status_changes (document_id, from_status, to_status, changed_by_user_id, via, reason, changed_at) \
         SELECT id, 'approved', 'draft', $1, 'mcp', '커밋 없음', now() FROM documents",
    )
    .bind(e.user.id)
    .execute(&mut *c)
    .await
    .expect("커밋 없는 행");
    let pid = scalar_i64(&mut c, "SELECT id::bigint FROM projects").await as i32;
    // 판을 가리키는 참조가 없을 때 — 참조는 부르는 쪽이 먼저 지운다
    sqlx::query("DELETE FROM \"references\"")
        .execute(&mut *c)
        .await
        .expect("참조");
    SpecService { db: &mut c }
        .clear_index(pid)
        .await
        .expect("비우기");
    assert_eq!(scalar_i64(&mut c, "SELECT count(*) FROM versions").await, 0);
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE commit_hash IS NOT NULL"
        )
        .await,
        0
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE commit_hash IS NULL"
        )
        .await,
        1
    );
    assert_eq!(scalar_i64(&mut c, "SELECT count(*) FROM items").await, 2);
}

#[tokio::test]
async fn mark_convention_error_replaces_the_three_columns() {
    use syncdoc_core::types::{ValidateResult, Violation};
    let e = env().await;
    let r = e.create("PRD", PRD).await;
    let mut c = e.conn().await;
    let mut spec = SpecService { db: &mut c };
    let id = spec.get_document(&r.doc_id).await.expect("문서").summary.id;
    let bad = ValidateResult {
        violations: vec![Violation {
            line: 2,
            rule: "frontmatter.doc_id".into(),
            message: "파일명 X ≠ 'Y'".into(),
        }],
        warnings: vec![],
    };
    spec.mark_convention_error(id, &bad).await.expect("오류");
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM documents WHERE has_convention_error AND convention_error_detail = 'frontmatter.doc_id: 파일명 X ≠ ''Y'''"
        )
        .await,
        1
    );
    SpecService { db: &mut c }
        .mark_convention_error(id, &ValidateResult::default())
        .await
        .expect("비움");
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM documents WHERE NOT has_convention_error AND convention_error_detail IS NULL AND incomplete_warnings IS NULL"
        )
        .await,
        1
    );
}
