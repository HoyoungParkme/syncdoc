//! 마크다운 순수 함수 — frontmatter·코드 마스킹·헤딩·항목 블록 (SYNC-MS-014 · SYNC-DOM-004 1장 markdown.rs).
//! 파이썬 판 `backend/app/core/markdown.py`와 같다. DB 없음 — spec·reference가 같이 쓴다.
//! 문자 분류·정규식은 `pycompat`(파이썬 3.12와 같은 표)로 — YAML·마크다운 라이브러리를 쓰지 않는다.

use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;

use crate::pycompat::chars::strip;
use crate::pycompat::re::compile;

/// 문서 ID 꼴 (STD-001 1.2)
pub static DOC_ID: LazyLock<Regex> = LazyLock::new(|| compile(r"^[A-Z]{1,4}-[A-Z]+-\d{3}$"));
/// 참조 `[[…]]` (STD-001 1.4)
pub static REF: LazyLock<Regex> = LazyLock::new(|| compile(r"\[\[([^\]]+)\]\]"));
/// 헤딩 — `#` 1~6, 빈칸 하나, 첫 토큰, 빈칸 하나 뒤 나머지 (STD-001 1.3)
pub static HEADING: LazyLock<Regex> = LazyLock::new(|| compile(r"^(#{1,6}) (\S+)(?: (.*))?$"));
/// frontmatter — 본문 머리의 `---` 두 줄 사이 (파이썬 `re.S`)
static FRONTMATTER: LazyLock<Regex> = LazyLock::new(|| compile(r"(?s)^---\n(.*?)\n---\n"));

/// SYNC-MS-014#markdown.parse_frontmatter
pub fn parse_frontmatter(body: &str) -> (IndexMap<String, String>, usize) {
    let Some(m) = FRONTMATTER.captures(body) else {
        return (IndexMap::new(), 0);
    };
    let mut fm = IndexMap::new();
    for line in m[1].split('\n') {
        let (k, v) = line.split_once(':').unwrap_or((line, ""));
        fm.insert(strip(k).to_string(), strip(v).to_string());
    }
    (fm, m[0].matches('\n').count())
}
