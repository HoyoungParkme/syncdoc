//! 저장하는 시각 — SYNC-STD-004#DEV-18 (파이썬 판 `core/clock.py`와 같은 규칙).
//! 시스템 시계는 뒤로 튈 수 있다. 직전에 내준 값보다 늘 크게 — 같거나 작으면 1μs를 더한다.
//! 마이크로초까지만 — PostgreSQL `timestamptz`와 파이썬 `datetime`의 정밀도다.

use std::sync::Mutex;

use time::{Duration, OffsetDateTime};

static LAST: Mutex<Option<OffsetDateTime>> = Mutex::new(None);

/// 지금 시각(UTC, μs). 직전 값보다 반드시 크다
pub fn now() -> OffsetDateTime {
    let t = OffsetDateTime::now_utc();
    let t = t.replace_nanosecond(t.microsecond() * 1_000).unwrap_or(t);
    let mut last = LAST.lock().unwrap_or_else(|e| e.into_inner());
    let t = match *last {
        Some(prev) if t <= prev => prev + Duration::microseconds(1),
        _ => t,
    };
    *last = Some(t);
    t
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn never_goes_back() {
        let mut prev = now();
        for _ in 0..10_000 {
            let t = now();
            assert!(t > prev);
            assert_eq!(t.nanosecond() % 1_000, 0);
            prev = t;
        }
    }
}
