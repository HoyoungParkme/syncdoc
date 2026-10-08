//! SYNC-MS-017·MS-014(L7)·MS-015(L7)·MS-018(L7) 테스트 관점 — 시험 DB · 임시 데이터 자리 · 진짜 git.
//! 저장 파이프라인을 끝에서 끝으로 돌리며 서비스·조회를 함께 본다

mod support;

use std::path::Path;
use std::process::Command;
use std::time::Duration;

use sqlx::{PgConnection, PgPool};
use syncdoc_core::account::model::UserRow;
use syncdoc_core::account::service::AccountService;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline::{self, SaveInput};
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::queries;
use syncdoc_core::reference::service::ReferenceService;
use syncdoc_core::spec::SpecService;
use syncdoc_core::types::{Author, AuthorKind, Entry, SaveResult, Storage};

const CODE: &str = "LP";

/// 항목 둘(R1·R2)인 PRD — frontmatter 없이 보내면 서버가 채운다
const PRD: &str = "# 저장 시험\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명.\n\n#### R2 둘째 기능\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n";

fn scn(refs: &str) -> String {
    format!(
        "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LP-PRD-001]\n---\n# 시나리오\n\n## 1. 페르소나\n\n## 2. 시나리오\n\n#### S1 첫 흐름\n근거: {refs}\n\n## 3. 대응표\n\n표에서 [[LP-PRD-001#R1]]\n"
    )
}

struct Env {
    db: support::TestDb,
    _tmp: tempfile::TempDir,
    repos: ServerRepos,
    user: UserRow,
}

impl Env {
    fn pool(&self) -> &PgPool {
        &self.db.pool
    }

    fn workdir(&self) -> std::path::PathBuf {
        self.repos.repos.join(CODE)
    }

    fn author(&self) -> Author {
        Author {
            kind: AuthorKind::Agent,
            user: self.user.clone(),
            instructed_by: Some(self.user.clone()),
            via: Entry::Mcp,
        }
    }

    async fn create(&self, doc_type: &str, body: &str) -> Result<SaveResult, Problem> {
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
                author: self.author(),
                message: format!("{doc_type} 만들기"),
                confirm_item_deletion: false,
            },
        )
        .await
    }

    async fn update(
        &self,
        doc_id: &str,
        body: &str,
        expected: i64,
        confirm: bool,
    ) -> Result<SaveResult, Problem> {
        pipeline::save_pipeline(
            self.pool(),
            &self.repos,
            SaveInput {
                entry: Entry::Mcp,
                doc_id: Some(doc_id.into()),
                doc_type: None,
                body: body.into(),
                expected_version: Some(expected),
                project_code: None,
                author: self.author(),
                message: format!("{doc_id} 고치기"),
                confirm_item_deletion: confirm,
            },
        )
        .await
    }

    async fn conn(&self) -> sqlx::pool::PoolConnection<sqlx::Postgres> {
        self.pool().acquire().await.expect("연결")
    }

    async fn body_of(&self, doc_id: &str) -> String {
        let mut c = self.conn().await;
        SpecService { db: &mut c }
            .get_document(doc_id)
            .await
            .expect("문서")
            .body
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
    .init_project(CODE, "저장 시험", &u, false, Storage::Server)
    .await
    .expect("프로젝트");
    tx.commit().await.expect("커밋");
    Env {
        db,
        _tmp: tmp,
        repos,
        user: u,
    }
}

fn git(cwd: &Path, args: &[&str]) -> String {
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

async fn scalar_i64(c: &mut PgConnection, sql: &str) -> i64 {
    sqlx::query_scalar::<_, i64>(sqlx::AssertSqlSafe(sql.to_string()))
        .fetch_one(c)
        .await
        .expect(sql)
}

#[tokio::test]
async fn create_issues_id_commits_and_extracts_references() {
    let e = env().await;
    let r = e.create("PRD", PRD).await.expect("만들기");
    assert_eq!((r.doc_id.as_str(), r.version_no), ("LP-PRD-001", 1));
    assert_eq!(r.status, "draft");
    let origin = e.repos.origins.join(format!("{CODE}.git"));
    assert_eq!(git(&origin, &["rev-parse", "main"]), r.commit_hash);
    assert_eq!(
        r.next_step.as_deref(),
        Some(
            "LP-PRD-001 v1 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)"
        )
    );
    // 파일은 {NN-TYPE}/{doc_id}.md, frontmatter는 서버가 채웠다
    let file = git(&origin, &["show", "main:docs/specs/02-PRD/LP-PRD-001.md"]);
    assert!(
        file.starts_with(
            "---\ndoc_id: LP-PRD-001\ntype: PRD\ntitle: 저장 시험\nstatus: draft\n---\n"
        )
    );
    assert!(
        r.warnings.iter().all(|w| w.starts_with("section.")),
        "{:?}",
        r.warnings
    );
    let mut c = e.conn().await;
    assert_eq!(scalar_i64(&mut c, "SELECT count(*) FROM items").await, 2);
    let via: String = sqlx::query_scalar("SELECT via || ':' || author_kind FROM versions")
        .fetch_one(&mut *c)
        .await
        .expect("판");
    assert_eq!(via, "mcp:agent");
    // 처리 지점이 앱 커밋만큼 앞섰다
    let last: Option<String> = sqlx::query_scalar("SELECT last_processed_commit FROM repositories")
        .fetch_one(&mut *c)
        .await
        .expect("저장소");
    assert_eq!(last.as_deref(), Some(r.commit_hash.as_str()));
    // 두 번째 같은 타입 → 002, 다음 단계 문서는 참조를 뽑는다(upstream·항목 안·항목 밖)
    drop(c);
    let s = e
        .create("SCN", &scn("[[LP-PRD-001#R2]] [[#S1]] [[LP-PRD-001#]]"))
        .await
        .expect("SCN");
    assert_eq!(s.doc_id, "LP-SCN-001");
    let mut c = e.conn().await;
    let rows: Vec<(Option<String>, String, bool, bool, bool)> = sqlx::query_as(
        r#"SELECT fi.item_id, r.raw_target, r.is_missing, r.to_item_id IS NOT NULL, r.to_document_id IS NOT NULL
           FROM "references" r LEFT JOIN items fi ON fi.id = r.from_item_id ORDER BY r.id"#,
    )
    .fetch_all(&mut *c)
    .await
    .expect("참조");
    assert_eq!(
        rows,
        [
            (
                Some("S1".into()),
                "LP-PRD-001#R2".into(),
                false,
                true,
                false
            ),
            (Some("S1".into()), "#S1".into(), false, true, false),
            (Some("S1".into()), "LP-PRD-001#".into(), false, false, true),
            (None, "LP-PRD-001#R1".into(), false, true, false),
            (None, "LP-PRD-001".into(), false, false, true),
        ]
    );
}

#[tokio::test]
async fn violations_leave_nothing_and_unknown_type_is_frontmatter_type() {
    let e = env().await;
    let before = git(&e.workdir(), &["rev-parse", "HEAD"]);
    let bad = PRD.replace("#### R2", "#### R02");
    match e.create("PRD", &bad).await {
        Err(Problem::ConventionViolation { violations, .. }) => {
            assert_eq!(violations[0].rule, "item.padding");
        }
        other => panic!("{other:?}"),
    }
    match e.create("XYZ", "본문").await {
        Err(Problem::ConventionViolation { violations, .. }) => {
            assert_eq!(violations[0].rule, "frontmatter.type");
            assert_eq!(violations[0].message, "type 'XYZ'");
        }
        other => panic!("{other:?}"),
    }
    // 빈 코드 → 파이썬 str(None)
    let r = pipeline::save_pipeline(
        e.pool(),
        &e.repos,
        SaveInput {
            entry: Entry::Mcp,
            doc_id: None,
            doc_type: Some("PRD".into()),
            body: PRD.into(),
            expected_version: None,
            project_code: Some(String::new()),
            author: e.author(),
            message: "m".into(),
            confirm_item_deletion: false,
        },
    )
    .await;
    assert!(
        matches!(&r, Err(Problem::NotFound { resource, id }) if resource == "project" && id == "None"),
        "{r:?}"
    );
    assert_eq!(git(&e.workdir(), &["rev-parse", "HEAD"]), before);
    let mut c = e.conn().await;
    assert_eq!(
        scalar_i64(&mut c, "SELECT count(*) FROM documents").await,
        0
    );
}

#[tokio::test]
async fn dom_class_needs_api_first() {
    let e = env().await;
    let body = "# 클래스 명세\n";
    match e.create("DOM", body).await {
        Err(Problem::PreconditionUnmet { requires, have }) => {
            assert_eq!(
                requires,
                "API 문서(REST 또는 MCP) — 클래스의 메서드는 API가 정한다"
            );
            assert!(have.is_empty());
        }
        other => panic!("{other:?}"),
    }
    // API 문서가 하나라도 있으면(휴지통 것까지) 선행조건을 넘는다 · ERD는 클래스 명세를 본다
    let mut c = e.conn().await;
    let pid: i32 = sqlx::query_scalar("SELECT id FROM projects")
        .fetch_one(&mut *c)
        .await
        .expect("프로젝트");
    sqlx::query(
        "INSERT INTO documents (project_id, doc_id, doc_type, status, current_body, current_version_no, trashed_at) \
         VALUES ($1, 'LP-API-001', 'API', 'draft', 'x', 1, now()), \
                ($1, 'LP-DOM-001', 'DOM', 'draft', E'---\\ntitle: 도메인 모델\\n---\\n', 1, NULL)",
    )
    .bind(pid)
    .execute(&mut *c)
    .await
    .expect("문서");
    let mut svc = SpecService { db: &mut c };
    assert_eq!(
        svc.precondition(pid, "DOM", "클래스 명세")
            .await
            .expect("선행"),
        None
    );
    let erd = svc.precondition(pid, "DOM", "ERD").await.expect("선행");
    assert_eq!(
        erd,
        Some((
            "DOM 클래스 명세 — 테이블은 엔티티 클래스에서 나온다".to_string(),
            vec!["LP-DOM-001".to_string()]
        ))
    );
    assert_eq!(
        svc.precondition(pid, "DOM", "도메인 모델")
            .await
            .expect("선행"),
        None
    );
    assert_eq!(
        svc.precondition(pid, "PRD", "클래스").await.expect("선행"),
        None
    );
    assert_eq!(
        svc.issue_doc_id(pid, CODE, "API").await.expect("발급"),
        "LP-API-002"
    );
}

#[tokio::test]
async fn update_conflict_delete_confirm_broken_then_restored() {
    let e = env().await;
    e.create("PRD", PRD).await.expect("PRD");
    e.create("SCN", &scn("[[LP-PRD-001#R2]]"))
        .await
        .expect("SCN");
    let prd = e.body_of("LP-PRD-001").await;
    // 낡은 판 → 현재 판과 본문
    match e.update("LP-PRD-001", &prd, 9, false).await {
        Err(Problem::VersionConflict {
            current_version,
            current_body,
        }) => assert_eq!((current_version, current_body), (1, prd.clone())),
        other => panic!("{other:?}"),
    }
    // 하위가 있는 R2를 지운다 → 확인 요청(하위는 이름으로)
    let without = prd.replace("#### R2 둘째 기능\n설명.\n\n", "");
    match e.update("LP-PRD-001", &without, 1, false).await {
        Err(Problem::ItemDeletionNeedsConfirm { deleted_items }) => {
            assert_eq!(deleted_items.len(), 1);
            assert_eq!(deleted_items[0].item_id, "R2");
            let d = &deleted_items[0].downstream[0];
            assert_eq!(
                (
                    d.doc_id.as_deref(),
                    d.item_id.as_deref(),
                    d.display_name.as_deref()
                ),
                (Some("LP-SCN-001"), Some("S1"), Some("첫 흐름"))
            );
        }
        other => panic!("{other:?}"),
    }
    let r = e
        .update("LP-PRD-001", &without, 1, true)
        .await
        .expect("확인 뒤");
    assert_eq!(r.version_no, 2);
    assert_eq!(r.warnings.last().map(String::as_str), Some("ref.broken: 1"));
    let mut c = e.conn().await;
    let v = queries::document_view(&mut c, &e.repos, "LP-SCN-001", &e.user)
        .await
        .expect("문서");
    assert_eq!(v.missing_refs, ["LP-PRD-001#R2"]);
    assert_eq!(v.items[0].missing_refs, ["LP-PRD-001#R2"]);
    assert_eq!(v.prev_doc_id.as_deref(), Some("LP-PRD-001"));
    assert_eq!(v.project_name, "저장 시험");
    let author = v.summary.author.expect("작성자");
    assert_eq!(
        (
            author.kind.as_str(),
            author.user.map(|u| u.github_login),
            author.via.as_str()
        ),
        ("agent", Some("hoyoung".to_string()), "mcp")
    );
    match queries::item_view(&mut c, &e.repos, "LP-PRD-001", "R2", &e.user).await {
        Err(Problem::ItemDeleted { deleted_at }) => assert!(deleted_at.is_some()),
        other => panic!("{other:?}"),
    }
    match queries::item_view(&mut c, &e.repos, "LP-PRD-001", "R9", &e.user).await {
        Err(Problem::NotFoundWithItems {
            id,
            available_items,
            ..
        }) => assert_eq!(
            (id.as_str(), available_items),
            ("LP-PRD-001#R9", vec!["R1".to_string()])
        ),
        other => panic!("{other:?}"),
    }
    drop(c);
    // 에이전트가 지운 ID를 다시 쓰면 재사용 — 되살리기는 웹의 몫(L9)
    match e.update("LP-PRD-001", &prd, 2, false).await {
        Err(Problem::ConventionViolation { violations, .. }) => {
            assert_eq!(violations[0].rule, "item.reused");
        }
        other => panic!("{other:?}"),
    }
    // 항목이 돌아오면(되살리기 흉내) resolve_missing이 다시 잇는다 · 다른 문서를 가리키는 것은 그대로
    let mut c = e.conn().await;
    sqlx::query("UPDATE items SET is_deleted = false, deleted_at = NULL WHERE item_id = 'R2'")
        .execute(&mut *c)
        .await
        .expect("되살림");
    let pid: i32 = sqlx::query_scalar("SELECT id FROM projects")
        .fetch_one(&mut *c)
        .await
        .expect("프로젝트");
    let mut refs = ReferenceService { db: &mut c };
    assert_eq!(
        refs.resolve_missing(pid, Some("LP-SCN-001"))
            .await
            .expect("잇기"),
        0
    );
    assert_eq!(
        refs.resolve_missing(pid, Some("LP-PRD-001"))
            .await
            .expect("잇기"),
        1
    );
    assert_eq!(refs.mark_missing(&[]).await.expect("빈 것"), 0);
    let v = queries::document_view(&mut c, &e.repos, "LP-SCN-001", &e.user)
        .await
        .expect("문서");
    assert!(v.missing_refs.is_empty(), "{:?}", v.missing_refs);
}

#[tokio::test]
async fn later_upstream_resolves_waiting_references() {
    let e = env().await;
    // 상위(PRD)보다 먼저 만든 SCN의 참조는 미존재 — PRD를 만들면 그 자리에서 풀린다(UC-S2 2a2)
    e.create("SCN", &scn("[[LP-PRD-001#R1]]"))
        .await
        .expect("SCN");
    let mut c = e.conn().await;
    assert_eq!(
        scalar_i64(
            &mut c,
            r#"SELECT count(*) FROM "references" WHERE is_missing"#
        )
        .await,
        3
    );
    drop(c);
    e.create("PRD", PRD).await.expect("PRD");
    let mut c = e.conn().await;
    assert_eq!(
        scalar_i64(
            &mut c,
            r#"SELECT count(*) FROM "references" WHERE is_missing"#
        )
        .await,
        0
    );
    // 같은 본문을 다시 → 커밋 없이 HEAD로 새 판, 참조는 그대로(같은 행)
    drop(c);
    let before = git(&e.workdir(), &["rev-parse", "HEAD"]);
    let body = e.body_of("LP-SCN-001").await;
    let mut c = e.conn().await;
    let ids: Vec<i32> = sqlx::query_scalar(r#"SELECT id FROM "references" ORDER BY id"#)
        .fetch_all(&mut *c)
        .await
        .expect("참조");
    drop(c);
    let r = e
        .update("LP-SCN-001", &body, 1, false)
        .await
        .expect("같은 본문");
    assert_eq!((r.version_no, r.commit_hash.as_str()), (2, before.as_str()));
    let mut c = e.conn().await;
    let again: Vec<i32> = sqlx::query_scalar(r#"SELECT id FROM "references" ORDER BY id"#)
        .fetch_all(&mut *c)
        .await
        .expect("참조");
    assert_eq!(ids, again);
}

#[tokio::test]
async fn references_view_names_targets_and_sources() {
    let e = env().await;
    e.create("PRD", PRD).await.expect("PRD");
    e.create(
        "SCN",
        &scn("[[LP-PRD-001#R1]] [[LP-PRD-001]] [[LP-UC-001#UC-A1]]"),
    )
    .await
    .expect("SCN");
    let mut c = e.conn().await;
    let up = queries::item_references_view(&mut c, &e.repos, "LP-SCN-001", "S1", &e.user)
        .await
        .expect("참조");
    let got: Vec<_> = up
        .upstream
        .iter()
        .map(|r| {
            (
                r.doc_id.as_deref(),
                r.item_id.as_deref(),
                r.raw_target.as_str(),
                r.is_missing,
            )
        })
        .collect();
    assert_eq!(
        got,
        [
            (Some("LP-PRD-001"), Some("R1"), "LP-PRD-001#R1", false),
            (Some("LP-PRD-001"), None, "LP-PRD-001", false),
            (None, None, "LP-UC-001#UC-A1", true),
        ]
    );
    // 항목 안과 항목 밖(대응표)에서 R1을 건 것 — 밖은 출발 문서(제목)로
    let down = queries::item_references_view(&mut c, &e.repos, "LP-PRD-001", "R1", &e.user)
        .await
        .expect("참조");
    let got: Vec<_> = down
        .downstream
        .iter()
        .map(|r| {
            (
                r.item_id.as_deref(),
                r.display_name.as_deref(),
                r.raw_target.as_str(),
            )
        })
        .collect();
    assert_eq!(
        got,
        [
            (Some("S1"), Some("첫 흐름"), "LP-PRD-001#R1"),
            (None, Some("시나리오"), "LP-PRD-001#R1"),
        ]
    );
    let list = queries::document_list(&mut c, &e.repos, CODE, &e.user, None, None)
        .await
        .expect("목록");
    let counts: Vec<_> = list
        .iter()
        .map(|d| (d.doc_id.as_str(), d.counts["broken_ref"]))
        .collect();
    assert_eq!(counts, [("LP-PRD-001", 0), ("LP-SCN-001", 1)]);
    assert!(
        queries::document_list(&mut c, &e.repos, CODE, &e.user, Some(2), Some("approved"))
            .await
            .expect("목록")
            .is_empty()
    );
    // 남의 것은 없는 것과 같다
    let other = user(&mut c, "other").await;
    assert!(matches!(
        queries::document_view(&mut c, &e.repos, "LP-PRD-001", &other).await,
        Err(Problem::NotFound { .. })
    ));
    let names = AccountService { db: &mut c }
        .users_by_ids(&[e.user.id, other.id, 9999])
        .await
        .expect("이름");
    assert_eq!(names.len(), 2);
    assert_eq!(names[&e.user.id].display_name, "hoyoung 님");
    let refs = ReferenceService { db: &mut c }
        .upstream_of_document(list[1].id, false)
        .await
        .expect("상위");
    assert!(refs.iter().all(|r| !r.is_missing));
}

#[tokio::test]
async fn approved_document_is_demoted_on_edit() {
    let e = env().await;
    e.create("PRD", PRD).await.expect("PRD");
    let approved = e
        .body_of("LP-PRD-001")
        .await
        .replace("status: draft", "status: approved");
    let mut c = e.conn().await;
    sqlx::query("UPDATE documents SET status = 'approved', current_body = $1")
        .bind(&approved)
        .execute(&mut *c)
        .await
        .expect("완료로");
    drop(c);
    let edited = approved.replace("설명.", "고친 설명.");
    let r = e
        .update("LP-PRD-001", &edited, 1, false)
        .await
        .expect("고치기");
    assert_eq!(r.status, "draft");
    let file = git(
        &e.workdir(),
        &["show", "HEAD:docs/specs/02-PRD/LP-PRD-001.md"],
    );
    assert!(file.contains("status: draft\n") && file.contains("고친 설명."));
    let mut c = e.conn().await;
    let why: String = sqlx::query_scalar(
        "SELECT from_status || '>' || to_status || ':' || via || ':' || reason FROM status_changes",
    )
    .fetch_one(&mut *c)
    .await
    .expect("상태 변경");
    assert_eq!(why, "approved>draft:mcp:본문 수정으로 자동 강등");
}

#[tokio::test]
async fn concurrent_saves_second_conflicts_and_trashed_is_refused() {
    let e = env().await;
    e.create("PRD", PRD).await.expect("PRD");
    let body = e.body_of("LP-PRD-001").await;
    let (ga, na) = (body.replace("설명.", "가."), body.replace("설명.", "나."));
    let (a, b) = tokio::join!(
        e.update("LP-PRD-001", &ga, 1, false),
        e.update("LP-PRD-001", &na, 1, false),
    );
    let oks = [&a, &b].iter().filter(|r| r.is_ok()).count();
    assert_eq!(oks, 1, "{a:?} {b:?}");
    assert!([&a, &b].iter().any(|r| matches!(
        r,
        Err(Problem::VersionConflict {
            current_version: 2,
            ..
        })
    )));
    let mut c = e.conn().await;
    sqlx::query("UPDATE documents SET trashed_at = '2026-10-08T01:02:03Z'")
        .execute(&mut *c)
        .await
        .expect("휴지통");
    drop(c);
    match e.update("LP-PRD-001", &body, 2, false).await {
        Err(Problem::DocumentTrashed { trashed_at }) => {
            assert_eq!(trashed_at, "2026-10-08T01:02:03+00:00");
        }
        other => panic!("{other:?}"),
    }
}

#[tokio::test]
async fn dropped_caller_still_finishes_the_save() {
    let e = env().await;
    // 첫 poll에서 작업을 띄우고 곧바로 버린다 — 저장은 끝까지 간다
    let _ = tokio::time::timeout(Duration::from_millis(1), e.create("PRD", PRD)).await;
    let mut done = false;
    for _ in 0..200 {
        let mut c = e.conn().await;
        if scalar_i64(&mut c, "SELECT count(*) FROM versions").await == 1 {
            done = true;
            break;
        }
        drop(c);
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    assert!(done, "저장이 끝나지 않았다");
    assert!(pipeline::wait_idle(Duration::from_secs(5)).await);
    let mut c = e.conn().await;
    let hash: String = sqlx::query_scalar("SELECT commit_hash FROM versions")
        .fetch_one(&mut *c)
        .await
        .expect("판");
    assert_eq!(git(&e.workdir(), &["rev-parse", "HEAD"]), hash);
}

#[tokio::test]
async fn outside_commit_is_card_l11_and_idle_wait_times_out() {
    let e = env().await;
    // 앱이 만든 프로젝트 → 밀린 것 없음, 확인 시각이 적힌다
    assert_eq!(
        pipeline::read_pending(e.pool(), &e.repos, CODE, &e.user)
            .await
            .expect("읽기"),
        0
    );
    let mut c = e.conn().await;
    let (behind, fetched): (Option<i32>, bool) =
        sqlx::query_as("SELECT behind_by, fetched_at IS NOT NULL FROM repositories")
            .fetch_one(&mut *c)
            .await
            .expect("저장소");
    assert_eq!((behind, fetched), (Some(0), true));
    drop(c);
    // 밖에서 서버 저장소에 민 커밋 → L11
    let outside = e._tmp.path().join("outside");
    let origin = e.repos.origins.join(format!("{CODE}.git"));
    git(
        e._tmp.path(),
        &[
            "clone",
            "-q",
            origin.to_str().expect("경로"),
            outside.to_str().expect("경로"),
        ],
    );
    std::fs::write(outside.join("x.txt"), "x").expect("파일");
    git(&outside, &["add", "x.txt"]);
    git(
        &outside,
        &[
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "밖",
        ],
    );
    git(&outside, &["push", "-q", "origin", "HEAD:main"]);
    assert!(matches!(
        e.create("PRD", PRD).await,
        Err(Problem::NotImplemented { card }) if card == "L11"
    ));
    // 쓰기 락을 쥐고 있으면 기다림이 끝나지 않는다
    let lock = pipeline::write_lock(CODE);
    assert!(std::sync::Arc::ptr_eq(&lock, &pipeline::write_lock(CODE)));
    assert!(!std::sync::Arc::ptr_eq(&lock, &pipeline::read_lock(CODE)));
    let held = lock.lock().await;
    assert!(!pipeline::wait_idle(Duration::from_millis(100)).await);
    drop(held);
    assert!(pipeline::wait_idle(Duration::from_secs(10)).await);
}
