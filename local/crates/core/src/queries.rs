//! queries — 읽기 조합 (SYNC-MS-018 · SYNC-DOM-004 4.7). 파이썬 판 `core/queries.py`와 같은 이름·같은 처리.
//! 여러 묶음의 서비스를 불러 응답 하나로 엮는다 — 쓰지 않는다. 프로젝트 요약(L6)과 MCP 읽기 도구의 넷(L7).

use indexmap::IndexMap;
use sqlx::PgConnection;

use crate::account::model::UserRow;
use crate::account::service::AccountService;
use crate::errors::Problem;
use crate::project::service::{ProjectService, ServerRepos};
use crate::reference::service::ReferenceService;
use crate::spec::SpecService;
use crate::types::{
    ApiAuthor, AuthorRef, DocumentSummary, ProjectSummary, STAGES, StageSummary, Storage,
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
