"""0015_code_graphs — code_graphs (카드 AX).

SYNC-DOM-003#code_graphs · SYNC-PRD-001#R13 (2026-09-30 코드 대조 결정).
프로젝트마다 한 행 — PK가 곧 project_id(FK, cascade). 명세 표를 가리키지 않는다.
graph는 줄인 모양 {functions, calls} — 코드 본문은 없다(저장소에서 읽는다).

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "code_graphs",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("commit_hash", sa.String(40)),
        sa.Column("source", sa.String(10)),
        sa.Column("graph", postgresql.JSONB(), nullable=False),
        sa.Column("function_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(300)),
    )


def downgrade() -> None:
    op.drop_table("code_graphs")
