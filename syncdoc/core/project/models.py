"""SYNC-DOM-002 2.1 프로젝트 — Project · Repository.

테이블은 SYNC-DOM-003#projects · #repositories.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from syncdoc.db import Base


class Project(Base):
    """SYNC-DOM-002#Project"""

    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("code ~ '^[A-Z]{1,4}$'", name="ck_projects_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(4), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Repository(Base):
    """SYNC-DOM-002#Repository"""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    remote_url: Mapped[str] = mapped_column(String(300))
    workdir_path: Mapped[str] = mapped_column(String(300))
    last_processed_commit: Mapped[str | None] = mapped_column(String(40))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
