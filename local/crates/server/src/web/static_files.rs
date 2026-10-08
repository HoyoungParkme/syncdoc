//! 화면 빌드와 캐시 규칙 — SYNC-INFRA-001 4.1 (파이썬 판 `main.py`의 `spa`·`_file`과 같다).
//! 같은 React 빌드(`npm run build` → `backend/app/web/static`)를 담는다 — debug는 디스크에서 읽고,
//! release는 실행 파일에 담는다(빌드가 없으면 release는 컴파일되지 않는다).

use std::time::{Duration, UNIX_EPOCH};

use axum::http::{HeaderMap, HeaderValue, Method, StatusCode, Uri, header};
use axum::response::{IntoResponse, Response};
use percent_encoding::percent_decode_str;
use rust_embed::{EmbeddedFile, RustEmbed};
use syncdoc_core::errors::Problem;

use crate::web::problem::render;

#[derive(RustEmbed)]
#[folder = "$CARGO_MANIFEST_DIR/../../../backend/app/web/static"]
#[cfg_attr(debug_assertions, allow_missing = true)]
struct Build;

/// 이름에 해시가 든 번들·판 번호가 든 글꼴 — 낡을 수 없다
const BUNDLE: &str = "public, max-age=31536000, immutable";
/// 그 밖의 파일과 화면 틀 — 매번 새 판인지 묻는다. 같으면 304
const PLAIN: &str = "no-cache";
/// API 앞머리는 화면 틀로 떨어지지 않는다 (#158)
const API_PREFIXES: [&str; 6] = ["api", "auth", "hooks", "mcp", "git", "specs"];

/// 라우터에 없는 경로 — API 앞머리는 404 problem, 그 밖은 화면 빌드
pub async fn fallback(method: Method, uri: Uri, headers: HeaderMap) -> Response {
    let path = percent_decode_str(uri.path())
        .decode_utf8_lossy()
        .into_owned();
    let rel = path.strip_prefix('/').unwrap_or(&path).to_string();
    let first = rel.split('/').next().unwrap_or("");
    if API_PREFIXES.contains(&first) {
        return render(&Problem::NotFound {
            resource: "path".into(),
            id: path.into(),
        });
    }
    if method != Method::GET && method != Method::HEAD {
        return render(&Problem::MethodNotAllowed {
            method: method.to_string(),
            allow: vec!["GET".into()],
        });
    }
    serve(&rel, &headers)
}

fn serve(rel: &str, headers: &HeaderMap) -> Response {
    let Some(index) = Build::get("index.html") else {
        return render(&Problem::Blank {
            status: 500,
            title: "error".into(),
            detail: Some("React 빌드 결과가 없다 — frontend/에서 npm run build".into()),
        });
    };
    let found = if rel.is_empty() {
        None
    } else {
        Build::get(rel)
    };
    if rel.starts_with("assets/") || rel.starts_with("fonts/") {
        return match found {
            Some(f) => file(rel, f, BUNDLE, headers),
            None => (StatusCode::NOT_FOUND, [(header::CACHE_CONTROL, "no-store")]).into_response(),
        };
    }
    let name = rel.rsplit('/').next().unwrap_or("");
    match found {
        Some(f) if name != "index.html" => file(rel, f, PLAIN, headers),
        _ => file("index.html", index, PLAIN, headers),
    }
}

/// 파일 응답 — If-None-Match가 먼저, 없으면 If-Modified-Since. 같으면 304(ETag·Cache-Control만)
fn file(name: &str, f: EmbeddedFile, cache: &'static str, headers: &HeaderMap) -> Response {
    let etag = format!("\"{}\"", hex(&f.metadata.sha256_hash()));
    let modified = f.metadata.last_modified();
    let unchanged = match headers
        .get(header::IF_NONE_MATCH)
        .and_then(|v| v.to_str().ok())
    {
        Some(asked) if !asked.is_empty() => asked.split(',').any(|t| {
            let t = t.trim();
            let t = t.strip_prefix("W/").unwrap_or(t);
            t == etag || t == "*"
        }),
        _ => match (
            modified,
            headers
                .get(header::IF_MODIFIED_SINCE)
                .and_then(|v| v.to_str().ok())
                .and_then(|v| httpdate::parse_http_date(v).ok()),
        ) {
            (Some(m), Some(since)) => since
                .duration_since(UNIX_EPOCH)
                .is_ok_and(|s| m <= s.as_secs()),
            _ => false,
        },
    };
    let etag_value = HeaderValue::from_str(&etag).unwrap_or(HeaderValue::from_static("\"\""));
    if unchanged {
        return (
            StatusCode::NOT_MODIFIED,
            [
                (header::ETAG, etag_value),
                (header::CACHE_CONTROL, HeaderValue::from_static(cache)),
            ],
        )
            .into_response();
    }
    let mut resp = (
        [
            (header::CACHE_CONTROL, HeaderValue::from_static(cache)),
            (
                header::CONTENT_TYPE,
                HeaderValue::from_static(content_type(name)),
            ),
            (header::ETAG, etag_value),
        ],
        f.data.into_owned(),
    )
        .into_response();
    if let Some(m) = modified
        && let Ok(v) = HeaderValue::from_str(&httpdate::fmt_http_date(
            UNIX_EPOCH + Duration::from_secs(m),
        ))
    {
        resp.headers_mut().insert(header::LAST_MODIFIED, v);
    }
    resp
}

/// 파이썬 판 이미지(python 3.12 mimetypes)가 내는 값 그대로 — 글꼴·LICENSE는 octet-stream
fn content_type(name: &str) -> &'static str {
    let ext = name
        .rsplit_once('.')
        .map(|(_, e)| e.to_ascii_lowercase())
        .unwrap_or_default();
    match ext.as_str() {
        "html" | "htm" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "txt" => "text/plain; charset=utf-8",
        "json" => "application/json",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "ico" => "image/vnd.microsoft.icon",
        _ => "application/octet-stream",
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
