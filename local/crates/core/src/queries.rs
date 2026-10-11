//! queries — 읽기 조합 (SYNC-MS-018 · SYNC-DOM-004 4.7). 파이썬 판 `core/queries.py`와 같은 이름·같은 처리.
//! 여러 묶음의 서비스를 불러 응답 하나로 엮는다 — 쓰지 않는다. 프로젝트 요약(L6)·MCP 읽기 도구의 넷(L7)·웹 읽기(L8)·코드(L12).

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;
use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;
use sqlx::PgConnection;
use syncdoc_codegraph::{CallDiff, Function as CodeFn, Graph as CodeGraph};

use crate::account::model::UserRow;
use crate::account::service::AccountService;
use crate::codegraph::{CodeGraphRow, CodeGraphService};
use crate::errors::Problem;
use crate::markdown::parse_frontmatter;
use crate::project::service::{ProjectService, ServerRepos};
use crate::pycompat::pyset::IntSet;
use crate::pycompat::re::compile;
use crate::reference::service::ReferenceService;
use crate::spec::{DIFF_CONTEXT_LINES, SpecService};
use crate::types::{
    ApiAuthor, AuthorRef, BrokenRefSummary, ChainItem, ChainRow, CodeBrief, CodeCallEdge,
    CodeCalls, CodeFunction, CodeGraphInfo, CodeRef, CodeText, CodeView, Diff, DocType, Document,
    DocumentSummary, DownstreamDoc, DownstreamView, Graph, GraphEdge, GraphNode, GraphScope,
    ItemChain, ItemRef, ItemReferences, ItemView, ProjectDetail, ProjectItem, ProjectSummary,
    STAGES, StageSummary, Storage, stage_of,
};

/// 작성자(id만) → 이름 붙은 작성자 — 파이썬 `_api_author`. 지시자는 id가 있을 때만
async fn api_author(
    db: &mut PgConnection,
    r: Option<&AuthorRef>,
) -> Result<Option<ApiAuthor>, Problem> {
    let Some(r) = r else {
        return Ok(None);
    };
    let ids: Vec<i32> = std::iter::once(r.user_id)
        .chain(r.instructed_by_id)
        .collect();
    let names = AccountService { db }.users_by_ids(&ids).await?;
    Ok(Some(ApiAuthor {
        kind: r.kind.clone(),
        user: names.get(&r.user_id).cloned(),
        instructed_by: r.instructed_by_id.and_then(|i| names.get(&i).cloned()),
        via: r.via.clone(),
    }))
}

/// upstream 낱말 — 파이썬 `re.findall(r"[\w-]+", …)`
static UPSTREAM_WORD: LazyLock<Regex> = LazyLock::new(|| compile(r"[\w-]+"));

/// 문서 ID의 프로젝트 코드 — 첫 `-` 앞(없으면 전부, 파이썬 `doc_id.split("-")[0]`)
fn code_of(doc_id: &str) -> &str {
    doc_id.split('-').next().unwrap_or("")
}

/// SYNC-MS-018#queries.project_summary
pub async fn project_summary(
    db: &mut PgConnection,
    repos: &ServerRepos,
    user: &UserRow,
) -> Result<Vec<ProjectSummary>, Problem> {
    let projects = ProjectService {
        db: &mut *db,
        repos,
    }
    .list_owned(user)
    .await?;
    let mut out = Vec::with_capacity(projects.len());
    for (p, r) in projects {
        let docs = SpecService { db: &mut *db }
            .list_by_project(p.id, None, None, None)
            .await?;
        let ids: Vec<i32> = docs.iter().map(|d| d.id).collect();
        // 프로젝트당 한 번 — 단계마다 부르면 같은 프로젝트를 11번 훑는다
        let per_doc = ReferenceService { db: &mut *db }
            .count_missing_by_document(&ids)
            .await?;
        let mut stages: Vec<StageSummary> = Vec::with_capacity(STAGES.len());
        for (i, doc_type) in STAGES.iter().enumerate() {
            let n = i as i32 + 1;
            let stage_docs: Vec<_> = docs.iter().filter(|d| d.stage == Some(n)).collect();
            // 하나라도 초안이면 초안 (UC-H14 1a)
            let status = if stage_docs.is_empty() {
                None
            } else if stage_docs.iter().any(|d| d.status == "draft") {
                Some("draft".to_string())
            } else {
                stage_docs.iter().map(|d| d.status.clone()).min()
            };
            let gate = !stage_docs.is_empty()
                && stages
                    .iter()
                    .any(|s| s.doc_count > 0 && s.status.as_deref() != Some("approved"));
            let broken = stage_docs
                .iter()
                .map(|d| per_doc.get(&d.id).copied().unwrap_or(0))
                .sum();
            stages.push(StageSummary {
                stage: n,
                doc_type: (*doc_type).to_string(),
                status,
                doc_count: stage_docs.len() as i64,
                gate_warning: gate,
                broken_count: broken,
            });
        }
        let mut counts = IndexMap::new();
        counts.insert("broken_ref".to_string(), per_doc.values().sum());
        counts.insert(
            "convention_errors".to_string(),
            docs.iter().filter(|d| d.has_convention_error).count() as i64,
        );
        counts.insert(
            "incomplete".to_string(),
            docs.iter()
                .filter(|d| !d.incomplete_warnings.is_empty())
                .count() as i64,
        );
        let storage = Storage::parse(&r.storage).unwrap_or(Storage::Github);
        out.push(ProjectSummary {
            code: p.code,
            name: p.name,
            storage,
            // 서버 저장이면 없음 — 서버 안 경로는 밖으로 안 낸다
            remote_url: (storage != Storage::Server).then_some(r.remote_url),
            stages,
            std_docs: docs
                .iter()
                .filter(|d| d.doc_type == "STD")
                .cloned()
                .collect(),
            counts,
            updated_at: docs.iter().map(|d| d.updated_at).max(),
        });
    }
    // 최근 것 먼저, 문서 없는 것은 뒤에 원래 차례로 — 파이썬 안정 정렬(reverse=True)
    out.sort_by(|a, b| {
        (b.updated_at.is_some(), b.updated_at).cmp(&(a.updated_at.is_some(), a.updated_at))
    });
    Ok(out)
}

/// SYNC-MS-018#queries.document_list
pub async fn document_list(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
    stage: Option<i32>,
    status: Option<&str>,
) -> Result<Vec<DocumentSummary>, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let mut docs = SpecService { db: &mut *db }
        .list_by_project(project.id, stage, status, None)
        .await?;
    let ids: Vec<i32> = docs.iter().map(|d| d.id).collect();
    // 쿼리 한 번 (N+1 금지)
    let missing = ReferenceService { db: &mut *db }
        .count_missing_by_document(&ids)
        .await?;
    for d in &mut docs {
        d.counts.insert(
            "broken_ref".to_string(),
            missing.get(&d.id).copied().unwrap_or(0),
        );
        d.author = api_author(&mut *db, d.last_author.as_ref()).await?;
    }
    Ok(docs)
}

/// SYNC-MS-018#queries.document_view
pub async fn document_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    user: &UserRow,
) -> Result<Document, Problem> {
    // 0. 본문을 읽기 전에 소유를 가른다 — 남의 문서가 잠깐이라도 비치면 안 된다
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    let mut doc = SpecService { db: &mut *db }.get_document(doc_id).await?;
    (doc.prev_doc_id, doc.next_doc_id) = SpecService { db: &mut *db }.neighbors(doc_id).await?;
    // 4a. 미존재 참조 — 문서 것은 중복 없이 정렬(완료 게이트가 보는 값과 같게), 항목 것은 처음 본 차례로
    let missing: Vec<_> = ReferenceService { db: &mut *db }
        .upstream_of_document(doc.summary.id, true)
        .await?
        .into_iter()
        .filter(|e| e.is_missing)
        .collect();
    let mut all: Vec<String> = missing.iter().map(|e| e.raw_target.clone()).collect();
    all.sort();
    all.dedup();
    doc.missing_refs = all;
    let mut by_item: HashMap<i32, Vec<String>> = HashMap::new();
    for e in &missing {
        // 절 본문에서 온 것은 항목이 없다
        let Some(pk) = e.from_item_pk else { continue };
        let targets = by_item.entry(pk).or_default();
        if !targets.contains(&e.raw_target) {
            targets.push(e.raw_target.clone());
        }
    }
    for item in &mut doc.items {
        item.missing_refs = by_item.remove(&item.pk).unwrap_or_default();
    }
    doc.summary.author = api_author(&mut *db, doc.summary.last_author.as_ref()).await?;
    // 브레드크럼은 코드가 아니라 이름으로 시작한다
    doc.project_name = project.name;
    Ok(doc)
}

/// SYNC-MS-018#queries.item_view
pub async fn item_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    item_id: &str,
    user: &UserRow,
) -> Result<ItemView, Problem> {
    ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    SpecService { db }.get_item(doc_id, item_id).await
}

/// 문서 pk → 문서 전체를 가리키는 `ItemRef`(항목 없음, 제목) — 파이썬 `_doc_refs`
async fn doc_refs(db: &mut PgConnection, ids: &[i32]) -> Result<HashMap<i32, ItemRef>, Problem> {
    Ok(SpecService { db }
        .describe_documents(ids)
        .await?
        .into_iter()
        .map(|(i, r)| {
            let ref_ = ItemRef {
                doc_id: Some(r.doc_id),
                display_name: Some(r.title),
                ..ItemRef::default()
            };
            (i, ref_)
        })
        .collect())
}

/// 미존재 참조의 `ItemRef` — 대상 없이 `raw_target`만
fn missing_ref(raw_target: &str) -> ItemRef {
    ItemRef {
        raw_target: raw_target.to_string(),
        is_missing: true,
        ..ItemRef::default()
    }
}

/// SYNC-MS-018#queries.item_references_view
///
/// 참조마다 새 `ItemRef`에 제 `raw_target` — 같은 대상을 두 꼴로 가리킨 참조가 서로 덮지 않는다(#353)
pub async fn item_references_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    item_id: &str,
    user: &UserRow,
) -> Result<ItemReferences, Problem> {
    ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    let pk = SpecService { db: &mut *db }
        .resolve_item(doc_id, item_id)
        .await?;
    let up = ReferenceService { db: &mut *db }.upstream(pk).await?;
    // 이 항목을 가리키는 참조만 — 문서 전체를 가리킨 것은 항목의 하위가 아니다(#160)
    let down = ReferenceService { db: &mut *db }.downstream(pk).await?;
    let need: Vec<i32> = up
        .iter()
        .filter_map(|e| e.to_item_pk)
        .chain(down.iter().filter_map(|e| e.from_item_pk))
        .collect();
    let names = SpecService { db: &mut *db }.describe_items(&need).await?;
    let doc_ids: Vec<i32> = up
        .iter()
        .filter(|e| e.to_item_pk.is_none())
        .filter_map(|e| e.to_document_id)
        .collect();
    let doc_names = doc_refs(&mut *db, &doc_ids).await?;
    let upstream = up
        .iter()
        .map(|e| {
            if e.is_missing {
                return missing_ref(&e.raw_target);
            }
            // 항목이면 항목 이름에서, 없으면 같은 수의 문서에서(파이썬 `{**doc_names, **names}`)
            let found = match e.to_item_pk {
                Some(p) => names.get(&p).or_else(|| doc_names.get(&p)),
                None => e.to_document_id.and_then(|d| doc_names.get(&d)),
            };
            match found {
                Some(r) => ItemRef {
                    raw_target: e.raw_target.clone(),
                    ..r.clone()
                },
                None => missing_ref(&e.raw_target),
            }
        })
        .collect();
    // 항목 밖(절 본문·표)에서 건 참조는 출발 문서로 — 건너뛰면 패널이 「고립 항목」이라 했다(#160)
    let from_ids: Vec<i32> = down
        .iter()
        .filter(|e| e.from_item_pk.is_none())
        .map(|e| e.from_document_id)
        .collect();
    let froms = doc_refs(&mut *db, &from_ids).await?;
    let downstream = down
        .iter()
        .filter_map(|e| {
            let r = match e.from_item_pk {
                Some(p) => names.get(&p),
                None => froms.get(&e.from_document_id),
            }?;
            Some(ItemRef {
                doc_id: r.doc_id.clone(),
                item_id: r.item_id.clone(),
                display_name: r.display_name.clone(),
                raw_target: e.raw_target.clone(),
                ..ItemRef::default()
            })
        })
        .collect();
    Ok(ItemReferences {
        doc_id: doc_id.to_string(),
        item_id: item_id.to_string(),
        upstream,
        downstream,
    })
}

/// SYNC-MS-018#queries.project_detail
///
/// 동기화 칸은 DB에 적힌 값 그대로 — 받아 오지 않는다(UI-4 요소 7)
pub async fn project_detail(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
) -> Result<ProjectDetail, Problem> {
    let (project, repo) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let mut recent = SpecService { db: &mut *db }
        .recent_changes(project.id, 10)
        .await?;
    let ids: Vec<i32> = recent
        .iter()
        .map(|r| r.author.user_id)
        .chain(recent.iter().filter_map(|r| r.author.instructed_by_id))
        .collect();
    let names = AccountService { db: &mut *db }.users_by_ids(&ids).await?;
    for r in &mut recent {
        r.author_view = Some(ApiAuthor {
            kind: r.author.kind.clone(),
            user: names.get(&r.author.user_id).cloned(),
            instructed_by: r
                .author
                .instructed_by_id
                .and_then(|i| names.get(&i).cloned()),
            via: r.author.via.clone(),
        });
    }
    let summary = project_summary(&mut *db, repos, user)
        .await?
        .into_iter()
        .find(|p| p.code == code)
        .ok_or_else(|| Problem::Internal {
            log: format!("프로젝트 {code}의 요약이 없다"),
        })?;
    let docs = document_list(&mut *db, repos, code, user, None, None).await?;
    Ok(ProjectDetail {
        summary,
        docs,
        recent_changes: recent,
        last_processed_commit: repo.last_processed_commit,
        behind_by: repo.behind_by,
        fetched_at: repo.fetched_at,
    })
}

/// SYNC-MS-018#queries.project_items
///
/// `kind`는 라우터가 패턴으로 거른다 — 그 밖은 파이썬 `ValueError`처럼 처리하지 못한 오류
pub async fn project_items(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    kind: &str,
    user: &UserRow,
) -> Result<Vec<ProjectItem>, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    match kind {
        "broken_ref" => {
            let edges = ReferenceService { db: &mut *db }
                .missing_in_project(project.id)
                .await?;
            let item_pks: Vec<i32> = edges.iter().filter_map(|e| e.from_item_pk).collect();
            let names = SpecService { db: &mut *db }
                .describe_items(&item_pks)
                .await?;
            let doc_ids: Vec<i32> = edges
                .iter()
                .filter(|e| e.from_item_pk.is_none())
                .map(|e| e.from_document_id)
                .collect();
            let docs = doc_refs(&mut *db, &doc_ids).await?;
            Ok(edges
                .iter()
                .filter_map(|e| {
                    let src = match e.from_item_pk {
                        Some(p) => names.get(&p),
                        None => docs.get(&e.from_document_id),
                    }?;
                    Some(ProjectItem::Broken(BrokenRefSummary {
                        source: src.clone(),
                        raw_target: e.raw_target.clone(),
                    }))
                })
                .collect())
        }
        "convention_errors" => Ok(SpecService { db: &mut *db }
            .list_by_project(project.id, None, None, Some(true))
            .await?
            .into_iter()
            .map(|d| ProjectItem::Document(Box::new(d)))
            .collect()),
        "incomplete" => Ok(SpecService { db: &mut *db }
            .list_by_project(project.id, None, None, None)
            .await?
            .into_iter()
            .filter(|d| !d.incomplete_warnings.is_empty())
            .map(|d| ProjectItem::Document(Box::new(d)))
            .collect()),
        other => Err(Problem::Internal {
            log: format!("unknown kind {other}"),
        }),
    }
}

/// SYNC-MS-018#queries.graph_view
///
/// 11단계를 다 그리되 범위로 골라낸다. 끝점이 범위 밖인 간선은 버린다 — 범위 밖과 미존재 참조는 다르다
pub async fn graph_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
    scope: GraphScope,
) -> Result<Graph, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let mut briefs = SpecService { db: &mut *db }
        .list_items_by_project(project.id)
        .await?;
    if scope == GraphScope::Approved {
        let ok: std::collections::HashSet<String> = SpecService { db: &mut *db }
            .list_by_project(project.id, None, Some("approved"), None)
            .await?
            .into_iter()
            .map(|d| d.doc_id)
            .collect();
        briefs.retain(|b| ok.contains(&b.doc_id));
    }
    let node_id = |doc_id: &str, item_id: Option<&str>| match item_id {
        Some(i) => format!("{doc_id}#{i}"),
        None => doc_id.to_string(),
    };
    let item_ids: HashMap<i32, String> = briefs
        .iter()
        .filter_map(|b| {
            b.item_id
                .as_deref()
                .map(|i| (b.pk, node_id(&b.doc_id, Some(i))))
        })
        .collect();
    let doc_ids: HashMap<i32, String> = briefs
        .iter()
        .filter(|b| b.item_id.is_none())
        .map(|b| (b.pk, b.doc_id.clone()))
        .collect();
    let pks: Vec<i32> = item_ids.keys().copied().collect();
    let edges = ReferenceService { db: &mut *db }
        .references_among(&pks, true)
        .await?;
    let mut out_edges = Vec::new();
    let mut touched: std::collections::HashSet<String> = std::collections::HashSet::new();
    for e in &edges {
        let src = match e.from_item_pk {
            Some(p) => item_ids.get(&p),
            None => doc_ids.get(&e.from_document_id),
        };
        let Some(src) = src else { continue };
        let dst = if let Some(p) = e.to_item_pk {
            // 대상이 범위 밖이다. 미존재 참조가 아니므로 그리지 않는다
            let Some(d) = item_ids.get(&p) else { continue };
            Some(d.clone())
        } else if let Some(d) = e.to_document_id {
            let Some(d) = doc_ids.get(&d) else { continue };
            Some(d.clone())
        } else {
            None
        };
        touched.insert(src.clone());
        if let Some(d) = &dst {
            touched.insert(d.clone());
        }
        out_edges.push(GraphEdge {
            from_: src.clone(),
            to: dst,
            raw_target: e.raw_target.clone(),
            is_missing: e.is_missing,
        });
    }
    let nodes = briefs
        .iter()
        .map(|b| {
            let id = node_id(&b.doc_id, b.item_id.as_deref());
            GraphNode {
                isolated: !touched.contains(&id),
                id,
                doc_id: b.doc_id.clone(),
                item_id: b.item_id.clone(),
                stage: b.stage,
            }
        })
        .collect();
    Ok(Graph {
        nodes,
        edges: out_edges,
        project_name: project.name,
    })
}

/// 한 방향으로 너비 우선 — 본 것은 파이썬 `set`에, 사이클은 본 표시로 멈추고 끝에 시작점을 뺀다 (파이썬 `_closure`)
async fn closure(db: &mut PgConnection, start: i32, upward: bool) -> Result<IntSet, Problem> {
    let mut seen = IntSet::new();
    let mut queue = std::collections::VecDeque::from([start]);
    while let Some(pk) = queue.pop_front() {
        let edges = if upward {
            ReferenceService { db: &mut *db }.upstream(pk).await?
        } else {
            ReferenceService { db: &mut *db }.downstream(pk).await?
        };
        for e in edges {
            let next = if upward { e.to_item_pk } else { e.from_item_pk };
            if let Some(n) = next
                && let Ok(key) = u64::try_from(n)
                && !seen.contains(key)
            {
                seen.add(key);
                queue.push_back(n);
            }
        }
    }
    if let Ok(key) = u64::try_from(start) {
        seen.discard(key);
    }
    Ok(seen)
}

/// SYNC-MS-018#queries.item_chain
///
/// 직접 참조가 아니라 전이적 폐포다. 역할은 어느 폐포에서 나왔는지로 정한다 — 단계 번호로 정하면 되돌아오는
/// 참조에서 근거를 파생으로 잘못 적는다. 한 단계 안의 차례는 파이썬 `set`의 순회 차례다
pub async fn item_chain(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    item_id: &str,
    user: &UserRow,
) -> Result<ItemChain, Problem> {
    ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    let pk = SpecService { db: &mut *db }
        .resolve_item(doc_id, item_id)
        .await?;
    let ups = closure(&mut *db, pk, true).await?;
    let downs = closure(&mut *db, pk, false).await?;
    let as_pk = |k: u64| i32::try_from(k).unwrap_or(0);
    let mut all: Vec<i32> = ups.iter().map(as_pk).collect();
    all.extend(downs.iter().map(as_pk));
    all.push(pk);
    let described = SpecService { db: &mut *db }.describe_items(&all).await?;
    let mut statuses: HashMap<String, String> = HashMap::new();
    for r in described.values() {
        if let Some(d) = &r.doc_id
            && !statuses.contains_key(d)
        {
            let status = SpecService { db: &mut *db }
                .get_document(d)
                .await?
                .summary
                .status;
            statuses.insert(d.clone(), status);
        }
    }
    let order = std::iter::once((pk, "self"))
        .chain(ups.iter().map(|k| (as_pk(k), "upstream")))
        .chain(downs.iter().map(|k| (as_pk(k), "downstream")));
    let mut by_stage: HashMap<i32, Vec<ChainItem>> = HashMap::new();
    for (p, role) in order {
        let Some(r) = described.get(&p) else { continue };
        let Some(d) = &r.doc_id else { continue };
        // STD는 단계 밖이라 체인에 안 놓는다
        let Some(stage) = d.split('-').nth(1).and_then(stage_of) else {
            continue;
        };
        by_stage.entry(stage).or_default().push(ChainItem {
            ref_: r.clone(),
            role: role.to_string(),
            status: statuses
                .get(d)
                .cloned()
                .unwrap_or_else(|| "draft".to_string()),
        });
    }
    let item = described
        .get(&pk)
        .cloned()
        .ok_or_else(|| Problem::Internal {
            log: format!("{doc_id}#{item_id}의 표시 정보가 없다"),
        })?;
    Ok(ItemChain {
        item,
        upstream_count: ups.len() as i64,
        downstream_count: downs.len() as i64,
        // 항상 11행 — 체인이 어디서 끊겼는지가 이 화면의 목적이다
        rows: STAGES
            .iter()
            .enumerate()
            .map(|(i, t)| {
                let stage = i as i32 + 1;
                ChainRow {
                    stage,
                    doc_type: (*t).to_string(),
                    items: by_stage.remove(&stage).unwrap_or_default(),
                }
            })
            .collect(),
    })
}

/// SYNC-MS-018#queries.diff_with_impact
pub async fn diff_with_impact(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    from_no: i32,
    to_no: i32,
    user: &UserRow,
) -> Result<Diff, Problem> {
    ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    let mut d = SpecService { db: &mut *db }
        .diff(doc_id, from_no, to_no, DIFF_CONTEXT_LINES)
        .await?;
    let ids: Vec<String> = d.hunks.iter().filter_map(|h| h.item_id.clone()).collect();
    let pks = SpecService { db: &mut *db }
        .resolve_items(doc_id, &ids)
        .await?;
    // 항목 ID → pk — 이름에서 되짚는다(파이썬 `describe_items`)
    let by_id: HashMap<String, i32> = SpecService { db: &mut *db }
        .describe_items(&pks)
        .await?
        .into_iter()
        .filter_map(|(pk, r)| r.item_id.map(|i| (i, pk)))
        .collect();
    let pk_list: Vec<i32> = by_id.values().copied().collect();
    let counts = ReferenceService { db: &mut *db }
        .count_downstream(&pk_list)
        .await?;
    for h in &mut d.hunks {
        // 새 항목·항목 밖은 0
        h.downstream_count = h
            .item_id
            .as_ref()
            .and_then(|i| by_id.get(i))
            .and_then(|pk| counts.get(pk))
            .copied()
            .unwrap_or(0);
    }
    Ok(d)
}

/// 문서 제목 — 없는 문서면 문서 ID (파이썬 `_title_of`)
async fn title_of(db: &mut PgConnection, doc_id: &str) -> Result<String, Problem> {
    let id = match (SpecService { db: &mut *db }).get_document(doc_id).await {
        Ok(d) => d.summary.id,
        Err(Problem::NotFound { .. }) => return Ok(doc_id.to_string()),
        Err(other) => return Err(other),
    };
    Ok(SpecService { db }
        .describe_documents(&[id])
        .await?
        .remove(&id)
        .map_or_else(|| doc_id.to_string(), |r| r.title))
}

/// SYNC-MS-018#queries.downstream_view
///
/// 항목이 없는 문서는 문서 참조도 안 나온다 — 간선을 그 문서의 항목들로 찾는다(파이썬과 같다)
pub async fn downstream_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    user: &UserRow,
) -> Result<DownstreamView, Problem> {
    ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    let document = SpecService { db: &mut *db }.get_document(doc_id).await?;
    let pks = SpecService { db: &mut *db }
        .item_pks(document.summary.id)
        .await?;
    let by_pk: HashMap<i32, String> = pks.iter().map(|(i, p)| (*p, i.clone())).collect();
    let pk_list: Vec<i32> = pks.values().copied().collect();
    let edges: Vec<_> = ReferenceService { db: &mut *db }
        .references_among(&pk_list, true)
        .await?
        .into_iter()
        .filter(|e| {
            e.to_item_pk.is_some_and(|p| by_pk.contains_key(&p))
                || e.to_document_id == Some(document.summary.id)
        })
        .collect();
    let item_pks: Vec<i32> = edges.iter().filter_map(|e| e.from_item_pk).collect();
    let names = SpecService { db: &mut *db }
        .describe_items(&item_pks)
        .await?;
    let doc_pks: Vec<i32> = edges.iter().map(|e| e.from_document_id).collect();
    let docs = SpecService { db: &mut *db }
        .describe_documents(&doc_pks)
        .await?;
    let mut by_item: IndexMap<String, Vec<ItemRef>> = IndexMap::new();
    let mut by_doc: IndexMap<String, std::collections::BTreeSet<String>> = IndexMap::new();
    for e in &edges {
        let key = match e.to_item_pk.and_then(|p| by_pk.get(&p)) {
            Some(i) => i.clone(),
            None => "(문서)".to_string(),
        };
        // 출발 항목이면 이름 지도의 것 그대로(raw_target 없음), 아니면 출발 문서
        let r = match e.from_item_pk.and_then(|p| names.get(&p)) {
            Some(r) => r.clone(),
            None => match docs.get(&e.from_document_id) {
                Some(d) => ItemRef {
                    doc_id: Some(d.doc_id.clone()),
                    display_name: Some(d.title.clone()),
                    raw_target: e.raw_target.clone(),
                    ..ItemRef::default()
                },
                None => continue,
            },
        };
        // 같은 문서 안 참조는 추적표 대상이 아니다
        if r.doc_id.as_deref() == Some(doc_id) {
            continue;
        }
        by_doc
            .entry(r.doc_id.clone().unwrap_or_default())
            .or_default()
            .insert(key.clone());
        by_item.entry(key).or_default().push(r);
    }
    let mut by_document = Vec::with_capacity(by_doc.len());
    for (d, items) in by_doc {
        let title = title_of(&mut *db, &d).await?;
        by_document.push(DownstreamDoc {
            doc_id: d,
            title,
            items: items.into_iter().collect(),
        });
    }
    by_document.sort_by(|a, b| {
        let stage = |d: &str| d.split('-').nth(1).and_then(stage_of).unwrap_or(99);
        (stage(&a.doc_id), &a.doc_id).cmp(&(stage(&b.doc_id), &b.doc_id))
    });
    Ok(DownstreamView {
        by_item,
        by_document,
    })
}

/// SYNC-MS-018#queries.trash_list
///
/// 건수는 안 센다 — 휴지통 목록에는 수치가 없다
pub async fn trash_list(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
) -> Result<Vec<DocumentSummary>, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let mut docs = SpecService { db: &mut *db }
        .list_trashed(project.id)
        .await?;
    for d in &mut docs {
        d.author = api_author(&mut *db, d.last_author.as_ref()).await?;
    }
    Ok(docs)
}

// ── 코드 그래프 (카드 L12) — 대조는 부를 때 계산한다. 그래프는 code_graphs, 「호출하는 것」은 명세

/// 그래프 행의 머리 — 몸통은 싣지 않는다
fn graph_info(row: &CodeGraphRow) -> CodeGraphInfo {
    CodeGraphInfo {
        commit_hash: row.commit_hash.clone(),
        source: row.source.clone(),
        built_at: row.built_at,
        error: row.error.clone(),
        function_count: row.function_count,
    }
}

/// 프로젝트의 MINISPEC 항목마다 (문서ID#항목ID, 블록) — `spec_calls`의 재료 (파이썬 `_ms_items`)
async fn ms_items(
    db: &mut PgConnection,
    project_id: i32,
) -> Result<Vec<(String, String)>, Problem> {
    let mut spec = SpecService { db };
    let mut out = Vec::new();
    for d in spec
        .list_by_project(project_id, stage_of("MS"), None, None)
        .await?
    {
        let doc = spec.get_document(&d.doc_id).await?;
        let Some(t) = DocType::parse(&doc.summary.doc_type) else {
            continue;
        };
        for b in SpecService::item_blocks(&doc.body, t, None) {
            out.push((format!("{}#{}", doc.summary.doc_id, b.item_id), b.text));
        }
    }
    Ok(out)
}

/// 프로젝트의 클래스 명세 — DOM 문서 중 제목에 「클래스」가 든 것 전부, 문서 순서 (파이썬 `_class_docs`).
/// 구현이 둘이면 클래스 명세도 둘이다(STD-001 2.6)
async fn class_docs(db: &mut PgConnection, project_id: i32) -> Result<Vec<String>, Problem> {
    let mut spec = SpecService { db };
    let mut out = Vec::new();
    for d in spec
        .list_by_project(project_id, stage_of("DOM"), None, None)
        .await?
    {
        let doc = spec.get_document(&d.doc_id).await?;
        let fm = parse_frontmatter(&doc.body).0;
        if fm.get("title").is_some_and(|t| t.contains("클래스")) {
            out.push(d.doc_id);
        }
    }
    Ok(out)
}

/// MS 문서 ID → 그 문서 upstream의 클래스 명세 — 꼭 하나일 때만 (파이썬 `_impl_of`, MS-018 code_view 2)
async fn impl_of(
    db: &mut PgConnection,
    project_id: i32,
) -> Result<HashMap<String, String>, Problem> {
    let classes = class_docs(&mut *db, project_id).await?;
    let mut spec = SpecService { db };
    let mut out = HashMap::new();
    for d in spec
        .list_by_project(project_id, stage_of("MS"), None, None)
        .await?
    {
        let body = spec.get_document(&d.doc_id).await?.body;
        let fm = parse_frontmatter(&body).0;
        let up = fm.get("upstream").map_or("", String::as_str);
        let hits: Vec<&str> = UPSTREAM_WORD
            .find_iter(up.trim_matches(['[', ']']))
            .map(|m| m.as_str())
            .filter(|x| classes.iter().any(|c| c == x))
            .collect();
        if let [one] = hits[..] {
            out.insert(d.doc_id, one.to_string());
        }
    }
    Ok(out)
}

/// 항목 ID → 대조 한 줄 — 대조의 차례(항목 ID 순) 그대로 (파이썬 `_diffs`)
async fn diffs_of(
    db: &mut PgConnection,
    project_id: i32,
    graph: &CodeGraph,
) -> Result<IndexMap<String, CallDiff>, Problem> {
    let items = ms_items(&mut *db, project_id).await?;
    let impls = impl_of(&mut *db, project_id).await?;
    let spec = syncdoc_codegraph::spec_calls(&items, Some(&impls));
    Ok(syncdoc_codegraph::compare(graph, &spec)
        .into_iter()
        .map(|d| (d.ms_id.clone(), d))
        .collect())
}

/// 부르는 것·불리는 곳 한 줄 — 대조에 그 항목의 함수가 없으면 자리 없이 (파이썬 `_code_ref`)
fn code_ref(
    ms_id: &str,
    diffs: &IndexMap<String, CallDiff>,
    fns: &HashMap<&str, &CodeFn>,
    status: Option<&str>,
) -> CodeRef {
    let f = diffs
        .get(ms_id)
        .and_then(|d| d.function.as_deref())
        .and_then(|k| fns.get(k));
    CodeRef {
        ms_id: ms_id.to_string(),
        qual: f.map(|f| f.qual.clone()),
        file: f.map(|f| f.file.clone()),
        line: f.map(|f| f.line),
        status: status.map(str::to_string),
    }
}

/// `item_neighbors`의 함수 → 대조 없는 한 줄 — 항목 ID는 그 함수의 item (파이썬 `_item_ref`)
fn item_ref(f: &CodeFn) -> CodeRef {
    CodeRef {
        ms_id: f.item.clone().unwrap_or_default(),
        qual: Some(f.qual.clone()),
        file: Some(f.file.clone()),
        line: Some(f.line),
        status: None,
    }
}

/// 함수 목록 한 줄 (파이썬 `_code_brief`)
fn code_brief(d: &CallDiff, fns: &HashMap<&str, &CodeFn>) -> CodeBrief {
    let f = d.function.as_deref().and_then(|k| fns.get(k));
    CodeBrief {
        ms_id: d.ms_id.clone(),
        qual: f.map(|f| f.qual.clone()),
        file: f.map(|f| f.file.clone()),
        line: f.map(|f| f.line),
        same: d.same.len() as i64,
        code_only: d.code_only.len() as i64,
        spec_only: d.spec_only.len() as i64,
    }
}

/// key → 함수 — 같은 key면 뒤의 것 (파이썬 dict)
fn by_key(graph: &CodeGraph) -> HashMap<&str, &CodeFn> {
    graph
        .functions
        .iter()
        .map(|f| (f.key.as_str(), f))
        .collect()
}

/// SYNC-MS-018#queries.code_view
///
/// MINISPEC 항목이면 그 함수의 부르는 것(코드만·명세만·같음 순)·불리는 곳, 다른 항목이면 하위
/// 체인의 MINISPEC 함수, MINISPEC 문서 단위면 그 문서 함수 전부. 그래프가 없으면 `graph` 없이
pub async fn code_view(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    item_id: Option<&str>,
    user: &UserRow,
) -> Result<CodeView, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    let doc = SpecService { db: &mut *db }.get_document(doc_id).await?;
    if let Some(item) = item_id {
        SpecService { db: &mut *db }
            .resolve_item(doc_id, item)
            .await?;
    }
    let is_ms = doc.summary.doc_type == "MS";
    let item_id = item_id.map(str::to_string);
    let Some(row) = CodeGraphService { db: &mut *db }.get(project.id).await? else {
        return Ok(CodeView {
            graph: None,
            doc_id: doc_id.to_string(),
            item_id,
            is_ms,
            missing: false,
            function: None,
            functions: Vec::new(),
        });
    };
    let info = graph_info(&row);
    let graph = &row.graph;
    let diffs = diffs_of(&mut *db, project.id, graph).await?;
    let order: Vec<String> = DocType::parse(&doc.summary.doc_type)
        .map(|t| SpecService::item_blocks(&doc.body, t, None))
        .unwrap_or_default()
        .into_iter()
        .map(|b| b.item_id)
        .collect();
    let fns = by_key(graph);
    let mut function: Option<CodeFunction> = None;
    let mut missing = false;
    if let (true, Some(item)) = (is_ms, item_id.as_deref()) {
        let ms_id = format!("{doc_id}#{item}");
        let found = diffs.get(&ms_id).and_then(|d| {
            d.function
                .as_deref()
                .and_then(|k| fns.get(k))
                .map(|f| (d, f))
        });
        match found {
            None => missing = true,
            Some((d, f)) => {
                let calls = d
                    .code_only
                    .iter()
                    .map(|x| code_ref(x, &diffs, &fns, Some("code_only")))
                    .chain(
                        d.spec_only
                            .iter()
                            .map(|x| code_ref(x, &diffs, &fns, Some("spec_only"))),
                    )
                    .chain(
                        d.same
                            .iter()
                            .map(|x| code_ref(x, &diffs, &fns, Some("same"))),
                    )
                    .collect();
                let callers = diffs
                    .values()
                    .filter(|o| o.same.contains(&ms_id) || o.code_only.contains(&ms_id))
                    .map(|o| code_ref(&o.ms_id, &diffs, &fns, None))
                    .collect();
                function = Some(CodeFunction {
                    ms_id: ms_id.clone(),
                    qual: f.qual.clone(),
                    file: f.file.clone(),
                    line: f.line,
                    end: f.end,
                    calls,
                    callers,
                });
            }
        }
    }
    if let (None, Some(item)) = (&function, item_id.as_deref()) {
        // 3a — API·UI 항목의 함수: item으로 찾고 항목 있는 이웃까지, 대조 없음
        let ms_id = format!("{doc_id}#{item}");
        if let Some(f) = syncdoc_codegraph::item_function(graph, &ms_id) {
            missing = false;
            let (fwd, back) = syncdoc_codegraph::item_neighbors(graph, &f.key);
            let refs = |keys: &[String]| -> Vec<CodeRef> {
                keys.iter()
                    .filter_map(|k| fns.get(k.as_str()))
                    .map(|f| item_ref(f))
                    .collect()
            };
            function = Some(CodeFunction {
                ms_id,
                qual: f.qual.clone(),
                file: f.file.clone(),
                line: f.line,
                end: f.end,
                calls: refs(&fwd),
                callers: refs(&back),
            });
        }
    }
    let mut functions = Vec::new();
    if let (Some(item), false) = (item_id.as_deref(), is_ms) {
        let chain = item_chain(&mut *db, repos, doc_id, item, user).await?;
        for r in chain.rows.iter().filter(|r| r.doc_type == "MS") {
            for ci in &r.items {
                let Some(it) = ci.ref_.item_id.as_deref().filter(|i| !i.is_empty()) else {
                    continue;
                };
                if ci.role != "downstream" {
                    continue;
                }
                let id = format!("{}#{it}", ci.ref_.doc_id.as_deref().unwrap_or("None"));
                if let Some(d) = diffs.get(&id) {
                    functions.push(code_brief(d, &fns));
                }
            }
        }
    } else if is_ms {
        for i in &order {
            if let Some(d) = diffs.get(&format!("{doc_id}#{i}")) {
                functions.push(code_brief(d, &fns));
            }
        }
    }
    Ok(CodeView {
        graph: Some(info),
        doc_id: doc_id.to_string(),
        item_id,
        is_ms,
        missing,
        function,
        functions,
    })
}

/// SYNC-MS-018#queries.code_calls
///
/// MINISPEC 항목 사이의 호출 선 — 같음·코드만·명세만(UI-8 2.6)
pub async fn code_calls(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    user: &UserRow,
) -> Result<CodeCalls, Problem> {
    let (project, _) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let Some(row) = CodeGraphService { db: &mut *db }.get(project.id).await? else {
        return Ok(CodeCalls {
            graph: None,
            edges: Vec::new(),
        });
    };
    let diffs = diffs_of(&mut *db, project.id, &row.graph).await?;
    let mut edges = Vec::new();
    for d in diffs.values() {
        for (status, xs) in [
            ("same", &d.same),
            ("code_only", &d.code_only),
            ("spec_only", &d.spec_only),
        ] {
            edges.extend(xs.iter().map(|x| CodeCallEdge {
                from: d.ms_id.clone(),
                to: x.clone(),
                status: status.to_string(),
            }));
        }
    }
    Ok(CodeCalls {
        graph: Some(graph_info(&row)),
        edges,
    })
}

/// 같은 파일에서 이 함수 다음 함수의 앞 줄 — 끝 줄을 모르는(파이썬 밖) 함수의 끝 (파이썬 `_next_start`)
fn next_start(functions: &[CodeFn], f: &CodeFn) -> Option<i64> {
    functions
        .iter()
        .filter(|g| g.file == f.file && g.line > f.line)
        .map(|g| g.line)
        .min()
        .map(|l| l - 1)
}

/// 함수의 끝 줄 — 끝 줄, 없으면 다음 함수 앞 줄, 그것도 없으면 시작 + 59
fn end_of(functions: &[CodeFn], f: &CodeFn) -> i64 {
    f.end
        .filter(|e| *e != 0)
        .or_else(|| next_start(functions, f).filter(|e| *e != 0))
        .unwrap_or(f.line + 59)
}

/// SYNC-MS-018#queries.code_source
///
/// 코드 보기(8.21). 그래프 커밋의 저장소에서 읽는다 — 읽기는 `CodeGraphService.read` 한곳
pub async fn code_source(
    db: &mut PgConnection,
    repos: &ServerRepos,
    doc_id: &str,
    item_id: &str,
    user: &UserRow,
) -> Result<CodeText, Problem> {
    let (project, repo) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code_of(doc_id), user)
    .await?;
    SpecService { db: &mut *db }
        .resolve_item(doc_id, item_id)
        .await?;
    let mut svc = CodeGraphService { db: &mut *db };
    let Some(row) = svc.get(project.id).await? else {
        return Err(Problem::NotFound {
            resource: "code_graph".into(),
            id: project.code.clone().into(),
        });
    };
    let ms_id = format!("{doc_id}#{item_id}");
    let spec = BTreeMap::from([(ms_id.clone(), BTreeSet::new())]);
    let d = syncdoc_codegraph::compare(&row.graph, &spec);
    let fns = &row.graph.functions;
    let by_function = d
        .first()
        .and_then(|d| d.function.as_deref())
        .and_then(|k| fns.iter().find(|x| x.key == k));
    // API·UI 항목 — item으로
    let Some(f) = by_function.or_else(|| syncdoc_codegraph::item_function(&row.graph, &ms_id))
    else {
        return Err(Problem::NotFound {
            resource: "function".into(),
            id: ms_id.into(),
        });
    };
    let end = end_of(fns, f);
    let (file, line) = (f.file.clone(), f.line);
    svc.read(
        &repos.git,
        project.id,
        Path::new(&repo.workdir_path),
        &file,
        line,
        Some(end),
    )
    .await
}

/// SYNC-MS-018#queries.code_text
///
/// 코드 그래프의 코드(UI-17 4.6). 그래프의 함수를 파일·시작 줄로 짚는다 — 항목이 없어도 읽는다.
/// 읽기는 `code_source`와 같은 `CodeGraphService.read` 한곳이라 코드 탭과 같은 본문이다
pub async fn code_text(
    db: &mut PgConnection,
    repos: &ServerRepos,
    code: &str,
    file: &str,
    line: i64,
    user: &UserRow,
) -> Result<CodeText, Problem> {
    let (project, repo) = ProjectService {
        db: &mut *db,
        repos,
    }
    .get_owned(code, user)
    .await?;
    let mut svc = CodeGraphService { db: &mut *db };
    let Some(row) = svc.get(project.id).await? else {
        return Err(Problem::NotFound {
            resource: "code_graph".into(),
            id: project.code.clone().into(),
        });
    };
    let fns = &row.graph.functions;
    let Some(f) = fns.iter().find(|x| x.file == file && x.line == line) else {
        return Err(Problem::NotFound {
            resource: "function".into(),
            id: format!("{file}:{line}").into(),
        });
    };
    let end = end_of(fns, f);
    let (path, start) = (f.file.clone(), f.line);
    svc.read(
        &repos.git,
        project.id,
        Path::new(&repo.workdir_path),
        &path,
        start,
        Some(end),
    )
    .await
}
