//! 이전 SQL을 실행 파일에 담는 목록 — `local/migrations/NNNN_*.sql` (SYNC-STD-004#DEV-7).
//! `cargo xtask migrations`가 만든 파일을 이름 순으로 `include_str!`한다. 리비전은 이름 앞 네 자리.

use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let manifest = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let dir = manifest.join("../../migrations");
    println!("cargo:rerun-if-changed={}", dir.display());
    let mut files: Vec<PathBuf> = fs::read_dir(&dir)
        .expect("local/migrations — cargo xtask migrations")
        .map(|e| e.expect("migrations 항목").path())
        .filter(|p| p.extension().is_some_and(|x| x == "sql"))
        .collect();
    files.sort();
    let mut out = String::from(
        "/// 이전 SQL — (리비전, 파일 이름, SQL). build.rs가 local/migrations에서 만든 목록\n\
         pub static MIGRATIONS: &[(&str, &str, &str)] = &[\n",
    );
    for f in &files {
        println!("cargo:rerun-if-changed={}", f.display());
        let name = f
            .file_name()
            .expect("파일 이름")
            .to_string_lossy()
            .into_owned();
        let rev = name.get(..4).expect("NNNN_이름.sql");
        let abs = f.canonicalize().expect("절대 경로");
        out += &format!("    ({rev:?}, {name:?}, include_str!({abs:?})),\n");
    }
    out += "];\n";
    let dest = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR")).join("migrations.rs");
    fs::write(dest, out).expect("migrations.rs");
}
