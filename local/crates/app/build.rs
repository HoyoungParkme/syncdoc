//! 윈도 실행 파일에 아이콘을 담는다 (SYNC-DOM-004 1장 packaging, 카드 L4).
//! 윈도에서 윈도용으로 빌드할 때만 — 리눅스에서 윈도 대상을 검사(`cargo check --target …-windows-msvc`)할 때는 건너뛴다.

fn main() {
    println!("cargo:rerun-if-changed=../../packaging/icon.ico");
    println!("cargo:rerun-if-changed=app.rc");
    let target_windows = std::env::var("CARGO_CFG_TARGET_OS").is_ok_and(|os| os == "windows");
    if target_windows && cfg!(windows) {
        embed_resource::compile("app.rc", embed_resource::NONE)
            .manifest_optional()
            .expect("아이콘 자원");
    }
}
