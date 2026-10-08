//! ReferenceService — SYNC-MS-015 (파이썬 판 SYNC-MS-003과 같은 이름·같은 처리). 카드 L6 몫은 세기 하나

use std::collections::HashMap;

use sqlx::PgConnection;

use super::repo;
use crate::errors::Problem;

/// 참조 서비스 — 연결을 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10)
pub struct ReferenceService<'c> {
    pub db: &'c mut PgConnection,
}

impl ReferenceService<'_> {
    /// SYNC-MS-015#ReferenceService.count_missing_by_document
    pub async fn count_missing_by_document(
        &mut self,
        document_ids: &[i32],
    ) -> Result<HashMap<i32, i64>, Problem> {
        if document_ids.is_empty() {
            return Ok(HashMap::new());
        }
        Ok(repo::count_missing_by_document(&mut *self.db, document_ids).await?)
    }
}
