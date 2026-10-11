//! 서비스

use std::sync::Arc;

use crate::repo::Repo;
use crate::util::{self as u, width as w};
use super::util::*;

pub struct ThingService {
    repo: Arc<Repo>,
    spare: Option<Box<Repo>>,
}

pub trait Count {
    fn count(&self) -> usize;
}

impl ThingService {
    /// FX-MS-003#ThingService.new
    pub fn new() -> Self {
        ThingService { repo: Arc::new(Repo::new()), spare: None }
    }

    /// FX-MS-003#ThingService.find 찾기
    #[allow(dead_code)]
    #[inline]
    pub fn find(&self, id: usize) -> usize {
        let r = Repo::new();
        let found = r.find(id);
        let n: usize = w() + u::width() + pad();
        self.repo.find(id).map_or(n, |_| Self::helper(found.is_some()))
    }

    fn helper(b: bool) -> usize {
        usize::from(b)
    }
}

impl<T: Clone> Count for Wrapper<T> {
    fn count(&self) -> usize {
        1
    }
}

impl Count for ThingService {
    // 보통 주석
    /// FX-MS-003#ThingService.count
    fn count(&self) -> usize {
        self.find(0)
    }
}

pub struct Wrapper<T>(T);

#[cfg(test)]
mod tests {
    #[test]
    fn counts() {
        assert_eq!(1, 1);
    }
}
