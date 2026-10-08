//! 규약·템플릿 사본 — 파이썬 판 `web/routers/specs.py`와 같은 바이트.
//! 폐쇄망판 README의 규약 링크가 여기를 가리킨다(SPECS_URL 기본값, INFRA 8.1). `docs/specs/STD`·`_templates`의
//! `.md`를 실행 파일에 담는다(INFRA 9.2). 둘 밖이나 `..`는 없는 것과 같은 404.

use axum::http::{Uri, header};
use axum::response::{IntoResponse, Response};
use percent_encoding::percent_decode_str;
use rust_embed::RustEmbed;
use syncdoc_core::errors::Problem;

use crate::web::problem::render;

#[derive(RustEmbed)]
#[folder = "$CARGO_MANIFEST_DIR/../../../docs/specs"]
#[include = "STD/*.md"]
#[include = "_templates/*.md"]
struct Specs;

const SHARED: [&str; 2] = ["STD", "_templates"];

/// SYNC-API-001#GET/specs/{path}
pub async fn spec_copy(uri: Uri) -> Response {
    let raw = uri.path().strip_prefix("/specs/").unwrap_or("");
    let path = percent_decode_str(raw).decode_utf8_lossy().into_owned();
    // 파이썬 PurePosixPath(path.strip("/")).parts — 빈 조각과 `.`은 버리고 `..`은 남긴다
    let parts: Vec<&str> = path
        .trim_matches('/')
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    if parts.first().is_none_or(|p| !SHARED.contains(p)) || parts.contains(&"..") {
        return not_found(path);
    }
    let rel = parts.join("/");
    let prefix = format!("{rel}/");
    let mut names: Vec<String> = Specs::iter()
        .filter_map(|f| f.strip_prefix(prefix.as_str()).map(str::to_string))
        .filter(|n| !n.contains('/'))
        .collect();
    if !names.is_empty() {
        names.sort();
        return (
            [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
            listing(&rel, &names),
        )
            .into_response();
    }
    if rel.ends_with(".md")
        && let Some(f) = Specs::get(&rel)
    {
        return (
            [(header::CONTENT_TYPE, "text/plain; charset=utf-8")],
            f.data.into_owned(),
        )
            .into_response();
    }
    not_found(path)
}

fn not_found(path: String) -> Response {
    render(&Problem::NotFound {
        resource: "specs".into(),
        id: path.into(),
    })
}

/// 폴더 → 파일 목록 HTML. 링크는 절대 경로 — README가 `/specs/_templates`를 슬래시 없이 건다
fn listing(rel: &str, names: &[String]) -> String {
    let rel = escape(rel);
    let rows: String = names
        .iter()
        .map(|n| {
            let n = escape(n);
            format!("<li><a href=\"/specs/{rel}/{n}\">{n}</a></li>")
        })
        .collect();
    format!(
        "<!doctype html><meta charset=\"utf-8\"><title>{rel}</title><h1>{rel}</h1><ul>{rows}</ul>"
    )
}

/// 파이썬 `html.escape(s, quote=True)`
fn escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}
