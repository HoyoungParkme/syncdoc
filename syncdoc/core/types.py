"""SYNC-DOM-002 2.7 열거형 · 2.8 내부 타입(DTO) + API 응답 형태(SYNC-API-001 4장과 같은 이름).

열거형은 DB enum이 아니라 varchar + 앱 검증(SYNC-DOM-003 설계 규칙). 타입은 여기 한 곳에만.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from syncdoc.core.account.models import AccessToken, User


class DocType(StrEnum):
    RFQ = "RFQ"
    PRD = "PRD"
    SCN = "SCN"
    UC = "UC"
    INFRA = "INFRA"
    DOM = "DOM"
    UI = "UI"
    API = "API"
    SEQ = "SEQ"
    MS = "MS"
    CODE = "CODE"
    STD = "STD"


class DocStatus(StrEnum):
    draft = "draft"
    review = "review"
    approved = "approved"


class AuthorKind(StrEnum):
    human = "human"
    agent = "agent"


class FlagKind(StrEnum):
    needs_check = "needs_check"
    broken_ref = "broken_ref"
    upstream_impact = "upstream_impact"


class Propagation(StrEnum):
    propagate = "propagate"
    skip = "skip"
    undecided = "undecided"


class Entry(StrEnum):
    mcp = "mcp"
    web_revert = "web_revert"
    web_status = "web_status"
    github = "github"


def fold_via(entry: Entry) -> str:
    """Author.via → versions.via. web_revert·web_status는 web으로 접는다(DOM-002 2.8)."""
    return "web" if entry in (Entry.web_revert, Entry.web_status) else str(entry)


@dataclass(frozen=True)
class Author:
    kind: AuthorKind
    user: User
    instructed_by: User | None
    via: Entry


@dataclass(frozen=True)
class AuthorRef:
    """SpecService가 돌려주는 작성 주체 — id만. UserRef로 채우는 건 queries."""

    kind: str
    user_id: int
    instructed_by_id: int | None
    via: str


@dataclass
class StageSummary:
    stage: int
    doc_type: str
    status: str | None
    doc_count: int
    gate_warning: bool = False


@dataclass
class ProjectSummary:
    """SYNC-API-001 ProjectSummary. stages는 항상 11개."""

    code: str
    name: str
    remote_url: str
    stages: list[StageSummary]
    std_docs: list[DocumentSummary]
    counts: dict[str, int]
    updated_at: datetime | None


@dataclass
class ProjectDetail(ProjectSummary):
    """SYNC-API-001 ProjectDetail — ProjectSummary + 문서 목록 + 최근 변경(status 커밋 포함)."""

    docs: list[DocumentSummary] = field(default_factory=list)
    recent_changes: list[Version] = field(default_factory=list)


@dataclass(frozen=True)
class RepoStatus:
    """SYNC-API-001 RepoStatus — UI-14 표 2. behind_by=None이면 처리한 커밋이 아직 없다."""

    code: str
    remote_url: str
    last_processed_commit: str | None
    synced_at: datetime | None
    behind_by: int | None


@dataclass
class RebuildResult:
    """SYNC-API-001 RebuildResult."""

    docs: int
    items: int
    references: int
    versions: int
    convention_errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class IssuedToken:
    token: AccessToken
    raw: str


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str  # A | M | D
    commit_hash: str
    author_login: str
    message: str


@dataclass(frozen=True)
class Commit:
    hash: str
    login: str
    date: datetime
    message: str


@dataclass(frozen=True)
class GithubUser:
    id: int
    login: str
    name: str


# 11단계 순서 (SYNC-STD-001 2장). STD는 단계 밖
STAGE_OF: dict[str, int] = {
    t: i + 1
    for i, t in enumerate(
        ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE"]
    )
}


@dataclass(frozen=True)
class Violation:
    line: int
    rule: str
    message: str


@dataclass(frozen=True)
class Warning:
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.message}" if self.message else self.rule


@dataclass(frozen=True)
class ValidateResult:
    violations: list[Violation]
    warnings: list[Warning]


@dataclass(frozen=True)
class ItemBlock:
    item_id: str
    display_name: str
    level: int
    start_line: int
    end_line: int
    text: str


@dataclass
class DocItem:
    """Document.items[] 원소 (SYNC-API-001 Document.items)."""

    pk: int
    item_id: str
    display_name: str | None
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UserRef:
    """SYNC-API-001 UserRef."""

    id: int
    github_login: str
    display_name: str


@dataclass
class ApiAuthor:
    """SYNC-API-001 Author — queries가 AuthorRef를 users_by_ids로 채운 것."""

    kind: str
    user: UserRef | None
    instructed_by: UserRef | None
    via: str


@dataclass
class DocumentSummary:
    """SYNC-API-001 DocumentSummary. counts는 queries가 채운다."""

    id: int
    doc_id: str
    doc_type: str
    stage: int | None
    status: str
    current_version_no: int
    has_convention_error: bool
    incomplete_warnings: list[str]
    updated_at: datetime
    last_author: AuthorRef | None
    counts: dict[str, int] = field(default_factory=dict)
    author: ApiAuthor | None = None  # queries가 채운다 (API Author)


@dataclass
class Document(DocumentSummary):
    """SYNC-API-001 Document. items[].flags·prev/next는 queries.document_view가 붙인다."""

    body: str = ""
    commit_hash: str | None = None  # 최근 버전의 커밋 (API-002 get_document)
    current_version_id: int | None = None  # 최근 versions.id — detect_impact의 prev
    missing_refs: list[str] = field(default_factory=list)  # queries.document_view 4a가 채운다(B4)
    convention_error_detail: str | None = None
    items: list[DocItem] = field(default_factory=list)
    prev_doc_id: str | None = None
    next_doc_id: str | None = None


@dataclass
class ItemView:
    pk: int
    doc_id: str
    item_id: str
    display_name: str | None
    body: str
    doc_status: str
    doc_version_no: int
    flags: list[str] = field(default_factory=list)


@dataclass
class ItemRef:
    """SYNC-API-001 ItemRef. 문서 전체 참조면 item_id=None."""

    doc_id: str | None
    item_id: str | None
    display_name: str | None
    raw_target: str = ""
    is_missing: bool = False
    is_deleted: bool = False
    deleted_at: datetime | None = None  # API에 없음 — flag_view의 cause_deleted_at용(보고)


@dataclass(frozen=True)
class DiffLine:
    op: str  # add | del | ctx
    text: str


@dataclass
class Hunk:
    """SYNC-API-001 Diff.hunks[]. downstream_count는 queries.diff_with_impact가 채운다."""

    item_id: str | None
    lines: list[DiffLine]
    downstream_count: int = 0


@dataclass
class Diff:
    """SYNC-API-001 Diff."""

    from_version: int
    to_version: int
    hunks: list[Hunk]


@dataclass
class Version:
    """SYNC-API-001 Version (DTO) — list_versions·recent_changes. status 커밋이면 version_no=None.

    doc_id는 프로젝트 단위 목록(recent_changes)이 문서를 가리키는 데 쓴다.
    author는 id만(AuthorRef) — 이름은 queries가 users_by_ids로 author_view에 채운다.
    """

    doc_id: str
    version_no: int | None
    commit_hash: str
    message: str
    author: AuthorRef
    created_at: datetime
    author_view: ApiAuthor | None = None


@dataclass(frozen=True)
class ItemBrief:
    """DOM-002 2.8 ItemBrief — list_items_by_project → graph_view. 문서 노드는 item_id=None."""

    pk: int
    doc_id: str
    item_id: str | None
    stage: int | None
    display_name: str | None


@dataclass(frozen=True)
class DocRef:
    """문서 pk → 표시 정보 (describe_documents). 문서 단위 참조 대상·댓글 응답의 doc_id."""

    document_id: int
    doc_id: str
    title: str
    stage: int | None
    status: str


@dataclass(frozen=True)
class VersionBrief:
    """버전 id → 요약 (versions_by_ids). 플래그의 cause_version_no, 미결정 목록."""

    id: int
    document_id: int
    version_no: int
    created_at: datetime
    message: str
    commit_hash: str = ""  # DOM-002 2.8에 없음 — decision_view의 Version용(보고)
    author: AuthorRef | None = None


@dataclass(frozen=True)
class PendingDecision:
    """SYNC-API-001 Todo.pending_decisions[]."""

    version_id: int
    doc_id: str
    version_no: int
    message: str
    affected_count: int
    created_at: datetime


@dataclass
class Todo:
    """SYNC-API-001 Todo — 여섯 묶음 + 담당 미지정. total은 unassigned 제외."""

    needs_check: list[FlagSummary]
    broken_ref: list[FlagSummary]
    upstream_impact: list[FlagSummary]
    pending_decisions: list[PendingDecision]
    convention_errors: list[DocumentSummary]
    unresolved_comments: list[CommentSummary]
    unassigned: list[FlagSummary]
    total: int


@dataclass
class AffectedItem(ItemRef):
    """SYNC-API-001 DecisionDetail.affected[] — ItemRef + 어느 변경 항목의 하위인지 + 담당."""

    caused_by_items: list[str] = field(default_factory=list)
    assignee: UserRef | None = None


@dataclass
class DecisionDetail:
    """SYNC-API-001 DecisionDetail."""

    version: Version
    doc_id: str
    change_diff: Diff
    affected: list[AffectedItem]
    choice: str


@dataclass
class ItemReferences:
    doc_id: str
    item_id: str
    upstream: list[ItemRef]
    downstream: list[ItemRef]
    flags: list[FlagSummary]


@dataclass
class UpstreamCheck:
    target: ItemRef
    target_version_no: int
    target_status: str
    referenced_from: list[str]


@dataclass
class FlagSummary:
    """SYNC-API-001 FlagSummary — Flag 행에 ItemRef·UserRef를 채운 것.

    assignee_id는 API에 없다 — TrackingService.resolve가 돌려줄 때 UserRef는 입구(라우터)가
    users_by_ids로 채운다(AuthorRef→Author와 같은 방식. tracking은 account를 못 부른다, 3.2).
    """

    id: int
    kind: str
    target: ItemRef
    cause: ItemRef | None
    cause_version_no: int | None
    assignee: UserRef | None
    raised_at: datetime
    resolved_at: datetime | None
    assignee_id: int | None = None


@dataclass
class FlagDetail(FlagSummary):
    """SYNC-API-001 FlagDetail — FlagSummary + 원인 diff·내 항목 본문.

    cause_deleted_at(broken_ref)·cause_body(upstream_impact)는 MS-008 flag_view 4·4a에만 있고
    API 스키마에는 없다(보고).
    """

    cause_diff: Diff | None = None
    cause_change_count: int = 0
    target_body: str = ""
    target_version_no: int = 0  # UI-11 3.2 "v7" — 문서 API를 또 부르지 않게 (MS-008 5단계)
    target_changed_since_raise: bool = False
    cause_deleted_at: datetime | None = None
    cause_body: str | None = None


@dataclass(frozen=True)
class DecisionResult:
    """SYNC-DOM-002 2.8 DecisionResult — record_decision."""

    choice: str
    flags_raised: int


@dataclass
class CommentSummary:
    id: int
    doc_id: str
    line_no: int
    excerpt: str
    author: UserRef | None
    created_at: datetime


@dataclass(frozen=True)
class RefEdge:
    from_item_pk: int | None
    to_item_pk: int | None
    to_document_id: int | None
    raw_target: str
    is_missing: bool


@dataclass(frozen=True)
class ExtractResult:
    added: int
    removed: int
    missing: int


@dataclass(frozen=True)
class SaveResult:
    doc_id: str
    version_no: int
    commit_hash: str
    status: str
    pending_decision_version_id: int | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "version_no": self.version_no,
            "commit_hash": self.commit_hash,
            "status": self.status,
            "pending_decision_version_id": self.pending_decision_version_id,
            "warnings": self.warnings,
        }
