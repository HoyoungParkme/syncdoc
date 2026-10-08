//! SYNC-MS-014 테스트 관점 — 정답 파일(파이썬 판이 만든 것)과 같고, 파이썬 판 SYNC-MS-002의 경우들

#[path = "support/spec_answers.rs"]
mod spec_answers;
mod support;

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde_json::Value;
use sqlx::PgConnection;
use syncdoc_core::errors::Problem;
use syncdoc_core::markdown;
use syncdoc_core::spec::{DIFF_CONTEXT_LINES, SpecService};
use syncdoc_core::types::{DiffOp, DocStatus, DocType, Entry};

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("저장소 뿌리")
}

fn golden() -> Value {
    let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/golden/spec.json");
    serde_json::from_str(&std::fs::read_to_string(p).expect("정답 파일")).expect("JSON")
}

#[test]
fn golden_cases_match_python() {
    let g = golden();
    let cases = g["cases"].as_array().expect("cases");
    let mut bad = Vec::new();
    for py in cases {
        let rs = spec_answers::answer(&spec_answers::input_of(py));
        if let Some(d) = spec_answers::first_difference("", py, &rs) {
            bad.push(format!("{} — {d}", py["name"]));
        }
    }
    assert!(cases.len() >= 100, "본 사례 {}", cases.len()); // 본 것의 수 (STD-004)
    assert!(
        bad.is_empty(),
        "{}/{} 다르다:\n{}",
        bad.len(),
        cases.len(),
        bad.join("\n")
    );
}

#[test]
fn pattern_tables_are_python_strings() {
    assert_eq!(golden()["patterns"], spec_answers::patterns());
}

/// 지금의 명세 — 템플릿 빼고 전부
fn specs() -> Vec<PathBuf> {
    let mut out = Vec::new();
    for dir in std::fs::read_dir(repo_root().join("docs/specs")).expect("명세") {
        let dir = dir.expect("자리").path();
        if !dir.is_dir() || dir.ends_with("_templates") {
            continue;
        }
        for f in std::fs::read_dir(&dir).expect("문서") {
            let f = f.expect("파일").path();
            if f.extension().is_some_and(|e| e == "md") {
                out.push(f);
            }
        }
    }
    out.sort();
    out
}

#[test]
fn every_spec_passes_check_with_no_warnings() {
    let specs = specs();
    assert!(specs.len() >= 30, "본 명세 {}", specs.len());
    for path in specs {
        let body = std::fs::read_to_string(&path).expect("본문");
        let (fm, _) = markdown::parse_frontmatter(&body);
        let dt = DocType::parse(&fm["type"]).expect("타입");
        let r = SpecService::check(&body, dt, Entry::Github, None, &HashSet::new());
        assert!(
            r.violations.is_empty() && r.warnings.is_empty(),
            "{}: {r:?}",
            path.display()
        );
    }
}

#[test]
fn every_template_filled_with_an_id_passes() {
    let dir = repo_root().join("docs/specs/_templates");
    let mut seen = 0;
    let mut names: Vec<_> = std::fs::read_dir(&dir)
        .expect("템플릿")
        .map(|e| e.expect("파일").file_name().into_string().expect("이름"))
        .collect();
    names.sort();
    for name in names {
        if name == "DOM.md" || name == "API.md" || !name.ends_with(".md") {
            continue;
        }
        let typ = name.split('-').next().unwrap_or("").trim_end_matches(".md");
        let body = std::fs::read_to_string(dir.join(&name))
            .expect("본문")
            .replacen("doc_id: \n", &format!("doc_id: XXXX-{typ}-001\n"), 1);
        let r = SpecService::check(
            &body,
            DocType::parse(typ).expect("타입"),
            Entry::Github,
            None,
            &HashSet::new(),
        );
        assert!(
            r.violations.is_empty() && r.warnings.is_empty(),
            "{name}: {r:?}"
        );
        seen += 1;
    }
    assert_eq!(seen, 15); // 본 것의 수 — 0이면 안 본 것이다
}

const PRD: &str = "---\ndoc_id: EXMP-PRD-001\ntype: PRD\ntitle: 예시 제품\nstatus: draft\nupstream: [EXMP-RFQ-001]\n---\n\n# 예시 제품 PRD\n\n## 1. 목표\n\n#### G1 첫 목표\n한 줄로.\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명. 근거: [[EXMP-RFQ-001#Q2]]\n##### 인수기준\n- [ ] 둘\n\n#### N1 성능\n```markdown\n#### R99 코드블록 안 헤딩은 항목이 아니다 [[BAD REF]]\n```\n\n## 4. 성공지표\n\n## 5. 미결사항\n";

#[test]
fn item_blocks_boundaries_like_ms_002() {
    let blocks = SpecService::item_blocks(PRD, DocType::Prd, None);
    let ids: Vec<&str> = blocks.iter().map(|b| b.item_id.as_str()).collect();
    assert_eq!(ids, ["G1", "R1", "N1"]);
    assert!(blocks[1].text.contains("##### 인수기준")); // 아래 레벨은 블록 안
    assert!(blocks[2].text.contains("R99") && !blocks[2].text.contains("## 4."));
}

#[test]
fn check_variants_like_ms_002() {
    let none = HashSet::new();
    let rules = |body: &str, entry, cs, deleted: &HashSet<String>| -> Vec<String> {
        SpecService::check(body, DocType::Prd, entry, cs, deleted)
            .violations
            .into_iter()
            .map(|v| v.rule)
            .collect()
    };
    assert!(rules(PRD, Entry::Mcp, None, &none).is_empty());
    assert_eq!(
        rules("# 없음\n", Entry::Github, None, &none),
        ["frontmatter.missing"]
    );
    assert_eq!(
        rules(
            &PRD.replace("#### R1 ", "#### R01 "),
            Entry::Github,
            None,
            &none
        ),
        ["item.padding"]
    );
    assert_eq!(
        rules(
            &PRD.replace("#### R1 ", "#### R1. "),
            Entry::Github,
            None,
            &none
        ),
        ["item.punct"]
    );
    let deleted: HashSet<String> = ["R1".to_string()].into();
    assert_eq!(rules(PRD, Entry::Mcp, None, &deleted), ["item.reused"]);
    assert!(rules(PRD, Entry::WebRevert, None, &deleted).is_empty()); // 되돌리기는 복원
    assert_eq!(
        rules(PRD, Entry::Mcp, Some(DocStatus::Approved), &none),
        ["frontmatter.status_change"]
    );
    assert!(rules(PRD, Entry::Github, Some(DocStatus::Approved), &none).is_empty());
    let w = SpecService::check(
        &PRD.replace("## 4. 성공지표\n", ""),
        DocType::Prd,
        Entry::Github,
        None,
        &none,
    );
    assert!(w.violations.is_empty() && w.warnings.len() == 1); // 경고 하나, 저장은 된다
}

#[test]
fn apply_frontmatter_like_ms_002() {
    let got = SpecService::apply_frontmatter(
        "# 제목\n본문\n",
        "EXMP-PRD-002",
        DocType::Prd,
        DocStatus::Draft,
    )
    .expect("채움");
    assert_eq!(
        got,
        "---\ndoc_id: EXMP-PRD-002\ntype: PRD\ntitle: 제목\nstatus: draft\n---\n# 제목\n본문\n"
    );
    let err = SpecService::apply_frontmatter(PRD, "EXMP-PRD-009", DocType::Prd, DocStatus::Draft)
        .expect_err("다른 doc_id");
    assert!(matches!(err, Problem::ConventionViolation { .. }));
    let kept =
        SpecService::apply_frontmatter(PRD, "EXMP-PRD-001", DocType::Prd, DocStatus::Approved)
            .expect("같은 doc_id");
    assert!(kept.contains("upstream: [EXMP-RFQ-001]") && kept.contains("status: approved"));
}

#[test]
fn diff_bodies_like_ms_002() {
    let v2 = PRD.replace("한 줄로.", "두 줄로.");
    let d = SpecService::diff_bodies(PRD, &v2, DocType::Prd, 1, 2, DIFF_CONTEXT_LINES);
    let ids: Vec<Option<&str>> = d.hunks.iter().map(|h| h.item_id.as_deref()).collect();
    assert_eq!(ids, [Some("G1")]);
    let ops: Vec<(DiffOp, &str)> = d.hunks[0]
        .lines
        .iter()
        .filter(|l| l.op != DiffOp::Ctx)
        .map(|l| (l.op, l.text.as_str()))
        .collect();
    assert_eq!(ops, [(DiffOp::Del, "한 줄로."), (DiffOp::Add, "두 줄로.")]);
    let ws = PRD.replace("한 줄로.", "  한 줄로.  ");
    assert!(
        SpecService::diff_bodies(PRD, &ws, DocType::Prd, 1, 2, 3)
            .hunks
            .is_empty()
    );
    // #345 — `---` 줄 삭제와 `++`로 시작하는 줄 추가가 남는다
    let a = PRD.replace("한 줄로.\n", "한 줄로.\n---\n");
    let b = PRD.replace("한 줄로.\n", "한 줄로.\n++x\n");
    let d = SpecService::diff_bodies(&a, &b, DocType::Prd, 2, 3, 3);
    let ops: Vec<(DiffOp, &str)> = d.hunks[0]
        .lines
        .iter()
        .filter(|l| l.op != DiffOp::Ctx)
        .map(|l| (l.op, l.text.as_str()))
        .collect();
    assert_eq!(ops, [(DiffOp::Del, "---"), (DiffOp::Add, "++x")]);
}

// ── DB (시험 DB 5434) ──

async fn seed(c: &mut PgConnection, detail: Option<&str>, trashed: bool) -> i32 {
    let user: i32 = sqlx::query_scalar(
        "INSERT INTO users (github_login, display_name, kind) VALUES ('local', '로컬', 'local') RETURNING id",
    )
    .fetch_one(&mut *c)
    .await
    .expect("사용자");
    let project: i32 = sqlx::query_scalar(
        "INSERT INTO projects (code, name, owner_user_id) VALUES ('EXMP', '예시', $1) RETURNING id",
    )
    .bind(user)
    .fetch_one(&mut *c)
    .await
    .expect("프로젝트");
    let doc: i32 = sqlx::query_scalar(
        "INSERT INTO documents (project_id, doc_id, doc_type, status, current_body, current_version_no, \
         convention_error_detail, trashed_at) VALUES ($1, 'EXMP-PRD-001', 'PRD', 'draft', $2, 2, $3, \
         CASE WHEN $4 THEN now() END) RETURNING id",
    )
    .bind(project)
    .bind(PRD)
    .bind(detail)
    .bind(trashed)
    .fetch_one(&mut *c)
    .await
    .expect("문서");
    sqlx::query("INSERT INTO items (document_id, item_id, is_deleted) VALUES ($1, 'R1', true), ($1, 'G1', false)")
        .bind(doc)
        .execute(&mut *c)
        .await
        .expect("항목");
    for (no, body) in [
        (1, PRD.to_string()),
        (2, PRD.replace("한 줄로.", "두 줄로.")),
    ] {
        sqlx::query(
            "INSERT INTO versions (document_id, version_no, commit_hash, body, author_kind, author_user_id, via, message) \
             VALUES ($1, $2, 'h', $3, 'agent', $4, 'mcp', 'spec')",
        )
        .bind(doc)
        .bind(no)
        .bind(body)
        .bind(user)
        .execute(&mut *c)
        .await
        .expect("판");
    }
    doc
}

#[tokio::test]
async fn validate_reads_deleted_ids_and_skips_restored_documents() {
    for (detail, trashed, reused) in [
        (None, false, true),
        (Some("file.deleted: 파일이 지워짐"), false, false),
        (None, true, false),
    ] {
        let db = support::test_db().await;
        let mut c = db.pool.acquire().await.expect("연결");
        seed(&mut c, detail, trashed).await;
        let r = SpecService { db: &mut c }
            .validate(PRD, DocType::Prd, Entry::Mcp, None)
            .await
            .expect("검증");
        let rules: Vec<&str> = r.violations.iter().map(|v| v.rule.as_str()).collect();
        assert_eq!(
            rules.contains(&"item.reused"),
            reused,
            "{detail:?} {trashed}"
        );
        let r = SpecService { db: &mut c }
            .validate(PRD, DocType::Prd, Entry::WebRevert, None)
            .await
            .expect("되돌리기");
        assert!(r.violations.is_empty());
    }
    // 없는 문서·빈 doc_id — 삭제 집합이 비었다
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    let r = SpecService { db: &mut c }
        .validate(PRD, DocType::Prd, Entry::Mcp, None)
        .await
        .expect("없는 문서");
    assert!(r.violations.is_empty());
}

#[tokio::test]
async fn diff_reads_versions_and_reports_not_found_like_python() {
    let db = support::test_db().await;
    let mut c = db.pool.acquire().await.expect("연결");
    seed(&mut c, None, false).await;
    let mut svc = SpecService { db: &mut c };
    let d = svc.diff("EXMP-PRD-001", 1, 2, 3).await.expect("diff");
    assert_eq!(
        d,
        SpecService::diff_bodies(
            PRD,
            &PRD.replace("한 줄로.", "두 줄로."),
            DocType::Prd,
            1,
            2,
            3
        )
    );
    assert!(
        svc.diff("EXMP-PRD-001", 2, 2, 3)
            .await
            .expect("같은 판")
            .hunks
            .is_empty()
    );
    match svc.diff("EXMP-PRD-001", 1, 9, 3).await {
        Err(Problem::NotFound { resource, id }) => {
            assert_eq!(
                (resource.as_str(), id),
                ("version", Value::from("EXMP-PRD-001 v9"))
            )
        }
        other => panic!("판 없음이어야 한다: {other:?}"),
    }
    match svc.diff("EXMP-PRD-404", 1, 2, 3).await {
        Err(Problem::NotFound { resource, id }) => {
            assert_eq!(
                (resource.as_str(), id),
                ("document", Value::from("EXMP-PRD-404"))
            )
        }
        other => panic!("문서 없음이어야 한다: {other:?}"),
    }
}
