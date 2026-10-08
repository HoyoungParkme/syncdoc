//! queries — 읽기 조합 (SYNC-MS-018 · SYNC-DOM-004 4.7). 파이썬 판 `core/queries.py`와 같은 이름·같은 처리.
//! 여러 묶음의 서비스를 불러 응답 하나로 엮는다 — 쓰지 않는다. 지금(카드 L6)은 프로젝트 요약 하나다.

use indexmap::IndexMap;
use sqlx::PgConnection;

use crate::account::model::UserRow;
use crate::errors::Problem;
use crate::project::service::{ProjectService, ServerRepos};
use crate::reference::service::ReferenceService;
use crate::spec::SpecService;
use crate::types::{ProjectSummary, STAGES, StageSummary, Storage};

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
