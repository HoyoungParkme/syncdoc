"""SYNC-API-001 4장 — AccessToken(+발급 응답 token) · CommitEmail · 요청 IssueToken·AddEmail."""

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
    last_used_at: datetime | None  # 만료가 없어 안 쓰는 토큰을 찾는 단서 (UI-13 3.5)


class IssuedToken(AccessToken):
    token: str  # 원문. 이 응답에서만


class IssueToken(BaseModel):
    label: str = Field(max_length=50)


class CommitEmail(Base):
    id: int
    email: str
    added_at: datetime


class AddEmail(BaseModel):
    # 최소 형식만 본다. 틀린 이메일은 아무 커밋과도 안 맞아 무해하고, 규칙을 조이면
    # 멀쩡한 주소를 거절한다. 진짜 방어는 commit_emails.email의 유일 제약이다
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
