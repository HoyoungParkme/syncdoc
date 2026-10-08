//! SpecService — SYNC-MS-014 (파이썬 판 SYNC-MS-002와 같은 이름·같은 처리). 카드 L5 몫은 명세 엔진이다.
//! 파이썬 판과 바이트까지 같다 — 문자 분류·정규식·repr·difflib은 `pycompat`(파이썬 3.12)로.
//! 맞춤은 정답 파일(`crates/core/tests/golden/spec.json`)과 `cargo xtask spec-diff`가 본다.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;
use sqlx::PgConnection;

use super::model::{DocumentRow, VersionRow};
use super::repo;
use crate::clock;
use crate::errors::Problem;
use crate::markdown::{self, DOC_ID, HEADING, REF};
use crate::pycompat::chars::{is_decimal, lstrip, strip};
use crate::pycompat::difflib::unified_diff;
use crate::pycompat::re::compile;
use crate::pycompat::repr::repr;
use crate::types::{
    Author, AuthorRef, Diff, DiffLine, DiffOp, DocItem, DocRef, DocStatus, DocType, Document,
    DocumentSummary, Entry, Hunk, ItemBlock, ItemRef, ItemView, ValidateResult, Violation, Warning,
    fold_via, py_isoformat, stage_of,
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

/// 판 행 → 작성자(id만) — 파이썬 `_author_of`
fn author_of(v: &VersionRow) -> AuthorRef {
    AuthorRef {
        kind: v.author_kind.clone(),
        user_id: v.author_user_id,
        instructed_by_id: v.instructed_by_user_id,
        via: v.via.clone(),
    }
}

/// 문서 행 + 최근 판 → 요약 — 파이썬 `_summary_fields`. `incomplete_warnings`는 JSON 목록(없거나 비면 빈 것)
fn summary_of(r: &DocumentRow, latest: Option<&VersionRow>) -> Result<DocumentSummary, Problem> {
    let raw = r
        .incomplete_warnings
        .as_deref()
        .filter(|w| !w.is_empty())
        .unwrap_or("[]");
    let warnings: Vec<String> = serde_json::from_str(raw).map_err(|e| Problem::Internal {
        log: format!(
            "{}의 incomplete_warnings가 JSON 목록이 아니다 — {e}",
            r.doc_id
        ),
    })?;
    Ok(DocumentSummary {
        id: r.id,
        doc_id: r.doc_id.clone(),
        doc_type: r.doc_type.clone(),
        stage: stage_of(&r.doc_type),
        status: r.status.clone(),
        current_version_no: r.current_version_no,
        has_convention_error: r.has_convention_error,
        incomplete_warnings: warnings,
        updated_at: r.updated_at,
        last_author: latest.map(author_of),
        author: None,
        counts: Default::default(),
        trashed_at: r.trashed_at,
    })
}

/// 타입 문자열로 항목 블록 — 모르는 타입이면 없다(파이썬 `patterns_for`가 패턴을 못 준다)
fn blocks_of(body: &str, doc_type: &str, title: Option<&str>) -> Vec<ItemBlock> {
    DocType::parse(doc_type).map_or_else(Vec::new, |t| SpecService::item_blocks(body, t, title))
}

/// 규약 결과 → documents의 오류·경고 열 — 파이썬 `_apply_validate`.
/// 오류 문장은 `rule: message`를 줄마다, 경고는 `str(w)`들의 JSON 목록(`ensure_ascii` 없이, 비면 없음)
fn convention_columns(vr: &ValidateResult) -> (bool, Option<String>, Option<String>) {
    let detail = vr
        .violations
        .iter()
        .map(|v| format!("{}: {}", v.rule, v.message))
        .collect::<Vec<_>>()
        .join("\n");
    let warnings = (!vr.warnings.is_empty()).then(|| {
        let items: Vec<String> = vr
            .warnings
            .iter()
            .map(|w| serde_json::to_string(&w.to_string()).unwrap_or_default())
            .collect();
        format!("[{}]", items.join(", "))
    });
    (
        !vr.violations.is_empty(),
        (!detail.is_empty()).then_some(detail),
        warnings,
    )
}

/// 새 판 행 — 시각은 저장 시각(SYNC-STD-004#DEV-18), `via`는 입구를 접은 것 (파이썬 `_new_version`)
fn new_version<'a>(
    document_id: i32,
    version_no: i32,
    commit_hash: &'a str,
    body: &'a str,
    author: &Author,
    message: &'a str,
) -> repo::NewVersion<'a> {
    repo::NewVersion {
        document_id,
        version_no,
        commit_hash,
        body,
        author_kind: author.kind.as_str(),
        author_user_id: author.user.id,
        instructed_by_user_id: author.instructed_by.as_ref().map(|u| u.id),
        via: fold_via(author.via),
        message,
        created_at: clock::now(),
    }
}

fn not_found(resource: &str, id: &str) -> Problem {
    Problem::NotFound {
        resource: resource.to_string(),
        id: serde_json::Value::from(id),
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

    /// SYNC-MS-014#SpecService.validate
    pub async fn validate(
        &mut self,
        body: &str,
        doc_type: &str,
        entry: Entry,
        current_status: Option<DocStatus>,
    ) -> Result<ValidateResult, Problem> {
        let (fm, _) = markdown::parse_frontmatter(body);
        let deleted = self
            .deleted_item_ids(fm.get("doc_id").map(String::as_str))
            .await?;
        let (body, doc_type) = (body.to_string(), doc_type.to_string());
        // 긴 본문 파싱은 일꾼 스레드를 막지 않게 (SYNC-STD-004#DEV-16)
        tokio::task::spawn_blocking(move || {
            SpecService::check(&body, &doc_type, entry, current_status, &deleted)
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
    ///
    /// 타입은 문자열 그대로 — 모르는 타입도 파이썬처럼 `frontmatter.type` 위반까지 간다
    pub fn check(
        body: &str,
        doc_type: &str,
        entry: Entry,
        current_status: Option<DocStatus>,
        deleted: &HashSet<String>,
    ) -> ValidateResult {
        let dt = doc_type;
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
                    && matches!(dt, "DOM" | "MS" | "API")
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
        if items.is_empty() && !matches!(dt, "CODE" | "STD") {
            w.push(warning("item.none", ""));
        }
        // 6. DOM 클래스 명세 — 2장·4장 엔티티 속성 대조 · 「폴더 구조」 절의 층 표(카드 BM)
        if dt == "DOM" && title.unwrap_or("").contains("클래스") {
            w.extend(entity_mismatch(body));
            if !has_layer_table(&lines) {
                w.push(warning("layer.table", ""));
            }
        }
        // 7. INFRA 제약 — 줄 머리 「출처:」 (STD-001 2.5·4장, #120). 마스킹한 줄이라 코드블록 안은 안 센다
        if dt == "INFRA" {
            for b in SpecService::item_blocks(body, DocType::Infra, title) {
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
        doc_type: &str,
        status: DocStatus,
    ) -> Result<String, Problem> {
        let (fm, fm_lines) = markdown::parse_frontmatter(body);
        if fm.is_empty() {
            let title = H1
                .captures(body)
                .map_or_else(|| doc_id.to_string(), |c| strip(&c[1]).to_string());
            return Ok(format!(
                "---\ndoc_id: {doc_id}\ntype: {doc_type}\ntitle: {title}\nstatus: {}\n---\n{body}",
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
            ("type", doc_type),
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
    ///
    /// 상태는 문자열 그대로 비교한다 — MCP `list_documents`가 받은 값을 거르지 않는다(파이썬과 같다)
    pub async fn list_by_project(
        &mut self,
        project_id: i32,
        stage: Option<i32>,
        status: Option<&str>,
        has_convention_error: Option<bool>,
    ) -> Result<Vec<DocumentSummary>, Problem> {
        let mut rows: Vec<_> = repo::documents_of_project(&mut *self.db, project_id)
            .await?
            .into_iter()
            .filter(|r| r.trashed_at.is_none())
            .filter(|r| stage.is_none() || stage_of(&r.doc_type) == stage)
            .filter(|r| status.is_none_or(|s| r.status == s))
            .filter(|r| has_convention_error.is_none_or(|h| r.has_convention_error == h))
            .collect();
        let ids: Vec<i32> = rows.iter().map(|r| r.id).collect();
        let latest = repo::latest_versions(&mut *self.db, &ids).await?;
        rows.sort_by(|a, b| {
            (stage_of(&a.doc_type).unwrap_or(99), &a.doc_id)
                .cmp(&(stage_of(&b.doc_type).unwrap_or(99), &b.doc_id))
        });
        rows.iter()
            .map(|r| summary_of(r, latest.get(&r.id)))
            .collect()
    }

    /// SYNC-MS-014#SpecService.get_document
    pub async fn get_document(&mut self, doc_id: &str) -> Result<Document, Problem> {
        let Some(row) = repo::document_by_doc_id(&mut *self.db, doc_id).await? else {
            return Err(not_found("document", doc_id));
        };
        let items = repo::items_of(&mut *self.db, row.id, false)
            .await?
            .into_iter()
            .map(|i| DocItem {
                pk: i.id,
                item_id: i.item_id,
                display_name: i.display_name,
                missing_refs: Vec::new(),
            })
            .collect();
        let latest = repo::latest_version(&mut *self.db, row.id).await?;
        Ok(Document {
            summary: summary_of(&row, latest.as_ref())?,
            body: row.current_body,
            commit_hash: latest.as_ref().map(|v| v.commit_hash.clone()),
            current_version_id: latest.as_ref().map(|v| v.id),
            missing_refs: Vec::new(),
            convention_error_detail: row.convention_error_detail,
            items,
            prev_doc_id: None,
            next_doc_id: None,
            project_name: String::new(),
        })
    }

    /// SYNC-MS-014#SpecService.issue_doc_id
    pub async fn issue_doc_id(
        &mut self,
        project_id: i32,
        code: &str,
        doc_type: &str,
    ) -> Result<String, Problem> {
        let mut max = 0i64;
        // 휴지통 것까지 센다 — 번호를 다시 쓰지 않는다. 끝 `-` 뒤 수(파이썬 `int(d.rsplit("-", 1)[1])`)
        for d in repo::doc_ids_of_type(&mut *self.db, project_id, doc_type).await? {
            let tail = d.rsplit_once('-').map_or(d.as_str(), |(_, t)| t);
            let n: i64 = tail.parse().map_err(|_| Problem::Internal {
                log: format!("문서 ID {d}의 번호를 못 읽는다"),
            })?;
            max = max.max(n);
        }
        Ok(format!("{code}-{doc_type}-{:03}", max + 1))
    }

    /// SYNC-MS-014#SpecService.precondition
    ///
    /// DOM 셋의 순서 — 클래스 명세 ← API 문서, ERD ← 클래스 명세. 존재만 본다(상태·승인은 신호, PRD R6)
    pub async fn precondition(
        &mut self,
        project_id: i32,
        doc_type: &str,
        title: &str,
    ) -> Result<Option<(String, Vec<String>)>, Problem> {
        if doc_type != "DOM" {
            return Ok(None);
        }
        let key = |t: Option<&str>| subtype_of("DOM", t).map(|i| SUBTYPES[i].1);
        let sub = key(Some(title));
        if !matches!(sub, Some("클래스" | "ERD")) {
            return Ok(None); // 도메인 모델은 첫 문서다. 키워드 없음은 validate가 잡는다
        }
        let docs = repo::documents_of_project(&mut *self.db, project_id).await?;
        let (ok, requires) = if sub == Some("클래스") {
            (
                docs.iter().any(|d| d.doc_type == "API"),
                "API 문서(REST 또는 MCP) — 클래스의 메서드는 API가 정한다",
            )
        } else {
            // 제목은 documents에 열이 없다 — 본문 frontmatter에서
            (
                docs.iter().any(|d| {
                    d.doc_type == "DOM"
                        && key(markdown::parse_frontmatter(&d.current_body)
                            .0
                            .get("title")
                            .map(String::as_str))
                            == Some("클래스")
                }),
                "DOM 클래스 명세 — 테이블은 엔티티 클래스에서 나온다",
            )
        };
        if ok {
            return Ok(None);
        }
        let mut have: Vec<String> = docs
            .iter()
            .filter(|d| d.doc_type == "DOM")
            .map(|d| d.doc_id.clone())
            .collect();
        have.sort();
        Ok(Some((requires.to_string(), have)))
    }

    /// SYNC-MS-014#SpecService.get_item
    ///
    /// `~`는 `/`로 — 경로에 `/`를 못 싣는 항목 ID(`GET/api/me`)를 MCP·웹이 그렇게 보낸다
    pub async fn get_item(&mut self, doc_id: &str, item_id: &str) -> Result<ItemView, Problem> {
        let document = self.get_document(doc_id).await?;
        let item_id = item_id.replace('~', "/");
        let Some(item) = repo::item_of(&mut *self.db, document.summary.id, &item_id).await? else {
            return Err(Problem::NotFoundWithItems {
                resource: "item".to_string(),
                id: format!("{doc_id}#{item_id}"),
                available_items: document.items.iter().map(|i| i.item_id.clone()).collect(),
            });
        };
        if item.is_deleted {
            return Err(Problem::ItemDeleted {
                deleted_at: item.deleted_at.map(py_isoformat),
            });
        }
        let block = blocks_of(&document.body, &document.summary.doc_type, None)
            .into_iter()
            .find(|b| b.item_id == item_id)
            .ok_or_else(|| Problem::Internal {
                log: format!("{doc_id}#{item_id} 행은 있는데 본문에 블록이 없다"),
            })?;
        Ok(ItemView {
            pk: item.id,
            doc_id: doc_id.to_string(),
            item_id,
            display_name: item.display_name,
            body: block.text,
            doc_status: document.summary.status,
            doc_version_no: document.summary.current_version_no,
        })
    }

    /// SYNC-MS-014#SpecService.detect_deleted_items
    pub async fn detect_deleted_items(
        &mut self,
        document: &Document,
        body: &str,
    ) -> Result<Vec<i32>, Problem> {
        let new_ids: HashSet<String> = blocks_of(body, &document.summary.doc_type, None)
            .into_iter()
            .map(|b| b.item_id)
            .collect();
        Ok(repo::items_of(&mut *self.db, document.summary.id, false)
            .await?
            .into_iter()
            .filter(|i| !new_ids.contains(&i.item_id))
            .map(|i| i.id)
            .collect())
    }

    /// SYNC-MS-014#SpecService.describe_items
    pub async fn describe_items(
        &mut self,
        item_pks: &[i32],
    ) -> Result<HashMap<i32, ItemRef>, Problem> {
        if item_pks.is_empty() {
            return Ok(HashMap::new());
        }
        Ok(repo::items_with_doc_id(&mut *self.db, item_pks)
            .await?
            .into_iter()
            .map(|r| {
                let ref_ = ItemRef {
                    doc_id: Some(r.doc_id),
                    item_id: Some(r.item.item_id),
                    display_name: r.item.display_name,
                    is_deleted: r.item.is_deleted,
                    deleted_at: r.item.deleted_at,
                    ..ItemRef::default()
                };
                (r.item.id, ref_)
            })
            .collect())
    }

    /// SYNC-MS-014#SpecService.describe_documents
    pub async fn describe_documents(
        &mut self,
        document_ids: &[i32],
    ) -> Result<HashMap<i32, DocRef>, Problem> {
        if document_ids.is_empty() {
            return Ok(HashMap::new());
        }
        Ok(repo::documents_by_ids(&mut *self.db, document_ids)
            .await?
            .into_iter()
            .map(|r| {
                // 제목은 frontmatter에서, 비면 문서 ID (파이썬 `… or row.doc_id`)
                let title = markdown::parse_frontmatter(&r.current_body)
                    .0
                    .get("title")
                    .filter(|t| !t.is_empty())
                    .cloned()
                    .unwrap_or_else(|| r.doc_id.clone());
                let d = DocRef {
                    document_id: r.id,
                    stage: stage_of(&r.doc_type),
                    doc_id: r.doc_id,
                    title,
                    status: r.status,
                };
                (d.document_id, d)
            })
            .collect())
    }

    /// SYNC-MS-014#SpecService.create
    ///
    /// 상태는 frontmatter가 `draft`·`approved`면 그것, 아니면 `draft`(둘 밖의 값은 DB에 들이지 않는다, #99)
    #[allow(clippy::too_many_arguments)]
    pub async fn create(
        &mut self,
        project_id: i32,
        doc_id: &str,
        doc_type: &str,
        body: &str,
        commit_hash: &str,
        author: &Author,
        message: &str,
        validate_result: &ValidateResult,
    ) -> Result<VersionRow, Problem> {
        let (fm, _) = markdown::parse_frontmatter(body);
        let status = match fm.get("status").map(String::as_str) {
            Some(s @ ("draft" | "approved")) => s,
            _ => "draft",
        };
        let (has_error, detail, warnings) = convention_columns(validate_result);
        let id = repo::insert_document(
            &mut *self.db,
            &repo::NewDocument {
                project_id,
                doc_id,
                doc_type,
                status,
                body,
                has_convention_error: has_error,
                convention_error_detail: detail.as_deref(),
                incomplete_warnings: warnings.as_deref(),
            },
        )
        .await?;
        for b in blocks_of(body, doc_type, fm.get("title").map(String::as_str)) {
            repo::insert_item(&mut *self.db, id, &b.item_id, &b.display_name).await?;
        }
        Ok(repo::insert_version(
            &mut *self.db,
            &new_version(id, 1, commit_hash, body, author, message),
        )
        .await?)
    }

    /// SYNC-MS-014#SpecService.save
    ///
    /// 파이썬 `save`의 `mcp` 갈래 — 재구축(`rebuild`)과 상태 커밋 해시(`github`)는 카드 L11
    #[allow(clippy::too_many_arguments)]
    pub async fn save(
        &mut self,
        document: &Document,
        body: &str,
        commit_hash: &str,
        author: &Author,
        message: &str,
        deleted_item_pks: &[i32],
        validate_result: &ValidateResult,
    ) -> Result<VersionRow, Problem> {
        let row = repo::document_by_id(&mut *self.db, document.summary.id)
            .await?
            .ok_or_else(|| Problem::Internal {
                log: format!("저장할 문서 {}가 없다", document.summary.doc_id),
            })?;
        let new_no = row.current_version_no + 1;
        let version = repo::insert_version(
            &mut *self.db,
            &new_version(row.id, new_no, commit_hash, body, author, message),
        )
        .await?;
        let (fm, _) = markdown::parse_frontmatter(body);
        for b in blocks_of(body, &row.doc_type, fm.get("title").map(String::as_str)) {
            match repo::item_of(&mut *self.db, row.id, &b.item_id).await? {
                // 본문에 다시 나타났으므로 되살린다 (MS-002 save 3, #15)
                Some(item) => repo::restore_item(&mut *self.db, item.id, &b.display_name).await?,
                None => {
                    repo::insert_item(&mut *self.db, row.id, &b.item_id, &b.display_name).await?;
                }
            }
        }
        for pk in deleted_item_pks {
            repo::mark_item_deleted(&mut *self.db, *pk, clock::now()).await?;
        }
        // github는 frontmatter가 진실이다. 둘 밖의 값이면 DB를 안 바꾼다 (#99)
        let fm_status = fm
            .get("status")
            .map(String::as_str)
            .filter(|s| matches!(*s, "draft" | "approved"));
        let mut new_status = match (author.via, fm_status) {
            (Entry::Github, Some(s)) => s,
            _ => row.status.as_str(),
        };
        // 6. 자동 강등 — mcp·되돌리기는 이 자리에서 내린다(본문 커밋 하나에 담기므로 커밋 해시 없음) (#58)
        if row.status == "approved" && body != row.current_body && new_status == "approved" {
            new_status = "draft";
            repo::insert_status_change(
                &mut *self.db,
                &repo::NewStatusChange {
                    document_id: row.id,
                    from_status: Some("approved"),
                    to_status: "draft",
                    changed_by_user_id: author.user.id,
                    via: fold_via(author.via),
                    reason: Some("본문 수정으로 자동 강등"),
                    commit_hash: None,
                    changed_at: clock::now(),
                },
            )
            .await?;
        }
        let (has_error, detail, warnings) = convention_columns(validate_result);
        // 7. 어느 입구든 저장되면 휴지통에서 나온다 (UC-A8 4)
        repo::update_saved_document(
            &mut *self.db,
            &repo::SavedDocument {
                id: row.id,
                body,
                version_no: new_no,
                status: new_status,
                has_convention_error: has_error,
                convention_error_detail: detail.as_deref(),
                incomplete_warnings: warnings.as_deref(),
            },
        )
        .await?;
        Ok(version)
    }
}
