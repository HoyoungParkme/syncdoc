//! 실행 파일에 담는 것이 바뀌면 다시 담는다 — 화면 빌드(`backend/app/web/static`)와
//! 규약·템플릿 사본(`docs/specs/STD`·`_templates`). rust-embed는 폴더에 새로 생긴 파일을 스스로 모른다.

fn main() {
    for dir in [
        "../../../backend/app/web/static",
        "../../../docs/specs/STD",
        "../../../docs/specs/_templates",
    ] {
        println!("cargo:rerun-if-changed={dir}");
    }
}
