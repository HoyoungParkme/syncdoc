//! SYNC-MS-012#settings.load 테스트 관점

use std::fs;

use syncdoc_app::settings::{FILE, load};

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
