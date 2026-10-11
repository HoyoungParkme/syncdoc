//! SYNC-MS-018(L8)·MS-014(L8)·MS-015(L8)·MS-013 asset_path 테스트 관점 — 시험 DB · 임시 데이터 자리 · 진짜 git.
//! 저장 파이프라인으로 문서를 쌓고 웹 읽기의 조회를 본다

mod support;

use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::pipeline::{self, SaveInput};
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::queries;
use syncdoc_core::reference::service::ReferenceService;
use syncdoc_core::spec::SpecService;
use syncdoc_core::types::{Author, AuthorKind, Entry, GraphScope, ProjectItem, Storage};

const CODE: &str = "LR";

const PRD: &str = "# 읽기 시험\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명.\n\n#### R2 둘째 기능\n설명.\n\n#### R3 외톨이\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n";
const SCN: &str = "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LR-PRD-001]\n---\n# 시나리오\n\n## 1. 페르소나\n\n## 2. 시나리오\n\n#### S1 첫 흐름\n근거: [[LR-PRD-001#R1]] · [[LR-PRD-001#R2]] · [[LR-PRD-009#R1]]\n\n## 3. 대응표\n\n표에서 [[LR-PRD-001#R1]] · [[LR-PRD-001]]\n";
const UC: &str = "# 유스케이스\n\n## 1. 액터\n\n## 2. 사용자 목표 수준 유스케이스\n\n#### UC-A1 첫 일\n근거 [[LR-SCN-001#S1]]\n\n## 3. 하위기능 수준 유스케이스\n\n## 4. 대응표\n";

struct Env {
    db: support::TestDb,
    tmp: tempfile::TempDir,
    repos: ServerRepos,
    user: UserRow,
}

impl Env {
    fn author(&self) -> Author {
        Author {
            kind: AuthorKind::Agent,
            user: self.user.clone(),
            instructed_by: Some(self.user.clone()),
            via: Entry::Mcp,
        }
    }

    async fn create(&self, doc_type: &str, body: &str) -> String {
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
                author: self.author(),
                message: format!("{doc_type} 만들기"),
                confirm_item_deletion: false,
            },
        )
        .await
        .expect("만들기")
        .doc_id
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
                author: self.author(),
                message: "고침".into(),
                confirm_item_deletion: true,
            },
        )
        .await
        .expect("고치기");
    }

    async fn conn(&self) -> sqlx::pool::PoolConnection<sqlx::Postgres> {
        self.db.pool.acquire().await.expect("연결")
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

/// PRD(R1·R2·R3) ← SCN(S1이 R1·R2와 없는 문서를, 대응표가 R1과 PRD 전체를) ← UC(UC-A1이 S1을)
async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut tx = db.pool.begin().await.expect("트랜잭션");
    let u = user(&mut tx, "reader").await;
    ProjectService {
        db: &mut tx,
        repos: &repos,
    }
    .init_project(CODE, "읽기 시험", &u, false, Storage::Server)
    .await
    .expect("프로젝트");
    tx.commit().await.expect("커밋");
    let e = Env {
        db,
        tmp,
        repos,
        user: u,
    };
    e.create("PRD", PRD).await;
    e.create("SCN", SCN).await;
    e.create("UC", UC).await;
    e
}

async fn pid(c: &mut PgConnection) -> i32 {
    sqlx::query_scalar("SELECT id FROM projects")
        .fetch_one(c)
        .await
        .expect("프로젝트")
}

#[tokio::test]
async fn project_detail_lists_recent_changes_with_names_and_db_sync_values() {
    let e = env().await;
    let prd = {
        let mut c = e.conn().await;
        SpecService { db: &mut c }
            .get_document("LR-PRD-001")
            .await
            .expect("문서")
            .body
    };
    e.update("LR-PRD-001", &prd.replace("설명.", "고친 설명."), 1)
        .await;
    let mut c = e.conn().await;
    sqlx::query("UPDATE repositories SET behind_by = 2")
        .execute(&mut *c)
        .await
        .expect("동기화 칸");
    let d = queries::project_detail(&mut c, &e.repos, CODE, &e.user)
        .await
        .expect("상세");
    let recent: Vec<_> = d
        .recent_changes
        .iter()
        .map(|v| (v.doc_id.as_str(), v.version_no))
        .collect();
    assert_eq!(
        recent,
        [
            ("LR-PRD-001", Some(2)),
            ("LR-UC-001", Some(1)),
            ("LR-SCN-001", Some(1)),
            ("LR-PRD-001", Some(1)),
        ]
    );
    let a = d.recent_changes[0].author_view.as_ref().expect("이름");
    assert_eq!(
        (
            a.kind.as_str(),
            a.user.as_ref().map(|u| u.github_login.as_str())
        ),
        ("agent", Some("reader"))
    );
    assert_eq!(d.behind_by, Some(2));
    assert!(d.last_processed_commit.is_some());
    assert_eq!(d.docs.len(), 3);
    assert!(d.docs.iter().all(|x| x.author.is_some()));
    assert_eq!(d.summary.code, CODE);
    let other = user(&mut c, "other").await;
    assert!(matches!(
        queries::project_detail(&mut c, &e.repos, CODE, &other).await,
        Err(Problem::NotFound { .. })
    ));
}

#[tokio::test]
async fn project_items_broken_refs_errors_and_incomplete() {
    let e = env().await;
    let mut c = e.conn().await;
    let broken = queries::project_items(&mut c, &e.repos, CODE, "broken_ref", &e.user)
        .await
        .expect("끊어진 참조");
    let got: Vec<_> = broken
        .iter()
        .map(|x| match x {
            ProjectItem::Broken(b) => (
                b.source.doc_id.clone(),
                b.source.item_id.clone(),
                b.raw_target.clone(),
            ),
            ProjectItem::Document(_) => panic!("문서가 왔다"),
        })
        .collect();
    assert_eq!(
        got,
        [(
            Some("LR-SCN-001".to_string()),
            Some("S1".to_string()),
            "LR-PRD-009#R1".to_string()
        )]
    );
    sqlx::query("UPDATE documents SET has_convention_error = true WHERE doc_id = 'LR-UC-001'")
        .execute(&mut *c)
        .await
        .expect("오류 표시");
    let errs = queries::project_items(&mut c, &e.repos, CODE, "convention_errors", &e.user)
        .await
        .expect("규약 오류");
    assert_eq!(errs.len(), 1);
    let inc = queries::project_items(&mut c, &e.repos, CODE, "incomplete", &e.user)
        .await
        .expect("미완성");
    assert!(
        inc.iter()
            .all(|x| matches!(x, ProjectItem::Document(d) if !d.incomplete_warnings.is_empty()))
    );
    assert!(matches!(
        queries::project_items(&mut c, &e.repos, CODE, "nope", &e.user).await,
        Err(Problem::Internal { .. })
    ));
}

#[tokio::test]
async fn graph_nodes_edges_isolated_and_approved_scope() {
    let e = env().await;
    let mut c = e.conn().await;
    let g = queries::graph_view(&mut c, &e.repos, CODE, &e.user, GraphScope::All)
        .await
        .expect("관계도");
    assert_eq!(g.project_name, "읽기 시험");
    // 문서 셋 + 항목(R1·R2·R3·S1·UC-A1)
    assert_eq!(g.nodes.len(), 8);
    assert_eq!(g.nodes[0].id, "LR-PRD-001");
    let r3 = g
        .nodes
        .iter()
        .find(|n| n.id == "LR-PRD-001#R3")
        .expect("R3");
    assert!(r3.isolated);
    let missing = g
        .edges
        .iter()
        .find(|x| x.raw_target == "LR-PRD-009#R1")
        .expect("미존재");
    assert!(missing.is_missing && missing.to.is_none());
    assert!(
        g.edges
            .iter()
            .any(|x| x.from_ == "LR-SCN-001" && x.to.as_deref() == Some("LR-PRD-001"))
    );
    // PRD만 완료 — 범위 밖으로 가는 간선은 없다
    sqlx::query("UPDATE documents SET status = 'approved' WHERE doc_id = 'LR-PRD-001'")
        .execute(&mut *c)
        .await
        .expect("완료");
    let a = queries::graph_view(&mut c, &e.repos, CODE, &e.user, GraphScope::Approved)
        .await
        .expect("관계도");
    assert!(a.nodes.iter().all(|n| n.doc_id == "LR-PRD-001"));
    assert!(a.edges.is_empty());
}

#[tokio::test]
async fn item_chain_is_a_closure_with_eleven_rows() {
    let e = env().await;
    let mut c = e.conn().await;
    let ch = queries::item_chain(&mut c, &e.repos, "LR-SCN-001", "S1", &e.user)
        .await
        .expect("체인");
    assert_eq!(ch.rows.len(), 11);
    assert_eq!((ch.upstream_count, ch.downstream_count), (2, 1));
    let row = |stage: usize| -> Vec<(String, String)> {
        ch.rows[stage - 1]
            .items
            .iter()
            .map(|i| (i.ref_.item_id.clone().unwrap_or_default(), i.role.clone()))
            .collect()
    };
    assert_eq!(row(3), [("S1".to_string(), "self".to_string())]);
    assert_eq!(row(4), [("UC-A1".to_string(), "downstream".to_string())]);
    // 같은 단계의 둘 — 파이썬 set 차례(작은 pk가 먼저인 작은 표)
    assert_eq!(
        row(2),
        [
            ("R1".to_string(), "upstream".to_string()),
            ("R2".to_string(), "upstream".to_string())
        ]
    );
    // UC-A1에서 보면 S1을 건너 R1·R2까지
    let ch = queries::item_chain(&mut c, &e.repos, "LR-UC-001", "UC-A1", &e.user)
        .await
        .expect("체인");
    assert_eq!((ch.upstream_count, ch.downstream_count), (3, 0));
    assert!(matches!(
        queries::item_chain(&mut c, &e.repos, "LR-SCN-001", "S9", &e.user).await,
        Err(Problem::NotFound { .. })
    ));
}

#[tokio::test]
async fn diff_counts_downstream_and_downstream_view_groups_by_target() {
    let e = env().await;
    let prd = {
        let mut c = e.conn().await;
        SpecService { db: &mut c }
            .get_document("LR-PRD-001")
            .await
            .expect("문서")
            .body
    };
    e.update(
        "LR-PRD-001",
        &prd.replace("#### R1 첫 기능\n설명.", "#### R1 첫 기능\n고친 설명.")
            .replace("## 5. 미결사항\n", "## 5. 미결사항\n\n#### R4 새것\n새.\n"),
        1,
    )
    .await;
    let mut c = e.conn().await;
    let d = queries::diff_with_impact(&mut c, &e.repos, "LR-PRD-001", 1, 2, &e.user)
        .await
        .expect("diff");
    let counts: Vec<_> = d
        .hunks
        .iter()
        .map(|h| (h.item_id.clone().unwrap_or_default(), h.downstream_count))
        .collect();
    // R1은 S1과 대응표가 가리킨다 · 새 항목은 0
    assert_eq!(counts, [("R1".to_string(), 2), ("R4".to_string(), 0)]);
    assert!(matches!(
        queries::diff_with_impact(&mut c, &e.repos, "LR-PRD-001", 1, 9, &e.user).await,
        Err(Problem::NotFound { resource, .. }) if resource == "version"
    ));
    let v = queries::downstream_view(&mut c, &e.repos, "LR-PRD-001", &e.user)
        .await
        .expect("추적표");
    let keys: Vec<&str> = v.by_item.keys().map(String::as_str).collect();
    assert_eq!(keys, ["R1", "R2", "(문서)"]);
    assert_eq!(v.by_item["R1"].len(), 2);
    // 출발 항목이면 raw_target이 비었다(파이썬과 같다), 출발 문서면 있다
    assert_eq!(v.by_item["R1"][0].raw_target, "");
    assert_eq!(v.by_item["R1"][1].raw_target, "LR-PRD-001#R1");
    assert_eq!(v.by_document.len(), 1);
    assert_eq!(
        (
            v.by_document[0].doc_id.as_str(),
            v.by_document[0].title.as_str()
        ),
        ("LR-SCN-001", "시나리오")
    );
    assert_eq!(v.by_document[0].items, ["(문서)", "R1", "R2"]);
}

#[tokio::test]
async fn versions_and_services_for_the_graph() {
    let e = env().await;
    let mut c = e.conn().await;
    let doc: i32 = sqlx::query_scalar("SELECT id FROM documents WHERE doc_id = 'LR-PRD-001'")
        .fetch_one(&mut *c)
        .await
        .expect("문서");
    // 커밋 있는 상태 변경(에이전트) · 커밋 없는 자동 강등(안 나온다)
    sqlx::query(
        "INSERT INTO status_changes (document_id, from_status, to_status, changed_by_user_id, via, reason, commit_hash, changed_at) \
         VALUES ($1, 'draft', 'approved', $2, 'mcp', 'r', 'abc', now() + interval '1 hour'), \
                ($1, 'approved', 'draft', $2, 'web', 'r', NULL, now() + interval '2 hour')",
    )
    .bind(doc)
    .bind(e.user.id)
    .execute(&mut *c)
    .await
    .expect("상태 변경");
    let rows = SpecService { db: &mut c }
        .list_versions("LR-PRD-001")
        .await
        .expect("이력");
    assert_eq!(rows.len(), 2);
    assert_eq!(
        (
            rows[0].version_no,
            rows[0].message.as_str(),
            rows[0].author.kind.as_str()
        ),
        (None, "status(LR-PRD-001): draft → approved", "agent")
    );
    assert_eq!(rows[1].version_no, Some(1));
    assert!(matches!(
        SpecService { db: &mut c }.list_versions("LR-PRD-404").await,
        Err(Problem::NotFound { .. })
    ));
    let p = pid(&mut c).await;
    let briefs = SpecService { db: &mut c }
        .list_items_by_project(p)
        .await
        .expect("목록");
    let ids: Vec<String> = briefs
        .iter()
        .map(|b| {
            format!(
                "{}{}",
                b.doc_id,
                b.item_id
                    .as_deref()
                    .map(|i| format!("#{i}"))
                    .unwrap_or_default()
            )
        })
        .collect();
    assert_eq!(
        ids,
        [
            "LR-PRD-001",
            "LR-SCN-001",
            "LR-UC-001",
            "LR-PRD-001#R1",
            "LR-PRD-001#R2",
            "LR-PRD-001#R3",
            "LR-SCN-001#S1",
            "LR-UC-001#UC-A1"
        ]
    );
    let pks = SpecService { db: &mut c }
        .resolve_items("LR-PRD-001", &["R3".into(), "R1".into(), "R9".into()])
        .await
        .expect("pk");
    assert_eq!(pks.len(), 2);
    assert!(pks[0] < pks[1]);
    let counts = ReferenceService { db: &mut c }
        .count_downstream(&pks)
        .await
        .expect("수");
    assert_eq!(counts.values().sum::<i64>(), 2);
    let missing = ReferenceService { db: &mut c }
        .missing_in_project(p)
        .await
        .expect("미존재");
    assert_eq!(missing.len(), 1);
    assert!(
        ReferenceService { db: &mut c }
            .references_among(&[], true)
            .await
            .expect("빈 것")
            .is_empty()
    );
}

#[tokio::test]
async fn asset_path_only_inside_specs_with_allowed_extensions() {
    let e = env().await;
    let specs = e.repos.repos.join(CODE).join("docs/specs");
    std::fs::create_dir_all(specs.join("assets")).expect("assets");
    std::fs::write(specs.join("assets/x.PNG"), b"\x89PNG").expect("그림");
    std::fs::write(e.tmp.path().join("secret.png"), b"s").expect("바깥");
    #[cfg(unix)]
    std::os::unix::fs::symlink(
        e.tmp.path().join("secret.png"),
        specs.join("assets/link.png"),
    )
    .expect("링크");
    let mut c = e.conn().await;
    let mut svc = ProjectService {
        db: &mut c,
        repos: &e.repos,
    };
    let got = svc
        .asset_path(CODE, "07-UI/../assets/x.PNG", &e.user)
        .await
        .expect("그림");
    assert!(got.ends_with("assets/x.PNG"));
    for bad in [
        "../../../secret.png",
        "02-PRD/LR-PRD-001.md",
        "assets/none.png",
        "",
        "assets/link.png",
    ] {
        match svc.asset_path(CODE, bad, &e.user).await {
            Err(Problem::NotFound { resource, id }) => {
                assert_eq!((resource.as_str(), id.as_str()), ("file", Some(bad)));
            }
            other => panic!("{bad}: {other:?}"),
        }
    }
    let other = user(&mut *svc.db, "other").await;
    assert!(matches!(
        svc.asset_path(CODE, "assets/x.PNG", &other).await,
        Err(Problem::NotFound { resource, .. }) if resource == "project"
    ));
}

#[tokio::test]
async fn trash_list_has_only_trashed_documents_newest_first() {
    let e = env().await;
    let mut c = e.conn().await;
    assert!(
        queries::trash_list(&mut c, &e.repos, CODE, &e.user)
            .await
            .expect("빈 휴지통")
            .is_empty()
    );
    sqlx::query(
        "UPDATE documents SET trashed_at = CASE doc_id WHEN 'LR-UC-001' THEN now() ELSE now() - interval '1 day' END \
         WHERE doc_id IN ('LR-UC-001', 'LR-SCN-001')",
    )
    .execute(&mut *c)
    .await
    .expect("휴지통");
    let t = queries::trash_list(&mut c, &e.repos, CODE, &e.user)
        .await
        .expect("휴지통");
    let ids: Vec<&str> = t.iter().map(|d| d.doc_id.as_str()).collect();
    assert_eq!(ids, ["LR-UC-001", "LR-SCN-001"]);
    assert!(
        t.iter()
            .all(|d| d.trashed_at.is_some() && d.author.is_some() && d.counts.is_empty())
    );
    let other = user(&mut c, "other").await;
    assert!(matches!(
        queries::trash_list(&mut c, &e.repos, CODE, &other).await,
        Err(Problem::NotFound { .. })
    ));
}
