"""SYNC-API-001 4장 공통 스키마 — UserRef · User · Author · ItemRef · BrokenRefSummary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.types import ApiAuthor
from app.core.types import BrokenRefSummary as BrokenRefSummaryDto
from app.core.types import ItemRef as ItemRefDto


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRef(Base):
    id: int
    github_login: str
    display_name: str


class User(UserRef):
    created_at: datetime


class Author(Base):
    kind: str
    user: UserRef | None
    instructed_by: UserRef | None
    via: str

    @classmethod
    def of(cls, a: ApiAuthor | None) -> Author | None:
        return cls.model_validate(a) if a else None


class ItemRef(Base):
    doc_id: str | None
    item_id: str | None
    display_name: str | None
    raw_target: str = ""
    is_missing: bool = False

    @classmethod
    def of(cls, r: ItemRefDto | None) -> ItemRef | None:
        return cls.model_validate(r) if r else None


class BrokenRefSummary(Base):
    """SYNC-API-001 BrokenRefSummary — 대상이 없는 참조 하나. UI-4 다이얼로그 6의 행.

    판별 필드 type (GET/api/projects/{code}/flags) — 클라이언트가 kind로 되짚지 않게 서버가 채운다.
    """

    type: Literal["broken_ref"] = "broken_ref"
    source: ItemRef  # 참조하는 쪽 — 이 프로젝트의 항목. 항목 밖 참조면 item_id=None
    raw_target: str

    @classmethod
    def of(cls, b: BrokenRefSummaryDto) -> BrokenRefSummary:
        return cls.model_validate(b)
