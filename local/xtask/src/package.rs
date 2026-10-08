//! 설치 파일 — `cargo xtask package windows|linux` (SYNC-INFRA-001 9.5 · SYNC-DOM-004 1장 packaging, 카드 L4).
//! 릴리즈 빌드(`cargo build --release -p syncdoc_app`)를 먼저 해 둔다. 재료를 `target/package/{os}/`에 모아
//! 윈도는 `makensis`로 setup.exe, 리눅스는 `dpkg-deb`로 .deb와 `appimagetool`로 AppImage를 만든다.
//! 함께 담는 PostgreSQL(theseus 16.15)과 MinGit은 판을 고정하고 해시를 본다.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

use crate::local_root;
use crate::pg_fetch::{self, curl};

/// 판 — 작업 공간 version (`local/Cargo.toml`)
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Git for Windows의 MinGit — 판과 해시 고정 (GitHub 릴리즈의 digest)
const MINGIT_TAG: &str = "v2.56.0.windows.2";
const MINGIT_ZIP: &str = "MinGit-2.56.0.2-64-bit.zip";
const MINGIT_SHA256: &str = "da35e72aa21c005a5a0d298cfbae110bc1609a815730ea0dde84b01a1b3cd3be";

/// AppImage를 만드는 도구 — 고정된 판이 없어(continuous) 받은 것의 해시를 기록에 남긴다
const APPIMAGETOOL: &str = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage";

pub fn run(os: &str) -> Result<(), String> {
    match os {
        "windows" => windows(),
        "linux" => linux(),
        other => Err(format!("모르는 대상 {other}")),
    }
}

fn package_dir(os: &str) -> PathBuf {
    local_root().join("target").join("package").join(os)
}

fn release_bin(name: &str) -> Result<PathBuf, String> {
    let p = local_root().join("target").join("release").join(name);
    if p.is_file() {
        Ok(p)
    } else {
        Err(format!(
            "{} 없음 — cargo build --release -p syncdoc_app 먼저",
            p.display()
        ))
    }
}

fn fresh(dir: &Path) -> Result<(), String> {
    if dir.exists() {
        fs::remove_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))
}

fn copy(from: &Path, to: &Path) -> Result<(), String> {
    if let Some(p) = to.parent() {
        fs::create_dir_all(p).map_err(|e| e.to_string())?;
    }
    fs::copy(from, to).map_err(|e| format!("{} → {}: {e}", from.display(), to.display()))?;
    Ok(())
}

/// 폴더째 — 심볼릭 링크는 링크로(리눅스 PostgreSQL의 lib*.so), 권한은 그대로
fn copy_tree(from: &Path, to: &Path) -> Result<(), String> {
    fs::create_dir_all(to).map_err(|e| e.to_string())?;
    for entry in fs::read_dir(from).map_err(|e| format!("{}: {e}", from.display()))? {
        let entry = entry.map_err(|e| e.to_string())?;
        let src = entry.path();
        let dst = to.join(entry.file_name());
        let ft = entry.file_type().map_err(|e| e.to_string())?;
        if ft.is_symlink() {
            let target = fs::read_link(&src).map_err(|e| e.to_string())?;
            #[cfg(unix)]
            std::os::unix::fs::symlink(&target, &dst).map_err(|e| e.to_string())?;
            #[cfg(not(unix))]
            {
                let _ = target;
                fs::copy(&src, &dst).map_err(|e| e.to_string())?;
            }
        } else if ft.is_dir() {
            copy_tree(&src, &dst)?;
        } else {
            fs::copy(&src, &dst).map_err(|e| format!("{}: {e}", src.display()))?;
        }
    }
    Ok(())
}

fn sha256_file(p: &Path) -> Result<String, String> {
    Ok(Sha256::digest(fs::read(p).map_err(|e| e.to_string())?)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

fn run_cmd(cmd: &mut Command, what: &str) -> Result<(), String> {
    let status = cmd
        .status()
        .map_err(|e| format!("{what}을 못 돌렸다 — {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{what} 실패 — {status}"))
    }
}

/// 윈도 — setup.exe
fn windows() -> Result<(), String> {
    let dir = package_dir("windows");
    let stage = dir.join("stage");
    let out = dir.join("out");
    fresh(&stage)?;
    fresh(&out)?;
    let packaging = local_root().join("packaging");
    copy(
        &release_bin("syncdoc-local.exe")?,
        &stage.join("syncdoc-local.exe"),
    )?;
    copy(&packaging.join("NOTICE.txt"), &stage.join("NOTICE.txt"))?;
    copy(&packaging.join("icon.ico"), &stage.join("icon.ico"))?;
    let pg = local_root()
        .join("target")
        .join("pg")
        .join(pg_fetch::WINDOWS)
        .join(pg_fetch::VERSION);
    pg_fetch::fetch(pg_fetch::WINDOWS, &pg)?;
    copy_tree(&pg, &stage.join("postgresql"))?;
    mingit(&stage.join("mingit"))?;
    let name = format!("SyncDoc-Local-{VERSION}-setup.exe");
    let makensis = which("makensis").ok_or("makensis 없음 — NSIS 3을 깐다")?;
    run_cmd(
        Command::new(makensis)
            .arg(format!("-DVERSION={VERSION}"))
            .arg(format!("-DSTAGE={}", stage.display()))
            .arg(format!("-DOUTFILE={}", out.join(&name).display()))
            .arg(packaging.join("windows").join("installer.nsi")),
        "makensis",
    )?;
    println!("만들었다 — {}", out.join(&name).display());
    Ok(())
}

/// MinGit을 받아 해시를 보고 푼다
fn mingit(dest: &Path) -> Result<(), String> {
    let dl = local_root().join("target").join("package").join("dl");
    fs::create_dir_all(&dl).map_err(|e| e.to_string())?;
    let zip = dl.join(MINGIT_ZIP);
    if !zip.is_file() || sha256_file(&zip)? != MINGIT_SHA256 {
        curl(
            &format!(
                "https://github.com/git-for-windows/git/releases/download/{MINGIT_TAG}/{MINGIT_ZIP}"
            ),
            &zip,
        )?;
    }
    let got = sha256_file(&zip)?;
    if got != MINGIT_SHA256 {
        return Err(format!("MinGit sha256이 다르다 — {got}"));
    }
    fs::create_dir_all(dest).map_err(|e| e.to_string())?;
    // 윈도의 tar(bsdtar)는 zip도 푼다
    run_cmd(
        Command::new("tar").arg("-xf").arg(&zip).arg("-C").arg(dest),
        "tar(MinGit)",
    )
}

/// 리눅스 — .deb와 AppImage
fn linux() -> Result<(), String> {
    let dir = package_dir("linux");
    let out = dir.join("out");
    fresh(&out)?;
    let bin = release_bin("syncdoc-local")?;
    let packaging = local_root().join("packaging");
    pg_fetch::run(None)?;
    let pg = local_root()
        .join("target")
        .join("pg")
        .join(pg_fetch::VERSION);

    // .deb — /opt/syncdoc-local, /usr/bin 링크, 프로그램 메뉴·아이콘
    let deb = dir.join("deb");
    fresh(&deb)?;
    let opt = deb.join("opt").join("syncdoc-local");
    copy(&bin, &opt.join("syncdoc-local"))?;
    copy_tree(&pg, &opt.join("postgresql"))?;
    copy(&packaging.join("NOTICE.txt"), &opt.join("NOTICE.txt"))?;
    let usr_bin = deb.join("usr").join("bin");
    fs::create_dir_all(&usr_bin).map_err(|e| e.to_string())?;
    #[cfg(unix)]
    std::os::unix::fs::symlink(
        "../../opt/syncdoc-local/syncdoc-local",
        usr_bin.join("syncdoc-local"),
    )
    .map_err(|e| e.to_string())?;
    copy(
        &packaging.join("linux").join("syncdoc-local.desktop"),
        &deb.join("usr/share/applications/syncdoc-local.desktop"),
    )?;
    copy(
        &packaging.join("icon.png"),
        &deb.join("usr/share/icons/hicolor/256x256/apps/syncdoc-local.png"),
    )?;
    let control = format!(
        "Package: syncdoc-local\nVersion: {VERSION}\nArchitecture: amd64\nMaintainer: HoyoungParkme <HoyoungParkme@users.noreply.github.com>\nDepends: git, libc6 (>= 2.35)\nSection: devel\nPriority: optional\nHomepage: https://github.com/HoyoungParkme/syncdoc\nDescription: SyncDoc Local - specs on this PC\n 싱크독_로컬 - 명세를 이 PC에서. PostgreSQL 16을 함께 담았다.\n"
    );
    let debian = deb.join("DEBIAN");
    fs::create_dir_all(&debian).map_err(|e| e.to_string())?;
    fs::write(debian.join("control"), control).map_err(|e| e.to_string())?;
    let deb_name = format!("syncdoc-local_{VERSION}_amd64.deb");
    run_cmd(
        Command::new("dpkg-deb")
            .args(["--root-owner-group", "--build"])
            .arg(&deb)
            .arg(out.join(&deb_name)),
        "dpkg-deb",
    )?;

    // AppImage — AppDir/usr/bin에 실행 파일과 postgresql/
    let appdir = dir.join("AppDir");
    fresh(&appdir)?;
    copy(&bin, &appdir.join("usr/bin/syncdoc-local"))?;
    copy_tree(&pg, &appdir.join("usr/bin/postgresql"))?;
    copy(
        &packaging.join("NOTICE.txt"),
        &appdir.join("usr/share/doc/syncdoc-local/NOTICE.txt"),
    )?;
    copy(
        &packaging.join("linux").join("AppRun"),
        &appdir.join("AppRun"),
    )?;
    copy(
        &packaging.join("linux").join("syncdoc-local.desktop"),
        &appdir.join("syncdoc-local.desktop"),
    )?;
    copy(
        &packaging.join("icon.png"),
        &appdir.join("syncdoc-local.png"),
    )?;
    let tool = local_root()
        .join("target")
        .join("package")
        .join("dl")
        .join("appimagetool-x86_64.AppImage");
    if !tool.is_file() {
        if let Some(p) = tool.parent() {
            fs::create_dir_all(p).map_err(|e| e.to_string())?;
        }
        curl(APPIMAGETOOL, &tool)?;
    }
    println!("appimagetool sha256 {}", sha256_file(&tool)?);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&tool, fs::Permissions::from_mode(0o755)).map_err(|e| e.to_string())?;
    }
    let app_name = format!("SyncDoc-Local-{VERSION}-x86_64.AppImage");
    run_cmd(
        Command::new(&tool)
            .arg("--appimage-extract-and-run")
            .arg(&appdir)
            .arg(out.join(&app_name))
            .env("ARCH", "x86_64"),
        "appimagetool",
    )?;
    println!(
        "만들었다 — {} · {}",
        out.join(deb_name).display(),
        out.join(app_name).display()
    );
    Ok(())
}

fn which(name: &str) -> Option<PathBuf> {
    let exts: &[&str] = if cfg!(windows) { &[".exe", ""] } else { &[""] };
    std::env::var_os("PATH").and_then(|paths| {
        std::env::split_paths(&paths).find_map(|dir| {
            exts.iter()
                .map(|e| dir.join(format!("{name}{e}")))
                .find(|p| p.is_file())
        })
    })
}
