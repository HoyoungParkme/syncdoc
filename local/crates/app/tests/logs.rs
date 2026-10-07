//! SYNC-MS-012#logs.init 테스트 관점 — 한 프로세스에 한 번만 걸 수 있어 시험 하나로

use std::fs;

use syncdoc_app::logs::{KEEP, init};

#[test]
fn keeps_latest_and_writes_today() {
    let dir = tempfile::tempdir().unwrap();
    let logs = dir.path().join("logs");
    fs::create_dir_all(&logs).unwrap();
    for day in 1..=20 {
        fs::write(
            logs.join(format!("syncdoc-local.2026-09-{day:02}.log")),
            "x",
        )
        .unwrap();
        fs::write(logs.join(format!("postgresql-2026-09-{day:02}.log")), "x").unwrap();
    }
    let guard = init(dir.path()).expect("로그");
    tracing::info!("시험 줄 — logs.init");
    drop(guard);
    let names: Vec<String> = fs::read_dir(&logs)
        .unwrap()
        .filter_map(|e| e.ok()?.file_name().into_string().ok())
        .collect();
    let pg: Vec<&String> = names
        .iter()
        .filter(|n| n.starts_with("postgresql-"))
        .collect();
    assert_eq!(pg.len(), KEEP);
    assert!(!names.contains(&"postgresql-2026-09-01.log".to_string()));
    let app: Vec<&String> = names
        .iter()
        .filter(|n| n.starts_with("syncdoc-local."))
        .collect();
    assert!(app.len() <= KEEP, "{app:?}");
    let today = app.iter().max().expect("오늘 파일");
    let text = fs::read_to_string(logs.join(today)).unwrap();
    assert!(text.contains("시험 줄 — logs.init"), "{today}: {text}");
}
