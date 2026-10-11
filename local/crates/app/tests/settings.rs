//! SYNC-MS-012#settings.load·settings.save 테스트 관점

use std::fs;

use syncdoc_app::settings::{FILE, load, save};
use syncdoc_server::local::SettingsChange;

#[test]
fn first_run_writes_defaults() {
    let dir = tempfile::tempdir().unwrap();
    let s = load(dir.path()).expect("처음");
    let text = fs::read_to_string(dir.path().join(FILE)).expect("파일이 생긴다");
    assert!(text.contains("LOCAL_LOGIN = \"local\"") && text.contains("LLM_MODEL = \"gpt-4o\""));
    assert_eq!(
        (
            s.local_login.as_str(),
            s.local_name.as_str(),
            s.llm_model.as_str()
        ),
        ("local", "local", "gpt-4o")
    );
    assert!(!s.llm_enabled);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(dir.path().join(FILE))
            .unwrap()
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o600);
    }
    let again = load(dir.path()).expect("다시");
    assert_eq!(again.local_login, s.local_login);
}

#[test]
fn derived_values() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join(FILE);
    fs::write(
        &path,
        "LOCAL_LOGIN = \"hoyoung\"\nLOCAL_NAME = \"  \"\nLLM_API_KEY = \"k\"\nOTHER = 1\n",
    )
    .unwrap();
    let s = load(dir.path()).expect("빈 이름");
    assert_eq!(s.local_name, "hoyoung");
    assert!(!s.llm_enabled, "주소가 없으면 꺼진다");
    fs::write(&path, "LOCAL_LOGIN = \"hoyoung\"\nLOCAL_NAME = \"호영\"\nLLM_API_URL = \" http://llm.local/v1 \"\nLLM_API_KEY = \"k\"\n").unwrap();
    let s = load(dir.path()).expect("다 있다");
    assert_eq!(
        (s.local_name.as_str(), s.llm_api_url.as_str()),
        ("호영", "http://llm.local/v1")
    );
    assert!(s.llm_enabled);
}

#[test]
fn bad_files_stop_with_a_sentence() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join(FILE);
    for (text, words) in [
        ("LOCAL_LOGIN = \"local", "못 읽는다"),
        ("LOCAL_LOGIN = \"\"\n", "1~50자"),
        (
            &*format!("LOCAL_LOGIN = \"{}\"\n", "a".repeat(51)),
            "1~50자",
        ),
        (
            &*format!("LOCAL_NAME = \"{}\"\n", "가".repeat(101)),
            "100자",
        ),
        ("LOCAL_LOGIN = 3\n", "글자여야"),
    ] {
        fs::write(&path, text).unwrap();
        let err = load(dir.path()).expect_err(text);
        assert!(err.to_string().contains(words), "{text}: {err}");
    }
}

/// L16 — 옛 판의 다섯 키 파일은 새 키가 기본값 · 상대 경로 백업 폴더·호스트 없는 공개 주소는 멈춘다
#[test]
fn new_keys_default_and_checked() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join(FILE),
        "LOCAL_LOGIN = \"me\"\nLLM_MODEL = \"m\"\n",
    )
    .unwrap();
    let s = load(dir.path()).expect("옛 판 파일");
    assert_eq!(
        (
            s.public_base_url.as_str(),
            s.backup_dir.as_str(),
            s.backup_password.as_str()
        ),
        ("", "", "")
    );
    fs::write(
        dir.path().join(FILE),
        "PUBLIC_BASE_URL = \"http://192.168.0.10:8010/\"\n",
    )
    .unwrap();
    assert_eq!(
        load(dir.path()).unwrap().public_base_url,
        "http://192.168.0.10:8010"
    );
    for bad in [
        "BACKUP_DIR = \"rel/dir\"",
        "PUBLIC_BASE_URL = \"192.168.0.10\"",
        "PUBLIC_BASE_URL = \"http://\"",
    ] {
        fs::write(dir.path().join(FILE), format!("{bad}\n")).unwrap();
        assert!(load(dir.path()).is_err(), "{bad}");
    }
}

/// L16 — 준 키만 바뀌고 주석·다른 키·차례가 그대로, 없던 키는 끝에
#[test]
fn save_changes_values_only() {
    let dir = tempfile::tempdir().unwrap();
    load(dir.path()).unwrap();
    let before = fs::read_to_string(dir.path().join(FILE)).unwrap();
    let backups = dir.path().join("b");
    save(
        dir.path(),
        &SettingsChange {
            name: Some("새 \"이름\"".into()),
            backup_dir: Some(backups.to_string_lossy().into_owned()),
            ..Default::default()
        },
    )
    .unwrap();
    let after = fs::read_to_string(dir.path().join(FILE)).unwrap();
    let s = load(dir.path()).unwrap();
    assert_eq!(s.local_name_raw, "새 \"이름\"");
    assert_eq!(s.backup_dir, backups.to_string_lossy());
    assert_eq!(s.local_login, "local");
    // 주석 줄은 그대로, 바뀐 줄은 둘
    let comments = |t: &str| {
        t.lines()
            .filter(|l| l.starts_with('#'))
            .map(str::to_string)
            .collect::<Vec<_>>()
    };
    assert_eq!(comments(&before), comments(&after));
    let changed = before
        .lines()
        .zip(after.lines())
        .filter(|(a, b)| a != b)
        .count();
    assert_eq!(changed, 2, "{after}");
    // 없던 키는 끝에
    fs::write(dir.path().join(FILE), "# 내 메모\nLOCAL_LOGIN = \"me\"\n").unwrap();
    save(
        dir.path(),
        &SettingsChange {
            llm_api_key: Some("k".into()),
            ..Default::default()
        },
    )
    .unwrap();
    let text = fs::read_to_string(dir.path().join(FILE)).unwrap();
    assert!(
        text.starts_with("# 내 메모\nLOCAL_LOGIN = \"me\"\n"),
        "{text}"
    );
    assert!(text.trim_end().ends_with("LLM_API_KEY = \"k\""), "{text}");
}
