"""SYNC-API-001 4장 — AccessToken(+발급 응답 token) · 요청 IssueToken."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.web.schemas.common import Base


class AccessToken(Base):
    id: int
    label: str
    issued_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class IssuedToken(AccessToken):
    token: str  # 원문. 이 응답에서만


class IssueToken(BaseModel):
    label: str = Field(max_length=50)
