//! 토큰 세 경로와 `/mcp` — 카드 L3 (SYNC-MS-016 · SYNC-API-002 1장 · SYNC-SEQ-001#SEQ-C2).
//! 바이트까지의 대조는 계약 시험(`contract/test_l3_*`)이 한다. 여기는 DB에 남는 것 — 사용 흔적이 커밋되는지.

#[path = "../../core/tests/support/mod.rs"]
mod support;

use axum::Router;
use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use sqlx::PgPool;
use syncdoc_server::app;
use syncdoc_server::state::AppState;
use time::OffsetDateTime;
use tower::ServiceExt;

const HOST: (&str, &str) = ("host", "127.0.0.1:8010");

fn router(pool: PgPool) -> Router {
    app(AppState {
        pool,
        local_login: "local".into(),
        local_name: "local".into(),
        llm_enabled: false,
        public_netloc: "127.0.0.1:8010".into(),
    })
}

async fn send(
    app: &Router,
    method: Method,
    path: &str,
    headers: &[(&str, &str)],
    body: &str,
) -> (StatusCode, String) {
    let mut req = Request::builder()
        .method(method)
        .uri(path)
        .header(HOST.0, HOST.1);
    for (k, v) in headers {
        req = req.header(*k, *v);
    }
    let resp = app
        .clone()
        .oneshot(req.body(Body::from(body.to_string())).expect("요청"))
        .await
        .expect("응답");
    let status = resp.status();
    let bytes = resp.into_body().collect().await.expect("본문").to_bytes();
    (status, String::from_utf8_lossy(&bytes).into_owned())
}

const JSON: (&str, &str) = ("content-type", "application/json");
const ACCEPT: (&str, &str) = ("accept", "application/json, text/event-stream");

async fn issue(app: &Router, label: &str) -> Value {
    let (s, body) = send(
        app,
        Method::POST,
        "/api/me/tokens",
        &[JSON],
        &format!("{{\"label\":\"{label}\"}}"),
    )
    .await;
    assert_eq!(s, StatusCode::CREATED, "{body}");
    serde_json::from_str(&body).expect("JSON")
}

#[tokio::test]
async fn token_routes_issue_list_revoke() {
    let db = support::test_db().await;
    let app = router(db.pool.clone());
    let t = issue(&app, "노트북").await;
    let keys: Vec<&str> = t
        .as_object()
        .expect("객체")
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        keys,
        [
            "id",
            "label",
            "issued_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
            "token"
        ]
    );
    let (s, list) = send(&app, Method::GET, "/api/me/tokens", &[], "").await;
    assert_eq!(s, StatusCode::OK);
    let list: Value = serde_json::from_str(&list).expect("JSON");
    assert_eq!(list[0]["id"], t["id"]);
    assert!(list[0].get("token").is_none());
    let (s, body) = send(
        &app,
        Method::DELETE,
        &format!("/api/me/tokens/{}", t["id"]),
        &[],
        "",
    )
    .await;
    assert_eq!((s, body.as_str()), (StatusCode::NO_CONTENT, ""));
    let (s, body) = send(&app, Method::DELETE, "/api/me/tokens/999999", &[], "").await;
    assert_eq!(s, StatusCode::NOT_FOUND);
    assert_eq!(
        body,
        r#"{"type":"urn:syncdoc:not-found","title":"not-found","status":404,"detail":"access_token 999999 없음","resource":"access_token","id":999999}"#
    );
}

#[tokio::test]
async fn mcp_use_is_committed_before_the_reply() {
    let db = support::test_db().await;
    let app = router(db.pool.clone());
    let t = issue(&app, "mcp").await;
    let bearer = format!("Bearer {}", t["token"].as_str().expect("원문"));
    let (s, body) = send(
        &app,
        Method::POST,
        "/mcp",
        &[("authorization", &bearer), ACCEPT, JSON],
        r#"{"jsonrpc":"2.0","id":1,"method":"ping"}"#,
    )
    .await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(
        body,
        "event: message\r\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\r\n\r\n"
    );
    // 다른 연결에서 보인다 — 커밋됐다
    let used: Option<OffsetDateTime> =
        sqlx::query_scalar("SELECT last_used_at FROM access_tokens WHERE id = $1")
            .bind(t["id"].as_i64().expect("id") as i32)
            .fetch_one(&db.pool)
            .await
            .expect("행");
    assert!(used.is_some());
}

#[tokio::test]
async fn mcp_refuses_missing_and_revoked_tokens_alike() {
    let db = support::test_db().await;
    let app = router(db.pool.clone());
    let want = "{\"type\": \"urn:syncdoc:unauthorized\", \"title\": \"unauthorized\", \"status\": 401, \"detail\": \"토큰 없음·폐기·만료\"}";
    let ping = r#"{"jsonrpc":"2.0","id":1,"method":"ping"}"#;
    let (s, body) = send(&app, Method::POST, "/mcp", &[ACCEPT, JSON], ping).await;
    assert_eq!((s, body.as_str()), (StatusCode::UNAUTHORIZED, want));
    let t = issue(&app, "x").await;
    send(
        &app,
        Method::DELETE,
        &format!("/api/me/tokens/{}", t["id"]),
        &[],
        "",
    )
    .await;
    let bearer = format!("Bearer {}", t["token"].as_str().expect("원문"));
    let (s, body) = send(
        &app,
        Method::POST,
        "/mcp",
        &[("authorization", &bearer), ACCEPT, JSON],
        ping,
    )
    .await;
    assert_eq!((s, body.as_str()), (StatusCode::UNAUTHORIZED, want));
}

#[tokio::test]
async fn tools_not_built_yet_name_their_card() {
    let db = support::test_db().await;
    let app = router(db.pool.clone());
    let t = issue(&app, "x").await;
    let bearer = format!("Bearer {}", t["token"].as_str().expect("원문"));
    let (s, body) = send(
        &app,
        Method::POST,
        "/mcp",
        &[("authorization", &bearer), ACCEPT, JSON],
        r#"{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"change_status","arguments":{"doc_id":"SYNC-PRD-001","to":"approved"}}}"#,
    )
    .await;
    assert_eq!(s, StatusCode::OK);
    assert!(body.contains(r#"\"card\": \"L9\""#), "{body}");
    assert!(body.contains(r#""isError":true"#), "{body}");
}
