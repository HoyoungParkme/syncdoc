//! 응답 형태 — SYNC-API-001 4장. 키 순서는 파이썬 판 `web/schemas`와 같다

use indexmap::IndexMap;
use serde::Serialize;
use syncdoc_core::account::model::AccessTokenRow;
use syncdoc_core::types::{
    ApiAuthor, BrokenRefSummary as BrokenRefDto, Diff as DiffDto, Document as DocumentDto,
    DocumentSummary as DocumentSummaryDto, DownstreamView as DownstreamDto, Graph as GraphDto,
    GraphEdge, GraphNode, ItemChain as ItemChainDto, ItemRef as ItemRefDto,
    ItemReferences as ItemReferencesDto, ItemView as ItemViewDto,
    ProjectDetail as ProjectDetailDto, ProjectItem, ProjectSummary as ProjectSummaryDto,
    SaveResult as SaveResultDto, StageSummary, TrashResult as TrashResultDto,
    UserRef as UserRefDto, Version as VersionDto, iso_utc,
};
use syncdoc_core::types::{
    CodeBrief as CodeBriefDto, CodeCalls as CodeCallsDto, CodeFunction as CodeFunctionDto,
    CodeGraphInfo as CodeGraphInfoDto, CodeNodes as CodeNodesDto, CodeRef as CodeRefDto,
    CodeText as CodeTextDto, CodeView as CodeViewDto,
};
use syncdoc_core::types::{
    HookStatus as HookStatusDto, RebuildResult as RebuildResultDto, RepoStatus as RepoStatusDto,
    SyncResult as SyncResultDto,
};

/// `Me` — `User`(id·github_login·display_name·created_at)에 판·모델·저장 방식을 더한 것
#[derive(Debug, Serialize)]
pub struct Me {
    pub id: i32,
    pub github_login: String,
    pub display_name: String,
    pub created_at: String,
    pub llm_enabled: bool,
    pub storage_modes: Vec<&'static str>,
    pub edition: &'static str,
    pub repo_private: bool,
}

/// `AccessToken` — 원문·해시 없음 (`web/schemas/account.py`)
#[derive(Debug, Serialize)]
pub struct AccessToken {
    pub id: i32,
    pub label: String,
    pub issued_at: String,
    pub expires_at: Option<String>,
    pub revoked_at: Option<String>,
    pub last_used_at: Option<String>,
}

impl From<AccessTokenRow> for AccessToken {
    fn from(t: AccessTokenRow) -> Self {
        AccessToken {
            id: t.id,
            label: t.label,
            issued_at: iso_utc(t.issued_at),
            expires_at: t.expires_at.map(iso_utc),
            revoked_at: t.revoked_at.map(iso_utc),
            last_used_at: t.last_used_at.map(iso_utc),
        }
    }
}

/// `IssuedToken` — `AccessToken` + 원문 `token`(이 응답에서만)
#[derive(Debug, Serialize)]
pub struct IssuedToken {
    #[serde(flatten)]
    pub token: AccessToken,
    #[serde(rename = "token")]
    pub raw: String,
}

/// `UserRef` — `web/schemas/common.py`
#[derive(Debug, Serialize)]
pub struct UserRef {
    pub id: i32,
    pub github_login: String,
    pub display_name: String,
}

impl From<&UserRefDto> for UserRef {
    fn from(u: &UserRefDto) -> Self {
        UserRef {
            id: u.id,
            github_login: u.github_login.clone(),
            display_name: u.display_name.clone(),
        }
    }
}

/// `Author` — 이름 붙은 작성자
#[derive(Debug, Serialize)]
pub struct Author {
    pub kind: String,
    pub user: Option<UserRef>,
    pub instructed_by: Option<UserRef>,
    pub via: String,
}

impl From<&ApiAuthor> for Author {
    fn from(a: &ApiAuthor) -> Self {
        Author {
            kind: a.kind.clone(),
            user: a.user.as_ref().map(UserRef::from),
            instructed_by: a.instructed_by.as_ref().map(UserRef::from),
            via: a.via.clone(),
        }
    }
}

/// `ItemRef` — `web/schemas/common.py`(안쪽 `is_deleted`·`deleted_at`은 내보내지 않는다)
#[derive(Debug, Serialize)]
pub struct ItemRef {
    pub doc_id: Option<String>,
    pub item_id: Option<String>,
    pub display_name: Option<String>,
    pub raw_target: String,
    pub is_missing: bool,
}

impl From<&ItemRefDto> for ItemRef {
    fn from(r: &ItemRefDto) -> Self {
        ItemRef {
            doc_id: r.doc_id.clone(),
            item_id: r.item_id.clone(),
            display_name: r.display_name.clone(),
            raw_target: r.raw_target.clone(),
            is_missing: r.is_missing,
        }
    }
}

/// `DocumentSummary` — `web/schemas/documents.py` (판별 필드 `type`이 맨 앞). 작성자는 읽기 조합이 이름을 붙인 것
#[derive(Debug, Serialize)]
pub struct DocumentSummary {
    #[serde(rename = "type")]
    pub kind: &'static str,
    pub doc_id: String,
    pub doc_type: String,
    pub stage: Option<i32>,
    pub status: String,
    pub current_version_no: i32,
    pub has_convention_error: bool,
    pub incomplete_warnings: Vec<String>,
    pub updated_at: String,
    pub last_author: Option<Author>,
    pub counts: IndexMap<String, i64>,
    pub trashed_at: Option<String>,
}

impl From<&DocumentSummaryDto> for DocumentSummary {
    fn from(d: &DocumentSummaryDto) -> Self {
        DocumentSummary {
            kind: "document",
            doc_id: d.doc_id.clone(),
            doc_type: d.doc_type.clone(),
            stage: d.stage,
            status: d.status.clone(),
            current_version_no: d.current_version_no,
            has_convention_error: d.has_convention_error,
            incomplete_warnings: d.incomplete_warnings.clone(),
            updated_at: iso_utc(d.updated_at),
            last_author: d.author.as_ref().map(Author::from),
            counts: d.counts.clone(),
            trashed_at: d.trashed_at.map(iso_utc),
        }
    }
}

/// `ProjectSummary` — `web/schemas/projects.py`
#[derive(Debug, Serialize)]
pub struct ProjectSummary {
    pub code: String,
    pub name: String,
    pub storage: &'static str,
    pub remote_url: Option<String>,
    pub stages: Vec<StageSummary>,
    pub std_docs: Vec<DocumentSummary>,
    pub counts: IndexMap<String, i64>,
    pub updated_at: Option<String>,
}

impl From<&ProjectSummaryDto> for ProjectSummary {
    fn from(p: &ProjectSummaryDto) -> Self {
        ProjectSummary {
            code: p.code.clone(),
            name: p.name.clone(),
            storage: p.storage.as_str(),
            remote_url: p.remote_url.clone(),
            stages: p.stages.clone(),
            std_docs: p.std_docs.iter().map(DocumentSummary::from).collect(),
            counts: p.counts.clone(),
            updated_at: p.updated_at.map(iso_utc),
        }
    }
}

/// `Document.items[]`
#[derive(Debug, Serialize)]
pub struct DocItem {
    pub item_id: String,
    pub display_name: Option<String>,
    pub missing_refs: Vec<String>,
}

/// `Document` — `DocumentSummary`의 키 뒤에 본문·해시·항목·이웃
#[derive(Debug, Serialize)]
pub struct Document {
    #[serde(flatten)]
    pub summary: DocumentSummary,
    pub body: String,
    pub commit_hash: Option<String>,
    pub convention_error_detail: Option<String>,
    pub items: Vec<DocItem>,
    pub prev_doc_id: Option<String>,
    pub next_doc_id: Option<String>,
    pub missing_refs: Vec<String>,
    pub project_name: String,
}

impl From<&DocumentDto> for Document {
    fn from(d: &DocumentDto) -> Self {
        Document {
            summary: DocumentSummary::from(&d.summary),
            body: d.body.clone(),
            commit_hash: d.commit_hash.clone(),
            convention_error_detail: d.convention_error_detail.clone(),
            items: d
                .items
                .iter()
                .map(|i| DocItem {
                    item_id: i.item_id.clone(),
                    display_name: i.display_name.clone(),
                    missing_refs: i.missing_refs.clone(),
                })
                .collect(),
            prev_doc_id: d.prev_doc_id.clone(),
            next_doc_id: d.next_doc_id.clone(),
            missing_refs: d.missing_refs.clone(),
            project_name: d.project_name.clone(),
        }
    }
}

/// `ItemView` — 항목 블록 (UI-18)
#[derive(Debug, Serialize)]
pub struct ItemView {
    pub doc_id: String,
    pub item_id: String,
    pub display_name: Option<String>,
    pub body: String,
    pub doc_status: String,
    pub doc_version_no: i32,
}

impl From<&ItemViewDto> for ItemView {
    fn from(v: &ItemViewDto) -> Self {
        ItemView {
            doc_id: v.doc_id.clone(),
            item_id: v.item_id.clone(),
            display_name: v.display_name.clone(),
            body: v.body.clone(),
            doc_status: v.doc_status.clone(),
            doc_version_no: v.doc_version_no,
        }
    }
}

/// `ItemReferences`
#[derive(Debug, Serialize)]
pub struct ItemReferences {
    pub doc_id: String,
    pub item_id: String,
    pub upstream: Vec<ItemRef>,
    pub downstream: Vec<ItemRef>,
}

impl From<&ItemReferencesDto> for ItemReferences {
    fn from(r: &ItemReferencesDto) -> Self {
        ItemReferences {
            doc_id: r.doc_id.clone(),
            item_id: r.item_id.clone(),
            upstream: r.upstream.iter().map(ItemRef::from).collect(),
            downstream: r.downstream.iter().map(ItemRef::from).collect(),
        }
    }
}

/// `DiffLine`
#[derive(Debug, Serialize)]
pub struct DiffLine {
    pub op: &'static str,
    pub text: String,
}

/// `Hunk` — 키는 `item_id`·`downstream_count`·`lines` 차례(파이썬 모델의 선언 차례)
#[derive(Debug, Serialize)]
pub struct Hunk {
    pub item_id: Option<String>,
    pub downstream_count: i64,
    pub lines: Vec<DiffLine>,
}

/// `Diff`
#[derive(Debug, Serialize)]
pub struct Diff {
    pub from_version: i32,
    pub to_version: i32,
    pub hunks: Vec<Hunk>,
}

impl From<&DiffDto> for Diff {
    fn from(d: &DiffDto) -> Self {
        use syncdoc_core::types::DiffOp;
        Diff {
            from_version: d.from_version,
            to_version: d.to_version,
            hunks: d
                .hunks
                .iter()
                .map(|h| Hunk {
                    item_id: h.item_id.clone(),
                    downstream_count: h.downstream_count,
                    lines: h
                        .lines
                        .iter()
                        .map(|l| DiffLine {
                            op: match l.op {
                                DiffOp::Add => "add",
                                DiffOp::Del => "del",
                                DiffOp::Ctx => "ctx",
                            },
                            text: l.text.clone(),
                        })
                        .collect(),
                })
                .collect(),
        }
    }
}

/// `ChainItem`
#[derive(Debug, Serialize)]
pub struct ChainItem {
    #[serde(rename = "ref")]
    pub ref_: ItemRef,
    pub role: String,
    pub status: String,
}

/// `ChainRow`
#[derive(Debug, Serialize)]
pub struct ChainRow {
    pub stage: i32,
    pub doc_type: String,
    pub items: Vec<ChainItem>,
}

/// `ItemChain` — 행은 늘 11
#[derive(Debug, Serialize)]
pub struct ItemChain {
    pub item: ItemRef,
    pub upstream_count: i64,
    pub downstream_count: i64,
    pub rows: Vec<ChainRow>,
}

impl From<&ItemChainDto> for ItemChain {
    fn from(c: &ItemChainDto) -> Self {
        ItemChain {
            item: ItemRef::from(&c.item),
            upstream_count: c.upstream_count,
            downstream_count: c.downstream_count,
            rows: c
                .rows
                .iter()
                .map(|r| ChainRow {
                    stage: r.stage,
                    doc_type: r.doc_type.clone(),
                    items: r
                        .items
                        .iter()
                        .map(|i| ChainItem {
                            ref_: ItemRef::from(&i.ref_),
                            role: i.role.clone(),
                            status: i.status.clone(),
                        })
                        .collect(),
                })
                .collect(),
        }
    }
}

/// `Version` — 이력 한 줄
#[derive(Debug, Serialize)]
pub struct Version {
    pub doc_id: String,
    pub version_no: Option<i32>,
    pub commit_hash: String,
    pub message: String,
    pub author: Option<Author>,
    pub created_at: String,
}

impl From<&VersionDto> for Version {
    fn from(v: &VersionDto) -> Self {
        Version {
            doc_id: v.doc_id.clone(),
            version_no: v.version_no,
            commit_hash: v.commit_hash.clone(),
            message: v.message.clone(),
            author: v.author_view.as_ref().map(Author::from),
            created_at: iso_utc(v.created_at),
        }
    }
}

/// `ProjectDetail` — `ProjectSummary`의 키 뒤에 문서·최근 변경·동기화 칸
#[derive(Debug, Serialize)]
pub struct ProjectDetail {
    #[serde(flatten)]
    pub summary: ProjectSummary,
    pub docs: Vec<DocumentSummary>,
    pub recent_changes: Vec<Version>,
    pub last_processed_commit: Option<String>,
    pub behind_by: Option<i32>,
    pub fetched_at: Option<String>,
}

impl From<&ProjectDetailDto> for ProjectDetail {
    fn from(p: &ProjectDetailDto) -> Self {
        ProjectDetail {
            summary: ProjectSummary::from(&p.summary),
            docs: p.docs.iter().map(DocumentSummary::from).collect(),
            recent_changes: p.recent_changes.iter().map(Version::from).collect(),
            last_processed_commit: p.last_processed_commit.clone(),
            behind_by: p.behind_by,
            fetched_at: p.fetched_at.map(iso_utc),
        }
    }
}

/// `Graph` — 노드·간선(간선의 `from`)·브레드크럼 이름
#[derive(Debug, Serialize)]
pub struct Graph {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
    pub project_name: String,
}

impl From<&GraphDto> for Graph {
    fn from(g: &GraphDto) -> Self {
        Graph {
            nodes: g.nodes.clone(),
            edges: g.edges.clone(),
            project_name: g.project_name.clone(),
        }
    }
}

/// `DownstreamDoc`
#[derive(Debug, Serialize)]
pub struct DownstreamDoc {
    pub doc_id: String,
    pub title: String,
    pub items: Vec<String>,
}

/// `DownstreamView` — 키는 도착 항목 ID(문서 단위는 「(문서)」)
#[derive(Debug, Serialize)]
pub struct DownstreamView {
    pub by_item: IndexMap<String, Vec<ItemRef>>,
    pub by_document: Vec<DownstreamDoc>,
}

impl From<&DownstreamDto> for DownstreamView {
    fn from(d: &DownstreamDto) -> Self {
        DownstreamView {
            by_item: d
                .by_item
                .iter()
                .map(|(k, v)| (k.clone(), v.iter().map(ItemRef::from).collect()))
                .collect(),
            by_document: d
                .by_document
                .iter()
                .map(|x| DownstreamDoc {
                    doc_id: x.doc_id.clone(),
                    title: x.title.clone(),
                    items: x.items.clone(),
                })
                .collect(),
        }
    }
}

/// `BrokenRefSummary` — 판별 필드 `type`이 맨 앞
#[derive(Debug, Serialize)]
pub struct BrokenRefSummary {
    #[serde(rename = "type")]
    pub kind: &'static str,
    pub source: ItemRef,
    pub raw_target: String,
}

impl From<&BrokenRefDto> for BrokenRefSummary {
    fn from(b: &BrokenRefDto) -> Self {
        BrokenRefSummary {
            kind: "broken_ref",
            source: ItemRef::from(&b.source),
            raw_target: b.raw_target.clone(),
        }
    }
}

/// `GET …/flags`의 한 행 — 끊어진 참조이거나 문서 요약
#[derive(Debug, Serialize)]
#[serde(untagged)]
pub enum ProjectItemOut {
    Broken(BrokenRefSummary),
    Document(Box<DocumentSummary>),
}

impl From<&ProjectItem> for ProjectItemOut {
    fn from(x: &ProjectItem) -> Self {
        match x {
            ProjectItem::Broken(b) => ProjectItemOut::Broken(BrokenRefSummary::from(b)),
            ProjectItem::Document(d) => {
                ProjectItemOut::Document(Box::new(DocumentSummary::from(&**d)))
            }
        }
    }
}

/// `SaveResult` — 웹 되돌리기·되살리기는 `next_step`이 null
#[derive(Debug, Serialize)]
pub struct SaveResult {
    pub doc_id: String,
    pub version_no: i32,
    pub commit_hash: String,
    pub status: String,
    pub warnings: Vec<String>,
    pub next_step: Option<String>,
}

impl From<&SaveResultDto> for SaveResult {
    fn from(r: &SaveResultDto) -> Self {
        SaveResult {
            doc_id: r.doc_id.clone(),
            version_no: r.version_no,
            commit_hash: r.commit_hash.clone(),
            status: r.status.clone(),
            warnings: r.warnings.clone(),
            next_step: r.next_step.clone(),
        }
    }
}

/// `TrashResult`
#[derive(Debug, Serialize)]
pub struct TrashResult {
    pub doc_id: String,
    pub commit_hash: String,
    pub broken_refs: i64,
    pub next_step: Option<String>,
}

impl From<&TrashResultDto> for TrashResult {
    fn from(r: &TrashResultDto) -> Self {
        TrashResult {
            doc_id: r.doc_id.clone(),
            commit_hash: r.commit_hash.clone(),
            broken_refs: r.broken_refs,
            next_step: Some(r.next_step.clone()),
        }
    }
}

/// `RepoStatus` — UI-14 표 2 (카드 L11)
#[derive(Debug, Serialize)]
pub struct RepoStatus {
    pub code: String,
    pub name: String,
    pub storage: String,
    pub remote_url: Option<String>,
    pub last_processed_commit: Option<String>,
    pub synced_at: Option<String>,
    pub behind_by: Option<i32>,
    pub fetched_at: Option<String>,
    pub error: Option<String>,
    pub hook: String,
    pub hook_error: Option<String>,
}

impl From<&RepoStatusDto> for RepoStatus {
    fn from(r: &RepoStatusDto) -> Self {
        RepoStatus {
            code: r.code.clone(),
            name: r.name.clone(),
            storage: r.storage.clone(),
            remote_url: r.remote_url.clone(),
            last_processed_commit: r.last_processed_commit.clone(),
            synced_at: r.synced_at.map(iso_utc),
            behind_by: r.behind_by,
            fetched_at: r.fetched_at.map(iso_utc),
            error: r.error.clone(),
            hook: r.hook.clone(),
            hook_error: r.hook_error.clone(),
        }
    }
}

/// `RebuildError`
#[derive(Debug, Serialize)]
pub struct RebuildError {
    pub doc_id: String,
    pub detail: String,
}

/// `RebuildResult`
#[derive(Debug, Serialize)]
pub struct RebuildResult {
    pub readme_updated: bool,
    pub docs: i64,
    pub items: i64,
    pub references: i64,
    pub versions: i64,
    pub convention_errors: Vec<RebuildError>,
}

impl From<&RebuildResultDto> for RebuildResult {
    fn from(r: &RebuildResultDto) -> Self {
        RebuildResult {
            readme_updated: r.readme_updated,
            docs: r.docs,
            items: r.items,
            references: r.references,
            versions: r.versions,
            convention_errors: r
                .convention_errors
                .iter()
                .map(|e| RebuildError {
                    doc_id: e.doc_id.clone(),
                    detail: e.detail.clone(),
                })
                .collect(),
        }
    }
}

/// `HookStatus`
#[derive(Debug, Serialize)]
pub struct HookStatus {
    pub hook: String,
    pub hook_error: Option<String>,
    pub created: bool,
}

impl From<&HookStatusDto> for HookStatus {
    fn from(h: &HookStatusDto) -> Self {
        HookStatus {
            hook: h.hook.clone(),
            hook_error: h.hook_error.clone(),
            created: h.created,
        }
    }
}

/// `SyncResult`
#[derive(Debug, Serialize)]
pub struct SyncResult {
    pub docs: i64,
    pub fetched_at: Option<String>,
}

impl From<&SyncResultDto> for SyncResult {
    fn from(r: &SyncResultDto) -> Self {
        SyncResult {
            docs: r.docs,
            fetched_at: r.fetched_at.map(iso_utc),
        }
    }
}

/// `CodeGraphInfo` — 코드 그래프 행의 머리 (`web/schemas/code.py`, 카드 L12)
#[derive(Debug, Serialize)]
pub struct CodeGraphInfo {
    pub commit_hash: Option<String>,
    pub source: Option<String>,
    pub built_at: String,
    pub error: Option<String>,
    pub function_count: i32,
}

impl From<&CodeGraphInfoDto> for CodeGraphInfo {
    fn from(g: &CodeGraphInfoDto) -> Self {
        CodeGraphInfo {
            commit_hash: g.commit_hash.clone(),
            source: g.source.clone(),
            built_at: iso_utc(g.built_at),
            error: g.error.clone(),
            function_count: g.function_count,
        }
    }
}

/// `CodeRef` — 부르는 것·불리는 곳 한 줄
#[derive(Debug, Serialize)]
pub struct CodeRef {
    pub ms_id: String,
    pub qual: Option<String>,
    pub file: Option<String>,
    pub line: Option<i64>,
    pub status: Option<String>,
}

impl From<&CodeRefDto> for CodeRef {
    fn from(r: &CodeRefDto) -> Self {
        CodeRef {
            ms_id: r.ms_id.clone(),
            qual: r.qual.clone(),
            file: r.file.clone(),
            line: r.line,
            status: r.status.clone(),
        }
    }
}

/// `CodeBrief` — 함수 목록 한 줄
#[derive(Debug, Serialize)]
pub struct CodeBrief {
    pub ms_id: String,
    pub qual: Option<String>,
    pub file: Option<String>,
    pub line: Option<i64>,
    pub same: i64,
    pub code_only: i64,
    pub spec_only: i64,
}

impl From<&CodeBriefDto> for CodeBrief {
    fn from(b: &CodeBriefDto) -> Self {
        CodeBrief {
            ms_id: b.ms_id.clone(),
            qual: b.qual.clone(),
            file: b.file.clone(),
            line: b.line,
            same: b.same,
            code_only: b.code_only,
            spec_only: b.spec_only,
        }
    }
}

/// `CodeFunction` — 항목의 함수
#[derive(Debug, Serialize)]
pub struct CodeFunction {
    pub ms_id: String,
    pub qual: String,
    pub file: String,
    pub line: i64,
    pub end: Option<i64>,
    pub calls: Vec<CodeRef>,
    pub callers: Vec<CodeRef>,
}

impl From<&CodeFunctionDto> for CodeFunction {
    fn from(f: &CodeFunctionDto) -> Self {
        CodeFunction {
            ms_id: f.ms_id.clone(),
            qual: f.qual.clone(),
            file: f.file.clone(),
            line: f.line,
            end: f.end,
            calls: f.calls.iter().map(CodeRef::from).collect(),
            callers: f.callers.iter().map(CodeRef::from).collect(),
        }
    }
}

/// `CodeView` — 코드 탭 (UI-5 8.18~8.22)
#[derive(Debug, Serialize)]
pub struct CodeView {
    pub graph: Option<CodeGraphInfo>,
    pub doc_id: String,
    pub item_id: Option<String>,
    pub is_ms: bool,
    pub missing: bool,
    pub function: Option<CodeFunction>,
    pub functions: Vec<CodeBrief>,
}

impl From<&CodeViewDto> for CodeView {
    fn from(v: &CodeViewDto) -> Self {
        CodeView {
            graph: v.graph.as_ref().map(CodeGraphInfo::from),
            doc_id: v.doc_id.clone(),
            item_id: v.item_id.clone(),
            is_ms: v.is_ms,
            missing: v.missing,
            function: v.function.as_ref().map(CodeFunction::from),
            functions: v.functions.iter().map(CodeBrief::from).collect(),
        }
    }
}

/// `CodeText` — 코드 보기 (UI-5 8.21 · UI-17 4.6)
#[derive(Debug, Serialize)]
pub struct CodeText {
    pub path: String,
    pub start: i64,
    pub end: i64,
    pub commit_hash: String,
    pub text: String,
    pub truncated: bool,
}

impl From<&CodeTextDto> for CodeText {
    fn from(t: &CodeTextDto) -> Self {
        CodeText {
            path: t.path.clone(),
            start: t.start,
            end: t.end,
            commit_hash: t.commit_hash.clone(),
            text: t.text.clone(),
            truncated: t.truncated,
        }
    }
}

/// `CodeCallEdge` — 파이썬 `from_`은 `from`으로 나간다
#[derive(Debug, Serialize)]
pub struct CodeCallEdge {
    pub from: String,
    pub to: String,
    pub status: String,
}

/// `CodeCalls` — 관계도 코드 호출 (UI-8 2.6)
#[derive(Debug, Serialize)]
pub struct CodeCalls {
    pub graph: Option<CodeGraphInfo>,
    pub edges: Vec<CodeCallEdge>,
}

impl From<&CodeCallsDto> for CodeCalls {
    fn from(c: &CodeCallsDto) -> Self {
        CodeCalls {
            graph: c.graph.as_ref().map(CodeGraphInfo::from),
            edges: c
                .edges
                .iter()
                .map(|e| CodeCallEdge {
                    from: e.from.clone(),
                    to: e.to.clone(),
                    status: e.status.clone(),
                })
                .collect(),
        }
    }
}

/// `CodeCommunity` — 커뮤니티 하나 (카드 L13)
#[derive(Debug, Serialize)]
pub struct CodeCommunity {
    pub id: i64,
    pub label: String,
    pub size: i64,
}

/// `CodeLayerSpec` — 층 표 명세 칸의 조각
#[derive(Debug, Serialize)]
pub struct CodeLayerSpec {
    #[serde(rename = "ref")]
    pub ref_: Option<String>,
    pub note: String,
}

/// `CodeLayer` — 항목 없는 함수의 층
#[derive(Debug, Serialize)]
pub struct CodeLayer {
    pub name: String,
    pub specs: Vec<CodeLayerSpec>,
}

/// `CodeNode` — 코드 그래프 노드 하나
#[derive(Debug, Serialize)]
pub struct CodeNode {
    pub key: String,
    pub name: String,
    pub qual: String,
    pub file: String,
    pub line: i64,
    pub community: Option<i64>,
    pub item: Option<String>,
    pub ms: Option<String>,
    pub status: Option<String>,
    pub layer: Option<CodeLayer>,
}

/// `CodeNodes` — 코드 그래프 노드 전부 (UI-17)
#[derive(Debug, Serialize)]
pub struct CodeNodes {
    pub graph: Option<CodeGraphInfo>,
    pub communities: Vec<CodeCommunity>,
    pub functions: Vec<CodeNode>,
    pub calls: Vec<[String; 2]>,
}

impl From<&CodeNodesDto> for CodeNodes {
    fn from(n: &CodeNodesDto) -> Self {
        CodeNodes {
            graph: n.graph.as_ref().map(CodeGraphInfo::from),
            communities: n
                .communities
                .iter()
                .map(|c| CodeCommunity {
                    id: c.id,
                    label: c.label.clone(),
                    size: c.size,
                })
                .collect(),
            functions: n
                .functions
                .iter()
                .map(|f| CodeNode {
                    key: f.key.clone(),
                    name: f.name.clone(),
                    qual: f.qual.clone(),
                    file: f.file.clone(),
                    line: f.line,
                    community: f.community,
                    item: f.item.clone(),
                    ms: f.ms.clone(),
                    status: f.status.clone(),
                    layer: f.layer.as_ref().map(|l| CodeLayer {
                        name: l.name.clone(),
                        specs: l
                            .specs
                            .iter()
                            .map(|s| CodeLayerSpec {
                                ref_: s.ref_.clone(),
                                note: s.note.clone(),
                            })
                            .collect(),
                    }),
                })
                .collect(),
            calls: n
                .calls
                .iter()
                .map(|(a, b)| [a.clone(), b.clone()])
                .collect(),
        }
    }
}
