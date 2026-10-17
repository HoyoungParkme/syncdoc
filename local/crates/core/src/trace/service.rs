//! TraceService — 실행 기록을 받아 두고(최근 300개) 내준다 (SYNC-MS-027 · 파이썬 판 `core/trace/service.py`).
//! 기록을 고치지 않는다 — 비밀 가리기는 기록 도구의 일이다(INFRA C13). 소유 검사는 부르는 쪽이 먼저 한다

use std::collections::BTreeSet;
use std::sync::LazyLock;

use regex::Regex;
use serde_json::Value;
use sqlx::PgConnection;
use time::{Date, Month, OffsetDateTime, PrimitiveDateTime, Time, UtcOffset};

use crate::clock;
use crate::errors::Problem;
use crate::types::{TraceBrief, TraceCoverage, TraceView};

/// 프로젝트마다 남기는 수 (2026-10-12 사용자 결정)
pub const KEEP: i64 = 300;
pub const MAX_EVENTS: usize = 20000;
/// 본문 — 입구가 먼저 본다
pub const MAX_BYTES: usize = 4 * 1024 * 1024;

const BRIEF: &str = "id, trace_key, kind, method, path, status, error, started_at, ms, commit_hash, \
     event_count, truncated, received_at";

type BriefRow = (
    i32,
    String,
    String,
    Option<String>,
    String,
    Option<i32>,
    Option<String>,
    OffsetDateTime,
    i32,
    Option<String>,
    i32,
    bool,
    OffsetDateTime,
);

fn brief(r: BriefRow) -> TraceBrief {
    TraceBrief {
        id: i64::from(r.0),
        trace_key: r.1,
        kind: r.2,
        method: r.3,
        path: r.4,
        status: r.5.map(i64::from),
        error: r.6,
        started_at: r.7,
        ms: i64::from(r.8),
        commit_hash: r.9,
        event_count: i64::from(r.10),
        truncated: r.11,
        received_at: r.12,
    }
}

fn invalid(reason: &str) -> Problem {
    Problem::TraceInvalid {
        reason: reason.to_string(),
        status: 422,
    }
}

static ISO: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]{1,6})?(Z|([+-])([0-9]{2}):([0-9]{2}))?$")
        .expect("ISO")
});

/// `startedAt` — 파이썬 판 `_started`와 같은 꼴(ISO 8601, 소수 6자리까지, Z나 ±hh:mm). 시간대가 없으면 UTC
fn started(text: &str) -> Result<OffsetDateTime, Problem> {
    let bad = || invalid("startedAt — 시각이 아니다");
    let m = ISO.captures(text).ok_or_else(bad)?;
    let n = |i: usize| m[i].parse::<i32>().map_err(|_| bad());
    let month = Month::try_from(u8::try_from(n(2)?).map_err(|_| bad())?).map_err(|_| bad())?;
    let date = Date::from_calendar_date(n(1)?, month, u8::try_from(n(3)?).map_err(|_| bad())?)
        .map_err(|_| bad())?;
    let micro = match m.get(7) {
        Some(f) => {
            let digits = &f.as_str()[1..];
            format!("{digits:0<6}").parse::<u32>().map_err(|_| bad())?
        }
        None => 0,
    };
    let as_u8 = |i: usize| -> Result<u8, Problem> { u8::try_from(n(i)?).map_err(|_| bad()) };
    let time = Time::from_hms_micro(as_u8(4)?, as_u8(5)?, as_u8(6)?, micro).map_err(|_| bad())?;
    let offset = match (m.get(9), m.get(10), m.get(11)) {
        (Some(sign), Some(_), Some(_)) => {
            let (h, mi) = (n(10)?, n(11)?);
            // 파이썬 `timezone` — 24시간보다 작아야 하고 분은 60보다 작아야 한다
            if h >= 24 || mi >= 60 {
                return Err(bad());
            }
            let s = if sign.as_str() == "-" { -1 } else { 1 };
            UtcOffset::from_hms((s * h) as i8, (s * mi) as i8, 0).map_err(|_| bad())?
        }
        _ => UtcOffset::UTC,
    };
    Ok(PrimitiveDateTime::new(date, time)
        .assume_offset(offset)
        .to_offset(UtcOffset::UTC))
}

/// 정수 값이 n인가 — 파이썬 `e["i"] != n`처럼 `1.0`도 1이다
fn is_num(v: &Value, n: i64) -> bool {
    v.as_i64() == Some(n) || v.as_f64() == Some(n as f64)
}

fn num(v: &Value) -> Option<f64> {
    v.as_f64()
}

/// SYNC-DOM-004 4.14 — 실행 기록 묶음 (SYNC-MS-027)
pub struct TraceService<'c> {
    pub db: &'c mut PgConnection,
}

impl TraceService<'_> {
    /// SYNC-MS-027#TraceService.save
    ///
    /// 꼴(부모·차례·startedAt)을 보고 넣는다. 같은 기록(trace_key)은 하나 — 있는 것을 돌려준다. 넣은 뒤 같은
    /// 트랜잭션에서 최근 300개만 남긴다
    pub async fn save(
        &mut self,
        project_id: i32,
        user_id: i32,
        record: &Value,
    ) -> Result<(TraceBrief, bool), Problem> {
        let events = record["events"].as_array().cloned().unwrap_or_default();
        let mut seen: Vec<f64> = Vec::new();
        for (n, e) in events.iter().enumerate() {
            if !is_num(&e["i"], n as i64) {
                return Err(invalid(&format!("events[{n}] — i가 차례가 아니다")));
            }
            let parent = &e["parent"];
            if !is_num(parent, -1) && !num(parent).is_some_and(|p| seen.contains(&p)) {
                return Err(invalid(&format!("events[{n}] — 부모가 없다")));
            }
            seen.extend(num(&e["i"]));
        }
        let started_at = started(record["startedAt"].as_str().unwrap_or_default())?;
        let key = record["id"].as_str().unwrap_or_default();
        let old: Option<BriefRow> = sqlx::query_as(sqlx::AssertSqlSafe(format!(
            "SELECT {BRIEF} FROM traces WHERE project_id = $1 AND trace_key = $2"
        )))
        .bind(project_id)
        .bind(key)
        .fetch_optional(&mut *self.db)
        .await?;
        if let Some(r) = old {
            return Ok((brief(r), false));
        }
        let kind = record["kind"].as_str().unwrap_or_default();
        let method = if kind == "job" {
            None
        } else {
            record["method"].as_str().map(str::to_string)
        };
        let error: Option<String> = record["error"]
            .as_str()
            .map(|e| e.chars().take(300).collect());
        let row: BriefRow = sqlx::query_as(sqlx::AssertSqlSafe(format!(
            "INSERT INTO traces (project_id, user_id, trace_key, kind, method, path, status, error, \
             started_at, ms, commit_hash, event_count, truncated, record, received_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, $15)
             RETURNING {BRIEF}"
        )))
        .bind(project_id)
        .bind(user_id)
        .bind(key)
        .bind(kind)
        .bind(method)
        .bind(record["path"].as_str().unwrap_or_default())
        .bind(record["status"].as_i64().map(|s| s as i32))
        .bind(error)
        .bind(started_at)
        .bind(record["ms"].as_i64().unwrap_or(0) as i32)
        .bind(record["commit"].as_str())
        .bind(events.len() as i32)
        .bind(record["truncated"].as_bool().unwrap_or(false))
        .bind(serde_json::to_string(record).unwrap_or_default())
        .bind(clock::now())
        .fetch_one(&mut *self.db)
        .await?;
        sqlx::query(
            "DELETE FROM traces WHERE project_id = $1 AND id NOT IN (
                 SELECT id FROM traces WHERE project_id = $1
                 ORDER BY received_at DESC, id DESC LIMIT $2)",
        )
        .bind(project_id)
        .bind(KEEP)
        .execute(&mut *self.db)
        .await?;
        Ok((brief(row), true))
    }

    /// SYNC-MS-027#TraceService.list_recent
    pub async fn list_recent(
        &mut self,
        project_id: i32,
        limit: i64,
    ) -> Result<Vec<TraceBrief>, Problem> {
        let rows: Vec<BriefRow> = sqlx::query_as(sqlx::AssertSqlSafe(format!(
            "SELECT {BRIEF} FROM traces WHERE project_id = $1
             ORDER BY received_at DESC, id DESC LIMIT $2"
        )))
        .bind(project_id)
        .bind(limit)
        .fetch_all(&mut *self.db)
        .await?;
        Ok(rows.into_iter().map(brief).collect())
    }

    /// SYNC-MS-027#TraceService.get
    pub async fn get(&mut self, project_id: i32, trace_id: i64) -> Result<TraceView, Problem> {
        let not_found = || Problem::NotFound {
            resource: "trace".into(),
            id: trace_id.to_string().into(),
        };
        let id = i32::try_from(trace_id).map_err(|_| not_found())?;
        let row: Option<(i32, String)> =
            sqlx::query_as("SELECT id, record::text FROM traces WHERE id = $1 AND project_id = $2")
                .bind(id)
                .bind(project_id)
                .fetch_optional(&mut *self.db)
                .await?;
        let Some((_, text)) = row else {
            return Err(not_found());
        };
        let head: BriefRow = sqlx::query_as(sqlx::AssertSqlSafe(format!(
            "SELECT {BRIEF} FROM traces WHERE id = $1"
        )))
        .bind(id)
        .fetch_one(&mut *self.db)
        .await?;
        let record: Value = serde_json::from_str(&text).map_err(|e| Problem::Internal {
            log: format!("traces {id}의 record를 못 읽었다: {e}"),
        })?;
        Ok(TraceView {
            brief: brief(head),
            record,
        })
    }

    /// SYNC-MS-027#TraceService.delete
    pub async fn delete(&mut self, project_id: i32, trace_id: Option<i64>) -> Result<i64, Problem> {
        let done = match trace_id {
            Some(t) => {
                self.get(project_id, t).await?;
                sqlx::query("DELETE FROM traces WHERE project_id = $1 AND id = $2")
                    .bind(project_id)
                    .bind(t as i32)
                    .execute(&mut *self.db)
                    .await?
            }
            None => {
                sqlx::query("DELETE FROM traces WHERE project_id = $1")
                    .bind(project_id)
                    .execute(&mut *self.db)
                    .await?
            }
        };
        Ok(done.rows_affected() as i64)
    }

    /// SYNC-MS-027#TraceService.coverage
    ///
    /// 기록 전부의 사건 — `@`로 시작하지 않는 fn은 함수 열쇠, infra는 (종류, 대상)
    pub async fn coverage(&mut self, project_id: i32) -> Result<TraceCoverage, Problem> {
        let rows: Vec<(Option<String>,)> =
            sqlx::query_as("SELECT (record->'events')::text FROM traces WHERE project_id = $1")
                .bind(project_id)
                .fetch_all(&mut *self.db)
                .await?;
        let mut keys: BTreeSet<String> = BTreeSet::new();
        let mut infra: BTreeSet<(String, String)> = BTreeSet::new();
        for (text,) in &rows {
            let events: Value = text
                .as_deref()
                .and_then(|t| serde_json::from_str(t).ok())
                .unwrap_or(Value::Null);
            for e in events.as_array().into_iter().flatten() {
                let f = e["fn"].as_str().unwrap_or_default();
                if !f.is_empty() && !f.starts_with('@') {
                    keys.insert(f.to_string());
                }
                if let Some(i) = e
                    .get("infra")
                    .filter(|i| i.as_object().is_some_and(|o| !o.is_empty()))
                {
                    let s = |k: &str| i[k].as_str().unwrap_or_default().to_string();
                    infra.insert((s("kind"), s("target")));
                }
            }
        }
        Ok(TraceCoverage {
            traces: rows.len() as i64,
            keys: keys.into_iter().collect(),
            infra: infra.into_iter().collect(),
        })
    }

    /// SYNC-MS-027#TraceService.delete_by_project
    pub async fn delete_by_project(&mut self, project_id: i32) -> Result<(), Problem> {
        sqlx::query("DELETE FROM traces WHERE project_id = $1")
            .bind(project_id)
            .execute(&mut *self.db)
            .await?;
        Ok(())
    }
}
