"""0019_traces — traces (카드 CI).

SYNC-DOM-003#traces · SYNC-PRD-001#R17 (2026-10-12 실행 기록 결정 — 프로젝트마다 최근 300개).
projects·users만 가리킨다(명세 표·code_graphs와 선이 없다). record는 기록 도구가 보낸 그대로,
목록에 쓰는 머리는 컬럼에. 같은 (project_id, trace_key)는 하나.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trace_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("method", sa.String(10)),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status", sa.Integer()),
        sa.Column("error", sa.String(300)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ms", sa.Integer(), nullable=False),
        sa.Column("commit_hash", sa.String(40)),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("record", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "trace_key", name="uq_traces_project_key"),
    )
    op.create_index("ix_traces_project_recent", "traces", ["project_id", sa.text("id DESC")])
    op.create_index("ix_traces_user_id", "traces", ["user_id"])


def downgrade() -> None:
    op.drop_table("traces")
