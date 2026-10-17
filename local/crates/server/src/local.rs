//! 이 PC — 설치형(app crate)이 쥔 일의 문 (SYNC-DOM-004 4.12 · SYNC-API-001 3.11, 카드 L16).
//! crate 의존이 `app → server` 한 방향이라 server가 문(`LocalOps`)을 두고 app이 채워 서버 상태에 넣는다.
//! 파이썬 판에는 없다 — 비어 있으면 `/api/local*`이 없는 경로다

use async_trait::async_trait;
use serde::Serialize;
use syncdoc_core::errors::Problem;

/// 백업 파일 하나 (API-001 `BackupFile`)
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub struct BackupFile {
    pub name: String,
    pub size: u64,
    pub encrypted: bool,
}

/// 켠 뒤 마지막 백업 시도
#[derive(Serialize, Clone, Debug)]
pub struct LastBackup {
    pub at: String,
    pub name: Option<String>,
    pub error: Option<String>,
}

/// 켠 뒤 마지막 다시 켜기 — `settings`·`restore`·`move`
#[derive(Serialize, Clone, Debug)]
pub struct LastOp {
    pub kind: &'static str,
    pub ok: bool,
    pub message: String,
    pub at: String,
}

/// 「백업」 카드
#[derive(Serialize, Clone, Debug)]
pub struct BackupInfo {
    pub dir: String,
    pub encrypted: bool,
    pub keep: usize,
    pub files: Vec<BackupFile>,
    pub last: Option<LastBackup>,
}

/// `GET /api/local` — 「이 PC」·「백업」 카드가 그리는 것. 키·암호 원문은 없다
#[derive(Serialize, Clone, Debug)]
pub struct LocalInfo {
    pub login: String,
    pub name: String,
    pub llm_api_url: String,
    pub llm_api_key_set: bool,
    pub llm_model: String,
    pub public_base_url: String,
    pub autostart: bool,
    pub data_dir: String,
    pub backup: BackupInfo,
    pub last_op: Option<LastOp>,
}

/// 설정 저장 — 준 칸만 바꾼다(없으면 그대로)
#[derive(Clone, Debug, Default)]
pub struct SettingsChange {
    pub name: Option<String>,
    pub llm_api_url: Option<String>,
    pub llm_api_key: Option<String>,
    pub llm_model: Option<String>,
    pub backup_dir: Option<String>,
    pub backup_password: Option<String>,
}

/// 이 PC의 일 — 처리기가 부른다. 다시 켜기(설정 저장·되살리기·옮기기)는 검사만 하고 runtime에 넘긴다
#[async_trait]
pub trait LocalOps: Send + Sync {
    /// 「이 PC」·「백업」 카드가 그리는 것
    async fn info(&self) -> Result<LocalInfo, Problem>;
    /// 설정 값만 바꾸고 다시 켜기를 건다
    async fn save_settings(&self, change: SettingsChange) -> Result<(), Problem>;
    /// 자동 시작 켜고 끄기
    async fn set_autostart(&self, on: bool) -> Result<(), Problem>;
    /// 지금 백업
    async fn backup_now(&self) -> Result<BackupFile, Problem>;
    /// 백업을 풀어 보고 되살리기를 건다
    async fn restore(&self, name: &str, password: Option<&str>) -> Result<(), Problem>;
    /// 옮길 자리를 보고 옮기기를 건다
    async fn move_to(&self, dir: &str) -> Result<(), Problem>;
}

/// 요청 보내기의 답 (SYNC-API-001#POST/api/local/request) — 머리 이름은 소문자, 본문은 UTF-8(못 읽는 바이트는 대체 문자)
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub struct LocalReply {
    pub status: u16,
    pub headers: indexmap::IndexMap<String, String>,
    pub body: String,
    pub truncated: bool,
    pub ms: u64,
}

/// 요청 보내기 본문 상한 — 넘으면 자르고 `truncated`
pub const REQUEST_MAX_BYTES: usize = 1024 * 1024;

/// SYNC-MS-027#local.request
///
/// 이 PC의 개발 서버(localhost·127.0.0.1·::1)로 요청 하나를 대신 보낸다 — 리다이렉트를 따르지 않고 10초, 본문은 1MB에서
/// 자른다. 주소가 이 PC가 아니면 request-refused, 닿지 못하거나 시간이 지나면 request-failed
pub async fn request(method: &str, url: &str, body: Option<&str>) -> Result<LocalReply, Problem> {
    let refused = || Problem::RequestRefused {
        url: url.to_string(),
    };
    let parsed = url::Url::parse(url).map_err(|_| refused())?;
    let local = matches!(
        parsed.host(),
        Some(url::Host::Domain("localhost"))
            | Some(url::Host::Ipv4(std::net::Ipv4Addr::LOCALHOST))
            | Some(url::Host::Ipv6(std::net::Ipv6Addr::LOCALHOST))
    );
    if !matches!(parsed.scheme(), "http" | "https") || !local {
        return Err(refused());
    }
    let failed = |e: reqwest::Error| Problem::RequestFailed {
        reason: if e.is_timeout() {
            "10초 안에 답이 없다".into()
        } else {
            format!("닿지 못했다: {e}")
        },
    };
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(failed)?;
    let m = reqwest::Method::from_bytes(method.as_bytes()).map_err(|_| refused())?;
    let mut req = client.request(m.clone(), parsed);
    if let Some(b) = body.filter(|_| m != reqwest::Method::GET) {
        req = req
            .header(reqwest::header::CONTENT_TYPE, "application/json")
            .body(b.to_string());
    }
    let t0 = std::time::Instant::now();
    let mut res = req.send().await.map_err(failed)?;
    let status = res.status().as_u16();
    let mut headers: indexmap::IndexMap<String, String> = indexmap::IndexMap::new();
    for (k, v) in res.headers() {
        let v = String::from_utf8_lossy(v.as_bytes()).into_owned();
        headers
            .entry(k.as_str().to_ascii_lowercase())
            .and_modify(|old| {
                old.push_str(", ");
                old.push_str(&v);
            })
            .or_insert(v);
    }
    let mut bytes: Vec<u8> = Vec::new();
    let mut truncated = false;
    while let Some(chunk) = res.chunk().await.map_err(failed)? {
        let room = REQUEST_MAX_BYTES - bytes.len();
        if chunk.len() > room {
            bytes.extend_from_slice(&chunk[..room]);
            truncated = true;
            break;
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(LocalReply {
        status,
        headers,
        body: String::from_utf8_lossy(&bytes).into_owned(),
        truncated,
        ms: t0.elapsed().as_millis() as u64,
    })
}

#[cfg(test)]
mod request_tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    /// 한 번만 답하는 작은 서버 — 답 바이트를 그대로 보낸다
    async fn once(reply: Vec<u8>) -> u16 {
        let l = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("bind");
        let port = l.local_addr().expect("addr").port();
        tokio::spawn(async move {
            if let Ok((mut s, _)) = l.accept().await {
                let mut buf = vec![0u8; 4096];
                let _ = s.read(&mut buf).await;
                let _ = s.write_all(&reply).await;
            }
        });
        port
    }

    #[tokio::test]
    async fn refuses_other_hosts() {
        for url in [
            "http://example.com/",
            "http://10.0.0.1:80/",
            "file:///etc/passwd",
            "nope",
        ] {
            assert!(
                matches!(
                    request("GET", url, None).await,
                    Err(Problem::RequestRefused { .. })
                ),
                "{url}"
            );
        }
    }

    #[tokio::test]
    async fn fails_when_nothing_listens() {
        let l = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = l.local_addr().expect("addr").port();
        drop(l);
        let r = request("GET", &format!("http://127.0.0.1:{port}/"), None).await;
        assert!(matches!(r, Err(Problem::RequestFailed { .. })));
    }

    #[tokio::test]
    async fn does_not_follow_redirects_and_lowercases_headers() {
        let port = once(b"HTTP/1.1 302 Found\r\nLocation: http://example.com/\r\nX-Thing: a\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".to_vec()).await;
        let r = request("POST", &format!("http://localhost:{port}/go"), Some("{}"))
            .await
            .expect("답");
        assert_eq!(r.status, 302);
        assert_eq!(
            r.headers.get("location").map(String::as_str),
            Some("http://example.com/")
        );
        assert_eq!(r.headers.get("x-thing").map(String::as_str), Some("a"));
    }

    #[tokio::test]
    async fn cuts_body_at_one_megabyte() {
        let n = REQUEST_MAX_BYTES + 10;
        let mut reply =
            format!("HTTP/1.1 200 OK\r\nContent-Length: {n}\r\nConnection: close\r\n\r\n")
                .into_bytes();
        reply.extend(std::iter::repeat_n(b'x', n));
        let port = once(reply).await;
        let r = request("GET", &format!("http://127.0.0.1:{port}/"), None)
            .await
            .expect("답");
        assert!(r.truncated && r.body.len() == REQUEST_MAX_BYTES);
    }
}
