//! 파이썬 호환 층 — 파이썬 판이 쓰는 꾸러미(pydantic·json·FastAPI)의 동작을 옮겨
//! 오류 문장과 값 꼴을 바이트로 같게 한다 (SYNC-DOM-004 1장 compat · SYNC-INFRA-001 9.8).

pub mod fastapi;
pub mod pydantic;
pub mod pyjson;
pub mod pyvalue;
pub mod uvicorn;
