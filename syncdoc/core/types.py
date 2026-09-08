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


@dataclass
class Version:
    """SYNC-API-001 Version (DTO) — list_versions·recent_changes. status 커밋이면 version_no=None.

    doc_id는 API 스키마에 없다 — 프로젝트 단위 목록(recent_changes)이 문서를 가리키려면 필요(보고).
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
    """SYNC-API-001 FlagSummary — queries가 Flag 행에 ItemRef·UserRef를 채운 것."""

    id: int
    kind: str
    target: ItemRef
    cause: ItemRef | None
    cause_version_no: int | None
    assignee: UserRef | None
    raised_at: datetime
    resolved_at: datetime | None


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
