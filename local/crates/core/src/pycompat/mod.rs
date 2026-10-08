//! 파이썬 호환 — 문자 분류·`repr`·정규식·`difflib`을 파이썬 3.12와 같게 (SYNC-DOM-004 1장 pycompat, 카드 L5).
//! 명세 엔진(SYNC-MS-014)이 파이썬 판과 바이트까지 같으려고 쓴다. 서버의 `compat`도 `repr`을 여기서 쓴다.

pub mod chars;
pub mod difflib;
pub mod re;
pub mod repr;
pub mod unicode;
