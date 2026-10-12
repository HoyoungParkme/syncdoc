//! pipeline — 쓰기 조율 (SYNC-MS-017 · SYNC-DOM-004 4.6). 파이썬 판 `core/pipeline.py`와 같은 이름·같은 처리·같은 차례.
//! 여러 서비스를 한 트랜잭션으로 묶고 git과 DB의 차례를 쥔다 — 검사가 다 끝난 뒤에야 git, git이 끝난 뒤에야 DB.
//! 카드 L7 몫은 `mcp` 입구다. 웹(L9)·GitHub·밀린 커밋 처리(L11)·코드 그래프 만들기(L12)는 그 카드가 더했다.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, LazyLock, Mutex};
use std::time::{Duration, Instant};

use indexmap::IndexMap;
use regex::{NoExpand, Regex};
use sqlx::{Connection, PgConnection, PgPool};

use crate::account::model::UserRow;
use crate::account::repo as account_repo;
use crate::account::service::AccountService;
use crate::clock;
use crate::codegraph::CodeGraphService;
use crate::errors::Problem;
use crate::infra::git::Committed;
use crate::markdown::parse_frontmatter;
use crate::project::repo as project_repo;
use crate::project::service::{ProjectService, ServerRepos};
use crate::pycompat::chars::is_digit;
use crate::pycompat::re::compile;
use crate::pycompat::repr::repr;
use crate::reference::service::ReferenceService;
use crate::spec::SpecService;
use crate::spec::repo as spec_repo;
use crate::types::{
    Author, AuthorKind, ChangedFile, DeletedItem, DocStatus, DocType, Document, Entry, MoveResult,
    RebuildError, RebuildResult, RefEdge, SaveResult, Storage, TrashResult, UploadResult,
    ValidateResult, Violation, py_isoformat, spec_dir, stage_of,
};

/// frontmatter의 `status:` 줄 — 첫 것 하나만 갈아 끼운다(파이썬 `_set_status`, `re.M`)
static STATUS_LINE: LazyLock<Regex> = LazyLock::new(|| compile(r"(?m)^status: .*$"));
/// `upstream`의 낱말 — 파이썬 `re.findall(r"[\w-]+", …)`
static UPSTREAM_TOKEN: LazyLock<Regex> = LazyLock::new(|| compile(r"[\w-]+"));

/// 저장 입력 (파이썬 `save_pipeline`의 인자) — 만들기는 `doc_id` 없이 `project_code`·`doc_type`,
/// 고치기는 `doc_id`·`expected_version`. `changed_items`는 파이썬도 쓰지 않아 받지 않는다.
/// `reason`은 상태 바꾸기의 사유, `restore`는 되살림(휴지통 검사를 지난다), `read_first`는 0단계를 할지 —
/// 부른 쪽(상태·되돌리기·되살리기)이 이미 읽었으면 거짓(파이썬 `session`을 넘긴 경우), `github`은 늘 거짓.
/// `commit_hash`는 `github` 입구의 파일 커밋(다른 입구는 없음)
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
    pub commit_hash: Option<String>,
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
/// 저장소에 쓰기 전에 밀린 커밋을 먼저 읽는다(DEV-19). **쓰기 락 밖에서 부른다** —
/// 커밋 처리가 파일마다 저장(쓰기 락)을 부른다
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
    // 받지 않는다 — 서버 저장소의 main 끝을 읽는다(MS-017 0장, 카드 L19)
    let head = repos.git.head(Path::new(&repo.remote_url)).await?;
    // 처리 지점이 없는 것은 등록 중뿐이다 — 등록이 스스로 저장소를 읽는다
    let Some(head) = head.filter(|h| last.as_deref().is_some_and(|l| l != h)) else {
        if last.is_some() {
            let mut c = pool.acquire().await?;
            project_repo::set_fetched(&mut c, repo.id, clock::now()).await?;
        }
        return Ok(0);
    };
    // 이미 읽기 락 안이다
    Ok(process_commit(pool, repos, code, &head, true).await?.len() as i64)
}

/// SYNC-MS-017#pipeline.process_commit
///
/// 전체가 읽기 락 안이다 — git 입구의 push 뒤·따라잡기·`read_pending`이 한 줄로 선다(#194).
/// `locked`는 이미 그 락을 쥔 부른 쪽이다. 파일 하나가 실패해도 다음 파일 — 실패가 있으면 처리 지점을 옮기지 않는다
pub async fn process_commit(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    head: &str,
    locked: bool,
) -> Result<Vec<SaveResult>, Problem> {
    let lock = read_lock(code);
    let _held = if locked {
        None
    } else {
        Some(lock.lock().await)
    };
    // 1. 처리 지점은 락 안에서 다시 읽는다 — 앞서 기다린 실행이 이미 따라잡아 놨을 수 있다
    let (_, repo) = {
        let mut c = pool.acquire().await?;
        ProjectService { db: &mut c, repos }.get(code).await?
    };
    let last = repo.last_processed_commit.clone();
    if last.as_deref() == Some(head) {
        return Ok(Vec::new());
    }
    let origin = PathBuf::from(&repo.remote_url);
    let workdir = PathBuf::from(&repo.workdir_path);
    // 2. 이미 처리한 커밋이거나 그 조상이면 아무것도 안 한다 — 처리 지점을 뒤로 돌리지 않는다
    if let Some(l) = last.as_deref().filter(|l| !l.is_empty())
        && repos
            .git
            .rev_list_count(&origin, &format!("{l}..{head}"))
            .await?
            == 0
    {
        return Ok(Vec::new());
    }
    let range = match last.as_deref().filter(|l| !l.is_empty()) {
        Some(l) => format!("{l}..{head}"),
        None => head.to_string(),
    };
    let mut files = repos
        .git
        .changed_files(&origin, &range, "docs/specs/")
        .await?;
    // 3b. 파이썬 판 그대로 — 디렉터리 이름(`02-PRD`)으로 찾아 번호 붙은 디렉터리는 모두 99, 경로 순이 곧 단계 순
    files.sort_by(|a, b| {
        let key = |f: &ChangedFile| {
            let parts = path_parts(&f.path);
            let stage = if parts.len() > 3 {
                stage_of(parts[2])
            } else {
                stage_of("")
            };
            (stage.unwrap_or(99), f.path.clone())
        };
        key(a).cmp(&key(b))
    });
    let mut results = Vec::new();
    let mut failed: Vec<String> = Vec::new();
    for f in &files {
        match process_file(pool, repos, &origin, code, f, head).await {
            Ok(r) => results.extend(r),
            Err(e) => {
                tracing::warn!("process_commit {code} {}: {e}", f.path);
                failed.push(f.path.clone());
            }
        }
    }
    if failed.is_empty() {
        let mut tx = pool.begin().await?;
        let now = clock::now();
        project_repo::advance_processed(&mut tx, repo.id, head, now).await?;
        // 방금 head까지 처리했으니 뒤처짐은 0이다
        project_repo::set_fetched(&mut tx, repo.id, now).await?;
        tx.commit().await?;
        // 작업 사본 폴더를 head로 — 첨부 파일 읽기만 쓴다(카드 L19)
        if let Err(e) = repos.git.materialize(&origin, head, &workdir).await {
            tracing::warn!("작업 사본 폴더 {code}: {e}");
        }
        // 5a. 코드 그래프 — 코드가 바뀌었거나 아직 없으면 (UC-S8). 명세만 바뀐 커밋은 건너뛴다
        let paths = if last.as_deref().is_some_and(|l| !l.is_empty()) {
            repos.git.changed_paths(&origin, &range).await?
        } else {
            Vec::new()
        };
        let has_graph = {
            let mut c = pool.acquire().await?;
            CodeGraphService { db: &mut c }
                .get(repo.project_id)
                .await?
                .is_some()
        };
        if syncdoc_codegraph::graph::touches_code(&paths) || !has_graph {
            schedule_code_graph(pool, repos, code, head);
        }
    }
    Ok(results)
}

/// 파이썬 `Path(p).parts` — `/`로 가르고 빈 조각·`.`은 버린다
fn path_parts(path: &str) -> Vec<&str> {
    path.split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect()
}

/// 파이썬 `Path(p).stem` — 마지막 조각에서 마지막 확장자를 뗀다(맨 앞 `.`은 확장자가 아니다)
fn path_stem(path: &str) -> &str {
    let name = path_parts(path).last().copied().unwrap_or("");
    match name.rfind('.') {
        Some(i) if i > 0 && i < name.len() - 1 => &name[..i],
        _ => name,
    }
}

type Processed<'a> = std::pin::Pin<
    Box<dyn std::future::Future<Output = Result<Vec<SaveResult>, Problem>> + Send + 'a>,
>;

/// `process_commit` 4 — 파일 하나. 삭제면 `mark_deleted`, 아니면 github 저장 + 파일 이름·디렉터리 위반 덧붙임.
/// 상자에 담은 future다 — 저장 → 밀린 커밋 읽기 → 커밋 처리 → 저장이 서로 부르는 고리를 여기서 끊는다
/// (그래야 저장을 따로 띄울 수 있다)
fn process_file<'a>(
    pool: &'a PgPool,
    repos: &'a ServerRepos,
    origin: &'a Path,
    code: &'a str,
    f: &'a ChangedFile,
    head: &'a str,
) -> Processed<'a> {
    Box::pin(process_file_inner(pool, repos, origin, code, f, head))
}

async fn process_file_inner(
    pool: &PgPool,
    repos: &ServerRepos,
    origin: &Path,
    code: &str,
    f: &ChangedFile,
    head: &str,
) -> Result<Vec<SaveResult>, Problem> {
    let doc_id = path_stem(&f.path).to_string();
    let parts = path_parts(&f.path);
    let dir_type = if parts.len() > 3 {
        type_of_dir(parts[2])
    } else {
        String::new()
    };
    let user = {
        let mut c = pool.acquire().await?;
        AccountService { db: &mut c }
            .user_for_commit(&f.author_email, &f.author_login)
            .await?
    };
    let author = Author {
        kind: AuthorKind::Human,
        user,
        instructed_by: None,
        via: Entry::Github,
    };
    if f.status == "D" {
        let mut tx = pool.begin().await?;
        let found = SpecService { db: &mut tx }.get_document(&doc_id).await;
        let document = match found {
            // 앱이 완전 삭제로 지운 문서의 삭제 커밋이거나 등록 전에 사라진 파일
            Err(Problem::NotFound { .. }) => return Ok(Vec::new()),
            Err(p) => return Err(p),
            Ok(d) => d,
        };
        if document.summary.trashed_at.is_some() {
            return Ok(Vec::new()); // 앱이 휴지통에 넣은 삭제 커밋 — 이미 반영돼 있다
        }
        let pks = SpecService { db: &mut tx }
            .mark_deleted(&document, &f.commit_hash, &author)
            .await?;
        ReferenceService { db: &mut tx }.mark_missing(&pks).await?;
        tx.commit().await?;
        return Ok(Vec::new());
    }
    // 앱이 직접 민 커밋(저장·상태·되돌리기)은 이미 기록돼 있다 — 다시 저장하면 같은 커밋의 판이 둘
    let known: Vec<String> = {
        let mut c = pool.acquire().await?;
        let versions = SpecService { db: &mut c }.list_versions(&doc_id).await;
        match versions {
            Ok(vs) => vs.into_iter().map(|v| v.commit_hash).collect(),
            Err(Problem::NotFound { .. }) => Vec::new(),
            Err(p) => return Err(p),
        }
    };
    if known.contains(&f.commit_hash) {
        return Ok(Vec::new());
    }
    let body = repos.git.read(origin, &f.path, head).await?;
    // 파이썬 `DocType(dir_type)` — 모르는 디렉터리면 그 파일은 실패한다(사람 실수라 알린다)
    if DocType::parse(&dir_type).is_none() {
        return Err(Problem::Internal {
            log: format!("{} is not a valid DocType", repr(&dir_type)),
        });
    }
    let r = save_pipeline(
        pool,
        repos,
        SaveInput {
            entry: Entry::Github,
            doc_id: Some(doc_id.clone()),
            doc_type: Some(dir_type.clone()),
            body: body.clone(),
            expected_version: None,
            project_code: Some(code.to_string()),
            author,
            message: f.message.clone(),
            confirm_item_deletion: false,
            reason: None,
            restore: false,
            read_first: false,
            commit_hash: Some(f.commit_hash.clone()),
        },
    )
    .await?;
    let (fm, _) = parse_frontmatter(&body);
    let shown = |k: &str| fm.get(k).map_or_else(|| "None".to_string(), |v| repr(v));
    let mut extra = Vec::new();
    if fm.get("doc_id").map(String::as_str) != Some(doc_id.as_str()) {
        extra.push(Violation {
            line: 2,
            rule: "frontmatter.doc_id".into(),
            message: format!("파일명 {doc_id} ≠ {}", shown("doc_id")),
        });
    }
    if fm.get("type").map(String::as_str) != Some(dir_type.as_str()) {
        extra.push(Violation {
            line: 2,
            rule: "frontmatter.doc_id".into(),
            message: format!("디렉터리 {dir_type} ≠ type {}", shown("type")),
        });
    }
    if !extra.is_empty() {
        let mut tx = pool.begin().await?;
        let mut spec = SpecService { db: &mut tx };
        let vr = spec.validate(&body, &dir_type, Entry::Github, None).await?;
        let id = spec.get_document(&doc_id).await?.summary.id;
        let mut violations = vr.violations;
        violations.extend(extra);
        spec.mark_convention_error(
            id,
            &ValidateResult {
                violations,
                warnings: vr.warnings,
            },
        )
        .await?;
        tx.commit().await?;
    }
    Ok(vec![r])
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

/// `save_pipeline` 본체 — 파이썬 `save_pipeline`·`_run`, 같은 차례·같은 문장
async fn save(pool: &PgPool, repos: &ServerRepos, input: SaveInput) -> Result<SaveResult, Problem> {
    let web_status = input.entry == Entry::WebStatus;
    // 서버 저장소에 git으로 민 것 — 원본이 진실이라 막지 않고, 묻지 않고, 밀지 않는다
    let github = input.entry == Entry::Github;
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
    // 1. 사람 경로는 소유를 가른다 — 남의 프로젝트는 없는 것과 같다. github은 사람이 없는 배치다
    let (project, repo) = if github {
        ProjectService { db: &mut tx, repos }.get(&code).await?
    } else {
        ProjectService { db: &mut tx, repos }
            .get_owned(&code, &author.user)
            .await?
    };
    let origin = Path::new(&repo.remote_url);
    let workdir = Path::new(&repo.workdir_path);
    let mut body = input.body.clone();
    // 2·3. 대상 문서 또는 생성
    let (doc_id, doc_type, document): (String, String, Option<Document>) = match &input.doc_id {
        Some(d) => {
            let found = SpecService { db: &mut tx }.get_document(d).await;
            match found {
                // github 신규 파일 — 파일 이름이 doc_id, frontmatter는 그대로
                Err(Problem::NotFound { .. }) if github => {
                    (d.clone(), input.doc_type.clone().unwrap_or_default(), None)
                }
                Err(p) => return Err(p),
                Ok(doc) => {
                    // 2. 휴지통 문서는 되살린 뒤 고친다 — 되살림은 이 검사를 지난다. github은 파일이
                    // 다시 push된 것 자체가 되살리기다(save가 휴지통을 비운다)
                    if let Some(t) = doc.summary.trashed_at
                        && !input.restore
                        && !github
                    {
                        return Err(Problem::DocumentTrashed {
                            trashed_at: py_isoformat(t),
                        });
                    }
                    (d.clone(), doc.summary.doc_type.clone(), Some(doc))
                }
            }
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
    if !vr.violations.is_empty() && !github {
        return Err(Problem::ConventionViolation {
            violations: vr.violations.clone(),
            warnings: vr.warnings.clone(),
        });
    }
    // 5. 판 — 검증 뒤
    if let Some(doc) = &document
        && !github
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
    }
    // github 진입은 물어볼 상대가 없다 — 커밋이 진실(SEQ-2). 삭제는 끊어진 참조로 통보
    if let Some(doc) = document.as_ref().filter(|_| !web_status && !github) {
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
    // 6a. 완료 문서를 고치면 본문의 status도 낮춘다 — **push 전에** (#47).
    // github은 작성자가 스스로 내렸으면 그것이 진실이다(frontmatter가 아직 approved일 때만)
    let path = format!("docs/specs/{}/{doc_id}.md", spec_dir(&doc_type));
    let mut status_commit_hash: Option<String> = None;
    if let Some(doc) = &document
        && !web_status
        && doc.summary.status == "approved"
        && body != doc.body
        && (!github
            || parse_frontmatter(&body).0.get("status").map(String::as_str) == Some("approved"))
    {
        body = STATUS_LINE
            .replacen(&body, 1, NoExpand("status: draft"))
            .into_owned();
        if github {
            // 커밋이 이미 저장소에 있으니 강등을 커밋 하나로 더 민다 — 그 해시를 상태 변경에 적어야
            // 다음 처리가 앱 커밋으로 거른다(#58). 미는 사람은 저장소를 등록한 사람이다
            let pusher = account_repo::user_by_id(&mut tx, repo.registered_by_user_id)
                .await?
                .ok_or_else(|| Problem::Internal {
                    log: format!("저장소 {code}를 등록한 사람이 없다"),
                })?;
            let one = IndexMap::from([(path.clone(), body.clone())]);
            status_commit_hash = Some(
                repos
                    .git
                    .commit(
                        origin,
                        workdir,
                        &format!("status({doc_id}): approved → draft\n\n본문 수정으로 자동 강등"),
                        &pusher,
                        &one,
                        &[],
                    )
                    .await?
                    .hash,
            );
        }
    }
    // 7. 커밋 — 여기까지 DB 쓰기 없음. github은 커밋이 이미 저장소에 있다
    let made = if github {
        None
    } else {
        let files = IndexMap::from([(path.clone(), body.clone())]);
        Some(
            repos
                .git
                .commit(origin, workdir, &input.message, &author.user, &files, &[])
                .await?,
        )
    };
    let commit_hash = match &made {
        Some(m) => m.hash.clone(),
        None => input.commit_hash.clone().unwrap_or_default(),
    };
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
        advance(&mut tx, &repo, made.as_ref()).await?;
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
                    false,
                    status_commit_hash.as_deref(),
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
    // 13a. 처리 지점 — 앱이 민 커밋은 이 저장이 곧 처리다. github은 처리하는 쪽이 옮긴다
    if !github {
        advance(&mut tx, &repo, made.as_ref()).await?;
    }
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

/// 처리 지점을 앞당긴다 — 앱이 만든 커밋은 그 저장이 곧 처리다(파이썬 `_advance_processed`, `made` 1).
/// 그 커밋의 부모가 처리 지점일 때만 — 파이썬 `rev_list_count("{처리 지점}..{해시}") == 1`과 같은 판정이다.
/// 사이에 밖에서 push가 끼었으면 부모가 처리 지점이 아니라 그대로 둔다(MS-017 0장, 카드 L19)
async fn advance(
    db: &mut sqlx::PgConnection,
    repo: &crate::project::model::RepositoryRow,
    made: Option<&Committed>,
) -> Result<(), Problem> {
    let Some(made) = made else {
        return Ok(());
    };
    let Some(last) = repo
        .last_processed_commit
        .as_deref()
        .filter(|l| !l.is_empty())
    else {
        return Ok(());
    };
    if made.parent.as_deref() == Some(last) && made.hash != last {
        project_repo::advance_processed(db, repo.id, &made.hash, clock::now()).await?;
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
        .read(Path::new(&repo.remote_url), &path, "refs/heads/main")
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
            commit_hash: None,
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
            commit_hash: None,
        },
    )
    .await
}

/// 들어오는 참조를 사람이 읽을 이름으로 — `DOC#ITEM` 또는 `DOC`, 못 찾으면 `?`, 정렬 (파이썬 `_inbound_names`)
async fn inbound_names(
    db: &mut sqlx::PgConnection,
    inbound: &[RefEdge],
) -> Result<Vec<String>, Problem> {
    let item_pks: Vec<i32> = inbound.iter().filter_map(|e| e.from_item_pk).collect();
    let names = SpecService { db: &mut *db }
        .describe_items(&item_pks)
        .await?;
    let doc_pks: Vec<i32> = inbound
        .iter()
        .filter(|e| e.from_item_pk.is_none())
        .map(|e| e.from_document_id)
        .collect();
    let docs = SpecService { db: &mut *db }
        .describe_documents(&doc_pks)
        .await?;
    let mut out: Vec<String> = inbound
        .iter()
        .map(|e| {
            if let Some(r) = e.from_item_pk.and_then(|p| names.get(&p)) {
                format!(
                    "{}#{}",
                    r.doc_id.as_deref().unwrap_or(""),
                    r.item_id.as_deref().unwrap_or("")
                )
            } else {
                docs.get(&e.from_document_id)
                    .map_or_else(|| "?".to_string(), |d| d.doc_id.clone())
            }
        })
        .collect();
    out.sort();
    Ok(out)
}

/// SYNC-MS-017#pipeline.trash_document
///
/// 따로 띄운 작업에서 — push한 뒤 DB를 쓰지 않은 채 멈추지 않는다
pub async fn trash_document(
    pool: &PgPool,
    repos: &ServerRepos,
    doc_id: &str,
    author: &Author,
    confirm: bool,
) -> Result<TrashResult, Problem> {
    let (pool, repos, doc_id, author) = (
        pool.clone(),
        repos.clone(),
        doc_id.to_string(),
        author.clone(),
    );
    tokio::spawn(async move { trash(&pool, &repos, &doc_id, &author, confirm).await })
        .await
        .map_err(|e| Problem::Internal {
            log: format!("휴지통 작업: {e}"),
        })?
}

/// `trash_document` 본체 — 파이썬과 같은 차례
async fn trash(
    pool: &PgPool,
    repos: &ServerRepos,
    doc_id: &str,
    author: &Author,
    confirm: bool,
) -> Result<TrashResult, Problem> {
    let code = code_of(doc_id);
    // 0. 밀린 커밋을 먼저 — 락 밖
    read_pending(pool, repos, code, &author.user).await?;
    let lock = write_lock(code);
    let _held = lock.lock().await;
    let mut tx = pool.begin().await?;
    let (_, repo) = ProjectService { db: &mut tx, repos }
        .get_owned(code, &author.user)
        .await?;
    let document = SpecService { db: &mut tx }.get_document(doc_id).await?;
    if let Some(t) = document.summary.trashed_at {
        return Err(Problem::DocumentTrashed {
            trashed_at: py_isoformat(t),
        });
    }
    // 2. 끊어질 것 — 막지 않는다, 보여준다
    let edges = ReferenceService { db: &mut tx }
        .inbound_of_document(document.summary.id)
        .await?;
    let inbound = inbound_names(&mut tx, &edges).await?;
    if !confirm {
        let title = parse_frontmatter(&document.body)
            .0
            .get("title")
            .cloned()
            .unwrap_or_default();
        return Err(Problem::DocumentDeletionNeedsConfirm {
            doc_id: doc_id.to_string(),
            title,
            version_count: document.summary.current_version_no,
            inbound_refs: inbound,
        });
    }
    // 4. 커밋 — 여기까지 DB 쓰기 없음
    let path = format!(
        "docs/specs/{}/{doc_id}.md",
        spec_dir(&document.summary.doc_type)
    );
    let made = repos
        .git
        .commit(
            Path::new(&repo.remote_url),
            Path::new(&repo.workdir_path),
            &format!("spec({doc_id}): 휴지통"),
            &author.user,
            &IndexMap::new(),
            &[path],
        )
        .await?;
    let commit_hash = made.hash.clone();
    // 5. 항목 삭제됨 + 휴지통 표시 + 그것을 가리키던 참조는 미존재로
    let pks = SpecService { db: &mut tx }
        .trash(&document, &commit_hash, author)
        .await?;
    let broken = ReferenceService { db: &mut tx }.mark_missing(&pks).await?;
    advance(&mut tx, &repo, Some(&made)).await?;
    tx.commit().await?;
    Ok(TrashResult {
        next_step: format!("{doc_id} 휴지통에 넣음 — 끊어진 참조 {broken}. 사람에게 알리고 멈춘다"),
        doc_id: doc_id.to_string(),
        commit_hash,
        broken_refs: broken,
    })
}

/// SYNC-MS-017#pipeline.restore_document
///
/// 휴지통에 넣기 직전 내용(휴지통 커밋의 부모)으로 새 판 — 항목이 돌아오고 기다리던 미존재 참조는 저장의 10a가 잇는다
pub async fn restore_document(
    pool: &PgPool,
    repos: &ServerRepos,
    doc_id: &str,
    author: &Author,
) -> Result<SaveResult, Problem> {
    let code = code_of(doc_id);
    read_pending(pool, repos, code, &author.user).await?;
    let mut c = pool.acquire().await?;
    let (_, repo) = ProjectService { db: &mut c, repos }
        .get_owned(code, &author.user)
        .await?;
    let document = SpecService { db: &mut c }.get_document(doc_id).await?;
    if document.summary.trashed_at.is_none() {
        return Err(Problem::DocumentNotTrashed);
    }
    let hash = SpecService { db: &mut c }
        .trash_commit(document.summary.id)
        .await?
        .ok_or_else(|| Problem::Internal {
            log: format!("{doc_id}의 휴지통 커밋이 없다"),
        })?;
    drop(c);
    let path = format!(
        "docs/specs/{}/{doc_id}.md",
        spec_dir(&document.summary.doc_type)
    );
    let body = repos
        .git
        .read(Path::new(&repo.remote_url), &path, &format!("{hash}^"))
        .await?;
    // 3. DB가 초안이다 — mcp 경로의 frontmatter.status_change에 안 걸리게
    let body = STATUS_LINE
        .replacen(&body, 1, NoExpand("status: draft"))
        .into_owned();
    let entry = if author.via == Entry::Mcp {
        Entry::Mcp
    } else {
        Entry::WebRevert
    };
    save_pipeline(
        pool,
        repos,
        SaveInput {
            entry,
            doc_id: Some(doc_id.to_string()),
            doc_type: None,
            body,
            expected_version: Some(i64::from(document.summary.current_version_no)),
            project_code: None,
            author: author.clone(),
            message: format!("spec({doc_id}): 되살림 — 휴지통에서"),
            confirm_item_deletion: false,
            reason: None,
            restore: true,
            read_first: false,
            commit_hash: None,
        },
    )
    .await
}

/// SYNC-MS-017#pipeline.purge_document
///
/// 웹에서만 — 파일은 휴지통 커밋에서 이미 없다(push 없음). 밀린 커밋은 읽지 않는다(파이썬과 같다)
pub async fn purge_document(
    pool: &PgPool,
    repos: &ServerRepos,
    doc_id: &str,
    author: &Author,
) -> Result<(), Problem> {
    let code = code_of(doc_id);
    let lock = write_lock(code);
    let _held = lock.lock().await;
    let mut tx = pool.begin().await?;
    ProjectService { db: &mut tx, repos }
        .get_owned(code, &author.user)
        .await?;
    let document = SpecService { db: &mut tx }.get_document(doc_id).await?;
    if document.summary.trashed_at.is_none() {
        return Err(Problem::DocumentNotTrashed);
    }
    // 2. 문지기 하나 — 아직 가리키는 곳. 미존재 참조는 `to_*`가 비어 여기 안 잡힌다
    let edges = ReferenceService { db: &mut tx }
        .inbound_of_document(document.summary.id)
        .await?;
    let inbound = inbound_names(&mut tx, &edges).await?;
    if !inbound.is_empty() {
        return Err(Problem::DocumentHasHistory {
            inbound_refs: inbound,
        });
    }
    SpecService { db: &mut tx }
        .delete_document(&document)
        .await?;
    tx.commit().await?;
    Ok(())
}

/// SYNC-MS-017#pipeline.rebuild
///
/// 쓰기 락을 쥐고 `conn` 위에 트랜잭션 하나 — 이미 트랜잭션이면 저장점(보관본 가져오기가 막 넣은 행을 본다).
/// 어느 단계든 실패하면 되돌리고 `rebuild-failed`
pub async fn rebuild(
    conn: &mut PgConnection,
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
) -> Result<RebuildResult, Problem> {
    let lock = write_lock(code);
    let _held = lock.lock().await;
    let mut tx = conn.begin().await?;
    let (project, repo) = ProjectService { db: &mut tx, repos }.get(code).await?;
    match rebuild_in(&mut tx, repos, &project, &repo).await {
        Ok((result, head)) => {
            tx.commit().await?;
            // 9. 작업 사본 폴더를 head로 — 파이썬의 `checkout origin/main` (카드 L19)
            let (origin, workdir) = (Path::new(&repo.remote_url), Path::new(&repo.workdir_path));
            if let Err(e) = repos.git.materialize(origin, &head, workdir).await {
                tracing::warn!("작업 사본 폴더 {code}: {e}");
            }
            // 10. 재구축은 늘 다시 만든다 (UC-S8)
            schedule_code_graph(pool, repos, code, &head);
            Ok(result)
        }
        Err(e) => {
            drop(tx); // 되돌린다 — DB는 재구축 전과 같다
            tracing::warn!("rebuild {code} 실패: {e}");
            Err(Problem::RebuildFailed {
                reason: e.to_string(),
            })
        }
    }
}

/// `rebuild` 2~8 — 트랜잭션 안에서. 읽은 끝(head)도 돌려준다
async fn rebuild_in(
    tx: &mut PgConnection,
    repos: &ServerRepos,
    project: &crate::project::model::ProjectRow,
    repo: &crate::project::model::RepositoryRow,
) -> Result<(RebuildResult, String), Problem> {
    let origin = PathBuf::from(&repo.remote_url);
    let mut result = RebuildResult::default();
    // 2. 받지 않는다 — 서버 저장소의 main 끝 (카드 L19)
    let head = repos.git.head(&origin).await?.ok_or_else(|| Problem::Git {
        cmd: "git rev-parse refs/heads/main".into(),
        stderr: "빈 저장소다".into(),
    })?;
    // 4. 판을 가리키는 외래 키는 참조의 것 하나 — 먼저 지운다(#38)
    ReferenceService { db: &mut *tx }.clear(project.id).await?;
    SpecService { db: &mut *tx }.clear_index(project.id).await?;
    // 5·6
    for path in repos.git.list(&origin, "docs/specs/*/*.md", &head).await? {
        let doc_id = path_stem(&path).to_string();
        let parts = path_parts(&path);
        let dir_type = if parts.len() > 3 {
            type_of_dir(parts[2])
        } else {
            String::new()
        };
        if DocType::parse(&dir_type).is_none() {
            result.convention_errors.push(RebuildError {
                doc_id,
                detail: format!("frontmatter.doc_id: 알 수 없는 디렉터리 {dir_type}"),
            });
            continue;
        }
        let found = SpecService { db: &mut *tx }.get_document(&doc_id).await;
        let mut document = match found {
            Ok(d) => Some(d),
            Err(Problem::NotFound { .. }) => None,
            Err(p) => return Err(p),
        };
        for c in repos.git.log(&origin, &path).await? {
            // 그 커밋 시점의 경로로 읽는다 — 이름이 바뀐 문서는 옛 커밋에서 옛 경로에 있다(#39)
            let at = if c.path.is_empty() { &path } else { &c.path };
            let body = repos.git.read(&origin, at, &c.hash).await?;
            let user = AccountService { db: &mut *tx }
                .user_for_commit(&c.email, &c.login)
                .await?;
            let author = Author {
                kind: AuthorKind::Human,
                user,
                instructed_by: None,
                via: Entry::Github,
            };
            let mut spec = SpecService { db: &mut *tx };
            match &document {
                Some(doc) if c.message.starts_with("status(") => {
                    spec.apply_status(doc, &body, Some(&c.hash), &author, None)
                        .await?;
                }
                _ => {
                    let vr = spec.validate(&body, &dir_type, Entry::Github, None).await?;
                    match &document {
                        None => {
                            spec.create(
                                project.id, &doc_id, &dir_type, &body, &c.hash, &author,
                                &c.message, &vr,
                            )
                            .await?;
                        }
                        Some(doc) => {
                            let deleted = spec.detect_deleted_items(doc, &body).await?;
                            spec.save(
                                doc, &body, &c.hash, &author, &c.message, &deleted, &vr, true, None,
                            )
                            .await?;
                        }
                    }
                    result.versions += 1;
                }
            }
            document = Some(spec.get_document(&doc_id).await?);
        }
        let Some(document) = document else {
            continue;
        };
        let (fm, _) = parse_frontmatter(&document.body);
        let upstream = fm
            .get("upstream")
            .map_or("", String::as_str)
            .trim_matches(['[', ']']);
        let upstream_ids: Vec<String> = UPSTREAM_TOKEN
            .find_iter(upstream)
            .map(|m| m.as_str().to_string())
            .collect();
        // 판을 가리키는 칸은 비울 수 없다 — 판 없는 문서(이력이 status( 커밋뿐)는 파이썬 판도 DB가 거절한다
        let version_id = spec_repo::latest_version(&mut *tx, document.summary.id)
            .await?
            .map(|v| v.id)
            .ok_or_else(|| Problem::Internal {
                log: format!("{doc_id}에 판이 없다"),
            })?;
        let item_pks = SpecService { db: &mut *tx }
            .item_pks(document.summary.id)
            .await?;
        let ex = ReferenceService { db: &mut *tx }
            .extract(
                document.summary.id,
                version_id,
                &document.body,
                &item_pks,
                &upstream_ids,
            )
            .await?;
        let mut spec = SpecService { db: &mut *tx };
        let vr = spec
            .validate(&document.body, &dir_type, Entry::Github, None)
            .await?;
        spec.mark_convention_error(document.summary.id, &vr).await?;
        if !vr.violations.is_empty() {
            let detail = vr
                .violations
                .iter()
                .map(|v| format!("{}: {}", v.rule, v.message))
                .collect::<Vec<_>>()
                .join("\n");
            result
                .convention_errors
                .push(RebuildError { doc_id, detail });
        }
        result.docs += 1;
        result.items += document.items.len() as i64;
        result.references += ex.added;
    }
    // 7. 파일 차례 때문에 미존재였던 참조를 푼다
    ReferenceService { db: &mut *tx }
        .resolve_missing(project.id, None)
        .await?;
    // 8. 재구축은 head까지 읽었다
    let now = clock::now();
    project_repo::advance_processed(&mut *tx, repo.id, &head, now).await?;
    project_repo::set_fetched(&mut *tx, repo.id, now).await?;
    Ok((result, head))
}

/// 코드 올리기 한도 — 한 번에 UTF-8 합 (사용자 결정 2026-09-30)
const UPLOAD_BYTES: i64 = 5 * 1024 * 1024;
/// 파일 + 지운 경로
const UPLOAD_COUNT: i64 = 500;
/// `upload_code` 3 — 올릴 수 없는 경로의 이유. 올려도 되면 없음 (파이썬 `_refusal`, UC-A10 2b)
fn refusal(path: &str) -> Option<&'static str> {
    if crate::pycompat::chars::strip(path).is_empty() {
        return Some("빈 경로");
    }
    if path.contains('\\') {
        return Some("역슬래시 — / 로 쓴다");
    }
    if path.starts_with('/') {
        return Some("절대 경로");
    }
    let parts = path_parts(path);
    if parts.contains(&"..") {
        return Some("상위 경로(..)");
    }
    if parts.contains(&".git") {
        return Some(".git");
    }
    if parts.len() >= 2 && parts[0] == "docs" && parts[1] == "specs" {
        return Some("명세 경로 — create_document·update_document로 쓴다");
    }
    // 비밀 꼴 — 파이썬 `CodeGraphService.DENY`
    if crate::codegraph::service::secret(parts.last().copied().unwrap_or("")) {
        return Some("비밀 꼴");
    }
    None
}

/// SYNC-MS-017#pipeline.upload_code
///
/// git이 없는 PC의 코드를 서버 저장소에 커밋 하나로 넣는다(UC-A10). 명세 경로는 받지 않아 판이 생기지 않는다
pub async fn upload_code(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    files: &IndexMap<String, String>,
    delete: &[String],
    message: &str,
    author: &Author,
) -> Result<UploadResult, Problem> {
    let (_, repo) = {
        let mut c = pool.acquire().await?;
        ProjectService { db: &mut c, repos }
            .get_owned(code, &author.user)
            .await?
    };
    // 1
    if repo.storage != Storage::Server.as_str() {
        return Err(Problem::StorageMismatch {
            storage: repo.storage.clone(),
            detail: None,
        });
    }
    // 2. 한도 — 락 밖
    let size: i64 = files.values().map(|c| c.len() as i64).sum();
    let count = (files.len() + delete.len()) as i64;
    if size > UPLOAD_BYTES || count > UPLOAD_COUNT {
        return Err(Problem::UploadTooLarge {
            limit_bytes: UPLOAD_BYTES,
            limit_count: UPLOAD_COUNT,
            size,
            count,
        });
    }
    // 3. 경로 — 올릴 것 → 지울 것, 그다음 이진
    let mut refused: Vec<(String, String)> = files
        .keys()
        .chain(delete.iter())
        .filter_map(|p| refusal(p).map(|r| (p.clone(), r.to_string())))
        .collect();
    refused.extend(
        files
            .iter()
            .filter(|(p, c)| c.contains('\0') && refusal(p).is_none())
            .map(|(p, _)| (p.clone(), "글자가 아니다(이진)".to_string())),
    );
    if !refused.is_empty() {
        return Err(Problem::UploadPathRefused { paths: refused });
    }
    // 4. 쓰기 전에 읽는다(DEV-19)
    read_pending(pool, repos, code, &author.user).await?;
    // 5
    let (origin, workdir) = (
        PathBuf::from(&repo.remote_url),
        PathBuf::from(&repo.workdir_path),
    );
    let made = {
        let lock = write_lock(code);
        let _held = lock.lock().await;
        repos
            .git
            .commit(&origin, &workdir, message, &author.user, files, delete)
            .await?
    };
    let (before, commit) = (made.parent.unwrap_or_default(), made.hash);
    // 6. 처리 지점을 이 커밋으로 — 명세 경로가 없으니 판은 생기지 않는다(코드 그래프는 L12)
    read_pending(pool, repos, code, &author.user).await?;
    Ok(UploadResult {
        changed: commit != before,
        commit,
        files: files.len() as i64,
        deleted: delete.len() as i64,
    })
}

/// SYNC-MS-017#pipeline.move_to_server
///
/// 서버 저장뿐이라 파이썬 판 1에서 늘 멈춘다 — 옮기는 갈래(복제·통지 거두기·원격 바꾸기)가 없다
pub async fn move_to_server(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
) -> Result<MoveResult, Problem> {
    let mut c = pool.acquire().await?;
    let (_, repo) = ProjectService { db: &mut c, repos }
        .get_owned(code, user)
        .await?;
    Err(Problem::StorageMismatch {
        storage: repo.storage,
        detail: Some("이미 서버 저장이다".to_string()),
    })
}

/// SYNC-MS-017#pipeline.move_to_github
///
/// 서버 저장이고 GitHub 저장은 켜지 않은 방식이다 — 파이썬 판 1a에서 늘 멈춘다. `remote_url`은 받기만 한다
pub async fn move_to_github(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
    remote_url: &str,
) -> Result<MoveResult, Problem> {
    let _ = remote_url;
    let mut c = pool.acquire().await?;
    ProjectService { db: &mut c, repos }
        .get_owned(code, user)
        .await?;
    Err(Problem::StorageUnavailable {
        storage: Storage::Github.as_str().to_string(),
        enabled: vec![Storage::Server.as_str().to_string()],
    })
}

/// SYNC-MS-017#pipeline.catch_up
///
/// 저장소마다 읽기 락 안에서 받고 → 뒤처짐을 DB에 적고 → 밀렸으면 커밋 처리. 저장소 하나가 실패해도 다음 저장소 —
/// 사유를 `fetch_error`에 남긴다(로그만 남기면 따라잡기가 죽은 프로젝트가 조용히 멈춘다, #46)
pub async fn catch_up(pool: &PgPool, repos: &ServerRepos) -> Result<Vec<SaveResult>, Problem> {
    let projects = {
        let mut c = pool.acquire().await?;
        ProjectService { db: &mut c, repos }.list_projects().await?
    };
    let mut out = Vec::new();
    for (project, repo) in projects {
        match catch_up_one(pool, repos, &project.code, repo.id).await {
            Ok(results) => out.extend(results),
            Err(e) => {
                tracing::warn!("catch_up {}: {e}", repo.remote_url);
                let reason: String = e.to_string().chars().take(300).collect();
                let written = async {
                    let mut c = pool.acquire().await?;
                    project_repo::set_fetch_error(&mut c, repo.id, &reason).await
                }
                .await;
                if let Err(e2) = written {
                    tracing::warn!("catch_up {}: 실패 사유를 못 적었다: {e2}", repo.remote_url);
                }
            }
        }
    }
    Ok(out)
}

/// `catch_up` 1~3 — 저장소 하나, 읽기 락 안에서. 처리 지점도 락 안에서 다시 읽는다(#194)
async fn catch_up_one(
    pool: &PgPool,
    repos: &ServerRepos,
    code: &str,
    repository_id: i32,
) -> Result<Vec<SaveResult>, Problem> {
    let lock = read_lock(code);
    let _held = lock.lock().await;
    let (_, repo) = {
        let mut c = pool.acquire().await?;
        ProjectService { db: &mut c, repos }.get(code).await?
    };
    let last = repo.last_processed_commit.filter(|l| !l.is_empty());
    let origin = PathBuf::from(&repo.remote_url);
    // 받지 않는다 — 서버 저장소의 main 끝. 커밋이 없는 저장소는 건너뛴다 (카드 L19)
    let Some(head) = repos.git.head(&origin).await? else {
        return Ok(Vec::new());
    };
    let behind = match &last {
        Some(l) if *l == head => Some(0),
        Some(l) => Some(
            i32::try_from(
                repos
                    .git
                    .rev_list_count(&origin, &format!("{l}..{head}"))
                    .await?,
            )
            .unwrap_or(i32::MAX),
        ),
        None => None,
    };
    {
        let mut c = pool.acquire().await?;
        project_repo::set_behind(&mut c, repository_id, behind, clock::now()).await?;
    }
    if last.as_deref() != Some(head.as_str()) {
        return process_commit(pool, repos, code, &head, true).await;
    }
    Ok(Vec::new())
}

/// SYNC-MS-017#pipeline.poll_loop
///
/// `interval` 자고 따라잡기 — 끝없이. 한 주기는 따로 띄워 패닉까지 받아 낸다(반복이 멈추면 폴링이 영영 없다)
pub async fn poll_loop(pool: PgPool, repos: Arc<ServerRepos>, interval: Duration) {
    loop {
        tokio::time::sleep(interval).await;
        let (p, r) = (pool.clone(), repos.clone());
        match tokio::spawn(async move { catch_up(&p, &r).await }).await {
            Ok(Ok(_)) => {}
            Ok(Err(e)) => tracing::warn!("poll_loop: {e}"),
            Err(e) => tracing::warn!("poll_loop: {e}"),
        }
    }
}

/// 프로젝트마다 그래프 만들기 하나 — 자리가 있으면 돌고 있다, 값은 「다음」 커밋(나중 것이 이긴다).
/// 열쇠는 작업 사본 자리 — 같은 코드라도 데이터 자리가 다르면(시험) 다른 프로젝트다
static GRAPH_JOBS: LazyLock<Mutex<HashMap<PathBuf, Option<String>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn graph_jobs() -> std::sync::MutexGuard<'static, HashMap<PathBuf, Option<String>>> {
    GRAPH_JOBS
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

/// 만들기 작업이 어떻게 끝나든(멈춰도) 자리를 비운다 — 남으면 다음 걸기가 「다음」만 적고 영영 안 돈다
struct GraphJob(PathBuf);

impl Drop for GraphJob {
    fn drop(&mut self) {
        graph_jobs().remove(&self.0);
    }
}

/// SYNC-MS-017#pipeline.schedule_code_graph
///
/// 저장소 락 밖에서 돈다 — 추출에 수 초가 걸려도 명세 처리와 쓰기를 막지 않는다. 프로젝트마다
/// 하나씩: 돌고 있으면 「다음」만 적고, 끝난 뒤 가장 최근 커밋으로 한 번 더(UC-S8 2b)
pub fn schedule_code_graph(pool: &PgPool, repos: &ServerRepos, code: &str, commit: &str) {
    let key = repos.repos.join(code);
    {
        let mut jobs = graph_jobs();
        if let Some(next) = jobs.get_mut(&key) {
            *next = Some(commit.to_string());
            return;
        }
        jobs.insert(key.clone(), None);
    }
    let (pool, repos, code) = (pool.clone(), repos.clone(), code.to_string());
    let mut commit = commit.to_string();
    tokio::spawn(async move {
        let job = GraphJob(key);
        loop {
            build_code_graph(&pool, &repos, &code, &commit).await;
            let next = graph_jobs().get_mut(&job.0).and_then(Option::take);
            match next {
                Some(n) => commit = n,
                None => break, // 자리는 job이 비운다
            }
        }
    });
}

/// `build_code_graph` 2~3 — 커밋을 임시 폴더에 풀어 원형을 얻고 줄이고 보강한다. 실패는 이유 문장
async fn graph_of(
    repos: &ServerRepos,
    origin: &Path,
    commit: &str,
) -> Result<(String, syncdoc_codegraph::Graph), String> {
    let tmp = tempfile::Builder::new()
        .prefix("syncdoc-graph-")
        .tempdir()
        .map_err(|e| e.to_string())?;
    repos
        .git
        .archive(origin, commit, tmp.path())
        .await
        .map_err(|e| e.to_string())?;
    let src = tmp.path().to_path_buf();
    // 파일 읽기·파싱·군집은 막히는 일이라 따로 — 커뮤니티는 보강 뒤에(보강이 더한 함수도 받는다).
    // 추출 원형은 TS/JS·Rust가 파일 노드뿐이라 보강이 찾은 함수·호출을 더해 묶는다(카드 L20) — graph.json이면 그대로
    let built = tokio::task::spawn_blocking(move || {
        let (source, raw) = syncdoc_codegraph::graph::load(&src)?;
        let graph = syncdoc_codegraph::enrich::enrich(&src, syncdoc_codegraph::graph::reduce(&raw));
        let raw = if source == "server" {
            syncdoc_codegraph::community::widen(&raw, &graph)
        } else {
            raw
        };
        let graph = syncdoc_codegraph::community::communities(&raw, graph);
        Ok::<_, syncdoc_codegraph::CodeGraphFailed>((source, graph))
    })
    .await
    .map_err(|e| e.to_string())?;
    drop(tmp);
    built.map_err(|e| e.0)
}

/// SYNC-MS-017#pipeline.build_code_graph
///
/// 그 커밋을 임시 폴더에 풀어(작업 사본을 안 건드린다) 저장소의 graph.json이나 추출로 그래프를 얻고,
/// 줄이고 보강해 한 행을 바꿔 끼운다. 배치라 실패는 삼키고 행에 남긴다
pub async fn build_code_graph(pool: &PgPool, repos: &ServerRepos, code: &str, commit: &str) {
    let found = async {
        let mut c = pool.acquire().await?;
        ProjectService { db: &mut c, repos }.get(code).await
    }
    .await;
    let (project, repo) = match found {
        Ok(x) => x,
        Err(Problem::NotFound { .. }) => return, // 그새 해제됐다
        Err(e) => {
            tracing::warn!("code graph code={code} 프로젝트를 못 읽었다: {e}");
            return;
        }
    };
    let t0 = Instant::now();
    let short: String = commit.chars().take(7).collect();
    let saved = match graph_of(repos, Path::new(&repo.remote_url), commit).await {
        Ok((source, graph)) => {
            let save = async {
                let mut tx = pool.begin().await?;
                CodeGraphService { db: &mut tx }
                    .save(project.id, commit, &source, &graph)
                    .await?;
                tx.commit().await?;
                Ok::<_, Problem>(())
            }
            .await;
            save.map(|()| (source, graph)).map_err(|e| e.to_string())
        }
        Err(reason) => Err(reason),
    };
    match saved {
        Ok((source, graph)) => tracing::info!(
            "code graph code={code} commit={short} source={source} functions={} calls={} communities={} elapsed={:.1}s",
            graph.functions.len(),
            graph.calls.len(),
            graph.communities.as_ref().map_or(0, Vec::len),
            t0.elapsed().as_secs_f64()
        ),
        Err(reason) => {
            // 배치다. 옛 그래프를 두고 이유만 남긴다 (UC-S8 2a) — 그새 프로젝트가 사라졌으면 남길 곳도 없다
            let _ = async {
                let mut tx = pool.begin().await?;
                CodeGraphService { db: &mut tx }
                    .fail(project.id, commit, &reason)
                    .await?;
                tx.commit().await?;
                Ok::<_, Problem>(())
            }
            .await;
            tracing::warn!("code graph code={code} commit={short} 실패: {reason}");
        }
    }
}

/// SYNC-MS-017#pipeline.type_of_dir
///
/// `06-DOM` → `DOM`, `STD` → `STD` — 앞 두 글자가 파이썬 `str.isdigit()`이고 `-`가 있을 때만 뗀다
pub fn type_of_dir(name: &str) -> String {
    let head: Vec<char> = name.chars().take(2).collect();
    if !head.is_empty() && head.iter().all(|c| is_digit(*c)) && name.contains('-') {
        return name.split_once('-').map_or(name, |(_, t)| t).to_string();
    }
    name.to_string()
}

#[cfg(test)]
mod tests {
    use super::{refusal, type_of_dir};

    #[test]
    fn refusal_like_python() {
        // 파이썬 `_refusal`로 뜬 답
        let cases = [
            ("a/./docs/x", None),
            (
                "docs//specs/x",
                Some("명세 경로 — create_document·update_document로 쓴다"),
            ),
            (
                "./docs/specs/y",
                Some("명세 경로 — create_document·update_document로 쓴다"),
            ),
            ("x/secretive.txt", Some("비밀 꼴")),
            ("İd_rsa", None),
            (".", None),
            ("", Some("빈 경로")),
            ("bin.dat", None),
        ];
        for (p, want) in cases {
            assert_eq!(refusal(p), want, "{p:?}");
        }
    }

    #[test]
    fn type_of_dir_like_python() {
        assert_eq!(type_of_dir("06-DOM"), "DOM");
        assert_eq!(type_of_dir("STD"), "STD");
        assert_eq!(type_of_dir("0-X"), "0-X"); // 앞 두 글자 `0-`는 숫자가 아니다
        assert_eq!(type_of_dir("A1-X"), "A1-X");
        assert_eq!(type_of_dir("²³-PRD"), "PRD"); // 파이썬 isdigit — \d가 아니다
        assert_eq!(type_of_dir("١٢-PRD"), "PRD");
        assert_eq!(type_of_dir("12"), "12");
        assert_eq!(type_of_dir(""), "");
        assert_eq!(type_of_dir("01-a-b"), "a-b");
    }
}
