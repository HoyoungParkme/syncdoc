"""SYNC-API-001 4장 — DocumentSummary · Document · ItemReferences · UpstreamCheck · ChangeStatus."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.types import Document as DocumentDto
from app.core.types import DocumentSummary as DocumentSummaryDto
from app.core.types import ItemReferences as ItemReferencesDto
from app.core.types import UpstreamCheck as UpstreamCheckDto
from app.web.schemas.common import Author, Base, FlagSummary, ItemRef


class DocumentSummary(Base):
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
        }


class DocItem(Base):
    item_id: str
    display_name: str | None
    flags: list[str]  # kind 문자열 (SYNC-MS-008#queries.document_view 3단계)


class Document(DocumentSummary):
    body: str
    commit_hash: str | None
    convention_error_detail: str | None
    items: list[DocItem]
    prev_doc_id: str | None
    next_doc_id: str | None
    missing_refs: list[str]  # queries.document_view 4a — 유저용 탭 회색 ?

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
        )


class ItemReferences(Base):
    doc_id: str
    item_id: str
    upstream: list[ItemRef]
    downstream: list[ItemRef]
    flags: list[FlagSummary]

    @classmethod
    def of(cls, r: ItemReferencesDto) -> ItemReferences:
        return cls.model_validate(r)


class UpstreamCheck(Base):
    target: ItemRef
    target_version_no: int
    target_status: str
    referenced_from: list[str]

    @classmethod
    def of(cls, u: UpstreamCheckDto) -> UpstreamCheck:
        return cls.model_validate(u)


class ChangeStatus(BaseModel):
    to: str
    reason: str | None = None
    upstream_mismatch: list[str] = []
    upstream_reviewed: bool = False
