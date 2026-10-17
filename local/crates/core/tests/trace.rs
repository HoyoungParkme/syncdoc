//! 카드 L27 테스트 관점 — 실행 기록(SYNC-MS-027 TraceService). 시험 DB · 임시 자리

mod support;

use serde_json::{Value, json};
use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::errors::Problem;
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::trace::TraceService;
use syncdoc_core::types::{Storage, iso_utc};

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

struct Env {
    db: support::TestDb,
    _tmp: tempfile::TempDir,
    repos: ServerRepos,
    me: UserRow,
    p: i32,
    q: i32,
}

async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let me = user(&mut c, "me").await;
    let mut ids = Vec::new();
    for code in ["LT", "LU"] {
        let p = ProjectService {
            db: &mut c,
            repos: &repos,
        }
        .init_project(&db.pool, code, "기록 시험", &me, false, Storage::Server)
        .await
        .expect("프로젝트");
        ids.push(p.0.id);
    }
    drop(c);
    Env {
        db,
        _tmp: tmp,
        repos,
        me,
        p: ids[0],
        q: ids[1],
    }
}

fn record(key: &str) -> Value {
    json!({
        "version": 1, "id": key, "kind": "back", "method": "GET", "path": "/api/x", "status": 200,
        "error": null, "startedAt": "2026-10-17T01:02:03Z", "ms": 12, "commit": "a".repeat(40),
        "truncated": false,
        "events": [
            {"i": 0, "parent": -1, "fn": "app/a.py:3", "t0": 0},
            {"i": 1, "parent": 0, "fn": "@infra", "t0": 1, "infra": {"kind": "db", "target": "db:5432"}},
            {"i": 2, "parent": 0, "fn": "app/b.py:9", "t0": 2}
        ]
    })
}

fn with(mut r: Value, k: &str, v: Value) -> Value {
    r[k] = v;
    r
}

#[tokio::test]
async fn save_returns_brief_and_same_key_once() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let mut svc = TraceService { db: &mut c };
    let (b, new) = svc.save(e.p, e.me.id, &record("t1")).await.expect("넣기");
    assert!(new);
    assert_eq!(
        (b.trace_key.as_str(), b.event_count, b.method.as_deref()),
        ("t1", 3, Some("GET"))
    );
    assert_eq!(iso_utc(b.started_at), "2026-10-17T01:02:03Z");
    let (k, _) = svc
        .save(
            e.p,
            e.me.id,
            &with(
                record("kst"),
                "startedAt",
                json!("2026-10-17T10:02:03.5+09:00"),
            ),
        )
        .await
        .expect("넣기");
    assert_eq!(iso_utc(k.started_at), "2026-10-17T01:02:03.500000Z");
    let (again, new2) = svc
        .save(e.p, e.me.id, &with(record("t1"), "path", json!("/other")))
        .await
        .expect("다시");
    assert!(!new2 && again.id == b.id && again.path == "/api/x");
}

#[tokio::test]
async fn keeps_recent_job_and_cut_error() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let mut svc = TraceService { db: &mut c };
    let long = "e".repeat(301);
    let job = with(
        with(record("j"), "kind", json!("job")),
        "error",
        json!(long),
    );
    let (b, _) = svc.save(e.p, e.me.id, &job).await.expect("넣기");
    assert!(b.method.is_none() && b.error.as_ref().map(|x| x.chars().count()) == Some(300));
    assert_eq!(
        svc.get(e.p, b.id).await.expect("하나").record["error"],
        json!(long)
    );
    svc.save(e.q, e.me.id, &record("q1"))
        .await
        .expect("다른 프로젝트");
    for n in 0..3 {
        svc.save(e.p, e.me.id, &record(&format!("t{n}")))
            .await
            .expect("넣기");
    }
    let keys: Vec<String> = svc
        .list_recent(e.p, 300)
        .await
        .expect("목록")
        .into_iter()
        .map(|b| b.trace_key)
        .collect();
    assert_eq!(keys, ["t2", "t1", "t0", "j"]);
    let two: Vec<String> = svc
        .list_recent(e.p, 2)
        .await
        .expect("목록")
        .into_iter()
        .map(|b| b.trace_key)
        .collect();
    assert_eq!(two, ["t2", "t1"]);
}

#[tokio::test]
async fn rejects_bad_events_and_time() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let mut svc = TraceService { db: &mut c };
    let reason = |r: Result<_, Problem>| match r {
        Err(Problem::TraceInvalid { reason, status }) => (reason, status),
        other => panic!("{other:?}"),
    };
    let orphan = with(
        record("a"),
        "events",
        json!([{"i": 0, "parent": 5, "fn": "a", "t0": 0}]),
    );
    assert_eq!(
        reason(svc.save(e.p, e.me.id, &orphan).await),
        ("events[0] — 부모가 없다".into(), 422)
    );
    let skip = with(
        record("a"),
        "events",
        json!([{"i": 1, "parent": -1, "fn": "a", "t0": 0}]),
    );
    assert_eq!(
        reason(svc.save(e.p, e.me.id, &skip).await).0,
        "events[0] — i가 차례가 아니다"
    );
    for bad in [
        "2026-13-01T00:00:00",
        "2026-10-17",
        "2026-02-30T00:00:00Z",
        "2026-10-17T00:00:00+24:00",
    ] {
        let r = with(record("a"), "startedAt", json!(bad));
        assert_eq!(
            reason(svc.save(e.p, e.me.id, &r).await).0,
            "startedAt — 시각이 아니다",
            "{bad}"
        );
    }
    assert!(svc.list_recent(e.p, 300).await.expect("목록").is_empty());
}

#[tokio::test]
async fn get_delete_coverage_and_other_project() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let mut svc = TraceService { db: &mut c };
    let empty = svc.coverage(e.p).await.expect("빈 것");
    assert_eq!(
        (empty.traces, empty.keys.len(), empty.infra.len()),
        (0, 0, 0)
    );
    let (a, _) = svc.save(e.p, e.me.id, &record("a")).await.expect("넣기");
    let fetch = with(
        record("b"),
        "events",
        json!([{"i": 0, "parent": -1, "fn": "@fetch", "t0": 0}, {"i": 1, "parent": 0, "fn": "app/a.py:3", "t0": 1}]),
    );
    svc.save(e.p, e.me.id, &fetch).await.expect("넣기");
    svc.save(e.q, e.me.id, &record("c")).await.expect("넣기");
    let cov = svc.coverage(e.p).await.expect("커버리지");
    assert_eq!(cov.traces, 2);
    assert_eq!(cov.keys, ["app/a.py:3", "app/b.py:9"]);
    assert_eq!(cov.infra, [("db".to_string(), "db:5432".to_string())]);
    assert!(matches!(
        svc.get(e.q, a.id).await,
        Err(Problem::NotFound { .. })
    ));
    assert!(matches!(
        svc.delete(e.q, Some(a.id)).await,
        Err(Problem::NotFound { .. })
    ));
    assert_eq!(svc.delete(e.p, Some(a.id)).await.expect("하나"), 1);
    assert_eq!(svc.delete(e.p, None).await.expect("전부"), 1);
    assert_eq!(svc.list_recent(e.q, 300).await.expect("목록").len(), 1);
}

#[tokio::test]
async fn delete_project_removes_traces() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    TraceService { db: &mut c }
        .save(e.p, e.me.id, &record("a"))
        .await
        .expect("넣기");
    ProjectService {
        db: &mut c,
        repos: &e.repos,
    }
    .delete_project("LT", &e.me)
    .await
    .expect("해제");
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM traces WHERE project_id = $1")
        .bind(e.p)
        .fetch_one(&mut *c)
        .await
        .expect("수");
    assert_eq!(n, 0);
}
