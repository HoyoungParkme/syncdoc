//! SYNC-MS-023 backup.* 테스트 관점 — 진짜 PostgreSQL(`cargo xtask pg-fetch`)·git, 임시 데이터 자리

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use sqlx::{Connection, PgConnection};
use syncdoc_app::backup::{Job, list, make, open, restore};
use syncdoc_app::paths::pg_dir;
use syncdoc_app::pg::{PgServer, start, stop};
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::git::Git;
use syncdoc_core::migrate;

fn sh(cwd: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(["-c", "user.name=t", "-c", "user.email=t@t"])
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("git");
    assert!(
        out.status.success(),
        "{args:?}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

fn git_for(data: &Path) -> Git {
    let global = data.join("gitconfig");
    fs::write(&global, "").expect("빈 설정");
    Git::new("git".into(), global)
}

/// 원본에 커밋 하나를 민다 — 그 해시
fn push_commit(tmp: &Path, origin: &Path, file: &str) -> String {
    let work = tmp.join(format!("w-{file}"));
    let _ = fs::remove_dir_all(&work);
    sh(
        tmp,
        &[
            "clone",
            "-q",
            origin.to_str().unwrap(),
            work.to_str().unwrap(),
        ],
    );
    fs::write(work.join(file), file).unwrap();
    sh(&work, &["add", "-A"]);
    sh(&work, &["commit", "-q", "-m", file]);
    sh(&work, &["push", "-q", "origin", "HEAD:main"]);
    sh(&work, &["rev-parse", "HEAD"])
}

async fn rows(pg: &PgServer) -> Vec<String> {
    let mut c = PgConnection::connect_with(&pg.options).await.unwrap();
    let v: Vec<String> = sqlx::query_scalar("SELECT github_login FROM users ORDER BY id")
        .fetch_all(&mut c)
        .await
        .unwrap();
    c.close().await.unwrap();
    v
}

async fn add_user(pg: &PgServer, login: &str) {
    let mut c = PgConnection::connect_with(&pg.options).await.unwrap();
    sqlx::query("INSERT INTO users (github_login, display_name, kind) VALUES ($1, $1, 'local')")
        .bind(login)
        .execute(&mut c)
        .await
        .unwrap();
    c.close().await.unwrap();
}

struct World {
    _tmp: tempfile::TempDir,
    data: PathBuf,
    backups: PathBuf,
    origin: PathBuf,
    pg: Option<PgServer>,
    git: Git,
}

impl World {
    fn pg(&self) -> &PgServer {
        self.pg.as_ref().unwrap()
    }

    fn job(&self, password: &str) -> Job {
        let pg = self.pg();
        Job {
            dir: self.backups.clone(),
            password: password.into(),
            bin: pg.bin.clone(),
            port: pg.port,
            pg_password: pg.password.clone(),
            git: Clone::clone(&self.git), // Git::clone(작업 사본 받기)와 이름이 겹친다
            origins: self.data.join("origins"),
            work: self.data.join("tmp"),
        }
    }
}

async fn world() -> World {
    let tmp = tempfile::tempdir().unwrap();
    let data = tmp.path().join("data");
    fs::create_dir_all(data.join("origins/_archive")).unwrap();
    let git = git_for(&data);
    let pg = start(&pg_dir().expect("pg-fetch"), &data)
        .await
        .expect("PostgreSQL");
    let mut c = PgConnection::connect_with(&pg.options).await.unwrap();
    migrate::apply(&mut c).await.unwrap();
    c.close().await.unwrap();
    let origin = data.join("origins/BKA.git");
    git.init_bare(&origin).await.unwrap();
    git.init_bare(&data.join("origins/_archive/OLD-20261001000000.git"))
        .await
        .unwrap();
    push_commit(tmp.path(), &origin, "one");
    add_user(&pg, "before").await;
    World {
        backups: tmp.path().join("backups"),
        _tmp: tmp,
        data,
        origin,
        pg: Some(pg),
        git,
    }
}

fn tar_names(file: &Path) -> Vec<String> {
    let mut a = tar::Archive::new(fs::File::open(file).unwrap());
    a.entries()
        .unwrap()
        .map(|e| e.unwrap().path().unwrap().to_string_lossy().into_owned())
        .collect()
}

#[tokio::test]
async fn backup_has_dump_and_mirrored_origins_and_restores_with_rollback() {
    let mut w = world().await;
    let head = sh(&w.origin, &["rev-parse", "main"]);
    // 암호 없이 — .tar, 안은 db.dump·origins.tar 차례
    let plain = make(&w.job("")).await.expect("백업");
    assert!(plain.name.starts_with("syncdoc-") && plain.name.ends_with(".tar") && !plain.encrypted);
    let file = w.backups.join(&plain.name);
    assert_eq!(tar_names(&file), ["db.dump", "origins.tar"]);
    assert_eq!(fs::metadata(&file).unwrap().len(), plain.size);
    assert!(
        fs::read_dir(&w.backups).unwrap().all(|e| !e
            .unwrap()
            .file_name()
            .to_string_lossy()
            .ends_with(".part"))
    );
    // 풀어 보기 — 거울은 원본과 같은 해시, 원격 없음
    let opened = open(&file, "", &w.pg().bin, &w.data.join("restore/incoming"))
        .await
        .expect("풀어 보기");
    let names = tar_names(&opened.origins);
    assert!(
        names.iter().any(|n| n == "origins/BKA.git/HEAD"),
        "{names:?}"
    );
    assert!(
        names
            .iter()
            .any(|n| n.starts_with("origins/_archive/OLD-20261001000000.git/"))
    );
    let look = w.data.join("look");
    fs::create_dir_all(&look).unwrap();
    let mut a = tar::Archive::new(fs::File::open(&opened.origins).unwrap());
    a.unpack(&look).unwrap();
    assert_eq!(
        sh(&look.join("origins/BKA.git"), &["rev-parse", "main"]),
        head
    );
    assert_eq!(sh(&look.join("origins/BKA.git"), &["remote"]), "");
    assert_eq!(
        sh(
            &look.join("origins/BKA.git"),
            &["config", "receive.denyNonFastForwards"]
        ),
        "true"
    );
    // 암호 — .gpg, 틀린 암호·없는 암호는 backup-invalid
    let enc = make(&w.job("비밀")).await.expect("암호 백업");
    assert!(enc.encrypted && enc.name.ends_with(".tar.gpg"));
    let efile = w.backups.join(&enc.name);
    for (pw, want) in [("틀림", "암호가 틀리다"), ("", "암호가 필요하다")] {
        match open(&efile, pw, &w.pg().bin, &w.data.join("restore/incoming")).await {
            Err(Problem::BackupInvalid { reason }) => assert_eq!(reason, want),
            other => panic!("{other:?}"),
        }
    }
    let junk = w.backups.join("syncdoc-20200101-000000.tar");
    fs::write(&junk, b"not a tar").unwrap();
    assert!(matches!(
        open(&junk, "", &w.pg().bin, &w.data.join("restore/incoming")).await,
        Err(Problem::BackupInvalid { .. })
    ));
    fs::remove_file(&junk).unwrap();
    let opened = open(
        &efile,
        "비밀",
        &w.pg().bin,
        &w.data.join("restore/incoming"),
    )
    .await
    .expect("맞는 암호");
    // 백업 뒤의 일 — 사용자 하나·커밋 하나
    add_user(w.pg(), "after").await;
    push_commit(w._tmp.path(), &w.origin, "two");
    fs::create_dir_all(w.data.join("repos/BKA")).unwrap();
    // 되살리기 — 백업 때로
    restore(&opened, w.pg(), &w.data).await.expect("되살리기");
    assert_eq!(rows(w.pg()).await, ["before"]);
    assert_eq!(sh(&w.origin, &["rev-parse", "main"]), head);
    assert!(!w.data.join("restore").exists(), "옆에 둔 것이 남지 않는다");
    assert!(
        !w.data.join("repos/BKA").exists(),
        "작업 사본은 켤 때 다시 만든다"
    );
    // 깨진 덤프로 되살리기 — 되돌아가 처음 그대로
    add_user(w.pg(), "kept").await;
    let mut bad = open(
        &efile,
        "비밀",
        &w.pg().bin,
        &w.data.join("restore/incoming"),
    )
    .await
    .unwrap();
    fs::write(&bad.dump, b"PGDMP garbage").unwrap();
    bad.name = "깨진".into();
    assert!(restore(&bad, w.pg(), &w.data).await.is_err());
    assert_eq!(rows(w.pg()).await, ["before", "kept"]);
    assert_eq!(sh(&w.origin, &["rev-parse", "main"]), head);
    stop(w.pg.take().unwrap()).await.unwrap();
}

#[tokio::test]
async fn keeps_fourteen_newest() {
    let mut w = world().await;
    fs::create_dir_all(&w.backups).unwrap();
    for d in 1..=15 {
        fs::write(
            w.backups
                .join(format!("syncdoc-200001{d:02}-000000.tar.gpg")),
            b"x",
        )
        .unwrap();
    }
    let made = make(&w.job("")).await.expect("백업");
    let names: Vec<String> = list(&w.backups)
        .unwrap()
        .into_iter()
        .map(|f| f.name)
        .collect();
    assert_eq!(names.len(), 14);
    assert_eq!(names[0], made.name);
    assert_eq!(names[13], "syncdoc-20000103-000000.tar.gpg");
    stop(w.pg.take().unwrap()).await.unwrap();
}
