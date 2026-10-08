//! 아이콘 — `packaging/icon.svg`에서 실행 파일·트레이·설치 파일이 쓰는 그림을 만든다 (SYNC-DOM-004 1장 packaging, 카드 L4).
//! icon.ico(16~256, PNG를 담은 ICO) · icon.png(256) · tray.rgba(32×32, 미리 곱하지 않은 RGBA). 손으로 고치지 않는다.

use std::fs;

use resvg::tiny_skia::{Pixmap, Transform};
use resvg::usvg::{Options, Tree};

use crate::local_root;

const ICO_SIZES: [u32; 7] = [16, 24, 32, 48, 64, 128, 256];

pub fn run() -> Result<(), String> {
    let dir = local_root().join("packaging");
    let svg = fs::read(dir.join("icon.svg")).map_err(|e| e.to_string())?;
    let tree = Tree::from_data(&svg, &Options::default()).map_err(|e| e.to_string())?;
    let mut pngs = Vec::new();
    for size in ICO_SIZES {
        pngs.push((
            size,
            render(&tree, size)?
                .encode_png()
                .map_err(|e| e.to_string())?,
        ));
    }
    let png256 = &pngs.last().ok_or("크기 없음")?.1;
    fs::write(dir.join("icon.png"), png256).map_err(|e| e.to_string())?;
    fs::write(dir.join("icon.ico"), ico(&pngs)).map_err(|e| e.to_string())?;
    let tray = render(&tree, 32)?;
    let rgba: Vec<u8> = tray
        .pixels()
        .iter()
        .flat_map(|p| {
            let c = p.demultiply();
            [c.red(), c.green(), c.blue(), c.alpha()]
        })
        .collect();
    fs::write(dir.join("tray.rgba"), rgba).map_err(|e| e.to_string())?;
    println!("아이콘을 만들었다 — icon.ico · icon.png · tray.rgba");
    Ok(())
}

fn render(tree: &Tree, size: u32) -> Result<Pixmap, String> {
    let mut pm = Pixmap::new(size, size).ok_or("그림 자리를 못 만든다")?;
    let scale = size as f32 / tree.size().width();
    resvg::render(tree, Transform::from_scale(scale, scale), &mut pm.as_mut());
    Ok(pm)
}

/// ICO — 머리 6바이트, 항목 16바이트씩, 그다음 PNG들
fn ico(pngs: &[(u32, Vec<u8>)]) -> Vec<u8> {
    let mut out = Vec::new();
    out.extend_from_slice(&[0, 0, 1, 0]);
    out.extend_from_slice(&(pngs.len() as u16).to_le_bytes());
    let mut offset = 6 + 16 * pngs.len() as u32;
    for (size, png) in pngs {
        let b = if *size >= 256 { 0 } else { *size as u8 };
        out.extend_from_slice(&[b, b, 0, 0]);
        out.extend_from_slice(&1u16.to_le_bytes());
        out.extend_from_slice(&32u16.to_le_bytes());
        out.extend_from_slice(&(png.len() as u32).to_le_bytes());
        out.extend_from_slice(&offset.to_le_bytes());
        offset += png.len() as u32;
    }
    for (_, png) in pngs {
        out.extend_from_slice(png);
    }
    out
}
