//! uvicorn 경로 — 요청 줄의 경로를 `urllib.parse.unquote`(UTF-8, errors="replace")로 푼 뒤 라우팅한다
//! (uvicorn 0.52.4 · starlette 1.6.0, SYNC-DOM-004 1장 compat). 파이썬 판은 푼 경로로 라우트를 고르고 경로 값을 넘긴다 —
//! `/api/m%65`는 `/api/me`, `%FF`는 U+FFFD. axum은 날 경로로 고르므로 앞에서 풀어 다시 담는다.

use axum::extract::Request;
use axum::http::Uri;
use axum::middleware::Next;
use axum::response::Response;

/// `urllib.parse.unquote` — `%XX` 묶음을 바이트로 모아 UTF-8로(못 읽는 바이트는 U+FFFD), 틀린 `%`는 그대로
pub fn unquote(s: &str) -> String {
    if !s.contains('%') {
        return s.to_string();
    }
    let b = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    let mut i = 0;
    let mut run: Vec<u8> = Vec::new();
    let hex = |c: u8| (c as char).to_digit(16);
    while i < b.len() {
        if b[i] == b'%'
            && i + 2 < b.len()
            && let (Some(h), Some(l)) = (hex(b[i + 1]), b.get(i + 2).and_then(|&c| hex(c)))
        {
            run.push((h * 16 + l) as u8);
            i += 3;
            continue;
        }
        if !run.is_empty() {
            out.push_str(&String::from_utf8_lossy(&run));
            run.clear();
        }
        let ch = s[i..].chars().next().unwrap_or('\u{fffd}');
        out.push(ch);
        i += ch.len_utf8();
    }
    if !run.is_empty() {
        out.push_str(&String::from_utf8_lossy(&run));
    }
    out
}

/// 푼 경로를 다시 URI에 담는다 — 경로에 그대로 둘 수 있는 글자(RFC 3986 pchar와 `/`) 말고는 퍼센트로.
/// axum이 경로 값을 한 번 풀면 파이썬이 넘기는 값과 같아진다
fn requote(path: &str) -> String {
    let mut out = String::with_capacity(path.len());
    for ch in path.chars() {
        if ch.is_ascii_alphanumeric() || "-._~!$&'()*+,;=:@/".contains(ch) {
            out.push(ch);
        } else {
            let mut buf = [0u8; 4];
            for b in ch.encode_utf8(&mut buf).bytes() {
                out.push_str(&format!("%{b:02X}"));
            }
        }
    }
    out
}

/// 미들웨어 — 경로에 `%`가 있으면 풀어 다시 담는다(쿼리는 그대로)
pub async fn decode_path(mut req: Request, next: Next) -> Response {
    let path = req.uri().path();
    if path.contains('%') {
        let decoded = requote(&unquote(path));
        let pq = match req.uri().query() {
            Some(q) => format!("{decoded}?{q}"),
            None => decoded,
        };
        let mut parts = req.uri().clone().into_parts();
        if let Ok(p) = pq.parse() {
            parts.path_and_query = Some(p);
            if let Ok(uri) = Uri::from_parts(parts) {
                *req.uri_mut() = uri;
            }
        }
    }
    next.run(req).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unquote_like_python() {
        assert_eq!(unquote("/api/m%65"), "/api/me");
        assert_eq!(unquote("%FF"), "\u{fffd}");
        assert_eq!(unquote("%E2%80%8B1"), "\u{200b}1");
        assert_eq!(unquote("%G1%2"), "%G1%2");
        assert_eq!(unquote("%2520"), "%20");
        assert_eq!(unquote("a%2Fb"), "a/b");
    }

    #[test]
    fn requote_then_axum_decode_is_identity() {
        assert_eq!(requote("/a b/%/é"), "/a%20b/%25/%C3%A9");
    }
}
