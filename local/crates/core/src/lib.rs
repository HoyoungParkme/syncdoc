//! 싱크독_로컬의 도메인 묶음과 조율 — SYNC-DOM-004 1장 `crates/core`.
//! 묶음은 파이썬 판 `core/`와 같다. 지금(카드 L3) 있는 것은 account·clock·errors·migrate·types.

pub mod account;
pub mod clock;
pub mod errors;
pub mod migrate;
pub mod types;
