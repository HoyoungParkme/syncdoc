//! 백업 — 만들기·목록·풀어 보기·되살리기·하루 한 번 (SYNC-MS-023 · SYNC-INFRA-001 6.1·9.6, 카드 L16).
//! 꼴은 Docker 묶음(카드 BR, `scripts/backup.sh`)과 같다 — tar 하나에 `db.dump`(`pg_dump -Fc`)와
//! `origins.tar`(항목 `origins/…`), 암호가 있으면 OpenPGP 대칭 암호(SEIPDv1·AES256 — `gpg --symmetric`과 서로 풀린다).
//! 그래서 Docker 묶음의 백업을 되살리고, 이 백업을 `gpg -d`·`pg_restore`로도 푼다

use std::ffi::OsStr;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use pgp::composed::{DecryptionOptions, Message, MessageBuilder, TheRing};
use pgp::crypto::sym::SymmetricKeyAlgorithm;
use pgp::types::{Password, Seipdv1ReadMode, StringToKey};
use sqlx::{Connection, PgConnection};
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::git::Git;
use syncdoc_core::migrate;
use syncdoc_server::local::{BackupFile, LocalOps};
use tokio::process::Command;

use crate::local::Local;
use crate::pg::{self, PgServer};
use crate::settings;

/// 남기는 수 — 카드 BR의 `BACKUP_KEEP` 기본값
pub const KEEP: usize = 14;

/// 백업 하나를 만드는 데 드는 것
pub struct Job {
    /// 백업 폴더
    pub dir: PathBuf,
    /// 비면 암호 없이(.tar)
    pub password: String,
    /// PostgreSQL 바이너리 자리(`bin/`)
    pub bin: PathBuf,
    pub port: u16,
    pub pg_password: String,
    pub git: Git,
    /// 서버 저장소 자리 `origins/`
    pub origins: PathBuf,
    /// 작업 자리 — 이 아래에 임시 폴더를 만들고 지운다
    pub work: PathBuf,
}

/// 풀어 본 백업 — 되살리기가 쓴다
#[derive(Debug)]
pub struct Opened {
    pub name: String,
    pub dump: PathBuf,
    pub origins: PathBuf,
}

fn failed(reason: impl Into<String>) -> Problem {
    Problem::BackupFailed {
        reason: reason.into(),
    }
}

fn invalid(reason: impl Into<String>) -> Problem {
    Problem::BackupInvalid {
        reason: reason.into(),
    }
}

/// 마지막 다섯 줄을 한 줄로
fn tail(text: &str) -> String {
    let lines: Vec<&str> = text.lines().rev().take(5).collect();
    lines.into_iter().rev().collect::<Vec<_>>().join(" / ")
}

/// 함께 담은 PostgreSQL 도구 — 성공이면 표준 출력, 실패면 표준 오류 끝. 암호는 환경 변수로만
async fn pg_tool(
    bin: &Path,
    tool: &str,
    conn: Option<(u16, &str)>,
    args: &[&OsStr],
) -> Result<String, String> {
    let mut cmd = Command::new(pg::exe(bin, tool));
    if let Some((port, password)) = conn {
        cmd.args(["-h", "127.0.0.1", "-p", &port.to_string(), "-U", "syncdoc"])
            .env("PGPASSWORD", password);
    }
    cmd.args(args)
        .stdin(std::process::Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let out = cmd.output().await.map_err(|e| e.to_string())?;
    if out.status.success() {
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    } else {
        Err(tail(&String::from_utf8_lossy(&out.stderr)))
    }
}

/// 이 PC의 지역 시각 — `%Y%m%d-%H%M%S` (BR의 `date`와 같은 꼴)
fn stamp() -> String {
    jiff::Zoned::now().strftime("%Y%m%d-%H%M%S").to_string()
}

/// 오늘(지역 날짜) 이름 머리 — `syncdoc-{YYYYMMDD}-`
fn today_prefix() -> String {
    format!("syncdoc-{}-", jiff::Zoned::now().strftime("%Y%m%d"))
}

/// 서버 저장소 사진 — 저장소마다 거울 복제(쓰기를 멈추지 않는다)
async fn snapshot(git: &Git, origins: &Path, dest: &Path) -> Result<(), Problem> {
    fs::create_dir_all(dest)?;
    for sub in ["", "_archive"] {
        let dir = origins.join(sub);
        if !dir.is_dir() {
            continue;
        }
        let mut names: Vec<_> = fs::read_dir(&dir)?
            .filter_map(Result::ok)
            .filter(|e| e.path().is_dir())
            .map(|e| e.file_name())
            .filter(|n| n.to_string_lossy().ends_with(".git"))
            .collect();
        names.sort();
        for n in names {
            git.mirror(&dir.join(&n), &dest.join(sub).join(&n)).await?;
        }
    }
    Ok(())
}

/// 바깥 tar를 `out`에 — 암호가 있으면 OpenPGP로 감싼다
fn write_outer(dump: &Path, origins_tar: &Path, password: &str, out: &Path) -> Result<(), Problem> {
    let plain = if password.is_empty() {
        out.to_path_buf()
    } else {
        out.with_extension("plain")
    };
    {
        let mut b = tar::Builder::new(BufWriter::new(File::create(&plain)?));
        b.append_path_with_name(dump, "db.dump")?;
        b.append_path_with_name(origins_tar, "origins.tar")?;
        b.into_inner()?.flush()?;
    }
    if !password.is_empty() {
        let done = encrypt(&plain, password, out);
        let _ = fs::remove_file(&plain);
        done?;
    }
    Ok(())
}

/// OpenPGP 대칭 암호 — SEIPDv1·AES256·iterated+salted S2K(gpg와 같은 꼴)
fn encrypt(plain: &Path, password: &str, out: &Path) -> Result<(), Problem> {
    let mut rng = rand_08::thread_rng();
    let mut b = MessageBuilder::from_file(plain).seipd_v1(&mut rng, SymmetricKeyAlgorithm::AES256);
    b.encrypt_with_password(
        StringToKey::new_default(&mut rng),
        &Password::from(password),
    )
    .map_err(|e| failed(format!("암호화하지 못했다 — {e}")))?;
    let mut w = BufWriter::new(File::create(out)?);
    b.to_writer(&mut rng, &mut w)
        .map_err(|e| failed(format!("암호화하지 못했다 — {e}")))?;
    w.flush()?;
    Ok(())
}

/// OpenPGP를 풀어 `out`에 — 끝까지 읽어야 무결성(MDC)이 맞는지 안다
fn decrypt(file: &Path, password: &str, out: &Path) -> Result<(), Problem> {
    let msg = Message::from_file(file).map_err(|e| invalid(format!("깨졌다 — {e}")))?;
    let pw = Password::from(password);
    let ring = TheRing {
        message_password: vec![&pw],
        decrypt_options: DecryptionOptions::new().set_seipdv1_read_mode(Seipdv1ReadMode::Streaming),
        ..Default::default()
    };
    let (msg, _) = msg
        .decrypt_the_ring(ring, true)
        .map_err(|_| invalid("암호가 틀리다"))?;
    let mut msg = if msg.is_compressed() {
        msg.decompress()
            .map_err(|e| invalid(format!("깨졌다 — {e}")))?
    } else {
        msg
    };
    let mut w = BufWriter::new(File::create(out)?);
    std::io::copy(&mut msg, &mut w).map_err(|e| invalid(format!("깨졌다 — {e}")))?;
    w.flush()?;
    Ok(())
}

/// 경로가 `.`·이름 조각뿐인가 — 절대 경로·`..`가 없다
fn plain_path(p: &Path) -> bool {
    p.components()
        .all(|c| matches!(c, Component::Normal(_) | Component::CurDir))
}

/// `origins.tar`를 `dest`에 푼다 — `origins/` 아래 보통 파일·폴더만
fn untar_origins(tar: &Path, dest: &Path) -> Result<(), Problem> {
    let mut a = tar::Archive::new(File::open(tar)?);
    for entry in a.entries()? {
        let mut e = entry?;
        let kind = e.header().entry_type();
        let path = e.path()?.into_owned();
        if !(kind.is_file() || kind.is_dir()) || !plain_path(&path) {
            continue;
        }
        let to = dest.join(&path);
        if kind.is_dir() {
            fs::create_dir_all(&to)?;
        } else {
            if let Some(parent) = to.parent() {
                fs::create_dir_all(parent)?;
            }
            e.unpack(&to)?;
        }
    }
    Ok(())
}

/// `origins.tar`의 항목이 모두 `origins/` 아래 보통 파일·폴더인가
fn origins_ok(tar: &Path) -> Result<bool, Problem> {
    let mut a = tar::Archive::new(File::open(tar)?);
    for entry in a.entries()? {
        let e = entry?;
        let kind = e.header().entry_type();
        let path = e.path()?.into_owned();
        let first = path
            .components()
            .find(|c| !matches!(c, Component::CurDir))
            .map(|c| c.as_os_str().to_os_string());
        if !(kind.is_file() || kind.is_dir())
            || !plain_path(&path)
            || first.as_deref() != Some(OsStr::new("origins"))
        {
            return Ok(false);
        }
    }
    Ok(true)
}

/// 바깥 tar에서 `db.dump`·`origins.tar`를 `work`로 꺼낸다 — 다른 항목은 둔다
fn unpack_outer(tar: &Path, work: &Path) -> Result<(), Problem> {
    let mut a = tar::Archive::new(File::open(tar)?);
    let entries = a.entries().map_err(|e| invalid(format!("깨졌다 — {e}")))?;
    for entry in entries {
        let mut e = entry.map_err(|e| invalid(format!("깨졌다 — {e}")))?;
        if !e.header().entry_type().is_file() {
            continue;
        }
        let path = e.path()?.into_owned();
        let name: Vec<_> = path
            .components()
            .filter(|c| !matches!(c, Component::CurDir))
            .collect();
        if let [Component::Normal(n)] = name.as_slice()
            && matches!(n.to_str(), Some("db.dump" | "origins.tar"))
        {
            e.unpack(work.join(n))
                .map_err(|e| invalid(format!("깨졌다 — {e}")))?;
        }
    }
    Ok(())
}

async fn blocking<T: Send + 'static>(
    f: impl FnOnce() -> Result<T, Problem> + Send + 'static,
) -> Result<T, Problem> {
    tokio::task::spawn_blocking(f)
        .await
        .map_err(|e| Problem::Internal {
            log: format!("백업 일이 멈췄다 — {e}"),
        })?
}

/// SYNC-MS-023#backup.make
pub async fn make(job: &Job) -> Result<BackupFile, Problem> {
    fs::create_dir_all(&job.dir).map_err(|e| failed(format!("폴더에 쓰지 못했다 — {e}")))?;
    fs::create_dir_all(&job.work)?;
    let tmp = tempfile::Builder::new()
        .prefix("backup-")
        .tempdir_in(&job.work)?;
    // 1. 덤프가 먼저 — 원본이 DB보다 앞서면 되살린 뒤 켤 때의 따라잡기가 메운다
    let dump = tmp.path().join("db.dump");
    pg_tool(
        &job.bin,
        "pg_dump",
        Some((job.port, &job.pg_password)),
        &[
            OsStr::new("-d"),
            OsStr::new("syncdoc"),
            OsStr::new("-Fc"),
            OsStr::new("-f"),
            dump.as_os_str(),
        ],
    )
    .await
    .map_err(|e| failed(format!("DB 덤프 실패 — {e}")))?;
    // 2. 서버 저장소 사진 → origins.tar(항목 origins/…)
    let snap = tmp.path().join("origins");
    snapshot(&job.git, &job.origins, &snap)
        .await
        .map_err(|e| failed(format!("서버 저장소 묶기 실패 — {e}")))?;
    let origins_tar = tmp.path().join("origins.tar");
    {
        let (snap, out) = (snap.clone(), origins_tar.clone());
        blocking(move || {
            let mut b = tar::Builder::new(BufWriter::new(File::create(&out)?));
            b.follow_symlinks(false);
            b.append_dir_all("origins", &snap)?;
            b.into_inner()?.flush()?;
            Ok(())
        })
        .await
        .map_err(|e| failed(format!("서버 저장소 묶기 실패 — {e}")))?;
    }
    // 3. 이름 — 같은 초에 있으면 1초 뒤로
    let ext = if job.password.is_empty() {
        ".tar"
    } else {
        ".tar.gpg"
    };
    let name = loop {
        let n = format!("syncdoc-{}{ext}", stamp());
        if !job.dir.join(&n).exists() {
            break n;
        }
        tokio::time::sleep(Duration::from_millis(1000)).await;
    };
    // 4. .part에 쓰고 이름을 바꾼다 — 반쯤 쓴 것이 백업 이름으로 남지 않게
    let part = job.dir.join(format!("{name}.part"));
    let fin = job.dir.join(&name);
    {
        let (password, part2) = (job.password.clone(), part.clone());
        let done = blocking(move || write_outer(&dump, &origins_tar, &password, &part2)).await;
        if let Err(p) = done {
            let _ = fs::remove_file(&part);
            return Err(match p {
                p @ Problem::BackupFailed { .. } => p,
                other => failed(format!("폴더에 쓰지 못했다 — {other}")),
            });
        }
    }
    fs::rename(&part, &fin).map_err(|e| failed(format!("폴더에 쓰지 못했다 — {e}")))?;
    // 5. 최근 KEEP개만 — 이름 순이 시각 순(Docker 묶음의 것도 같은 이름)
    for old in list(&job.dir)?.into_iter().skip(KEEP) {
        let _ = fs::remove_file(job.dir.join(&old.name));
    }
    let size = fs::metadata(&fin)?.len();
    Ok(BackupFile {
        encrypted: name.ends_with(".gpg"),
        name,
        size,
    })
}

/// SYNC-MS-023#backup.list
pub fn list(dir: &Path) -> Result<Vec<BackupFile>, Problem> {
    if !dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let Ok(name) = entry.file_name().into_string() else {
            continue;
        };
        if !name.starts_with("syncdoc-")
            || !(name.ends_with(".tar") || name.ends_with(".tar.gpg"))
            || !entry.file_type()?.is_file()
        {
            continue;
        }
        out.push(BackupFile {
            size: entry.metadata()?.len(),
            encrypted: name.ends_with(".gpg"),
            name,
        });
    }
    out.sort_by(|a, b| b.name.cmp(&a.name));
    Ok(out)
}

/// SYNC-MS-023#backup.open
pub async fn open(file: &Path, password: &str, bin: &Path, work: &Path) -> Result<Opened, Problem> {
    let name = file
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let _ = fs::remove_dir_all(work);
    fs::create_dir_all(work)?;
    let outer = if name.ends_with(".gpg") {
        if password.is_empty() {
            return Err(invalid("암호가 필요하다"));
        }
        let (file, password, out) = (
            file.to_path_buf(),
            password.to_string(),
            work.join("backup.tar"),
        );
        let out2 = out.clone();
        blocking(move || decrypt(&file, &password, &out2)).await?;
        out
    } else {
        file.to_path_buf()
    };
    {
        let (outer2, work2) = (outer.clone(), work.to_path_buf());
        blocking(move || unpack_outer(&outer2, &work2)).await?;
    }
    if outer.starts_with(work) {
        let _ = fs::remove_file(&outer);
    }
    let (dump, origins) = (work.join("db.dump"), work.join("origins.tar"));
    if !(dump.is_file() && origins.is_file()) {
        return Err(invalid("싱크독 백업이 아니다 — db.dump·origins.tar가 없다"));
    }
    pg_tool(
        bin,
        "pg_restore",
        None,
        &[OsStr::new("--list"), dump.as_os_str()],
    )
    .await
    .map_err(|e| invalid(format!("DB 덤프를 읽지 못한다 — {e}")))?;
    let o = origins.clone();
    if !blocking(move || origins_ok(&o)).await? {
        return Err(invalid("서버 저장소 묶음이 맞지 않다"));
    }
    Ok(Opened {
        name,
        dump,
        origins,
    })
}

/// 덤프를 DB에 — `public` 스키마를 비우고 한 트랜잭션으로(덤프에 없는 표가 남지 않는다)
async fn load_dump(pg: &PgServer, dump: &Path) -> Result<(), Problem> {
    let mut c = PgConnection::connect_with(&pg.options).await?;
    sqlx::raw_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        .execute(&mut c)
        .await?;
    c.close().await?;
    pg_tool(
        &pg.bin,
        "pg_restore",
        Some((pg.port, &pg.password)),
        &[
            OsStr::new("-d"),
            OsStr::new("syncdoc"),
            OsStr::new("--no-owner"),
            OsStr::new("--no-privileges"),
            OsStr::new("--single-transaction"),
            OsStr::new("--exit-on-error"),
            dump.as_os_str(),
        ],
    )
    .await
    .map_err(|e| Problem::Internal {
        log: format!("DB를 되돌리지 못했다 — {e}"),
    })?;
    Ok(())
}

/// SYNC-MS-023#backup.restore
pub async fn restore(opened: &Opened, pg: &PgServer, data_dir: &Path) -> Result<(), Problem> {
    let base = data_dir.join("restore");
    let previous = base.join("previous");
    let _ = fs::remove_dir_all(&previous);
    fs::create_dir_all(&previous)?;
    // 1. 옆에 두기 — 실패하면 아무것도 바꾸지 않은 채 끝
    let saved = previous.join("db.dump");
    pg_tool(
        &pg.bin,
        "pg_dump",
        Some((pg.port, &pg.password)),
        &[
            OsStr::new("-d"),
            OsStr::new("syncdoc"),
            OsStr::new("-Fc"),
            OsStr::new("-f"),
            saved.as_os_str(),
        ],
    )
    .await
    .map_err(|e| Problem::Internal {
        log: format!("지금 DB를 옆에 두지 못했다 — {e}"),
    })?;
    let origins = data_dir.join("origins");
    let kept = previous.join("origins");
    if origins.exists() {
        fs::rename(&origins, &kept)?;
    }
    // 2~4. 서버 저장소 · DB · 이전 SQL
    let attempt = async {
        let (tar, dest) = (opened.origins.clone(), data_dir.to_path_buf());
        blocking(move || untar_origins(&tar, &dest)).await?;
        fs::create_dir_all(&origins)?;
        load_dump(pg, &opened.dump).await?;
        let mut c = PgConnection::connect_with(&pg.options).await?;
        let applied = migrate::apply(&mut c).await;
        let _ = c.close().await;
        applied.map(|_| ())
    }
    .await;
    // 5. 작업 사본은 켤 때 다시 만든다(ProjectService.rehome)
    let repos = data_dir.join("repos");
    let _ = fs::remove_dir_all(&repos);
    fs::create_dir_all(&repos)?;
    match attempt {
        Ok(()) => {
            let _ = fs::remove_dir_all(&base);
            Ok(())
        }
        Err(p) => {
            // 7. 되돌린다 — 옆에 둔 원본과 DB로
            let _ = fs::remove_dir_all(&origins);
            if kept.exists() {
                fs::rename(&kept, &origins)?;
            } else {
                fs::create_dir_all(&origins)?;
            }
            if let Err(back) = load_dump(pg, &saved).await {
                tracing::error!(
                    "되살리기를 되돌리지 못했다 — {back} (옆에 둔 덤프: {})",
                    saved.display()
                );
            }
            Err(p)
        }
    }
}

/// 오늘 백업이 있나 — 없으면 할 때다
fn due(dir: &Path) -> bool {
    let prefix = today_prefix();
    !list(dir)
        .map(|v| v.iter().any(|f| f.name.starts_with(&prefix)))
        .unwrap_or(true)
}

/// SYNC-MS-023#backup.daily
pub async fn daily(local: Arc<Local>) {
    tokio::time::sleep(Duration::from_secs(60)).await;
    let mut tick = tokio::time::interval(Duration::from_secs(3600));
    loop {
        tick.tick().await;
        let Ok(conf) = settings::load(&local.data_dir) else {
            continue;
        };
        if conf.backup_dir.is_empty() || !due(Path::new(&conf.backup_dir)) {
            continue;
        }
        if let Err(p) = local.backup_now().await {
            tracing::warn!("하루 한 번 백업 — {p}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn due_only_when_today_is_missing() {
        let dir = tempfile::tempdir().unwrap();
        assert!(due(dir.path()));
        fs::write(dir.path().join("syncdoc-19990101-000000.tar"), b"x").unwrap();
        assert!(due(dir.path()));
        fs::write(
            dir.path().join(format!("{}090000.tar.gpg", today_prefix())),
            b"x",
        )
        .unwrap();
        assert!(!due(dir.path()));
    }

    #[test]
    fn list_newest_first_and_only_backups() {
        let dir = tempfile::tempdir().unwrap();
        for n in [
            "syncdoc-20261010-090000.tar.gpg",
            "syncdoc-20261011-090000.tar",
            "syncdoc-20261012-090000.tar.gpg.part",
            "other.tar",
        ] {
            fs::write(dir.path().join(n), b"xy").unwrap();
        }
        let got: Vec<_> = list(dir.path()).unwrap();
        assert_eq!(
            got.iter()
                .map(|f| (f.name.as_str(), f.encrypted, f.size))
                .collect::<Vec<_>>(),
            [
                ("syncdoc-20261011-090000.tar", false, 2),
                ("syncdoc-20261010-090000.tar.gpg", true, 2)
            ]
        );
        assert!(list(&dir.path().join("없음")).unwrap().is_empty());
    }

    /// gpg가 있으면 — 이 백업을 `gpg -d`로 풀고, `gpg --symmetric`(카드 BR)이 만든 것을 푼다
    #[test]
    fn gpg_reads_ours_and_we_read_gpg() {
        let ok = std::process::Command::new("gpg")
            .arg("--version")
            .output()
            .is_ok_and(|o| o.status.success());
        if !ok {
            eprintln!("gpg가 없어 건너뛴다");
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("gnupg");
        fs::create_dir(&home).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&home, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let gpg = |args: &[&OsStr]| {
            let out = std::process::Command::new("gpg")
                .env("GNUPGHOME", &home)
                .args([
                    "--batch",
                    "--yes",
                    "--quiet",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    "백업 암호",
                ])
                .args(args)
                .output()
                .unwrap();
            assert!(
                out.status.success(),
                "{}",
                String::from_utf8_lossy(&out.stderr)
            );
        };
        let plain = dir.path().join("p.tar");
        fs::write(&plain, vec![7u8; 100_000]).unwrap();
        let ours = dir.path().join("ours.tar.gpg");
        encrypt(&plain, "백업 암호", &ours).unwrap();
        let by_gpg = dir.path().join("by_gpg");
        gpg(&[
            OsStr::new("-d"),
            OsStr::new("-o"),
            by_gpg.as_os_str(),
            ours.as_os_str(),
        ]);
        assert_eq!(fs::read(&by_gpg).unwrap(), fs::read(&plain).unwrap());
        let theirs = dir.path().join("theirs.tar.gpg");
        gpg(&[
            OsStr::new("--symmetric"),
            OsStr::new("--cipher-algo"),
            OsStr::new("AES256"),
            OsStr::new("-o"),
            theirs.as_os_str(),
            plain.as_os_str(),
        ]);
        let by_us = dir.path().join("by_us");
        decrypt(&theirs, "백업 암호", &by_us).unwrap();
        assert_eq!(fs::read(&by_us).unwrap(), fs::read(&plain).unwrap());
    }

    #[test]
    fn encrypt_and_decrypt_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let plain = dir.path().join("p.tar");
        fs::write(&plain, b"tar bytes").unwrap();
        let enc = dir.path().join("p.tar.gpg");
        encrypt(&plain, "암호", &enc).unwrap();
        let out = dir.path().join("out");
        decrypt(&enc, "암호", &out).unwrap();
        assert_eq!(fs::read(&out).unwrap(), b"tar bytes");
        assert!(matches!(
            decrypt(&enc, "틀림", &out),
            Err(Problem::BackupInvalid { reason }) if reason == "암호가 틀리다"
        ));
        assert!(matches!(
            decrypt(&plain, "암호", &out),
            Err(Problem::BackupInvalid { reason }) if reason.starts_with("깨졌다")
        ));
    }
}
