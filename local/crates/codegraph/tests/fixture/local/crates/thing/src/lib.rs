//! 물건 crate

mod repo;
mod service;
mod util;

use crate::service::ThingService;

/// FX-MS-003#thing.top 맨 위 함수
pub fn top() -> usize {
    let svc = ThingService::new();
    svc.count() + util::width()
}
