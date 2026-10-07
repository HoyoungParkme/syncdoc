//! Host·Origin 가드 — SYNC-SEQ-001#SEQ-C3 · SYNC-INFRA-001 5장·9.4.
//! 파이썬 판 `web/auth.py`의 ClosedEditionGuard와 같은 순서·같은 판정이다. 라우팅 바깥에서 모든 요청에.

use axum::extract::{Request, State};
use axum::http::{Method, StatusCode, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use percent_encoding::percent_decode_str;
use syncdoc_core::errors::Problem;

use crate::state::AppState;
use crate::web::problem::render;

const LOCAL_HOSTS: [&str; 3] = ["127.0.0.1", "localhost", "::1"];
const UNSAFE: [Method; 4] = [Method::POST, Method::PUT, Method::PATCH, Method::DELETE];
/// 토큰이 사람을 정한다 — Origin을 보지 않는다 (SEQ-C2·29)
const TOKEN_PATHS: [&str; 2] = ["/mcp", "/git/"];
/// 폐쇄망판에는 없다 (API-001 1장)
const GITHUB_PATHS: [&str; 2] = ["/auth/github", "/hooks/github"];

/// 가드 — Host → 쓰기 요청의 Origin → GitHub 경로 404 → `/login` 302 순서
pub async fn guard(State(state): State<AppState>, req: Request, next: Next) -> Response {
    let host = header_text(&req, header::HOST).unwrap_or_default();
    let origin = header_text(&req, header::ORIGIN);
    let path = percent_decode_str(req.uri().path())
        .decode_utf8_lossy()
        .into_owned();
    if !allowed_host(&host, &state) {
        return render(&Problem::ForbiddenOrigin {
            host: Some(host),
            origin: None,
        });
    }
    if UNSAFE.contains(req.method())
        && let Some(o) = origin
        && !TOKEN_PATHS.iter().any(|p| path.starts_with(p))
        && !same_origin(&o, &host, &state)
    {
        return render(&Problem::ForbiddenOrigin {
            host: None,
            origin: Some(o),
        });
    }
    if GITHUB_PATHS.iter().any(|p| path.starts_with(p)) {
        return render(&Problem::NotFound {
            resource: "path".into(),
            id: path,
        });
    }
    if path == "/login" {
        return (StatusCode::FOUND, [(header::LOCATION, "/")]).into_response();
    }
    next.run(req).await
}

fn header_text(req: &Request, name: header::HeaderName) -> Option<String> {
    req.headers()
        .get(name)
        .map(|v| String::from_utf8_lossy(v.as_bytes()).into_owned())
}

/// 이름만 본다(포트 무시) — 이 PC의 이름이거나 공개 주소의 이름
fn allowed_host(host: &str, state: &AppState) -> bool {
    let name = hostname(host);
    !name.is_empty()
        && (LOCAL_HOSTS.contains(&name.as_str()) || name == hostname(&state.public_netloc))
}

/// Origin의 host:port가 요청 Host이거나 공개 주소다 (스킴은 안 본다)
fn same_origin(origin: &str, host: &str, state: &AppState) -> bool {
    let netloc = origin_netloc(origin);
    !netloc.is_empty()
        && (netloc == host.trim().to_lowercase() || netloc == state.public_netloc.to_lowercase())
}

/// 파이썬 `urlsplit("//" + netloc).hostname` — 사용자 정보·포트를 떼고 소문자. 못 읽으면 빈 글자
fn hostname(netloc: &str) -> String {
    let netloc = netloc.trim();
    let netloc = netloc.split(['/', '?', '#']).next().unwrap_or("");
    if netloc.contains('[') != netloc.contains(']') {
        return String::new();
    }
    let info = netloc.rsplit_once('@').map_or(netloc, |(_, h)| h);
    if let Some((before, rest)) = info.split_once('[') {
        let (name, port) = rest.split_once(']').unwrap_or((rest, ""));
        if !before.is_empty() || (!port.is_empty() && !port.starts_with(':')) || !bracketed_ok(name)
        {
            return String::new();
        }
        return name.to_lowercase();
    }
    info.split(':').next().unwrap_or("").to_lowercase()
}

/// 대괄호 안은 IPv6이거나 IPvFuture여야 한다 (파이썬 `_check_bracketed_host`)
fn bracketed_ok(name: &str) -> bool {
    if let Some(rest) = name.strip_prefix('v') {
        return rest.split_once('.').is_some_and(|(hex, tail)| {
            !hex.is_empty()
                && hex.chars().all(|c| c.is_ascii_hexdigit())
                && !tail.is_empty()
                && tail
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || "._~!$&'()*+,;=:-".contains(c))
        });
    }
    name.parse::<std::net::Ipv6Addr>().is_ok()
}

/// 파이썬 `urlsplit(origin).netloc` — `스킴://host:port/…`의 host:port, 소문자
fn origin_netloc(origin: &str) -> String {
    let s = origin.trim();
    let rest = match s.find(':') {
        Some(i)
            if i > 0
                && s.as_bytes()[0].is_ascii_alphabetic()
                && s[..i]
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c)) =>
        {
            &s[i + 1..]
        }
        _ => s,
    };
    match rest.strip_prefix("//") {
        Some(r) => r.split(['/', '?', '#']).next().unwrap_or("").to_lowercase(),
        None => String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hostname_like_urlsplit() {
        for (input, want) in [
            ("127.0.0.1:8010", "127.0.0.1"),
            ("LOCALHOST", "localhost"),
            (" localhost ", "localhost"),
            ("[::1]:8010", "::1"),
            ("[::1]", "::1"),
            ("evil@127.0.0.1", "127.0.0.1"),
            ("127.0.0.1:abc", "127.0.0.1"),
            ("::1", ""),
            ("[::1", ""),
            ("[127.0.0.1]", ""),
            ("x[::1]", ""),
            ("", ""),
        ] {
            assert_eq!(hostname(input), want, "{input:?}");
        }
    }

    #[test]
    fn origin_netloc_like_urlsplit() {
        assert_eq!(origin_netloc("http://127.0.0.1:8010"), "127.0.0.1:8010");
        assert_eq!(origin_netloc("HTTPS://LocalHost:8010/x"), "localhost:8010");
        assert_eq!(origin_netloc("null"), "");
        assert_eq!(origin_netloc(""), "");
        assert_eq!(origin_netloc("evil.example"), "");
    }
}
