//! pipeline — 쓰기 조율 (SYNC-MS-017 · SYNC-DOM-004 4.6). 파이썬 판 `core/pipeline.py`와 같은 이름·같은 처리·같은 차례.
//! 여러 서비스를 한 트랜잭션으로 묶고 git과 DB의 차례를 쥔다 — 검사가 다 끝난 뒤에야 git, git이 끝난 뒤에야 DB.
//! 카드 L7 몫은 `mcp` 입구다. 웹(L9)·GitHub·밀린 커밋 처리(L11)는 그 카드가 갈래를 더한다.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, LazyLock, Mutex};
use std::time::Duration;

use indexmap::IndexMap;
use regex::{NoExpand, Regex};
use sqlx::PgPool;

use crate::account::model::UserRow;
use crate::clock;
use crate::errors::Problem;
use crate::markdown::parse_frontmatter;
use crate::project::repo as project_repo;
use crate::project::service::{ProjectService, ServerRepos};
use crate::pycompat::re::compile;
use crate::reference::service::ReferenceService;
use crate::spec::SpecService;
use crate::types::{
    Author, AuthorKind, DeletedItem, DocStatus, Document, Entry, RefEdge, SaveResult, py_isoformat,
    spec_dir,
};

/// frontmatter의 `status:` 줄 — 첫 것 하나만 갈아 끼운다(파이썬 `_set_status`, `re.M`)
static STATUS_LINE: LazyLock<Regex> = LazyLock::new(|| compile(r"(?m)^status: .*$"));
/// `upstream`의 낱말 — 파이썬 `re.findall(r"[\w-]+", …)`
static UPSTREAM_TOKEN: LazyLock<Regex> = LazyLock::new(|| compile(r"[\w-]+"));

/// 저장 입력 (파이썬 `save_pipeline`의 인자) — 만들기는 `doc_id` 없이 `project_code`·`doc_type`,
/// 고치기는 `doc_id`·`expected_version`. `changed_items`는 파이썬도 쓰지 않아 받지 않는다.
/// `reason`은 상태 바꾸기의 사유, `restore`는 되살림(휴지통 검사를 지난다), `read_first`는 0단계를 할지 —
/// 부른 쪽(상태·되돌리기·되살리기)이 이미 읽었으면 거짓(파이썬 `session`을 넘긴 경우)
#[derive(Clone, Debug)]
pub struct SaveInput {
    pub entry: Entry,
    pub doc_id: Option<String>,
    pub doc_type: Option<String>,
    pub body: String,
    pub expected_version: Option<i64>,
    pub project_code: Option<String>,
    pub author: Author,
    pub message: String,
    pub confirm_item_deletion: bool,
    pub reason: Option<String>,
    pub restore: bool,
    pub read_first: bool,
}

type Locks = LazyLock<Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>>;

/// 쓰기 락 — 프로젝트 코드마다 하나, 프로세스 전역. 만들고 지우지 않는다(파이썬 `_locks`)
static WRITE_LOCKS: Locks = LazyLock::new(|| Mutex::new(HashMap::new()));

/// 읽기 락 — 쓰기 락과 따로인 지도. fetch와 커밋 처리를 저장소마다 한 줄로(#194)
static READ_LOCKS: Locks = LazyLock::new(|| Mutex::new(HashMap::new()));

fn lock_in(map: &Locks, code: &str) -> Arc<tokio::sync::Mutex<()>> {
    let mut m = map
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    m.entry(code.to_string()).or_default().clone()
}

/// SYNC-MS-017#pipeline.write_lock
///
/// 저장을 한 줄로 세운다 — 들어온 차례로, 시간 제한 없이(파이썬 `asyncio.Lock`과 같다)
pub fn write_lock(code: &str) -> Arc<tokio::sync::Mutex<()>> {
    lock_in(&WRITE_LOCKS, code)
}

/// SYNC-MS-017#pipeline.read_lock
///
/// 쓰기 락과 다른 락이다 — 커밋 처리가 파일마다 쓰기 락을 잡는다. 같은 락이면 교착한다
pub fn read_lock(code: &str) -> Arc<tokio::sync::Mutex<()>> {
    lock_in(&READ_LOCKS, code)
}

/// SYNC-MS-017#pipeline.wait_idle
///
/// 끌 때 — 지금까지 만든 쓰기 락을 차례로 잡아 본다. 다 잡으면 `true`, `limit`이 지나면 `false` (INFRA 9.1)
pub async fn wait_idle(limit: Duration) -> bool {
    let locks: Vec<_> = WRITE_LOCKS
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .values()
        .cloned()
        .collect();
    tokio::time::timeout(limit, async {
        for l in locks {
            drop(l.lock().await);
        }
    })
    .await
    .is_ok()
}

/// SYNC-MS-017#pipeline.read_pending
///
/// 저장소에 쓰기 전에 밀린 커밋을 먼저 읽는다(DEV-19). **쓰기 락 밖에서 부른다**.
/// 밀린 것이 있으면 카드 L11(커밋 처리)까지 저장하지 않는다(사용자 결정 2026-10-08)
pub async fn read_pending(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
) -> Result<i64, Problem> {
    let (_, repo) = {
        let mut c = pool.acquire().await?;
        // 쓰기 경로의 소유 검사를 겸한다
        ProjectService { db: &mut c, repos }
            .get_owned(code, user)
            .await?
    };
    let lock = read_lock(code);
    let _held = lock.lock().await;
    // 락 안에서 다시 읽는다 — 앞서 기다린 요청이 이미 따라잡아 놨을 수 있다
    let last = {
        let mut c = pool.acquire().await?;
        project_repo::last_processed_of(&mut c, repo.id)
            .await?
            .flatten()
    };
    let head = repos.git.fetch(Path::new(&repo.workdir_path)).await?;
    // 처리 지점이 없는 것은 등록 중뿐이다 — 등록이 스스로 저장소를 읽는다
    if last.as_deref().is_none_or(|l| l == head) {
        if last.is_some() {
            let mut c = pool.acquire().await?;
            project_repo::set_fetched(&mut c, repo.id, clock::now()).await?;
        }
        return Ok(0);
    }
    Err(Problem::NotImplemented {
        card: "L11".to_string(),
    })
}

/// SYNC-MS-017#pipeline.save_pipeline
///
/// 따로 띄운 작업에서 돈다 — 부른 요청이 끊겨도(입구의 future가 버려져도) push한 뒤 DB를 쓰지 않은 채 멈추지 않는다
pub async fn save_pipeline(
    pool: &PgPool,
    repos: &ServerRepos,
    input: SaveInput,
) -> Result<SaveResult, Problem> {
    let (pool, repos) = (pool.clone(), repos.clone());
    tokio::spawn(async move { save(&pool, &repos, input).await })
        .await
        .map_err(|e| Problem::Internal {
            log: format!("저장 작업: {e}"),
        })?
}

/// `save_pipeline` 본체 — 파이썬 `save_pipeline`·`_run`의 `mcp`·`web_revert`·`web_status` 갈래, 같은 차례·같은 문장
async fn save(pool: &PgPool, repos: &ServerRepos, input: SaveInput) -> Result<SaveResult, Problem> {
    if input.entry == Entry::Github {
        return Err(Problem::NotImplemented { card: "L11".into() });
    }
    let web_status = input.entry == Entry::WebStatus;
    // 앞. 프로젝트 코드 — 파이썬 `project_code or (doc_id.split("-")[0] if doc_id else None)`
    let code = match (&input.project_code, &input.doc_id) {
        (Some(c), _) if !c.is_empty() => c.clone(),
        (_, Some(d)) if !d.is_empty() => d.split('-').next().unwrap_or("").to_string(),
        _ => {
            return Err(Problem::NotFound {
                resource: "project".into(),
                id: serde_json::Value::from("None"),
            });
        }
    };
    let author = &input.author;
    // 0. 쓰기 전에 밀린 커밋을 읽는다 — 쓰기 락 밖이라 교착하지 않는다. 부른 쪽이 이미 읽었으면 건너뛴다
    if input.read_first {
        read_pending(pool, repos, &code, &author.user).await?;
    }
    let lock = write_lock(&code);
    let _held = lock.lock().await;
    let mut tx = pool.begin().await?;
    // 1. 사람 경로는 소유를 가른다 — 남의 프로젝트는 없는 것과 같다
    let (project, repo) = ProjectService { db: &mut tx, repos }
        .get_owned(&code, &author.user)
        .await?;
    let workdir = Path::new(&repo.workdir_path);
    let mut body = input.body.clone();
    // 2·3. 대상 문서 또는 생성
    let (doc_id, doc_type, document): (String, String, Option<Document>) = match &input.doc_id {
        Some(d) => {
            let doc = SpecService { db: &mut tx }.get_document(d).await?;
            // 2. 휴지통 문서는 되살린 뒤 고친다 — 되살림은 이 검사를 지난다
            if let Some(t) = doc.summary.trashed_at
                && !input.restore
            {
                return Err(Problem::DocumentTrashed {
                    trashed_at: py_isoformat(t),
                });
            }
            (d.clone(), doc.summary.doc_type.clone(), Some(doc))
        }
        None => {
            let doc_type = input.doc_type.clone().unwrap_or_default();
            let doc_id = SpecService { db: &mut tx }
                .issue_doc_id(project.id, &code, &doc_type)
                .await?;
            body = SpecService::apply_frontmatter(&body, &doc_id, &doc_type, DocStatus::Draft)?;
            // 3a. DOM 셋의 순서 — push·DB 쓰기 전
            let title = parse_frontmatter(&body)
                .0
                .get("title")
                .cloned()
                .unwrap_or_default();
            let unmet = SpecService { db: &mut tx }
                .precondition(project.id, &doc_type, &title)
                .await?;
            if let Some((requires, have)) = unmet {
                return Err(Problem::PreconditionUnmet { requires, have });
            }
            (doc_id, doc_type, None)
        }
    };
    // 4. 규약
    let current = document
        .as_ref()
        .and_then(|d| DocStatus::parse(&d.summary.status));
    let vr = SpecService { db: &mut tx }
        .validate(&body, &doc_type, input.entry, current)
        .await?;
    if !vr.violations.is_empty() {
        return Err(Problem::ConventionViolation {
            violations: vr.violations.clone(),
            warnings: vr.warnings.clone(),
        });
    }
    // 5. 판 — 검증 뒤
    if let Some(doc) = &document
        && input.expected_version != Some(i64::from(doc.summary.current_version_no))
    {
        return Err(Problem::VersionConflict {
            current_version: doc.summary.current_version_no,
            current_body: doc.body.clone(),
        });
    }
    // 6. 삭제 확인 — 하위 참조는 출발 항목의 이름으로(#50)
    let mut deleted: Vec<i32> = Vec::new();
    if let Some(doc) = document.as_ref().filter(|_| !web_status) {
        deleted = SpecService { db: &mut tx }
            .detect_deleted_items(doc, &body)
            .await?;
        let mut downstream: Vec<(i32, Vec<RefEdge>)> = Vec::with_capacity(deleted.len());
        for pk in &deleted {
            let edges = ReferenceService { db: &mut tx }.downstream(*pk).await?;
            downstream.push((*pk, edges));
        }
        if downstream.iter().any(|(_, e)| !e.is_empty()) && !input.confirm_item_deletion {
            let names: HashMap<i32, &str> = doc
                .items
                .iter()
                .map(|i| (i.pk, i.item_id.as_str()))
                .collect();
            let down_pks: Vec<i32> = downstream
                .iter()
                .flat_map(|(_, es)| es.iter().filter_map(|e| e.from_item_pk))
                .collect();
            let refnames = SpecService { db: &mut tx }
                .describe_items(&down_pks)
                .await?;
            let deleted_items = downstream
                .iter()
                .filter(|(_, es)| !es.is_empty())
                .map(|(pk, es)| DeletedItem {
                    item_id: names.get(pk).copied().unwrap_or_default().to_string(),
                    downstream: es
                        .iter()
                        .filter_map(|e| e.from_item_pk.and_then(|p| refnames.get(&p)).cloned())
                        .collect(),
                })
                .collect();
            return Err(Problem::ItemDeletionNeedsConfirm { deleted_items });
        }
    }
    // 6a. 완료 문서를 고치면 본문의 status도 낮춘다 — **push 전에** (#47)
    if let Some(doc) = &document
        && !web_status
        && doc.summary.status == "approved"
        && body != doc.body
    {
        body = STATUS_LINE
            .replacen(&body, 1, NoExpand("status: draft"))
            .into_owned();
    }
    // 7. push — 여기까지 DB 쓰기 없음
    let files = IndexMap::from([(
        format!("docs/specs/{}/{doc_id}.md", spec_dir(&doc_type)),
        body.clone(),
    )]);
    let commit_hash = repos
        .git
        .commit_push(workdir, &input.message, &author.user, &files, &[])
        .await?;
    // 8. 트랜잭션 — 상태 줄만 바꾼 것은 판을 만들지 않는다
    if web_status && let Some(doc) = &document {
        SpecService { db: &mut tx }
            .apply_status(
                doc,
                &body,
                Some(&commit_hash),
                author,
                input.reason.as_deref(),
            )
            .await?;
        advance(repos, workdir, &mut tx, &repo, &commit_hash).await?;
        tx.commit().await?;
        let mut c = pool.acquire().await?;
        let status = SpecService { db: &mut c }
            .get_document(&doc_id)
            .await?
            .summary
            .status;
        return Ok(SaveResult {
            doc_id,
            version_no: doc.summary.current_version_no,
            commit_hash,
            status,
            warnings: Vec::new(),
            next_step: None,
        });
    }
    let version = match &document {
        None => {
            SpecService { db: &mut tx }
                .create(
                    project.id,
                    &doc_id,
                    &doc_type,
                    &body,
                    &commit_hash,
                    author,
                    &input.message,
                    &vr,
                )
                .await?
        }
        Some(doc) => {
            SpecService { db: &mut tx }
                .save(
                    doc,
                    &body,
                    &commit_hash,
                    author,
                    &input.message,
                    &deleted,
                    &vr,
                )
                .await?
        }
    };
    // 9. 끊어진 참조 — 사라진 항목을 가리키던 참조가 그 자리에서 미존재가 된다
    let broken = ReferenceService { db: &mut tx }
        .mark_missing(&deleted)
        .await?;
    // 10. 참조 추출 · 10a. 이 문서를 기다리던 미존재 참조를 푼다(UC-S2 2a2)
    let item_pks = SpecService { db: &mut tx }
        .item_pks(version.document_id)
        .await?;
    let (fm, _) = parse_frontmatter(&body);
    let upstream = fm
        .get("upstream")
        .map_or("", String::as_str)
        .trim_matches(['[', ']']);
    let upstream_ids: Vec<String> = UPSTREAM_TOKEN
        .find_iter(upstream)
        .map(|m| m.as_str().to_string())
        .collect();
    ReferenceService { db: &mut tx }
        .extract(
            version.document_id,
            version.id,
            &body,
            &item_pks,
            &upstream_ids,
        )
        .await?;
    ReferenceService { db: &mut tx }
        .resolve_missing(project.id, Some(&doc_id))
        .await?;
    let mut warnings: Vec<String> = vr.warnings.iter().map(ToString::to_string).collect();
    if !deleted.is_empty() {
        warnings.push(format!("ref.broken: {broken}"));
    }
    // 13a. 처리 지점
    advance(repos, workdir, &mut tx, &repo, &commit_hash).await?;
    // 14. 커밋
    tx.commit().await?;
    let status = {
        let mut c = pool.acquire().await?;
        SpecService { db: &mut c }
            .get_document(&doc_id)
            .await?
            .summary
            .status
    };
    // 15. 문서 하나 쓰고 멈추라는 규약(STD-001 1.8)을 응답이 매번 다시 말한다 — mcp만
    let next_step = (input.entry == Entry::Mcp).then(|| {
        format!(
            "{doc_id} v{} 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — 다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)",
            version.version_no
        )
    });
    Ok(SaveResult {
        doc_id,
        version_no: version.version_no,
        commit_hash,
        status,
        warnings,
        next_step,
    })
}

/// 처리 지점을 앞당긴다 — 앱이 민 커밋은 그 저장이 곧 처리다(파이썬 `_advance_processed`, `made` 1).
/// 처리 지점부터 이 커밋까지가 하나일 때만 — 사이에 밖에서 push가 끼었으면 그대로 둔다
async fn advance(
    repos: &ServerRepos,
    workdir: &Path,
    db: &mut sqlx::PgConnection,
    repo: &crate::project::model::RepositoryRow,
    commit_hash: &str,
) -> Result<(), Problem> {
    let Some(last) = repo
        .last_processed_commit
        .as_deref()
        .filter(|l| !l.is_empty())
    else {
        return Ok(());
    };
    let behind = repos
        .git
        .rev_list_count(workdir, &format!("{last}..{commit_hash}"))
        .await?;
    if behind == 1 {
        project_repo::advance_processed(db, repo.id, commit_hash, clock::now()).await?;
    }
    Ok(())
}

/// 문서 ID의 프로젝트 코드 — 첫 `-` 앞 (파이썬 `doc_id.split("-")[0]`)
fn code_of(doc_id: &str) -> &str {
    doc_id.split('-').next().unwrap_or("")
}

/// SYNC-MS-017#pipeline.change_status
///
/// 본문은 **저장소에서** 읽는다 — DB 본문으로 커밋하면 아직 읽지 않은 커밋의 내용이 통째로 되돌아간다(#137).
/// 끊어진 참조는 읽을 때 센다 — 컬럼에 없다(STD-001 4장)
pub async fn change_status(
    pool: &PgPool,
    repos: &ServerRepos,
    doc_id: &str,
    to: DocStatus,
    author: &Author,
    reason: Option<&str>,
) -> Result<Document, Problem> {
    let code = code_of(doc_id);
    // 0. 밀린 커밋을 먼저 — 소유 검사도 여기서. 락 밖
    read_pending(pool, repos, code, &author.user).await?;
    let mut c = pool.acquire().await?;
    let (_, repo) = ProjectService { db: &mut c, repos }
        .get_owned(code, &author.user)
        .await?;
    let document = SpecService { db: &mut c }.get_document(doc_id).await?;
    if let Some(t) = document.summary.trashed_at {
        return Err(Problem::DocumentTrashed {
            trashed_at: py_isoformat(t),
        });
    }
    let mut missing: Vec<String> = ReferenceService { db: &mut c }
        .upstream_of_document(document.summary.id, true)
        .await?
        .into_iter()
        .filter(|e| e.is_missing)
        .map(|e| e.raw_target)
        .collect();
    missing.sort();
    missing.dedup();
    let s = &document.summary;
    if to == DocStatus::Approved
        && (s.has_convention_error || !s.incomplete_warnings.is_empty() || !missing.is_empty())
    {
        let mut warnings = s.incomplete_warnings.clone();
        warnings.extend(missing.iter().map(|t| format!("ref.missing: {t}")));
        return Err(Problem::StatusBlocked {
            convention_error_detail: document.convention_error_detail.clone(),
            warnings,
        });
    }
    // 3a. 이미 그 상태 — 아무것도 안 한다
    if s.status == to.as_str() {
        return Ok(document);
    }
    let path = format!("docs/specs/{}/{doc_id}.md", spec_dir(&s.doc_type));
    let src = match repos
        .git
        .read(Path::new(&repo.workdir_path), &path, "origin/main")
        .await
    {
        Ok(b) => b,
        // 저장소에 아직 파일이 없다 — 이 커밋이 파일을 만드는 복구가 된다
        Err(Problem::Git { .. } | Problem::Internal { .. }) => {
            tracing::warn!("change_status {doc_id}: origin/main에 {path}가 없다 — DB 본문으로");
            document.body.clone()
        }
        Err(other) => return Err(other),
    };
    let new_body = STATUS_LINE
        .replacen(&src, 1, NoExpand(&format!("status: {}", to.as_str())))
        .into_owned();
    save_pipeline(
        pool,
        repos,
        SaveInput {
            entry: Entry::WebStatus,
            doc_id: Some(doc_id.to_string()),
            doc_type: None,
            body: new_body,
            expected_version: Some(i64::from(s.current_version_no)),
            project_code: None,
            author: author.clone(),
            message: format!(
                "status({doc_id}): {} → {}\n\n{}",
                s.status,
                to.as_str(),
                reason.unwrap_or("")
            ),
            confirm_item_deletion: false,
            reason: reason.map(str::to_string),
            restore: false,
            read_first: false,
        },
    )
    .await?;
    let mut c = pool.acquire().await?;
    SpecService { db: &mut c }.get_document(doc_id).await
}

/// SYNC-MS-017#pipeline.revert
///
/// 본문은 `versions.body`에서 — 되돌리기는 옛 판을 쓰는 것이 목적이다. 0단계가 밀린 것을 먼저 흡수한다
pub async fn revert(
    pool: &PgPool,
    repos: &ServerRepos,
    doc_id: &str,
    to_version: i32,
    user: &UserRow,
    confirm_item_deletion: bool,
) -> Result<SaveResult, Problem> {
    read_pending(pool, repos, code_of(doc_id), user).await?;
    let mut c = pool.acquire().await?;
    let document = SpecService { db: &mut c }.get_document(doc_id).await?;
    let old_body = SpecService { db: &mut c }
        .version_body(doc_id, to_version)
        .await?;
    let current = document.summary.current_version_no;
    if to_version == current {
        return Err(Problem::AlreadyCurrent);
    }
    drop(c);
    save_pipeline(
        pool,
        repos,
        SaveInput {
            entry: Entry::WebRevert,
            doc_id: Some(doc_id.to_string()),
            doc_type: None,
            body: old_body,
            expected_version: Some(i64::from(current)),
            project_code: None,
            author: Author {
                kind: AuthorKind::Human,
                user: user.clone(),
                instructed_by: None,
                via: Entry::WebRevert,
            },
            message: format!("revert({doc_id}): v{current} → v{to_version} 내용으로"),
            confirm_item_deletion,
            reason: None,
            restore: false,
            read_first: false,
        },
    )
    .await
}
