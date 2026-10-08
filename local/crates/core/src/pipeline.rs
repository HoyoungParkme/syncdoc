//! pipeline — 쓰기 조율 (SYNC-MS-017 · SYNC-DOM-004 4.6). 파이썬 판 `core/pipeline.py`와 같은 이름·같은 처리·같은 차례.
//! 여러 서비스를 한 트랜잭션으로 묶고 git과 DB의 차례를 쥔다 — 검사가 다 끝난 뒤에야 git, git이 끝난 뒤에야 DB.
//! 카드 L7 몫은 `mcp` 입구다. 웹(L9)·GitHub·밀린 커밋 처리(L11)는 그 카드가 갈래를 더한다.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, LazyLock, Mutex};
use std::time::Duration;

use sqlx::PgPool;

use crate::account::model::UserRow;
use crate::clock;
use crate::errors::Problem;
use crate::project::repo as project_repo;
use crate::project::service::{ProjectService, ServerRepos};

type Locks = LazyLock<Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>>;

/// 쓰기 락 — 프로젝트 코드마다 하나, 프로세스 전역. 만들고 지우지 않는다(파이썬 `_locks`)
static WRITE_LOCKS: Locks = LazyLock::new(|| Mutex::new(HashMap::new()));

/// 읽기 락 — 쓰기 락과 따로인 지도. fetch와 커밋 처리를 저장소마다 한 줄로(#194)
static READ_LOCKS: Locks = LazyLock::new(|| Mutex::new(HashMap::new()));

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

/// SYNC-MS-017#pipeline.read_lock
///
/// 쓰기 락과 다른 락이다 — 커밋 처리가 파일마다 쓰기 락을 잡는다. 같은 락이면 교착한다
pub fn read_lock(code: &str) -> Arc<tokio::sync::Mutex<()>> {
    lock_in(&READ_LOCKS, code)
}

/// SYNC-MS-017#pipeline.wait_idle
///
/// 끌 때 — 지금까지 만든 쓰기 락을 차례로 잡아 본다. 다 잡으면 `true`, `limit`이 지나면 `false` (INFRA 9.1)
pub async fn wait_idle(limit: Duration) -> bool {
    let locks: Vec<_> = WRITE_LOCKS
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .values()
        .cloned()
        .collect();
    tokio::time::timeout(limit, async {
        for l in locks {
            drop(l.lock().await);
        }
    })
    .await
    .is_ok()
}

/// SYNC-MS-017#pipeline.read_pending
///
/// 저장소에 쓰기 전에 밀린 커밋을 먼저 읽는다(DEV-19). **쓰기 락 밖에서 부른다**.
/// 밀린 것이 있으면 카드 L11(커밋 처리)까지 저장하지 않는다(사용자 결정 2026-10-08)
pub async fn read_pending(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
) -> Result<i64, Problem> {
    let (_, repo) = {
        let mut c = pool.acquire().await?;
        // 쓰기 경로의 소유 검사를 겸한다
        ProjectService { db: &mut c, repos }
            .get_owned(code, user)
            .await?
    };
    let lock = read_lock(code);
    let _held = lock.lock().await;
    // 락 안에서 다시 읽는다 — 앞서 기다린 요청이 이미 따라잡아 놨을 수 있다
    let last = {
        let mut c = pool.acquire().await?;
        project_repo::last_processed_of(&mut c, repo.id)
            .await?
            .flatten()
    };
    let head = repos.git.fetch(Path::new(&repo.workdir_path)).await?;
    // 처리 지점이 없는 것은 등록 중뿐이다 — 등록이 스스로 저장소를 읽는다
    if last.as_deref().is_none_or(|l| l == head) {
        if last.is_some() {
            let mut c = pool.acquire().await?;
            project_repo::set_fetched(&mut c, repo.id, clock::now()).await?;
        }
        return Ok(0);
    }
    Err(Problem::NotImplemented {
        card: "L11".to_string(),
    })
}
