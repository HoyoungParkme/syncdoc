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
                commit_hash: None,
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

#[tokio::test]
async fn reference_clear_drops_this_projects_references() {
    use syncdoc_core::reference::service::ReferenceService;
    let e = env().await;
    e.create("PRD", PRD).await;
    e.create(
        "SCN",
        "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LS-PRD-001]\n---\n# 시나리오\n\n## 1. 페르소나\n\n## 2. 시나리오\n\n#### S1 흐름\n근거: [[LS-PRD-001#R1]]\n\n## 3. 대응표\n",
    )
    .await;
    let mut c = e.conn().await;
    assert!(scalar_i64(&mut c, "SELECT count(*) FROM \"references\"").await > 0);
    let pid = scalar_i64(&mut c, "SELECT id::bigint FROM projects").await as i32;
    ReferenceService { db: &mut c }
        .clear(pid)
        .await
        .expect("비우기");
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM \"references\"").await,
        0
    );
    ReferenceService { db: &mut c }
        .clear(pid + 1)
        .await
        .expect("다른 프로젝트");
}

#[tokio::test]
async fn user_for_commit_is_always_the_local_user() {
    use syncdoc_core::account::service::AccountService;
    let e = env().await; // 환경의 사용자가 kind=local 행 하나
    let mut c = e.conn().await;
    for (mail, login) in [
        ("a@x", "a"),
        ("9+octo@users.noreply.github.com", "octo"),
        ("", ""),
    ] {
        let u = AccountService { db: &mut c }
            .user_for_commit(mail, login)
            .await
            .expect("사용자");
        assert_eq!(u.id, e.user.id);
    }
    // 로컬 사용자가 없으면 internal — 켤 때 둔다
    sqlx::query("UPDATE users SET kind = 'github'")
        .execute(&mut *c)
        .await
        .expect("바꾸기");
    assert!(matches!(
        AccountService { db: &mut c }
            .user_for_commit("a@x", "a")
            .await,
        Err(Problem::Internal { .. })
    ));
}

#[tokio::test]
async fn list_projects_is_everyones_by_code() {
    let e = env().await;
    let mut c = e.conn().await;
    let other = user(&mut c, "other").await;
    ProjectService {
        db: &mut c,
        repos: &e.repos,
    }
    .init_project("AB", "남의 것", &other, false, Storage::Server)
    .await
    .expect("남의 프로젝트");
    let codes: Vec<String> = ProjectService {
        db: &mut c,
        repos: &e.repos,
    }
    .list_projects()
    .await
    .expect("목록")
    .into_iter()
    .map(|(p, _)| p.code)
    .collect();
    assert_eq!(codes, ["AB", "LS"]);
}

fn prd_file(status: &str, text: &str) -> String {
    format!(
        "---\ndoc_id: LS-PRD-001\ntype: PRD\ntitle: 따라잡기 시험\nstatus: {status}\n---\n{}",
        PRD.replace("설명.", text)
    )
}

impl Env {
    async fn github(&self, doc_id: &str, body: &str, commit: &str) -> SaveResult {
        pipeline::save_pipeline(
            self.pool(),
            &self.repos,
            SaveInput {
                entry: Entry::Github,
                doc_id: Some(doc_id.into()),
                doc_type: Some("PRD".into()),
                body: body.into(),
                expected_version: None,
                project_code: Some(CODE.into()),
                author: Author {
                    kind: AuthorKind::Human,
                    user: self.user.clone(),
                    instructed_by: None,
                    via: Entry::Github,
                },
                message: "밖에서".into(),
                confirm_item_deletion: false,
                reason: None,
                restore: false,
                read_first: false,
                commit_hash: Some(commit.into()),
            },
        )
        .await
        .expect("github 저장")
    }
}

#[tokio::test]
async fn save_pipeline_github_saves_violations_and_pushes_only_the_demotion() {
    let e = env().await;
    let head0 = git(&e.origin(), &["rev-parse", "main"]);
    // 새 파일 — 위반(frontmatter 상태가 둘 밖)이 있어도 저장, 밀지 않는다, 처리 지점도 그대로
    let broken = prd_file("weird", "설명.");
    let r = e
        .github(
            "LS-PRD-001",
            &broken,
            "1111111111111111111111111111111111111111",
        )
        .await;
    assert_eq!((r.version_no, r.next_step.clone()), (1, None));
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]), head0);
    let mut c = e.conn().await;
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM documents WHERE has_convention_error"
        )
        .await,
        1
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            &format!("SELECT count(*) FROM repositories WHERE last_processed_commit = '{head0}'")
        )
        .await,
        1
    );
    // 완료 문서를 밖에서 완료 그대로 고침 → 초안과 강등 커밋 하나(등록한 사람), 상태 변경 행에 그 해시
    sqlx::query("UPDATE documents SET status = 'approved'")
        .execute(&mut *c)
        .await
        .expect("완료로");
    let r = e
        .github(
            "LS-PRD-001",
            &prd_file("approved", "고친 설명."),
            "2222222222222222222222222222222222222222",
        )
        .await;
    assert_eq!((r.version_no, r.status.as_str()), (2, "draft"));
    let demoted = git(&e.origin(), &["rev-parse", "main"]);
    assert_ne!(demoted, head0);
    assert_eq!(
        git(&e.origin(), &["log", "-1", "--format=%s%n%b%an"]),
        "status(LS-PRD-001): approved → draft\n본문 수정으로 자동 강등\nhoyoung 님"
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            &format!("SELECT count(*) FROM status_changes WHERE commit_hash = '{demoted}'")
        )
        .await,
        1
    );
    // 작성자가 스스로 frontmatter를 내려 민 것 → 강등 커밋 없음, 상태 변경 행 없음
    sqlx::query("UPDATE documents SET status = 'approved'")
        .execute(&mut *c)
        .await
        .expect("완료로");
    let r = e
        .github(
            "LS-PRD-001",
            &prd_file("draft", "또 고친 설명."),
            "3333333333333333333333333333333333333333",
        )
        .await;
    assert_eq!(r.status, "draft");
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]), demoted);
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM status_changes").await,
        1
    );
}

fn scn_file(doc_id: &str, refs: &str) -> String {
    format!(
        "---\ndoc_id: {doc_id}\ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LS-PRD-001]\n---\n# 시나리오\n\n## 1. 페르소나\n\n## 2. 시나리오\n\n#### S1 흐름\n근거: {refs}\n\n## 3. 대응표\n"
    )
}

fn write(dir: &Path, path: &str, text: &str) {
    let f = dir.join(path);
    std::fs::create_dir_all(f.parent().expect("부모")).expect("폴더");
    std::fs::write(f, text).expect("파일");
    git(dir, &["add", path]);
}

fn commit_push(dir: &Path, message: &str) -> String {
    git(dir, &["commit", "-q", "-m", message]);
    git(dir, &["push", "-q", "origin", "HEAD:main"]);
    git(dir, &["rev-parse", "HEAD"])
}

impl Env {
    async fn read_pending(&self) -> i64 {
        pipeline::read_pending(self.pool(), &self.repos, CODE, &self.user)
            .await
            .expect("밀린 커밋")
    }

    async fn processed(&self) -> String {
        let mut c = self.conn().await;
        sqlx::query_scalar::<_, String>("SELECT last_processed_commit FROM repositories")
            .fetch_one(&mut *c)
            .await
            .expect("처리 지점")
    }
}

#[tokio::test]
async fn outside_push_becomes_documents_in_stage_order_and_deletions_break_refs() {
    let e = env().await;
    let out = e.outside();
    write(
        &out,
        "docs/specs/03-SCN/LS-SCN-001.md",
        &scn_file("LS-SCN-001", "[[LS-PRD-001#R1]]"),
    );
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "설명."),
    );
    let head = commit_push(&out, "spec: PRD·SCN 한 커밋");
    assert_eq!(e.read_pending().await, 2);
    assert_eq!(e.processed().await, head);
    let mut c = e.conn().await;
    // 상위가 먼저 저장돼 하위의 참조가 미존재가 아니다
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM \"references\" WHERE is_missing"
        )
        .await,
        0
    );
    assert_eq!(scalar_i64(&mut c, "SELECT count(*) FROM versions").await, 2);
    // 같은 head를 다시 — 아무것도 안 한다
    assert_eq!(e.read_pending().await, 0);
    // 앱이 민 커밋은 거른다 — 판이 하나만 는다
    let r = e
        .create("UC", "# 유스케이스\n\n## 1. 액터\n\n## 2. 사용자 목표 수준 유스케이스\n\n## 3. 하위기능 수준 유스케이스\n\n## 4. 대응표\n")
        .await;
    assert_eq!(r.version_no, 1);
    assert_eq!(scalar_i64(&mut c, "SELECT count(*) FROM versions").await, 3);
    // 밖에서 PRD를 지운다 → 초안·file.deleted·하위 참조 끊김, 문서 행은 남는다
    let out = e.outside();
    git(&out, &["rm", "-q", "docs/specs/02-PRD/LS-PRD-001.md"]);
    let del = commit_push(&out, "PRD 지움");
    e.read_pending().await;
    assert_eq!(
        scalar_i64(
            &mut c,
            &format!("SELECT count(*) FROM documents WHERE doc_id = 'LS-PRD-001' AND convention_error_detail = 'file.deleted: {del}'")
        )
        .await,
        1
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM \"references\" WHERE is_missing"
        )
        .await,
        1
    );
    // 되살려 민다 → 오류가 풀리고 항목이 살아나고 참조가 다시 이어진다
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "다시 설명."),
    );
    commit_push(&out, "PRD 되살림");
    e.read_pending().await;
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM documents WHERE doc_id = 'LS-PRD-001' AND NOT has_convention_error").await,
        1
    );
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM items WHERE is_deleted").await,
        0
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM \"references\" WHERE is_missing"
        )
        .await,
        0
    );
}

#[tokio::test]
async fn trashed_deletes_skip_and_name_mismatch_marks_and_unknown_dir_stalls() {
    let e = env().await;
    let out = e.outside();
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "설명."),
    );
    commit_push(&out, "PRD");
    e.read_pending().await;
    let mut c = e.conn().await;
    // 휴지통 문서의 삭제 커밋 — 이미 반영돼 있다
    sqlx::query("UPDATE documents SET trashed_at = now()")
        .execute(&mut *c)
        .await
        .expect("휴지통");
    git(&out, &["rm", "-q", "docs/specs/02-PRD/LS-PRD-001.md"]);
    commit_push(&out, "trash(LS-PRD-001)");
    e.read_pending().await;
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM documents WHERE has_convention_error"
        )
        .await,
        0
    );
    // 파일 이름 ≠ frontmatter doc_id·type → 저장되고 규약 오류
    write(
        &out,
        "docs/specs/03-SCN/LS-SCN-007.md",
        &scn_file("LS-SCN-001", "[[#S1]]").replace("type: SCN", "type: UC"),
    );
    let h = commit_push(&out, "이름 어긋남");
    e.read_pending().await;
    assert_eq!(e.processed().await, h);
    let detail: String = sqlx::query_scalar(
        "SELECT convention_error_detail FROM documents WHERE doc_id = 'LS-SCN-007'",
    )
    .fetch_one(&mut *c)
    .await
    .expect("오류");
    assert!(
        detail.contains("frontmatter.doc_id: 파일명 LS-SCN-007 ≠ 'LS-SCN-001'"),
        "{detail}"
    );
    assert!(
        detail.contains("frontmatter.doc_id: 디렉터리 SCN ≠ type 'UC'"),
        "{detail}"
    );
    // 모르는 디렉터리 — 그 파일이 실패해 처리 지점이 그대로다
    write(&out, "docs/specs/BOGUS/LS-BOGUS-001.md", "x\n");
    commit_push(&out, "모르는 디렉터리");
    assert_eq!(e.read_pending().await, 0);
    assert_eq!(e.processed().await, h);
}

impl Env {
    async fn rebuild(&self) -> Result<syncdoc_core::types::RebuildResult, Problem> {
        let mut c = self.conn().await;
        pipeline::rebuild(&mut c, &self.repos, CODE).await
    }
}

#[tokio::test]
async fn rebuild_matches_repository_keeps_item_pks_and_is_idempotent() {
    let e = env().await;
    let out = e.outside();
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "설명."),
    );
    write(
        &out,
        "docs/specs/03-SCN/LS-SCN-001.md",
        &scn_file("LS-SCN-001", "[[LS-PRD-001#R1]] [[LS-PRD-009#R1]]"),
    );
    commit_push(&out, "spec: 둘");
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "고친 설명."),
    );
    commit_push(&out, "spec: PRD 고침");
    e.read_pending().await;
    pipeline::change_status(
        e.pool(),
        &e.repos,
        "LS-PRD-001",
        DocStatus::Approved,
        &e.author(Entry::WebStatus),
        None,
    )
    .await
    .expect("완료로");
    let mut c = e.conn().await;
    let pks_before = scalar_i64(&mut c, "SELECT sum(id)::bigint FROM items").await;
    let r = e.rebuild().await.expect("재구축");
    // PRD 판 둘 + SCN 하나 — status( 커밋은 판이 아니다
    assert_eq!((r.docs, r.items, r.versions), (2, 3, 3));
    assert_eq!(r.references, 3, "{r:?}"); // R1→, 없는 PRD-009, 문서 upstream
    assert!(r.convention_errors.is_empty(), "{:?}", r.convention_errors);
    assert_eq!(
        scalar_i64(&mut c, "SELECT sum(id)::bigint FROM items").await,
        pks_before
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE commit_hash IS NOT NULL"
        )
        .await,
        1
    );
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM documents WHERE doc_id = 'LS-PRD-001' AND status = 'approved'"
        )
        .await,
        1
    );
    let head = git(&e.origin(), &["rev-parse", "main"]);
    assert_eq!(e.processed().await, head);
    // 두 번 — 같다, 상태 변경 행이 쌓이지 않는다
    let r2 = e.rebuild().await.expect("다시");
    assert_eq!((r2.docs, r2.versions), (2, 3));
    assert_eq!(
        scalar_i64(
            &mut c,
            "SELECT count(*) FROM status_changes WHERE commit_hash IS NOT NULL"
        )
        .await,
        1
    );
}

#[tokio::test]
async fn rebuild_survives_deleted_then_recreated_and_rolls_back_on_failure() {
    let e = env().await;
    let out = e.outside();
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "설명."),
    );
    commit_push(&out, "spec: PRD");
    git(&out, &["rm", "-q", "docs/specs/02-PRD/LS-PRD-001.md"]);
    commit_push(&out, "trash(LS-PRD-001)");
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "다시."),
    );
    commit_push(&out, "spec: 다시");
    write(&out, "docs/specs/BOGUS/LS-X-001.md", "x\n");
    commit_push(&out, "모르는 디렉터리");
    let r = e.rebuild().await.expect("지운 커밋이 있어도 끝난다(#325)");
    assert_eq!((r.docs, r.versions), (1, 2));
    assert_eq!(r.convention_errors.len(), 1);
    assert_eq!(
        (
            r.convention_errors[0].doc_id.as_str(),
            r.convention_errors[0].detail.as_str()
        ),
        ("LS-X-001", "frontmatter.doc_id: 알 수 없는 디렉터리 BOGUS")
    );
    // 실패 → 되돌린다
    let mut c = e.conn().await;
    let versions = scalar_i64(&mut c, "SELECT count(*) FROM versions").await;
    sqlx::query("UPDATE repositories SET workdir_path = '/없는/자리'")
        .execute(&mut *c)
        .await
        .expect("자리");
    assert!(matches!(
        e.rebuild().await,
        Err(Problem::RebuildFailed { .. })
    ));
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM versions").await,
        versions
    );
    assert!(matches!(
        pipeline::rebuild(&mut c, &e.repos, "NOPE").await,
        Err(Problem::NotFound { .. })
    ));
}

#[tokio::test]
async fn repo_status_is_mine_from_db_and_hook_is_none() {
    let e = env().await;
    let mut c = e.conn().await;
    let other = user(&mut c, "other").await;
    let mut ps = ProjectService {
        db: &mut c,
        repos: &e.repos,
    };
    ps.init_project("AB", "남의 것", &other, false, Storage::Server)
        .await
        .expect("남의 것");
    let rows = ps.repo_status(&e.user).await.expect("상태");
    assert_eq!(rows.len(), 1);
    let r = &rows[0];
    assert_eq!(
        (r.code.as_str(), r.name.as_str(), r.storage.as_str()),
        ("LS", "따라잡기 시험", "server")
    );
    assert_eq!(
        (r.remote_url.clone(), r.hook.as_str(), r.behind_by),
        (None, "none", None)
    );
    assert!(r.last_processed_commit.is_some());
    sqlx::query("UPDATE repositories SET fetch_error = '받기 실패' WHERE project_id = (SELECT id FROM projects WHERE code = 'LS')")
        .execute(&mut *ps.db)
        .await
        .expect("오류");
    assert_eq!(
        ps.repo_status(&e.user).await.expect("상태")[0]
            .error
            .as_deref(),
        Some("받기 실패")
    );
    // 통지 — 늘 none
    let h = ps.ensure_hook("LS", &e.user).await.expect("통지");
    assert_eq!(
        (h.hook.as_str(), h.hook_error.as_deref(), h.created),
        ("none", Some("서버 저장소는 통지가 없다"), false)
    );
    assert!(matches!(
        ps.ensure_hook("AB", &e.user).await,
        Err(Problem::NotFound { .. })
    ));
}

#[tokio::test]
async fn sync_now_reads_pending_and_rebuild_index_syncs_readme_first() {
    let e = env().await;
    let out = e.outside();
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "설명."),
    );
    commit_push(&out, "spec: PRD");
    let mut c = e.conn().await;
    let mut ps = ProjectService {
        db: &mut c,
        repos: &e.repos,
    };
    let r = ps
        .sync_now(e.pool(), "LS", &e.user)
        .await
        .expect("지금 가져오기");
    assert_eq!(r.docs, 1);
    assert!(r.fetched_at.is_some());
    assert_eq!(
        ps.sync_now(e.pool(), "LS", &e.user).await.expect("또").docs,
        0
    );
    // 재구축 위임 — README가 같으면 커밋 없음
    let before = git(&e.origin(), &["rev-parse", "main"]);
    let r = ps.rebuild_index("LS", &e.user).await.expect("재구축");
    assert_eq!((r.readme_updated, r.docs, r.versions), (false, 1, 1));
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]), before);
    // README를 밖에서 바꿔 둔 뒤 → 맞추고 커밋 하나, 밀림 0으로 끝난다
    let out = e.outside();
    write(&out, "docs/specs/README.md", "옛 README\n");
    commit_push(&out, "README 바꿈");
    let r = ps.rebuild_index("LS", &e.user).await.expect("재구축");
    assert!(r.readme_updated);
    let head = git(&e.origin(), &["rev-parse", "main"]);
    assert_eq!(
        git(&e.origin(), &["log", "-1", "--format=%s"]),
        "chore(LS): README를 싱크독 규약 링크로"
    );
    assert_eq!(e.processed().await, head);
    // 남의 것 → not-found, 아무것도 안 바뀐다
    let stranger = user(&mut *ps.db, "stranger").await;
    assert!(matches!(
        ps.rebuild_index("LS", &stranger).await,
        Err(Problem::NotFound { .. })
    ));
    assert!(matches!(
        ps.sync_now(e.pool(), "LS", &stranger).await,
        Err(Problem::NotFound { .. })
    ));
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]), head);
}

#[tokio::test]
async fn upload_code_commits_once_refuses_paths_and_limits() {
    use indexmap::IndexMap;
    let e = env().await;
    let agent = e.author(Entry::Mcp);
    let up = |files: Vec<(&str, String)>, delete: Vec<&str>| {
        let files: IndexMap<String, String> =
            files.into_iter().map(|(p, c)| (p.to_string(), c)).collect();
        let delete: Vec<String> = delete.into_iter().map(String::from).collect();
        let (pool, repos, agent) = (e.pool().clone(), e.repos.clone(), agent.clone());
        async move {
            pipeline::upload_code(&pool, &repos, CODE, &files, &delete, "코드", &agent).await
        }
    };
    // 먼저 밖에서 민 명세 — 올린 뒤에도 문서로 살아 있다(DEV-19)
    let out = e.outside();
    write(
        &out,
        "docs/specs/02-PRD/LS-PRD-001.md",
        &prd_file("draft", "설명."),
    );
    commit_push(&out, "spec: PRD");
    let r = up(
        vec![("a.py", "a = 1\n".into()), ("src/b.py", "b = 2\n".into())],
        vec![],
    )
    .await
    .expect("올리기");
    assert!(r.changed && r.files == 2 && r.deleted == 0);
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]), r.commit);
    assert_eq!(
        git(&e.origin(), &["log", "-1", "--format=%an"]),
        "hoyoung 님"
    );
    assert_eq!(e.processed().await, r.commit);
    let mut c = e.conn().await;
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM documents").await,
        1
    );
    // 지우기 하나 + 같은 내용 하나
    let r2 = up(vec![("src/b.py", "b = 2\n".into())], vec!["a.py"])
        .await
        .expect("지우기");
    assert!(r2.changed && r2.deleted == 1);
    let r3 = up(vec![("src/b.py", "b = 2\n".into())], vec![])
        .await
        .expect("같다");
    assert!(!r3.changed);
    assert_eq!(r3.commit, r2.commit);
    // 한도
    match up(vec![("big.txt", "x".repeat(5 * 1024 * 1024 + 1))], vec![]).await {
        Err(Problem::UploadTooLarge { size, count, .. }) => {
            assert_eq!((size, count), (5 * 1024 * 1024 + 1, 1))
        }
        other => panic!("{other:?}"),
    }
    let many: Vec<(String, String)> = (0..501)
        .map(|i| (format!("f{i}.txt"), String::new()))
        .collect();
    match up(
        many.iter().map(|(p, c)| (p.as_str(), c.clone())).collect(),
        vec![],
    )
    .await
    {
        Err(Problem::UploadTooLarge { count, .. }) => assert_eq!(count, 501),
        other => panic!("{other:?}"),
    }
    // 거절 경로 여덟 — 전부 알리고 아무것도 올리지 않는다
    let head = git(&e.origin(), &["rev-parse", "main"]);
    match up(
        vec![
            ("/abs.py", "x".into()),
            ("../x.py", "x".into()),
            (".git/config", "x".into()),
            ("docs/specs/02-PRD/x.md", "x".into()),
            ("cfg/.env.local", "x".into()),
            ("keys/Server.PEM", "x".into()),
            ("a\\b.py", "x".into()),
            ("bin.dat", "a\0b".into()),
        ],
        vec!["  "],
    )
    .await
    {
        Err(Problem::UploadPathRefused { paths }) => {
            let reasons: Vec<&str> = paths.iter().map(|(_, r)| r.as_str()).collect();
            assert_eq!(
                reasons,
                [
                    "절대 경로",
                    "상위 경로(..)",
                    ".git",
                    "명세 경로 — create_document·update_document로 쓴다",
                    "비밀 꼴",
                    "비밀 꼴",
                    "역슬래시 — / 로 쓴다",
                    "빈 경로",
                    "글자가 아니다(이진)",
                ]
            );
        }
        other => panic!("{other:?}"),
    }
    assert_eq!(git(&e.origin(), &["rev-parse", "main"]), head);
}

#[tokio::test]
async fn moves_are_refused_on_the_local_edition() {
    let e = env().await;
    match pipeline::move_to_server(e.pool(), &e.repos, CODE, &e.user).await {
        Err(Problem::StorageMismatch { storage, detail }) => {
            assert_eq!(
                (storage.as_str(), detail.as_deref()),
                ("server", Some("이미 서버 저장이다"))
            );
        }
        other => panic!("{other:?}"),
    }
    match pipeline::move_to_github(e.pool(), &e.repos, CODE, &e.user, "https://github.com/a/b")
        .await
    {
        Err(Problem::StorageUnavailable { storage, enabled }) => {
            assert_eq!(
                (storage.as_str(), enabled),
                ("github", vec!["server".to_string()])
            );
        }
        other => panic!("{other:?}"),
    }
    let mut c = e.conn().await;
    let stranger = user(&mut c, "stranger").await;
    assert!(matches!(
        pipeline::move_to_server(e.pool(), &e.repos, CODE, &stranger).await,
        Err(Problem::NotFound { .. })
    ));
    assert!(matches!(
        pipeline::move_to_github(e.pool(), &e.repos, CODE, &stranger, "x").await,
        Err(Problem::NotFound { .. })
    ));
}
