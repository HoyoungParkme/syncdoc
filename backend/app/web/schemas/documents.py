"""SYNC-API-001 4장 — DocumentSummary · Document · ItemReferences · ChangeStatus · Diff · Chain."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.types import Diff as DiffDto
from app.core.types import Document as DocumentDto
from app.core.types import DocumentSummary as DocumentSummaryDto
from app.core.types import ItemReferences as ItemReferencesDto
from app.web.schemas.common import Author, Base, ItemRef


class DocumentSummary(Base):
    # 판별 필드 (SYNC-API-001 GET/api/projects/{code}/flags). 클라이언트가 kind로
    # 되짚지 않게 서버가 고정값을 채운다
    type: Literal["document"] = "document"
    doc_id: str
    doc_type: str
    stage: int | None
    status: str
    current_version_no: int
    has_convention_error: bool
    incomplete_warnings: list[str]
    updated_at: datetime
    last_author: Author | None
    counts: dict[str, int]
    trashed_at: datetime | None = None  # 휴지통 (카드 R)

    @classmethod
    def of(cls, d: DocumentSummaryDto) -> DocumentSummary:
        return cls(**cls._fields(d))

    @staticmethod
    def _fields(d: DocumentSummaryDto) -> dict:
        return {
            "doc_id": d.doc_id,
            "doc_type": d.doc_type,
            "stage": d.stage,
            "status": d.status,
            "current_version_no": d.current_version_no,
            "has_convention_error": d.has_convention_error,
            "incomplete_warnings": d.incomplete_warnings,
            "updated_at": d.updated_at,
            "last_author": Author.of(d.author),
            "counts": d.counts,
            "trashed_at": d.trashed_at,
        }


class DocItem(Base):
    item_id: str
    display_name: str | None
    missing_refs: list[str]  # 이 항목에서 나간 참조 중 대상이 없는 것의 raw_target (UI-5 6.1 뱃지)


class Document(DocumentSummary):
    body: str
    commit_hash: str | None
    convention_error_detail: str | None
    items: list[DocItem]
    prev_doc_id: str | None
    next_doc_id: str | None
    missing_refs: list[str]  # queries.document_view 4a — 유저용 탭 회색 ?
    project_name: str

    @classmethod
    def of(cls, d: DocumentDto) -> Document:  # type: ignore[override]
        return cls(
            **cls._fields(d),
            body=d.body,
            commit_hash=d.commit_hash,
            convention_error_detail=d.convention_error_detail,
            items=[DocItem.model_validate(i) for i in d.items],
            prev_doc_id=d.prev_doc_id,
            next_doc_id=d.next_doc_id,
            missing_refs=d.missing_refs,
            project_name=d.project_name,
        )


class ItemReferences(Base):
    doc_id: str
    item_id: str
    upstream: list[ItemRef]
    downstream: list[ItemRef]

    @classmethod
    def of(cls, r: ItemReferencesDto) -> ItemReferences:
        return cls.model_validate(r)


class ChangeStatus(BaseModel):
    """POST /api/docs/{docId}/status — 토글 (UC-H8). 상위 대조는 없다 (카드 V)."""

    to: Literal["draft", "approved"]
    reason: str | None = None  # 선택. 이력(UI-7)에 남는다


class DiffLine(Base):
    op: Literal["add", "del", "ctx"]
    text: str


class Hunk(Base):
    item_id: str | None
    downstream_count: int
    lines: list[DiffLine]


class Diff(Base):
    from_version: int
    to_version: int
    hunks: list[Hunk]

    @classmethod
    def of(cls, d: DiffDto | None) -> Diff | None:
        return cls.model_validate(d) if d else None


class ChainItem(Base):
    ref: ItemRef
    role: str
    status: str


class ChainRow(Base):
    stage: int
    doc_type: str
    items: list[ChainItem]


class ItemChain(Base):
    """SYNC-API-001 ItemChain — UI-15. rows는 항상 11개."""

    item: ItemRef
    upstream_count: int
    downstream_count: int
    rows: list[ChainRow]

    @classmethod
    def of(cls, c) -> ItemChain:
        return cls.model_validate(c, from_attributes=True)


class AskTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class AskRequest(BaseModel):
    """POST /api/docs/{docId}/ask — 대화는 클라이언트가 통째로 보낸다. item_id는 힌트다."""

    question: str
    history: list[AskTurn] = []
    item_id: str | None = None


class AskStart(Base):
    """SYNC-API-001 start 이벤트. 이 앞의 오류는 상태 코드, 뒤는 error 이벤트."""

    doc_id: str
    item_id: str | None


class AskNote(Base):
    """SYNC-API-001 note 이벤트 — 모델이 읽기 전에 쓴 한 줄(UI-5 8.9)."""

    text: str


class AskRead(Base):
    """SYNC-API-001 read 이벤트 — 도구 실행이 끝났다."""

    tool: str
    target: str | None


class AskAnswer(Base):
    """SYNC-API-001 answer 이벤트. 저장되지 않는다 — 스트림이 전부다."""

    answer: str
    context_item_ids: list[str]
