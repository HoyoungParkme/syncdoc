//! SpecService — SYNC-MS-014 (파이썬 판 SYNC-MS-002와 같은 이름·같은 처리). 카드 L5 몫은 명세 엔진이다.
//! 파이썬 판과 바이트까지 같다 — 문자 분류·정규식·repr·difflib은 `pycompat`(파이썬 3.12)로.
//! 맞춤은 정답 파일(`crates/core/tests/golden/spec.json`)과 `cargo xtask spec-diff`가 본다.

use std::sync::LazyLock;

use regex::Regex;
use sqlx::PgConnection;

use crate::markdown;
use crate::pycompat::re::compile;
use crate::types::{DocType, ItemBlock};

/// 이력 diff의 앞뒤 줄 수 — 파이썬 `DIFF_CONTEXT_LINES`
pub const DIFF_CONTEXT_LINES: usize = 3;

/// SYNC-STD-001 2장 — 타입별 (항목 패턴, 필수 절). 파이썬 `TYPES`와 글자 하나 다르지 않다 —
/// 카드 L6의 `get_template`이 패턴 문자열을 그대로 내보낸다. 차례도 파이썬 dict 그대로
pub const TYPES: [(&str, &[&str], &[&str]); 12] = [
    (
        "RFQ",
        &[r"Q\d+"],
        &["배경", "요구", "사용자와 환경", "미정"],
    ),
    (
        "PRD",
        &[r"G\d+", r"R\d+", r"N\d+"],
        &["목표", "비목표", "요구사항", "성공지표", "미결사항"],
    ),
    (
        "SCN",
        &[r"P\d+", r"S\d+"],
        &["페르소나", "시나리오", "대응표"],
    ),
    (
        "UC",
        &[r"UC-[AHGS]\d+"],
        &[
            "액터",
            "사용자 목표 수준 유스케이스",
            "하위기능 수준 유스케이스",
            "대응표",
        ],
    ),
    (
        "INFRA",
        &[r"C\d+"],
        &[
            "제약",
            "구성도",
            "기술 스택",
            "데이터가 사는 곳",
            "인증과 접근",
            "미결사항",
        ],
    ),
    ("DOM", &[r"[A-Z][A-Za-z]+", r"[a-z][a-z0-9_]+"], &[]),
    ("UI", &[r"UI-\d+"], &[]),
    (
        "API",
        &[r"(GET|POST|PUT|PATCH|DELETE)/\S+", r"[a-z][a-z_]+"],
        &[],
    ),
    (
        "SEQ",
        &[r"SEQ-\d+", r"SEQ-C\d+"],
        &["생명선", "대응표", "되먹일 것"],
    ),
    ("MS", &[r"[A-Za-z_]+\.[a-z_]+"], &["함수 목록", "미결사항"]),
    // CODE 카드는 Z 다음 AA·AB…로 잇는다 — 두 글자도 항목 (STD-001 2.11, #153)
    (
        "CODE",
        &[r"[A-Z]+\d*"],
        &["슬라이스", "통합 테스트", "커밋", "미결사항"],
    ),
    ("STD", &[r"[A-Z]+-\d+", r"V-[A-Z]+"], &["미결사항"]),
];

/// 서브타입 — (타입, 제목 키워드, 항목 패턴, 필수 절). 파이썬 `SUBTYPES` 그대로, 차례대로 첫 키워드가 이긴다
pub const SUBTYPES: [(&str, &str, &[&str], &[&str]); 7] = [
    (
        "DOM",
        "도메인",
        &[r"[A-Z][A-Za-z]+"],
        &["개념 식별", "개념 모델", "개념별 정리", "경계", "미결사항"],
    ),
    (
        "DOM",
        "클래스",
        &[r"[A-Z][A-Za-z]+"],
        &[
            "폴더 구조",
            "엔티티",
            "의존 관계",
            "설계 클래스",
            "미결사항",
        ],
    ),
    (
        "DOM",
        "ERD",
        &[r"[a-z][a-z0-9_]+"],
        &["ERD", "DD", "인덱스", "미결사항"],
    ),
    // UI는 하나 또는 둘 — 어느 키워드든 같은 규약(STD-001 2.7). 필수 절은 미결사항 하나 (#105)
    ("UI", "화면 설계", &[r"UI-\d+"], &["미결사항"]),
    ("UI", "와이어프레임", &[r"UI-\d+"], &["미결사항"]),
    (
        "API",
        "REST",
        &[r"(GET|POST|PUT|PATCH|DELETE)/\S+"],
        &["규칙", "에러", "엔드포인트", "미결사항"],
    ),
    (
        "API",
        "MCP",
        &[r"[a-z][a-z_]+"],
        &["규칙", "도구", "에이전트 순서", "미결사항"],
    ),
];

/// `^(?:패턴|…)$` — 표와 같은 차례로 한 번만 컴파일한다
static TYPE_RES: LazyLock<Vec<Regex>> =
    LazyLock::new(|| TYPES.iter().map(|(_, pats, _)| item_regex(pats)).collect());
static SUBTYPE_RES: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    SUBTYPES
        .iter()
        .map(|(_, _, pats, _)| item_regex(pats))
        .collect()
});

fn item_regex(pats: &[&str]) -> Regex {
    compile(&format!("^(?:{})$", pats.join("|")))
}

/// 제목 키워드로 서브타입 — 파이썬 `subtype_of` (빈 제목은 없음)
fn subtype_of(doc_type: &str, title: Option<&str>) -> Option<usize> {
    SUBTYPES.iter().position(|(t, key, _, _)| {
        *t == doc_type && title.is_some_and(|ti| !ti.is_empty() && ti.contains(key))
    })
}

/// 타입·제목 → (항목 패턴, 필수 절) — 파이썬 `patterns_for`
fn patterns_for(
    doc_type: &str,
    title: Option<&str>,
) -> (Option<&'static Regex>, &'static [&'static str]) {
    if let Some(i) = subtype_of(doc_type, title) {
        return (Some(&SUBTYPE_RES[i]), SUBTYPES[i].3);
    }
    match TYPES.iter().position(|(t, _, _)| *t == doc_type) {
        Some(i) => (Some(&TYPE_RES[i]), TYPES[i].2),
        None => (None, &[]),
    }
}

/// 명세 서비스 — 연결을 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10).
/// DB가 필요 없는 함수는 연결 없이 부르는 연관 함수다
pub struct SpecService<'c> {
    pub db: &'c mut PgConnection,
}

impl SpecService<'_> {
    /// SYNC-MS-014#SpecService.item_blocks
    pub fn item_blocks(body: &str, doc_type: DocType, title: Option<&str>) -> Vec<ItemBlock> {
        let fm;
        let title = match title {
            Some(t) => Some(t),
            None => {
                fm = markdown::parse_frontmatter(body).0;
                fm.get("title").map(String::as_str)
            }
        };
        let (re, _) = patterns_for(doc_type.as_str(), title);
        let Some(re) = re else {
            return Vec::new();
        };
        markdown::cut_blocks(body, |tok| re.is_match(tok))
    }
}
