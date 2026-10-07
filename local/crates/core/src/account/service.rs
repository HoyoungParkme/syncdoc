//! AccountService — SYNC-MS-016 (파이썬 판 SYNC-MS-006과 같은 이름·같은 처리)

use sqlx::PgConnection;

use super::model::UserRow;
use super::repo;
use crate::errors::Problem;

/// 사용자·토큰 서비스 — 연결을 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10)
pub struct AccountService<'c> {
    pub db: &'c mut PgConnection,
}

impl AccountService<'_> {
    /// SYNC-MS-016#AccountService.ensure_local_user
    pub async fn ensure_local_user(
        &mut self,
        login: &str,
        display_name: &str,
    ) -> Result<UserRow, Problem> {
        let u = repo::local_user(&mut *self.db).await?;
        let other = repo::user_by_login(&mut *self.db, login).await?;
        if let Some(o) = &other
            && u.as_ref().is_none_or(|u| u.id != o.id)
        {
            return Err(Problem::Internal {
                log: format!("LOCAL_LOGIN {login}은 이미 다른 사용자다 — 다른 아이디로"),
            });
        }
        match u {
            Some(u) => Ok(repo::rename(&mut *self.db, u.id, login, display_name).await?),
            None => Ok(repo::add_local_user(&mut *self.db, login, display_name).await?),
        }
    }

    /// SYNC-MS-016#AccountService.local_user
    pub async fn local_user(
        &mut self,
        login: &str,
        display_name: &str,
    ) -> Result<UserRow, Problem> {
        match repo::local_user(&mut *self.db).await? {
            Some(u) => Ok(u),
            None => self.ensure_local_user(login, display_name).await,
        }
    }
}
