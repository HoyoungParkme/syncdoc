//! 열거형·DTO — SYNC-DOM-002 2.7·2.8 그대로 (Rust는 `syncdoc_core::types`).
//! 직렬화 이름(JSON 키·열거형 값)도 파이썬 판과 같다.

use time::OffsetDateTime;

use crate::account::model::AccessTokenRow;

/// 사용자 종류 — `users.kind`. DB enum이 아니라 varchar + 앱 검증 (SYNC-DOM-003)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UserKind {
    Github,
    Local,
    Placeholder,
}

impl UserKind {
    pub fn as_str(self) -> &'static str {
        match self {
            UserKind::Github => "github",
            UserKind::Local => "local",
            UserKind::Placeholder => "placeholder",
        }
    }
}

/// 토큰 발급 결과 — 원문(`raw`)은 이 값에만 있다 (SYNC-DOM-002 2.8 `IssuedToken`)
#[derive(Clone, Debug)]
pub struct IssuedToken {
    pub token: AccessTokenRow,
    pub raw: String,
}

/// API의 시각 — ISO 8601 UTC. 마이크로초 여섯 자리(0이면 뺀다), 끝은 `Z`.
/// 파이썬 판(pydantic)이 내는 바이트와 같다 — `2026-10-07T03:00:00.123456Z`
pub fn iso_utc(t: OffsetDateTime) -> String {
    let t = t.to_offset(time::UtcOffset::UTC);
    let micro = t.microsecond();
    let frac = if micro == 0 {
        String::new()
    } else {
        format!(".{micro:06}")
    };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}{frac}Z",
        t.year(),
        u8::from(t.month()),
        t.day(),
        t.hour(),
        t.minute(),
        t.second()
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use time::macros::datetime;

    #[test]
    fn iso_utc_like_pydantic() {
        assert_eq!(
            iso_utc(datetime!(2026-10-07 03:00:00.123456 UTC)),
            "2026-10-07T03:00:00.123456Z"
        );
        assert_eq!(
            iso_utc(datetime!(2026-10-07 03:00:00 UTC)),
            "2026-10-07T03:00:00Z"
        );
        assert_eq!(
            iso_utc(datetime!(2026-10-07 12:00:00.000010 +09:00)),
            "2026-10-07T03:00:00.000010Z"
        );
    }
}
