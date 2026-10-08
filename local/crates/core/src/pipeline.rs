//! pipeline — 쓰기 조율 (SYNC-MS-017 · SYNC-DOM-004 4.6). 파이썬 판 `core/pipeline.py`와 같은 이름·같은 처리·같은 차례.
//! 여러 서비스를 한 트랜잭션으로 묶고 git과 DB의 차례를 쥔다 — 검사가 다 끝난 뒤에야 git, git이 끝난 뒤에야 DB.
//! 카드 L7 몫은 `mcp` 입구다. 웹(L9)·GitHub·밀린 커밋 처리(L11)는 그 카드가 갈래를 더한다.

use std::collections::HashMap;
use std::sync::{Arc, LazyLock, Mutex};

type Locks = LazyLock<Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>>;

/// 쓰기 락 — 프로젝트 코드마다 하나, 프로세스 전역. 만들고 지우지 않는다(파이썬 `_locks`)
static WRITE_LOCKS: Locks = LazyLock::new(|| Mutex::new(HashMap::new()));

fn lock_in(map: &Locks, code: &str) -> Arc<tokio::sync::Mutex<()>> {
    let mut m = map
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    m.entry(code.to_string()).or_default().clone()
}

/// SYNC-MS-017#pipeline.write_lock
///
/// 저장을 한 줄로 세운다 — 들어온 차례로, 시간 제한 없이(파이썬 `asyncio.Lock`과 같다)
pub fn write_lock(code: &str) -> Arc<tokio::sync::Mutex<()>> {
    lock_in(&WRITE_LOCKS, code)
}
