//! queries — 읽기 조합 (SYNC-MS-018 · SYNC-DOM-004 4.7). 파이썬 판 `core/queries.py`와 같은 이름·같은 처리.
//! 여러 묶음의 서비스를 불러 응답 하나로 엮는다 — 쓰지 않는다. 프로젝트 요약(L6)과 MCP 읽기 도구의 넷(L7).

use std::collections::HashMap;

use indexmap::IndexMap;
use sqlx::PgConnection;

use crate::account::model::UserRow;
use crate::account::service::AccountService;
use crate::errors::Problem;
use crate::project::service::{ProjectService, ServerRepos};
use crate::reference::service::ReferenceService;
use crate::spec::SpecService;
use crate::types::{
    ApiAuthor, AuthorRef, BrokenRefSummary, Document, DocumentSummary, Graph, GraphEdge, GraphNode,
    GraphScope, ItemRef, ItemReferences, ItemView, ProjectDetail, ProjectItem, ProjectSummary,
    STAGES, StageSummary, Storage,
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
