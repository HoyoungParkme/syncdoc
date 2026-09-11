"""SYNC-DOM-002 2.6 계정 — User · CommitEmail · AccessToken. 테이블은 SYNC-DOM-003의 같은 이름."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    """SYNC-DOM-002#User"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_login: Mapped[str] = mapped_column(String(50), unique=True)
    github_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    github_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommitEmail(Base):
    """SYNC-DOM-002#CommitEmail

    User의 컬럼이 아니라 자식이다 — 한 사람이 여럿을 쓰고, email에 유일 제약이
    걸려야 커밋 작성자 판정이 답을 하나로 낸다.
    """

    __tablename__ = "commit_emails"
    __table_args__ = (Index("ix_commit_emails_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # 소문자로 정규화해 저장한다 — git 이메일은 대소문자가 흔들린다
    email: Mapped[str] = mapped_column(String(255), unique=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessToken(Base):
    """SYNC-DOM-002#AccessToken"""

    __tablename__ = "access_tokens"
    __table_args__ = (Index("ix_access_tokens_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(50))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 만료가 없으므로 안 쓰는 토큰을 찾는 단서 (UI-13 3.5). 인증 성공 때만 갱신
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
