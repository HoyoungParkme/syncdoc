//! SYNC-MS-023#datadir.check·datadir.copy 테스트 관점

use std::fs;

use syncdoc_app::datadir::{check, copy};
use syncdoc_core::errors::Problem;

fn reason(r: Result<std::path::PathBuf, Problem>) -> String {
    match r {
        Err(Problem::DataDirInvalid { reason }) => reason,
        other => panic!("{other:?}"),
    }
}

#[test]
fn check_refuses_relative_overlapping_and_full() {
    let tmp = tempfile::tempdir().unwrap();
    let cur = tmp.path().join("cur");
    fs::create_dir_all(cur.join("pgdata")).unwrap();
    assert_eq!(reason(check(&cur, "rel/dir")), "절대 경로가 아니다");
    assert_eq!(reason(check(&cur, "  ")), "절대 경로가 아니다");
    assert_eq!(
        reason(check(&cur, cur.join("inner").to_str().unwrap())),
        "지금 데이터 자리와 겹친다"
    );
    assert_eq!(
        reason(check(&cur, tmp.path().to_str().unwrap())),
        "지금 데이터 자리와 겹친다"
    );
    let full = tmp.path().join("full");
    fs::create_dir_all(&full).unwrap();
    fs::write(full.join("x"), b"x").unwrap();
    assert_eq!(
        reason(check(&cur, full.to_str().unwrap())),
        "비어 있지 않은 폴더다"
    );
    let file = tmp.path().join("file");
    fs::write(&file, b"x").unwrap();
    assert_eq!(
        reason(check(&cur, file.to_str().unwrap())),
        "비어 있지 않은 폴더다"
    );
    let new = tmp.path().join("new/deep");
    let got = check(&cur, &format!(" {} ", new.display())).expect("없는 폴더");
    assert_eq!(got, new);
    assert!(new.is_dir() && fs::read_dir(&new).unwrap().next().is_none());
}

#[test]
fn copy_takes_db_origins_settings_and_verifies() {
    let tmp = tempfile::tempdir().unwrap();
    let (from, to) = (tmp.path().join("from"), tmp.path().join("to"));
    for d in [
        "pgdata/base/1",
        "pgdata/pg_tblspc",
        "origins/A.git/objects",
        "repos/A",
        "logs",
    ] {
        fs::create_dir_all(from.join(d)).unwrap();
    }
    fs::write(from.join("pgdata/base/1/123"), vec![1u8; 4096]).unwrap();
    fs::write(from.join("origins/A.git/HEAD"), b"ref: refs/heads/main\n").unwrap();
    fs::write(from.join("settings.toml"), b"LOCAL_LOGIN = \"me\"\n").unwrap();
    fs::write(from.join("gitconfig"), b"").unwrap();
    fs::write(from.join("repos/A/x"), b"work").unwrap();
    fs::write(from.join("instance.json"), b"{}").unwrap();
    fs::create_dir_all(&to).unwrap();
    copy(&from, &to).expect("복사");
    assert_eq!(fs::read(to.join("pgdata/base/1/123")).unwrap().len(), 4096);
    assert!(to.join("pgdata/pg_tblspc").is_dir(), "빈 폴더도");
    assert!(to.join("origins/A.git/HEAD").is_file());
    assert!(to.join("settings.toml").is_file() && to.join("gitconfig").is_file());
    assert!(
        !to.join("repos").exists()
            && !to.join("logs").exists()
            && !to.join("instance.json").exists()
    );
    assert!(from.join("repos/A/x").is_file(), "옛 자리는 그대로");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(from.join("pgdata"), fs::Permissions::from_mode(0o700)).unwrap();
        let again = tmp.path().join("again");
        fs::create_dir_all(&again).unwrap();
        copy(&from, &again).unwrap();
        let mode = fs::metadata(again.join("pgdata"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o700, "PostgreSQL은 0700이어야 켠다");
    }
}
