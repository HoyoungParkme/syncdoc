//! AccountService — SYNC-MS-016 (파이썬 판 SYNC-MS-006과 같은 이름·같은 처리)

use std::collections::HashMap;

use rand::RngExt;
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::PgConnection;

use super::model::{AccessTokenRow, UserRow};
use super::repo;
use crate::clock;
use crate::errors::Problem;
use crate::types::{IssuedToken, UserRef};

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

    /// SYNC-MS-016#AccountService.list_tokens
    pub async fn list_tokens(&mut self, user: &UserRow) -> Result<Vec<AccessTokenRow>, Problem> {
        Ok(repo::tokens_of(&mut *self.db, user.id).await?)
    }

    /// SYNC-MS-016#AccountService.issue_token
    pub async fn issue_token(
        &mut self,
        user: &UserRow,
        label: &str,
    ) -> Result<IssuedToken, Problem> {
        let mut bytes = [0u8; 32];
        rand::rng().fill(&mut bytes);
        let raw = format!("syncdoc_pat_{}", base64url(&bytes));
        let token = repo::add_token(
            &mut *self.db,
            user.id,
            &sha256_hex(&raw),
            label,
            clock::now(),
        )
        .await?;
        Ok(IssuedToken { token, raw })
    }

    /// SYNC-MS-016#AccountService.revoke_token
    pub async fn revoke_token(&mut self, user: &UserRow, token_id: i64) -> Result<(), Problem> {
        // 파이썬 판은 id를 int4로 넘긴다 — 그 밖이면 DB가 거절한다(integer out of range)
        let Ok(id) = i32::try_from(token_id) else {
            return Err(Problem::Internal {
                log: format!("access_tokens.id {token_id}: integer out of range"),
            });
        };
        let Some(t) = repo::token_of_user(&mut *self.db, id, user.id).await? else {
            return Err(Problem::NotFound {
                resource: "access_token".into(),
                id: Value::from(token_id),
            });
        };
        repo::set_revoked(&mut *self.db, t.id, clock::now()).await?;
        Ok(())
    }

    /// SYNC-MS-016#AccountService.authenticate_token
    pub async fn authenticate_token(&mut self, raw: &str) -> Result<Option<UserRow>, Problem> {
        let Some(t) = repo::token_by_hash(&mut *self.db, &sha256_hex(raw)).await? else {
            return Ok(None);
        };
        let now = clock::now();
        if t.revoked_at.is_some() || t.expires_at.is_some_and(|e| e < now) {
            return Ok(None);
        }
        let Some(u) = repo::user_by_id(&mut *self.db, t.user_id).await? else {
            return Ok(None);
        };
        repo::set_last_used(&mut *self.db, t.id, clock::now()).await?;
        Ok(Some(u))
    }

    /// SYNC-MS-016#AccountService.users_by_ids
    pub async fn users_by_ids(&mut self, ids: &[i32]) -> Result<HashMap<i32, UserRef>, Problem> {
        if ids.is_empty() {
            return Ok(HashMap::new());
        }
        Ok(repo::users_by_ids(&mut *self.db, ids)
            .await?
            .into_iter()
            .map(|u| {
                let r = UserRef {
                    id: u.id,
                    github_login: u.github_login,
                    display_name: u.display_name,
                };
                (r.id, r)
            })
            .collect())
    }
}

/// 원문 → 저장하는 해시 (파이썬 `hashlib.sha256(raw.encode()).hexdigest()`)
pub fn sha256_hex(raw: &str) -> String {
    Sha256::digest(raw.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// base64url, 채움 없음 — 파이썬 `secrets.token_urlsafe`
fn base64url(bytes: &[u8]) -> String {
    const A: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let n = chunk
            .iter()
            .enumerate()
            .fold(0u32, |n, (i, &b)| n | (u32::from(b) << (16 - 8 * i)));
        for i in 0..=chunk.len() {
            out.push(char::from(A[((n >> (18 - 6 * i)) & 63) as usize]));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64url_like_python() {
        assert_eq!(base64url(b""), "");
        assert_eq!(base64url(b"f"), "Zg");
        assert_eq!(base64url(b"fo"), "Zm8");
        assert_eq!(base64url(b"foo"), "Zm9v");
        assert_eq!(base64url(&[0xfb, 0xff]), "-_8");
        assert_eq!(base64url(&[0u8; 32]).len(), 43);
    }

    #[test]
    fn sha256_hex_like_python() {
        assert_eq!(
            sha256_hex("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
