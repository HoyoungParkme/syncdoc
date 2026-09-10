"""SYNC-API-001 4장 공통 스키마 — UserRef · User · Author · ItemRef · FlagSummary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.types import ApiAuthor
from app.core.types import FlagSummary as FlagSummaryDto
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


class FlagSummary(Base):
    # 판별 필드 (SYNC-API-001 GET/api/projects/{code}/flags). 클라이언트가 kind로
    # 되짚지 않게 서버가 고정값을 채운다
    type: Literal["flag"] = "flag"
    id: int
    kind: str
    target: ItemRef
    cause: ItemRef | None
    cause_version_no: int | None
    assignee: UserRef | None
    raised_at: datetime
    resolved_at: datetime | None

    @classmethod
    def of(cls, f: FlagSummaryDto) -> FlagSummary:
        return cls.model_validate(f)
