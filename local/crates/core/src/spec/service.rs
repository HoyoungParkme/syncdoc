//! SpecService — SYNC-MS-014 (파이썬 판 SYNC-MS-002와 같은 이름·같은 처리). 카드 L5 몫은 명세 엔진이다.
//! 파이썬 판과 바이트까지 같다 — 문자 분류·정규식·repr·difflib은 `pycompat`(파이썬 3.12)로.
//! 맞춤은 정답 파일(`crates/core/tests/golden/spec.json`)과 `cargo xtask spec-diff`가 본다.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;
use sqlx::PgConnection;

use super::repo;
use crate::errors::Problem;
use crate::markdown::{self, DOC_ID, HEADING, REF};
use crate::pycompat::chars::{is_decimal, lstrip, strip};
use crate::pycompat::difflib::unified_diff;
use crate::pycompat::re::compile;
use crate::pycompat::repr::repr;
use crate::types::{
    AuthorRef, Diff, DiffLine, DiffOp, DocStatus, DocType, DocumentSummary, Entry, Hunk, ItemBlock,
    ValidateResult, Violation, Warning, stage_of,
};

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

/// `upstream`의 낱말 — 파이썬 `re.findall(r"[\w-]+", …)`
static UPSTREAM_TOKEN: LazyLock<Regex> = LazyLock::new(|| compile(r"[\w-]+"));
/// ID처럼 보이는 첫 토큰 — `item.pattern`
static ID_LIKE: LazyLock<Regex> = LazyLock::new(|| compile(r"^[A-Z]+-?\d+$"));
/// 절 제목 앞 번호 — `1.2 ` 같은 것
static SECTION_NUM: LazyLock<Regex> = LazyLock::new(|| compile(r"^[\d.]+\s*"));
/// 장 머리 `## N.` — `entity.mismatch`
static CHAPTER: LazyLock<Regex> = LazyLock::new(|| compile(r"^## (\d+)\."));
/// 첫 `# ` 헤딩 — 파이썬 `re.search(r"^# (.+)$", body, re.M)`
static H1: LazyLock<Regex> = LazyLock::new(|| compile(r"(?m)^# (.+)$"));
/// mermaid 클래스 — 파이썬 `class (\w+) \{(.*?)\}`(re.S)
static CLASS: LazyLock<Regex> = LazyLock::new(|| compile(r"(?s)class (\w+) \{(.*?)\}"));

fn violation(line: usize, rule: &str, message: &str) -> Violation {
    Violation {
        line,
        rule: rule.to_string(),
        message: message.to_string(),
    }
}

fn warning(rule: &str, message: &str) -> Warning {
    Warning {
        rule: rule.to_string(),
        message: message.to_string(),
    }
}

/// 파이썬 `f"{x!r}"` — 없으면 `None`
fn repr_opt(x: Option<&str>) -> String {
    x.map_or_else(|| "None".to_string(), repr)
}

/// 파이썬 `re.search(r"(?<![0-9])0\d", tok)` — regex에 룩비하인드가 없어 손으로 본다
fn has_padding(tok: &str) -> bool {
    let cs: Vec<char> = tok.chars().collect();
    (0..cs.len().saturating_sub(1))
        .any(|i| cs[i] == '0' && is_decimal(cs[i + 1]) && (i == 0 || !cs[i - 1].is_ascii_digit()))
}

/// 파이썬 `tok[:-1]`
fn drop_last(tok: &str) -> &str {
    let mut cs = tok.chars();
    cs.next_back();
    cs.as_str()
}

/// 「폴더 구조」 절에 머리가 경로·층·명세인 표가 있나 — 파이썬 `_has_layer_table`(STD-001 2.6, 카드 BM).
/// `lines`는 코드를 비운 줄 — 코드블록 안 표는 표가 아니다
fn has_layer_table(lines: &[String]) -> bool {
    let mut in_sec = false;
    for line in lines {
        if let Some(head) = line.strip_prefix("## ") {
            in_sec = SECTION_NUM
                .replace(strip(head), "")
                .starts_with("폴더 구조");
        } else if in_sec && lstrip(line).starts_with('|') {
            let cells: Vec<&str> = strip(line)
                .trim_matches('|')
                .split('|')
                .map(strip)
                .collect();
            if cells == ["경로", "층", "명세"] {
                return true;
            }
        }
    }
    false
}

/// DOM 클래스 명세 — 2장(엔티티)과 4장(설계) mermaid의 같은 클래스 속성이 다르면 경고(이름 차례)
fn entity_mismatch(body: &str) -> Vec<Warning> {
    let mut chapters: HashMap<String, String> = HashMap::new();
    let mut cur: Option<String> = None;
    for line in body.split('\n') {
        if let Some(m) = CHAPTER.captures(line) {
            cur = Some(m[1].to_string());
        }
        if let Some(c) = &cur {
            let text = chapters.entry(c.clone()).or_default();
            text.push_str(line);
            text.push('\n');
        }
    }
    let attrs = |text: &str| -> HashMap<String, BTreeSet<String>> {
        CLASS
            .captures_iter(text)
            .map(|m| {
                let set = m[2]
                    .split('\n')
                    .map(strip)
                    .filter(|a| a.starts_with('+'))
                    .map(str::to_string)
                    .collect();
                (m[1].to_string(), set)
            })
            .collect()
    };
    let empty = String::new();
    let a2 = attrs(chapters.get("2").unwrap_or(&empty));
    let a4 = attrs(chapters.get("4").unwrap_or(&empty));
    let mut names: Vec<&String> = a2.keys().collect();
    names.sort();
    names
        .into_iter()
        .filter(|n| a4.get(*n).is_some_and(|x| *x != a2[*n]))
        .map(|n| warning("entity.mismatch", n))
        .collect()
}

/// 본문 → {항목 ID: 블록 글} — 항목 밖 글은 `None` 키 하나 (MS-002 diff 2). 같은 ID는 처음 자리에 마지막 글
fn split_items(body: &str, doc_type: DocType) -> IndexMap<Option<String>, String> {
    let blocks = SpecService::item_blocks(body, doc_type, None);
    let lines: Vec<&str> = body.split('\n').collect();
    let mut covered: HashSet<usize> = HashSet::new();
    let mut out: IndexMap<Option<String>, String> = IndexMap::new();
    for blk in blocks {
        covered.extend(blk.start_line - 1..blk.end_line);
        out.insert(Some(blk.item_id), blk.text);
    }
    let rest: Vec<&str> = lines
        .iter()
        .enumerate()
        .filter(|(i, _)| !covered.contains(i))
        .map(|(_, l)| *l)
        .collect();
    let rest = rest.join("\n");
    if !strip(&rest).is_empty() {
        out.insert(None, rest);
    }
    out
}

/// 파이썬 `[ln.strip() for ln in text.split("\n") if ln.strip()]` — 공백만 바뀐 것은 같다
fn normalized(text: &str) -> Vec<&str> {
    text.split('\n')
        .map(strip)
        .filter(|l| !l.is_empty())
        .collect()
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

    /// SYNC-MS-014#SpecService.validate
    pub async fn validate(
        &mut self,
        body: &str,
        doc_type: DocType,
        entry: Entry,
        current_status: Option<DocStatus>,
    ) -> Result<ValidateResult, Problem> {
        let (fm, _) = markdown::parse_frontmatter(body);
        let deleted = self
            .deleted_item_ids(fm.get("doc_id").map(String::as_str))
            .await?;
        let body = body.to_string();
        // 긴 본문 파싱은 일꾼 스레드를 막지 않게 (SYNC-STD-004#DEV-16)
        tokio::task::spawn_blocking(move || {
            SpecService::check(&body, doc_type, entry, current_status, &deleted)
        })
        .await
        .map_err(|e| Problem::Internal {
            log: format!("규약 검사: {e}"),
        })
    }

    /// `item.reused`가 볼 삭제된 ID — 파일 삭제·휴지통으로 지워진 것을 되살리는 것은 복구라 빈 집합 (MS-002 validate 3)
    async fn deleted_item_ids(&mut self, doc_id: Option<&str>) -> Result<HashSet<String>, Problem> {
        let Some(doc_id) = doc_id.filter(|d| !d.is_empty()) else {
            return Ok(HashSet::new());
        };
        let Some(doc) = repo::document_by_doc_id(&mut *self.db, doc_id).await? else {
            return Ok(HashSet::new());
        };
        if doc
            .convention_error_detail
            .as_deref()
            .unwrap_or("")
            .starts_with("file.deleted:")
            || doc.trashed_at.is_some()
        {
            return Ok(HashSet::new());
        }
        Ok(repo::deleted_item_ids(&mut *self.db, doc.id)
            .await?
            .into_iter()
            .collect())
    }

    /// SYNC-MS-014#SpecService.check
    pub fn check(
        body: &str,
        doc_type: DocType,
        entry: Entry,
        current_status: Option<DocStatus>,
        deleted: &HashSet<String>,
    ) -> ValidateResult {
        let dt = doc_type.as_str();
        let mut v: Vec<Violation> = Vec::new();
        let mut w: Vec<Warning> = Vec::new();
        let (fm, _) = markdown::parse_frontmatter(body);
        let get = |k: &str| fm.get(k).map(String::as_str);
        // 1. frontmatter
        if fm.is_empty() {
            v.push(violation(1, "frontmatter.missing", "frontmatter 블록 없음"));
        } else {
            for f in ["doc_id", "type", "title", "status"] {
                if !fm.contains_key(f) {
                    v.push(violation(
                        2,
                        "frontmatter.field",
                        &format!("필수 필드 {f} 없음"),
                    ));
                }
            }
            if !TYPES
                .iter()
                .any(|(t, _, _)| *t == get("type").unwrap_or(""))
            {
                v.push(violation(
                    2,
                    "frontmatter.type",
                    &format!("type {}", repr_opt(get("type"))),
                ));
            }
            if !matches!(get("status"), Some("draft" | "approved")) {
                v.push(violation(
                    2,
                    "frontmatter.status",
                    get("status").unwrap_or("None"),
                ));
            }
            let did = get("doc_id").unwrap_or("");
            if !DOC_ID.is_match(did) {
                // 빈 값은 「create_document에 보낸 본문을 그대로 되돌려준」 흔한 실수다 (#51)
                let message = if did.is_empty() {
                    "비어 있음 — get_document가 돌려준 본문에서 시작하라".to_string()
                } else {
                    format!("형식 {}", repr(did))
                };
                v.push(violation(2, "frontmatter.doc_id", &message));
            } else if did.split('-').nth(1) != Some(dt) {
                v.push(violation(
                    2,
                    "frontmatter.doc_id",
                    &format!("{did}의 타입 ≠ {dt}"),
                ));
            }
            let upstream = get("upstream").unwrap_or("").trim_matches(['[', ']']);
            for u in UPSTREAM_TOKEN.find_iter(upstream) {
                if !DOC_ID.is_match(u.as_str()) {
                    v.push(violation(
                        2,
                        "frontmatter.ref",
                        &format!("upstream {}", repr(u.as_str())),
                    ));
                }
            }
            // 서브타입이 있는 타입(DOM·UI·API)은 제목의 키워드로 무엇인지 안다 (STD-001 2.6~2.8)
            let keys: Vec<&str> = SUBTYPES
                .iter()
                .filter(|(t, _, _, _)| *t == dt)
                .map(|(_, k, _, _)| *k)
                .collect();
            if !keys.is_empty() && subtype_of(dt, get("title")).is_none() {
                let want: Vec<String> = keys.iter().map(|k| format!("「{k}」")).collect();
                v.push(violation(
                    2,
                    "frontmatter.title.subtype",
                    &format!("{dt} 제목에 {} 중 하나가 있어야 한다", want.join("·")),
                ));
            }
            // 2. MCP 경로의 status 변경
            if entry == Entry::Mcp
                && let Some(cs) = current_status
                && get("status") != Some(cs.as_str())
            {
                v.push(violation(
                    2,
                    "frontmatter.status_change",
                    "상태 변경은 웹에서만(UC-H8)",
                ));
            }
        }
        // 3. 헤딩 순회
        let title = get("title");
        let (item_re, secs) = patterns_for(dt, title);
        let mut seen: HashSet<String> = HashSet::new();
        let mut items: Vec<String> = Vec::new();
        let mut sections: Vec<String> = Vec::new();
        let lines = markdown::masked_lines(body);
        for (i0, line) in lines.iter().enumerate() {
            let i = i0 + 1;
            let Some(h) = HEADING.captures(line) else {
                continue;
            };
            let tok = &h[2];
            let rest = h.get(3).map_or("", |m| m.as_str());
            let text = if rest.is_empty() {
                tok.to_string()
            } else {
                format!("{tok} {rest}")
            };
            if let Some(re) = item_re
                && re.is_match(tok)
            {
                if seen.contains(tok) {
                    v.push(violation(i, "item.duplicate", tok));
                }
                seen.insert(tok.to_string());
                items.push(tok.to_string());
                // 되돌리기는 재사용이 아니라 복원이다 (#48) — 에이전트(mcp)가 지운 ID를 다시 쓰는 것만 막는다
                if deleted.contains(tok) && entry != Entry::WebRevert {
                    v.push(violation(
                        i,
                        "item.reused",
                        &format!("{tok} — 삭제된 항목 ID 재사용"),
                    ));
                }
                if has_padding(tok) {
                    v.push(violation(i, "item.padding", tok));
                }
            } else {
                if (tok.ends_with('.') || tok.ends_with(':'))
                    && item_re.is_some_and(|re| re.is_match(drop_last(tok)))
                {
                    v.push(violation(i, "item.punct", tok));
                } else if ID_LIKE.is_match(tok) && item_re.is_some() {
                    v.push(violation(
                        i,
                        "item.pattern",
                        &format!("{tok} — ID처럼 보이지만 {dt} 패턴 아님"),
                    ));
                }
                sections.push(SECTION_NUM.replace(&text, "").into_owned());
                // 단어형 ID 타입에서만 — 절 제목이 항목으로 오인될 위험이 그쪽에만 있다. H1은 문서 제목
                if h[1].len() > 1
                    && item_re.is_some()
                    && matches!(doc_type, DocType::Dom | DocType::Ms | DocType::Api)
                    && !tok.starts_with(is_decimal)
                {
                    let head: String = text.chars().take(40).collect();
                    w.push(warning("section.unnumbered", &head));
                }
            }
        }
        // 4. 참조 형식
        for (i0, line) in lines.iter().enumerate() {
            for c in REF.captures_iter(line) {
                let r = &c[1];
                let (d, it) = r.split_once('#').unwrap_or((r, ""));
                let d = if d.is_empty() {
                    get("doc_id").unwrap_or("")
                } else {
                    d
                };
                if !DOC_ID.is_match(d) || (!it.is_empty() && it.contains(' ')) {
                    v.push(violation(i0 + 1, "ref.format", r));
                }
            }
        }
        // 5. 미완성
        for s in secs {
            if !sections.iter().any(|sec| sec.starts_with(s)) {
                w.push(warning("section.missing", s));
            }
        }
        if items.is_empty() && !matches!(doc_type, DocType::Code | DocType::Std) {
            w.push(warning("item.none", ""));
        }
        // 6. DOM 클래스 명세 — 2장·4장 엔티티 속성 대조 · 「폴더 구조」 절의 층 표(카드 BM)
        if doc_type == DocType::Dom && title.unwrap_or("").contains("클래스") {
            w.extend(entity_mismatch(body));
            if !has_layer_table(&lines) {
                w.push(warning("layer.table", ""));
            }
        }
        // 7. INFRA 제약 — 줄 머리 「출처:」 (STD-001 2.5·4장, #120). 마스킹한 줄이라 코드블록 안은 안 센다
        if doc_type == DocType::Infra {
            for b in SpecService::item_blocks(body, doc_type, title) {
                if !lines[b.start_line..b.end_line]
                    .iter()
                    .any(|x| x.starts_with("출처:"))
                {
                    w.push(warning("constraint.source", &b.item_id));
                }
            }
        }
        ValidateResult {
            violations: v,
            warnings: w,
        }
    }

    /// SYNC-MS-014#SpecService.apply_frontmatter
    pub fn apply_frontmatter(
        body: &str,
        doc_id: &str,
        doc_type: DocType,
        status: DocStatus,
    ) -> Result<String, Problem> {
        let (fm, fm_lines) = markdown::parse_frontmatter(body);
        if fm.is_empty() {
            let title = H1
                .captures(body)
                .map_or_else(|| doc_id.to_string(), |c| strip(&c[1]).to_string());
            return Ok(format!(
                "---\ndoc_id: {doc_id}\ntype: {}\ntitle: {title}\nstatus: {}\n---\n{body}",
                doc_type.as_str(),
                status.as_str()
            ));
        }
        if let Some(cur) = fm.get("doc_id")
            && !cur.is_empty()
            && cur != doc_id
        {
            return Err(Problem::ConventionViolation {
                violations: vec![violation(
                    2,
                    "frontmatter.doc_id",
                    &format!("발급 {doc_id}와 다름: {cur}"),
                )],
                warnings: Vec::new(),
            });
        }
        // 덮어쓸 키 — 첫 줄만 바꾸고, 없는 키는 이 차례로 끝에 더한다
        let mut forced: IndexMap<&str, &str> = IndexMap::from([
            ("doc_id", doc_id),
            ("type", doc_type.as_str()),
            ("status", status.as_str()),
        ]);
        let lines: Vec<&str> = body.split('\n').collect();
        let mut out: Vec<String> = vec!["---".to_string()];
        for line in &lines[1..fm_lines - 1] {
            match line.split_once(':') {
                Some((k, _)) if forced.contains_key(strip(k)) => {
                    let k = strip(k);
                    let v = forced.shift_remove(k).unwrap_or_default();
                    out.push(format!("{k}: {v}"));
                }
                _ => out.push((*line).to_string()),
            }
        }
        out.extend(forced.iter().map(|(k, v)| format!("{k}: {v}")));
        out.push("---".to_string());
        out.extend(lines[fm_lines..].iter().map(|l| (*l).to_string()));
        Ok(out.join("\n"))
    }

    /// SYNC-MS-014#SpecService.diff
    pub async fn diff(
        &mut self,
        doc_id: &str,
        from_no: i32,
        to_no: i32,
        context: usize,
    ) -> Result<Diff, Problem> {
        let Some(row) = repo::document_by_doc_id(&mut *self.db, doc_id).await? else {
            return Err(Problem::NotFound {
                resource: "document".to_string(),
                id: serde_json::Value::from(doc_id),
            });
        };
        let bodies = repo::version_bodies(&mut *self.db, row.id, &[from_no, to_no]).await?;
        for no in [from_no, to_no] {
            if !bodies.contains_key(&no) {
                return Err(Problem::NotFound {
                    resource: "version".to_string(),
                    id: serde_json::Value::from(format!("{doc_id} v{no}")),
                });
            }
        }
        let doc_type = DocType::parse(&row.doc_type).ok_or_else(|| Problem::Internal {
            log: format!("문서 {doc_id}의 타입 {}을 모른다", row.doc_type),
        })?;
        let (a, b) = (bodies[&from_no].clone(), bodies[&to_no].clone());
        // 긴 블록의 diff는 일꾼 스레드를 막지 않게 (SYNC-STD-004#DEV-16)
        tokio::task::spawn_blocking(move || {
            SpecService::diff_bodies(&a, &b, doc_type, from_no, to_no, context)
        })
        .await
        .map_err(|e| Problem::Internal {
            log: format!("diff: {e}"),
        })
    }

    /// SYNC-MS-014#SpecService.diff_bodies
    pub fn diff_bodies(
        from: &str,
        to: &str,
        doc_type: DocType,
        from_no: i32,
        to_no: i32,
        context: usize,
    ) -> Diff {
        let src = split_items(from, doc_type);
        let dst = split_items(to, doc_type);
        let mut order: Vec<Option<String>> = dst.keys().cloned().collect();
        order.extend(src.keys().filter(|k| !dst.contains_key(*k)).cloned());
        order.sort_by_key(|k| k.is_none()); // 항목 밖 글은 마지막 — 안정 정렬
        let mut hunks = Vec::new();
        for item_id in order {
            let a = src.get(&item_id).map_or("", String::as_str);
            let b = dst.get(&item_id).map_or("", String::as_str);
            if normalized(a) == normalized(b) {
                continue; // 공백만 바뀜 → hunk 없음
            }
            let lines = if a.is_empty() || b.is_empty() {
                // 새로 생긴 항목은 전부 add, 사라진 항목은 전부 del
                let (op, text) = if a.is_empty() {
                    (DiffOp::Add, b)
                } else {
                    (DiffOp::Del, a)
                };
                text.trim_end_matches('\n')
                    .split('\n')
                    .map(|t| DiffLine {
                        op,
                        text: t.to_string(),
                    })
                    .collect()
            } else {
                let al: Vec<&str> = a.split('\n').collect();
                let bl: Vec<&str> = b.split('\n').collect();
                // 머리 두 줄(`--- `·`+++ `)과 `@@`만 버린다 (#345)
                unified_diff(&al, &bl, context)
                    .into_iter()
                    .skip(2)
                    .filter(|ln| !ln.starts_with("@@"))
                    .map(|ln| {
                        let op = match ln.as_bytes().first() {
                            Some(b'+') => DiffOp::Add,
                            Some(b'-') => DiffOp::Del,
                            _ => DiffOp::Ctx,
                        };
                        DiffLine {
                            op,
                            text: ln[1..].to_string(),
                        }
                    })
                    .collect()
            };
            hunks.push(Hunk {
                item_id,
                lines,
                downstream_count: 0,
            });
        }
        Diff {
            from_version: from_no,
            to_version: to_no,
            hunks,
        }
    }

    /// SYNC-MS-014#SpecService.list_by_project
    pub async fn list_by_project(
        &mut self,
        project_id: i32,
        stage: Option<i32>,
        status: Option<DocStatus>,
        has_convention_error: Option<bool>,
    ) -> Result<Vec<DocumentSummary>, Problem> {
        let mut rows: Vec<_> = repo::documents_of_project(&mut *self.db, project_id)
            .await?
            .into_iter()
            .filter(|r| r.trashed_at.is_none())
            .filter(|r| stage.is_none() || stage_of(&r.doc_type) == stage)
            .filter(|r| status.is_none_or(|s| r.status == s.as_str()))
            .filter(|r| has_convention_error.is_none_or(|h| r.has_convention_error == h))
            .collect();
        let ids: Vec<i32> = rows.iter().map(|r| r.id).collect();
        let latest = repo::latest_versions(&mut *self.db, &ids).await?;
        rows.sort_by(|a, b| {
            (stage_of(&a.doc_type).unwrap_or(99), &a.doc_id)
                .cmp(&(stage_of(&b.doc_type).unwrap_or(99), &b.doc_id))
        });
        rows.into_iter()
            .map(|r| {
                let warnings: Vec<String> =
                    serde_json::from_str(r.incomplete_warnings.as_deref().unwrap_or("[]"))
                        .map_err(|e| Problem::Internal {
                            log: format!(
                                "{}의 incomplete_warnings가 JSON 목록이 아니다 — {e}",
                                r.doc_id
                            ),
                        })?;
                Ok(DocumentSummary {
                    id: r.id,
                    stage: stage_of(&r.doc_type),
                    author: None,
                    last_author: latest.get(&r.id).map(|v| AuthorRef {
                        kind: v.author_kind.clone(),
                        user_id: v.author_user_id,
                        instructed_by_id: v.instructed_by_user_id,
                        via: v.via.clone(),
                    }),
                    doc_id: r.doc_id,
                    doc_type: r.doc_type,
                    status: r.status,
                    current_version_no: r.current_version_no,
                    has_convention_error: r.has_convention_error,
                    incomplete_warnings: warnings,
                    updated_at: r.updated_at,
                    counts: Default::default(),
                    trashed_at: r.trashed_at,
                })
            })
            .collect()
    }
}
