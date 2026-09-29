"""0014_conversations — conversations · turns · attachments (카드 AQ·AR).

SYNC-DOM-003#conversations · #turns · #attachments · SYNC-PRD-001#R11 (2026-09-29 보관 결정).
세 표를 한 리비전에 만든다 — 첨부 행은 AR가 채우지만 표는 대화와 같이 있어야 대화 조회가
한 모양이다.
명세 표를 가리키지 않고 projects·users만 FK. 프로젝트·대화가 지워지면 cascade.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_conversations_project_user", "conversations", ["project_id", "user_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_table(
        "turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "progress", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "context_item_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_turns_conversation_seq"),
    )
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id", sa.Integer(), sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=80), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.LargeBinary(), nullable=False),
        sa.Column("text_cache", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_attachments_conversation", "attachments", ["conversation_id"])
    op.create_index("ix_attachments_turn_id", "attachments", ["turn_id"])
    op.create_index("ix_attachments_user_id", "attachments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_user_id", table_name="attachments")
    op.drop_index("ix_attachments_turn_id", table_name="attachments")
    op.drop_index("ix_attachments_conversation", table_name="attachments")
    op.drop_table("attachments")
    op.drop_table("turns")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_project_user", table_name="conversations")
    op.drop_table("conversations")
