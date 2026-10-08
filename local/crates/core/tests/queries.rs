//! SYNC-MS-018·MS-015·MS-014(list_by_project) 테스트 관점 — 시험 DB에 행을 넣어 요약을 본다

mod support;

use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::infra::git::Git;
use syncdoc_core::project::service::ServerRepos;
use syncdoc_core::queries::project_summary;
use syncdoc_core::reference::service::ReferenceService;
use syncdoc_core::spec::SpecService;
use syncdoc_core::types::DocStatus;

fn repos() -> ServerRepos {
    ServerRepos {
        git: Git {
            exe: "git".into(),
            global_config: "/dev/null".into(),
        },
        origins: "/nonexistent/origins".into(),
        repos: "/nonexistent/repos".into(),
        specs_url: "http://x/specs".into(),
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

async fn project(c: &mut PgConnection, code: &str, owner: i32) -> i32 {
    let id: i32 = sqlx::query_scalar(
        "INSERT INTO projects (code, name, owner_user_id) VALUES ($1, $1, $2) RETURNING id",
    )
    .bind(code)
    .bind(owner)
    .fetch_one(&mut *c)
    .await
    .expect("프로젝트");
    sqlx::query(
        "INSERT INTO repositories (project_id, storage, remote_url, workdir_path, registered_by_user_id) \
         VALUES ($1, 'server', '/o/x.git', '/r/x', $2)",
    )
    .bind(id)
    .bind(owner)
    .execute(&mut *c)
    .await
    .expect("저장소");
    id
}

/// 문서 하나 — 갱신 시각은 초로 준다
async fn doc(
    c: &mut PgConnection,
    pid: i32,
    doc_id: &str,
    status: &str,
    at: i64,
    warn: Option<&str>,
    trashed: bool,
) -> i32 {
    let t = doc_id.split('-').nth(1).expect("타입").to_string();
    sqlx::query_scalar(
        "INSERT INTO documents (project_id, doc_id, doc_type, status, current_body, current_version_no, \
         has_convention_error, incomplete_warnings, updated_at, trashed_at) \
         VALUES ($1, $2, $3, $4, 'x', 1, $5, $6, to_timestamp($7), CASE WHEN $8 THEN now() END) RETURNING id",
    )
    .bind(pid)
    .bind(doc_id)
    .bind(t)
    .bind(status)
    .bind(doc_id.ends_with("-009"))
    .bind(warn)
    .bind(at as f64)
    .bind(trashed)
    .fetch_one(c)
    .await
    .expect("문서")
}

async fn version(c: &mut PgConnection, did: i32, no: i32, by: i32, kind: &str) {
    sqlx::query(
        "INSERT INTO versions (document_id, version_no, commit_hash, body, author_kind, author_user_id, via, message) \
         VALUES ($1, $2, 'h', 'b', $3, $4, 'mcp', 'm')",
    )
    .bind(did)
    .bind(no)
    .bind(kind)
    .bind(by)
    .execute(c)
    .await
    .expect("판");
}

async fn missing_ref(c: &mut PgConnection, from: i32, vid_doc: i32, missing: bool) {
    let vid: i32 = sqlx::query_scalar(
        "SELECT id FROM versions WHERE document_id = $1 ORDER BY version_no LIMIT 1",
    )
    .bind(vid_doc)
    .fetch_one(&mut *c)
    .await
    .expect("판 id");
    sqlx::query(
        r#"INSERT INTO "references" (from_document_id, to_document_id, raw_target, is_missing, extracted_version_id)
           VALUES ($1, CASE WHEN $2 THEN NULL ELSE $1 END, 'X', $2, $3)"#,
    )
    .bind(from)
    .bind(missing)
    .bind(vid)
    .execute(c)
    .await
    .expect("참조");
}

#[tokio::test]
async fn summary_stages_counts_order_and_ownership() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "local").await;
    let other = user(&mut c, "other").await;
    let empty = project(&mut c, "EMP", u.id).await;
    let p = project(&mut c, "FULL", u.id).await;
    project(&mut c, "OTH", other.id).await;
    let _ = empty;
    let rfq = doc(&mut c, p, "FULL-RFQ-001", "draft", 1_000, None, false).await;
    let prd1 = doc(
        &mut c,
        p,
        "FULL-PRD-001",
        "approved",
        2_000,
        Some("[\"section.missing: 목표\"]"),
        false,
    )
    .await;
    let prd2 = doc(&mut c, p, "FULL-PRD-009", "approved", 3_000, None, false).await;
    let std = doc(&mut c, p, "FULL-STD-001", "approved", 500, None, false).await;
    doc(&mut c, p, "FULL-SCN-001", "draft", 9_000, None, true).await; // 휴지통 — 안 센다
    for (d, by) in [(rfq, u.id), (prd1, u.id), (prd2, other.id), (std, u.id)] {
        version(&mut c, d, 1, by, "human").await;
    }
    version(&mut c, prd2, 2, u.id, "agent").await;
    missing_ref(&mut c, prd1, prd1, true).await;
    missing_ref(&mut c, prd1, prd1, true).await;
    missing_ref(&mut c, rfq, rfq, false).await;
    let n = ReferenceService { db: &mut c }
        .count_missing_by_document(&[rfq, prd1, prd2])
        .await
        .expect("세기");
    assert_eq!((n.get(&prd1), n.get(&rfq)), (Some(&2), None));
    assert!(
        ReferenceService { db: &mut c }
            .count_missing_by_document(&[])
            .await
            .expect("빈")
            .is_empty()
    );

    let docs = SpecService { db: &mut c }
        .list_by_project(p, None, None, None)
        .await
        .expect("목록");
    let ids: Vec<&str> = docs.iter().map(|d| d.doc_id.as_str()).collect();
    assert_eq!(
        ids,
        [
            "FULL-RFQ-001",
            "FULL-PRD-001",
            "FULL-PRD-009",
            "FULL-STD-001"
        ]
    );
    let prd2_doc = &docs[2];
    assert_eq!(
        prd2_doc
            .last_author
            .as_ref()
            .map(|a| (a.kind.as_str(), a.user_id)),
        Some(("agent", u.id))
    );
    assert_eq!(docs[1].incomplete_warnings, ["section.missing: 목표"]);
    assert_eq!(docs[3].stage, None);
    let only = SpecService { db: &mut c }
        .list_by_project(p, Some(2), Some(DocStatus::Approved), Some(true))
        .await
        .expect("조건");
    assert_eq!(
        only.iter().map(|d| d.doc_id.as_str()).collect::<Vec<_>>(),
        ["FULL-PRD-009"]
    );

    let all = project_summary(&mut c, &repos(), &u).await.expect("요약");
    let codes: Vec<&str> = all.iter().map(|s| s.code.as_str()).collect();
    assert_eq!(codes, ["FULL", "EMP"]); // 최근 것 먼저, 문서 없는 것은 뒤 · 남의 것은 없다
    let full = &all[0];
    assert_eq!(full.stages.len(), 11);
    assert_eq!(
        (full.stages[0].status.as_deref(), full.stages[0].doc_count),
        (Some("draft"), 1)
    );
    // 앞 단계(RFQ)가 초안인데 PRD에 문서가 있다 → 관문 경고
    assert!(full.stages[1].gate_warning && !full.stages[0].gate_warning);
    assert_eq!(
        (
            full.stages[1].status.as_deref(),
            full.stages[1].broken_count
        ),
        (Some("approved"), 2)
    );
    assert_eq!(full.stages[2].doc_count, 0); // 휴지통 SCN
    assert_eq!(full.counts.get("broken_ref"), Some(&2));
    assert_eq!(full.counts.get("convention_errors"), Some(&1));
    assert_eq!(full.counts.get("incomplete"), Some(&1));
    assert_eq!(
        full.counts.keys().collect::<Vec<_>>(),
        ["broken_ref", "convention_errors", "incomplete"]
    );
    assert_eq!(
        full.std_docs
            .iter()
            .map(|d| d.doc_id.as_str())
            .collect::<Vec<_>>(),
        ["FULL-STD-001"]
    );
    assert_eq!(full.updated_at.map(|t| t.unix_timestamp()), Some(3_000));
    assert_eq!(full.remote_url, None);
    let emp = &all[1];
    assert!(
        emp.stages
            .iter()
            .all(|s| s.status.is_none() && s.doc_count == 0 && !s.gate_warning)
    );
    assert_eq!(emp.updated_at, None);
}
