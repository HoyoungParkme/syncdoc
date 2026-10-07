//! 이전 SQL — Alembic이 유일한 원본이다 (SYNC-STD-004#DEV-7 · SYNC-INFRA-001 9.2).
//! `local/migrations/NNNN_*.sql`은 `cargo xtask migrations`가 리비전마다 `alembic upgrade --sql`로
//! 만든 것이고, build.rs가 실행 파일에 담는다. 같은 `alembic_version` 표로 어디까지 올렸는지 안다.

use sqlx::PgConnection;

use crate::errors::Problem;

include!(concat!(env!("OUT_DIR"), "/migrations.rs"));

/// SYNC-MS-012#migrate.apply
pub async fn apply(db: &mut PgConnection) -> Result<Vec<&'static str>, Problem> {
    let start = match current_revision(db).await? {
        None => 0,
        Some(v) => match MIGRATIONS.iter().position(|(rev, _, _)| *rev == v) {
            Some(i) => i + 1,
            None => {
                return Err(Problem::Internal {
                    log: format!("DB가 이 프로그램보다 새 판이다(리비전 {v}) — 새 판을 설치한다"),
                });
            }
        },
    };
    let mut done = Vec::new();
    for (rev, name, sql) in &MIGRATIONS[start..] {
        // 파일마다 제 BEGIN·COMMIT을 들고 있다 — 파일 하나가 한 트랜잭션 (DEV-10의 예외)
        if let Err(e) = sqlx::raw_sql(*sql).execute(&mut *db).await {
            let _ = sqlx::raw_sql("ROLLBACK").execute(&mut *db).await;
            return Err(Problem::Internal {
                log: format!("이전 {name}에서 멈췄다 — {e}"),
            });
        }
        done.push(*rev);
    }
    Ok(done)
}

/// 지금 리비전 — 표가 없으면 처음(None), 행이 하나가 아니면 문제
async fn current_revision(db: &mut PgConnection) -> Result<Option<String>, Problem> {
    let exists: bool =
        sqlx::query_scalar("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            .fetch_one(&mut *db)
            .await?;
    if !exists {
        return Ok(None);
    }
    let rows: Vec<String> = sqlx::query_scalar("SELECT version_num FROM alembic_version")
        .fetch_all(&mut *db)
        .await?;
    match rows.as_slice() {
        [v] => Ok(Some(v.clone())),
        _ => Err(Problem::Internal {
            log: format!("alembic_version 행이 {}개다 — 하나여야 한다", rows.len()),
        }),
    }
}
