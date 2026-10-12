//! 이 PC — 처리기가 부르는 `LocalOps`의 짝 (SYNC-MS-023 · SYNC-DOM-004 4.12, 카드 L16).
//! 다시 켜기(설정 저장·되살리기·옮기기)는 검사만 하고 `Op`를 runtime에 보낸다 — runtime이 서빙을 내린 뒤 그 일을 한다

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use serde_json::Value;
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::git::Git;
use syncdoc_core::types::iso_utc;
use syncdoc_server::local::{
    BackupFile, BackupInfo, LastBackup, LastOp, LocalInfo, LocalOps, SettingsChange,
};
use tokio::sync::mpsc::UnboundedSender;

use crate::backup::{self, Job, Opened};
use crate::{autostart, datadir, settings};

/// runtime에 넘기는 다시 켜기
#[derive(Debug)]
pub enum Op {
    Settings,
    Restore(Opened),
    Move(PathBuf),
}

/// 프로세스 내내 사는 것 — 다시 켜도 남는다
#[derive(Default)]
pub struct Shared {
    pub last_backup: Mutex<Option<LastBackup>>,
    pub last_op: Mutex<Option<LastOp>>,
    /// 「지금 백업」·트레이·하루 한 번을 한 줄로
    pub backup_lock: tokio::sync::Mutex<()>,
}

impl Shared {
    /// 마지막 다시 켜기를 적는다
    pub fn record(&self, kind: &'static str, ok: bool, message: String) {
        tracing::info!("다시 켜기({kind}) — {message}");
        *self
            .last_op
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(LastOp {
            kind,
            ok,
            message,
            at: iso_utc(time::OffsetDateTime::now_utc()),
        });
    }
}

/// 잠금 안의 값을 베낀다 — 독이 들어도 읽는다
fn read<T: Clone>(m: &Mutex<T>) -> T {
    m.lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .clone()
}

/// 백업·되살리기가 부를 PostgreSQL
#[derive(Clone, Debug)]
pub struct PgInfo {
    pub bin: PathBuf,
    pub port: u16,
    pub password: String,
}

/// 이 PC — 켤 때마다 runtime이 만든다
pub struct Local {
    pub data_dir: PathBuf,
    pub pg: PgInfo,
    pub git: Git,
    pub shared: Arc<Shared>,
    pub ops: UnboundedSender<Op>,
}

impl Local {
    fn send(&self, op: Op) -> Result<(), Problem> {
        self.ops.send(op).map_err(|_| Problem::Internal {
            log: "다시 켜기를 받을 곳이 없다".into(),
        })
    }
}

#[async_trait]
impl LocalOps for Local {
    /// SYNC-MS-023#Local.info
    async fn info(&self) -> Result<LocalInfo, Problem> {
        let conf = settings::load(&self.data_dir)?;
        let files = if conf.backup_dir.is_empty() {
            Vec::new()
        } else {
            backup::list(std::path::Path::new(&conf.backup_dir))?
        };
        Ok(LocalInfo {
            login: conf.local_login,
            name: conf.local_name_raw,
            llm_api_url: conf.llm_api_url,
            llm_api_key_set: !conf.llm_api_key.is_empty(),
            llm_model: conf.llm_model,
            public_base_url: conf.public_base_url,
            autostart: autostart::enabled()?,
            data_dir: std::path::absolute(&self.data_dir)?
                .to_string_lossy()
                .into_owned(),
            backup: BackupInfo {
                encrypted: !conf.backup_password.is_empty(),
                dir: conf.backup_dir,
                keep: backup::KEEP,
                files,
                last: read(&self.shared.last_backup),
            },
            last_op: read(&self.shared.last_op),
        })
    }

    /// SYNC-MS-023#Local.save_settings
    async fn save_settings(&self, change: SettingsChange) -> Result<(), Problem> {
        settings::save(&self.data_dir, &change)?;
        self.send(Op::Settings)
    }

    /// SYNC-MS-023#Local.set_autostart
    async fn set_autostart(&self, on: bool) -> Result<(), Problem> {
        autostart::set(on)
    }

    /// SYNC-MS-023#Local.backup_now
    async fn backup_now(&self) -> Result<BackupFile, Problem> {
        let conf = settings::load(&self.data_dir)?;
        if conf.backup_dir.is_empty() {
            return Err(Problem::BackupUnconfigured);
        }
        let _held = self.shared.backup_lock.lock().await;
        let job = Job {
            dir: PathBuf::from(&conf.backup_dir),
            password: conf.backup_password,
            bin: self.pg.bin.clone(),
            port: self.pg.port,
            pg_password: self.pg.password.clone(),
            git: self.git.clone(),
            origins: self.data_dir.join("origins"),
            work: self.data_dir.join("tmp"),
        };
        let made = backup::make(&job).await;
        let at = iso_utc(time::OffsetDateTime::now_utc());
        let last = match &made {
            Ok(f) => {
                tracing::info!("백업 {} ({} 바이트) → {}", f.name, f.size, conf.backup_dir);
                LastBackup {
                    at,
                    name: Some(f.name.clone()),
                    error: None,
                }
            }
            Err(p) => {
                tracing::warn!("백업 실패 — {p}");
                LastBackup {
                    at,
                    name: None,
                    error: Some(p.to_string()),
                }
            }
        };
        *self
            .shared
            .last_backup
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(last);
        made
    }

    /// SYNC-MS-023#Local.restore
    async fn restore(&self, name: &str, password: Option<&str>) -> Result<(), Problem> {
        let conf = settings::load(&self.data_dir)?;
        if conf.backup_dir.is_empty() {
            return Err(Problem::BackupUnconfigured);
        }
        let dir = PathBuf::from(&conf.backup_dir);
        let listed = backup::list(&dir)?.iter().any(|f| f.name == name);
        if name.contains(['/', '\\']) || name.contains("..") || !listed {
            return Err(Problem::NotFound {
                resource: "backup".into(),
                id: Value::from(name),
            });
        }
        let password = password.map_or(conf.backup_password, str::to_string);
        let opened = backup::open(
            &dir.join(name),
            &password,
            &self.pg.bin,
            &self.data_dir.join("restore").join("incoming"),
        )
        .await?;
        self.send(Op::Restore(opened))
    }

    /// SYNC-MS-023#Local.move_to
    async fn move_to(&self, dir: &str) -> Result<(), Problem> {
        let target = datadir::check(&self.data_dir, dir)?;
        self.send(Op::Move(target))
    }
}
