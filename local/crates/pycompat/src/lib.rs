//! 파이썬 호환 — 문자 분류·`repr`·정규식·`difflib`·정수 `set` 차례·`random`·`sum`·`json.dumps`를 파이썬 3.12와 같게 (SYNC-DOM-004 1장 pycompat, 카드 L5·L8·L13·L14).
//! 명세 엔진(SYNC-MS-014)과 코드 그래프(SYNC-MS-022)가 파이썬 판과 바이트까지 같으려고 쓴다 — core는 `pycompat`으로
//! 다시 내보내고 서버의 `compat`도 `repr`을 여기서 쓴다. 맨 밑 crate다(카드 L12에서 core 밖으로).

pub mod chars;
pub mod difflib;
pub mod json;
pub mod pyset;
pub mod pysum;
pub mod random;
pub mod re;
pub mod repr;
pub mod unicode;
