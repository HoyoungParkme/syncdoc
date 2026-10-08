//! SYNC-MS-012#privilege.drop_admin — 윈도가 아니면 아무것도 안 한다.
//! 윈도 관리자 경로(다시 켜기)는 워크플로가 관리자 러너에서 깔아 켜 본다(`.github/workflows/local-release.yml`).

#[cfg(not(windows))]
#[test]
fn not_windows_does_nothing() {
    assert_eq!(syncdoc_app::privilege::drop_admin(), None);
}
