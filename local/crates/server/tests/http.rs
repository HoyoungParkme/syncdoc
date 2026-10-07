//! 서버 — 가드(SEQ-C3)·problem+json·405·정적 파일(INFRA 4.1)·/specs·/api/me.
//! 파이썬 판 `tests/web/test_closed_edition.py`·`test_static.py`와 같은 경우들을 같은 바이트로 본다.

#[path = "../../core/tests/support/mod.rs"]
mod support;

use axum::Router;
use axum::body::Body;
use axum::http::{HeaderMap, Method, Request, StatusCode, header};
use http_body_util::BodyExt;
use serde_json::Value;
use sqlx::PgPool;
use sqlx::postgres::{PgConnectOptions, PgPoolOptions};
use syncdoc_server::app;
use syncdoc_server::state::AppState;
use tower::ServiceExt;

const PORT: u16 = 8010;

fn state(pool: PgPool) -> AppState {
    AppState {
        pool,
        local_login: "local".into(),
        local_name: "로컬".into(),
        llm_enabled: false,
        public_netloc: format!("127.0.0.1:{PORT}"),
    }
}

/// DB가 필요 없는 시험 — 붙지 않는 풀
fn lazy_app() -> Router {
    let pool =
        PgPoolOptions::new().connect_lazy_with(PgConnectOptions::new().host("127.0.0.1").port(9));
    app(state(pool))
}

struct Resp {
    status: StatusCode,
    headers: HeaderMap,
    body: Vec<u8>,
}

impl Resp {
    fn json(&self) -> Value {
        serde_json::from_slice(&self.body).expect("JSON")
    }
    fn text(&self) -> String {
        String::from_utf8(self.body.clone()).expect("UTF-8")
    }
    fn header(&self, name: header::HeaderName) -> Option<&str> {
        self.headers.get(name).and_then(|v| v.to_str().ok())
    }
}

async fn call(app: Router, method: Method, path: &str, headers: &[(&str, &str)]) -> Resp {
    let mut req = Request::builder().method(method).uri(path);
    for (k, v) in headers {
        req = req.header(*k, *v);
    }
    let resp = app
        .oneshot(req.body(Body::empty()).expect("요청"))
        .await
        .expect("응답");
    let (parts, body) = resp.into_parts();
    let body = body.collect().await.expect("본문").to_bytes().to_vec();
    Resp {
        status: parts.status,
        headers: parts.headers,
        body,
    }
}

const HOST: (&str, &str) = ("host", "127.0.0.1:8010");

#[tokio::test]
async fn health() {
    let r = call(lazy_app(), Method::GET, "/health", &[HOST]).await;
    assert_eq!(r.status, StatusCode::OK);
    assert_eq!(r.header(header::CONTENT_TYPE), Some("application/json"));
    assert_eq!(r.text(), r#"{"status":"ok"}"#);
}

#[tokio::test]
async fn host_allow_list_like_python() {
    for host in [
        "127.0.0.1:8010",
        "localhost:8010",
        "LOCALHOST",
        "[::1]:8010",
        "evil@127.0.0.1",
    ] {
        let r = call(lazy_app(), Method::GET, "/health", &[("host", host)]).await;
        assert_eq!(r.status, StatusCode::OK, "{host}");
    }
    for host in [
        "evil.example",
        "",
        "127.0.0.1.evil.example",
        "[::1",
        "::1",
        "0.0.0.0:8010",
        "[0:0:0:0:0:0:0:1]",
    ] {
        let r = call(lazy_app(), Method::GET, "/health", &[("host", host)]).await;
        assert_eq!(r.status, StatusCode::FORBIDDEN, "{host}");
        assert_eq!(
            r.header(header::CONTENT_TYPE),
            Some("application/problem+json")
        );
        let want = format!(
            r#"{{"type":"urn:syncdoc:forbidden-origin","title":"forbidden-origin","status":403,"detail":"폐쇄망판은 이 PC(또는 PUBLIC_BASE_URL)에서만 쓴다","host":{}}}"#,
            serde_json::to_string(host).unwrap()
        );
        assert_eq!(r.text(), want, "{host}");
    }
}

#[tokio::test]
async fn origin_checked_only_on_writes() {
    // 쓰기 + 다른 Origin → 403 origin
    for origin in [
        "http://evil.example",
        "null",
        "http://localhost:8010",
        "http://127.0.0.1:9999",
    ] {
        let r = call(
            lazy_app(),
            Method::POST,
            "/api/me",
            &[HOST, ("origin", origin)],
        )
        .await;
        assert_eq!(r.status, StatusCode::FORBIDDEN, "{origin}");
        assert_eq!(r.json()["origin"], origin);
    }
    // 같은 곳(스킴은 안 본다)·Origin 없음 → 가드를 지나 405
    for headers in [
        vec![HOST, ("origin", "http://127.0.0.1:8010")],
        vec![HOST, ("origin", "https://127.0.0.1:8010")],
        vec![HOST],
    ] {
        let r = call(lazy_app(), Method::POST, "/api/me", &headers).await;
        assert_eq!(r.status, StatusCode::METHOD_NOT_ALLOWED, "{headers:?}");
    }
    // 읽기는 Origin을 안 본다
    let r = call(
        lazy_app(),
        Method::GET,
        "/health",
        &[HOST, ("origin", "http://evil.example")],
    )
    .await;
    assert_eq!(r.status, StatusCode::OK);
    // /mcp·/git/은 토큰 경로 — Origin을 안 본다(아직 없는 경로라 404)
    for path in ["/mcp", "/git/SYNC.git/info/refs"] {
        let r = call(
            lazy_app(),
            Method::POST,
            path,
            &[HOST, ("origin", "http://evil.example")],
        )
        .await;
        assert_eq!(r.status, StatusCode::NOT_FOUND, "{path}");
    }
}

#[tokio::test]
async fn guard_order_github_paths_and_login() {
    let r = call(lazy_app(), Method::GET, "/auth/github", &[HOST]).await;
    assert_eq!(r.status, StatusCode::NOT_FOUND);
    assert_eq!(
        r.text(),
        r#"{"type":"urn:syncdoc:not-found","title":"not-found","status":404,"detail":"path /auth/github 없음","resource":"path","id":"/auth/github"}"#
    );
    let r = call(lazy_app(), Method::POST, "/hooks/github", &[HOST]).await;
    assert_eq!(r.status, StatusCode::NOT_FOUND);
    let r = call(lazy_app(), Method::GET, "/login?next=/p/X", &[HOST]).await;
    assert_eq!(r.status, StatusCode::FOUND);
    assert_eq!(r.header(header::LOCATION), Some("/"));
    assert!(r.body.is_empty());
    // Host가 먼저다
    let r = call(
        lazy_app(),
        Method::GET,
        "/login",
        &[("host", "evil.example")],
    )
    .await;
    assert_eq!(r.status, StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn guard_covers_404_405_and_static() {
    for (method, path) in [
        (Method::GET, "/api/nope"),
        (Method::POST, "/health"),
        (Method::GET, "/assets/x.js"),
        (Method::GET, "/"),
    ] {
        let r = call(
            lazy_app(),
            method.clone(),
            path,
            &[("host", "evil.example")],
        )
        .await;
        assert_eq!(r.status, StatusCode::FORBIDDEN, "{method} {path}");
    }
}

#[tokio::test]
async fn api_prefixes_are_404_problems() {
    for path in [
        "/api",
        "/api/nonexistent",
        "/auth/logout",
        "/mcp",
        "/git/x",
        "/specs",
        "/hooks/x",
    ] {
        let r = call(lazy_app(), Method::GET, path, &[HOST]).await;
        assert_eq!(r.status, StatusCode::NOT_FOUND, "{path}");
        assert_eq!(r.json()["resource"], "path");
        assert_eq!(r.json()["id"], path);
    }
    let r = call(lazy_app(), Method::GET, "/api/nonexistent", &[HOST]).await;
    assert_eq!(
        r.text(),
        r#"{"type":"urn:syncdoc:not-found","title":"not-found","status":404,"detail":"path /api/nonexistent 없음","resource":"path","id":"/api/nonexistent"}"#
    );
}

#[tokio::test]
async fn method_not_allowed_lists_allow() {
    let r = call(lazy_app(), Method::POST, "/health", &[HOST]).await;
    assert_eq!(r.status, StatusCode::METHOD_NOT_ALLOWED);
    assert_eq!(r.header(header::ALLOW), Some("GET"));
    assert_eq!(
        r.text(),
        r#"{"type":"urn:syncdoc:method-not-allowed","title":"method-not-allowed","status":405,"detail":"이 경로에 POST 메서드는 없습니다","allow":["GET"]}"#
    );
    // 화면 틀 경로도 GET만
    let r = call(lazy_app(), Method::DELETE, "/p/SYNC", &[HOST]).await;
    assert_eq!(r.status, StatusCode::METHOD_NOT_ALLOWED);
    assert_eq!(r.json()["allow"], serde_json::json!(["GET"]));
}

#[tokio::test]
async fn static_cache_rules_and_304() {
    // 화면 틀 — 어느 화면 주소든 index.html, no-cache
    for path in [
        "/",
        "/index.html",
        "/p/SYNC",
        "/favicon.ico",
        "/health/",
        "/login/",
    ] {
        let r = call(lazy_app(), Method::GET, path, &[HOST]).await;
        assert_eq!(r.status, StatusCode::OK, "{path}");
        assert_eq!(r.header(header::CACHE_CONTROL), Some("no-cache"), "{path}");
        assert_eq!(
            r.header(header::CONTENT_TYPE),
            Some("text/html; charset=utf-8"),
            "{path}"
        );
        assert!(r.text().contains("<div id=\"root\">"), "{path}");
    }
    // 번들 — 1년 immutable. 없는 번들은 빈 404 + no-store
    let index = call(lazy_app(), Method::GET, "/", &[HOST]).await.text();
    let asset = index
        .split("src=\"")
        .nth(1)
        .and_then(|s| s.split('"').next())
        .expect("index.html의 스크립트");
    let r = call(lazy_app(), Method::GET, asset, &[HOST]).await;
    assert_eq!(r.status, StatusCode::OK);
    assert_eq!(
        r.header(header::CACHE_CONTROL),
        Some("public, max-age=31536000, immutable")
    );
    assert_eq!(
        r.header(header::CONTENT_TYPE),
        Some("text/javascript; charset=utf-8")
    );
    let etag = r.header(header::ETAG).expect("ETag").to_string();
    let modified = r
        .header(header::LAST_MODIFIED)
        .expect("Last-Modified")
        .to_string();
    for path in ["/assets/nope.js", "/fonts/nope.woff2"] {
        let r = call(lazy_app(), Method::GET, path, &[HOST]).await;
        assert_eq!(r.status, StatusCode::NOT_FOUND, "{path}");
        assert_eq!(r.header(header::CACHE_CONTROL), Some("no-store"));
        assert!(r.header(header::CONTENT_TYPE).is_none() && r.body.is_empty());
    }
    // 304 — If-None-Match(W/ 떼기·* 매치)가 먼저, 없으면 If-Modified-Since
    for inm in [
        etag.clone(),
        format!("W/{etag}"),
        format!("\"x\", {etag}"),
        "*".into(),
    ] {
        let r = call(
            lazy_app(),
            Method::GET,
            asset,
            &[HOST, ("if-none-match", &inm)],
        )
        .await;
        assert_eq!(r.status, StatusCode::NOT_MODIFIED, "{inm}");
        assert_eq!(r.header(header::ETAG), Some(etag.as_str()));
        assert_eq!(
            r.header(header::CACHE_CONTROL),
            Some("public, max-age=31536000, immutable")
        );
        assert!(r.body.is_empty());
    }
    let r = call(
        lazy_app(),
        Method::GET,
        asset,
        &[HOST, ("if-modified-since", &modified)],
    )
    .await;
    assert_eq!(r.status, StatusCode::NOT_MODIFIED);
    let r = call(
        lazy_app(),
        Method::GET,
        asset,
        &[
            HOST,
            ("if-none-match", "\"x\""),
            ("if-modified-since", &modified),
        ],
    )
    .await;
    assert_eq!(r.status, StatusCode::OK, "If-None-Match가 이긴다");
    // 그 밖의 파일 — no-cache, 글꼴은 octet-stream(파이썬 판 이미지와 같다)
    let r = call(lazy_app(), Method::GET, "/howto/token-issued.png", &[HOST]).await;
    assert_eq!(
        (
            r.status,
            r.header(header::CACHE_CONTROL),
            r.header(header::CONTENT_TYPE)
        ),
        (StatusCode::OK, Some("no-cache"), Some("image/png"))
    );
}

#[tokio::test]
async fn specs_listing_and_files() {
    let r = call(lazy_app(), Method::GET, "/specs/STD", &[HOST]).await;
    assert_eq!(r.status, StatusCode::OK);
    assert_eq!(
        r.header(header::CONTENT_TYPE),
        Some("text/html; charset=utf-8")
    );
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../docs/specs/STD");
    let mut names: Vec<String> = std::fs::read_dir(&dir)
        .unwrap()
        .filter_map(|e| e.ok()?.file_name().into_string().ok())
        .filter(|n| n.ends_with(".md"))
        .collect();
    names.sort();
    let rows: String = names
        .iter()
        .map(|n| format!("<li><a href=\"/specs/STD/{n}\">{n}</a></li>"))
        .collect();
    assert_eq!(
        r.text(),
        format!(
            "<!doctype html><meta charset=\"utf-8\"><title>STD</title><h1>STD</h1><ul>{rows}</ul>"
        )
    );
    let r = call(
        lazy_app(),
        Method::GET,
        "/specs/STD/SYNC-STD-001.md",
        &[HOST],
    )
    .await;
    assert_eq!(
        r.header(header::CONTENT_TYPE),
        Some("text/plain; charset=utf-8")
    );
    assert_eq!(
        r.text(),
        std::fs::read_to_string(dir.join("SYNC-STD-001.md")).unwrap()
    );
    let r = call(lazy_app(), Method::GET, "/specs/_templates/", &[HOST]).await;
    assert_eq!(r.status, StatusCode::OK);
    for (path, id) in [
        ("/specs/", ""),
        ("/specs/10-MS/SYNC-MS-012.md", "10-MS/SYNC-MS-012.md"),
        ("/specs/STD/../x", "STD/../x"),
        ("/specs/STD/nope.md", "STD/nope.md"),
    ] {
        let r = call(lazy_app(), Method::GET, path, &[HOST]).await;
        assert_eq!(r.status, StatusCode::NOT_FOUND, "{path}");
        assert_eq!(
            (r.json()["resource"].as_str(), r.json()["id"].as_str()),
            (Some("specs"), Some(id)),
            "{path}"
        );
    }
}

#[tokio::test]
async fn me_is_the_local_user() {
    let db = support::test_db().await;
    let r = call(app(state(db.pool.clone())), Method::GET, "/api/me", &[HOST]).await;
    assert_eq!(r.status, StatusCode::OK);
    assert_eq!(r.header(header::CONTENT_TYPE), Some("application/json"));
    let v = r.json();
    let keys: Vec<&str> = v.as_object().unwrap().keys().map(String::as_str).collect();
    assert_eq!(
        keys,
        [
            "id",
            "github_login",
            "display_name",
            "created_at",
            "llm_enabled",
            "storage_modes",
            "edition",
            "repo_private"
        ]
    );
    assert_eq!(
        (v["github_login"].as_str(), v["display_name"].as_str()),
        (Some("local"), Some("로컬"))
    );
    assert_eq!(
        (
            v["edition"].as_str(),
            v["repo_private"].as_bool(),
            v["llm_enabled"].as_bool()
        ),
        (Some("closed"), Some(true), Some(false))
    );
    assert_eq!(v["storage_modes"], serde_json::json!(["server"]));
    let at = v["created_at"].as_str().unwrap();
    assert!(
        at.len() >= 20 && at.ends_with('Z') && at.as_bytes()[10] == b'T',
        "{at}"
    );
    // 두 번 불러도 같은 사람
    let again = call(app(state(db.pool.clone())), Method::GET, "/api/me", &[HOST])
        .await
        .json();
    assert_eq!(again["id"], v["id"]);
}
