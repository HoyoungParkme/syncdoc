"""0011_drop_flags_decisions_comments — 협업 테이블 셋을 지운다 (카드 V).

SYNC-DOM-003 · SYNC-STD-004#DEV-7 · SYNC-RFQ-001#Q6.

한 사람이 프로젝트 하나를 혼자 쓴다. 플래그·전파 결정·댓글은 두세 명이 서로 확인하라고
만든 장치라 걷어냈다. 끊어진 참조는 references.is_missing이 대신한다
(SYNC-MS-003#ReferenceService.mark_missing). status_changes는 남는다 — 휴지통 되살리기와
이력이 쓴다.

downgrade는 **스키마만** 되돌린다 — 0001의 create_table 셋, 0008의 flags.target_version_id,
0007·0008의 DEFERRABLE 셋을 그대로 복원한다. 데이터는 돌아오지 않는다. 옛 행은 태그
`v1-collab`의 import_tracking이 각 저장소 backup/tracking.json에서 읽는다.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFERRABLE = (
    ("propagation_decisions", "propagation_decisions_version_id_fkey"),
    ("flags", "flags_cause_version_id_fkey"),
    ("flags", "flags_target_version_id_fkey"),
)


def upgrade() -> None:
    # 셋 다 다른 표가 참조하지 않는다 — 인덱스는 표와 함께 사라진다
    op.drop_table("comments")
    op.drop_table("propagation_decisions")
    op.drop_table("flags")


def downgrade() -> None:
    # ── 0001 그대로 ──
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("parent_comment_id", sa.Integer(), nullable=True),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("line_hash", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("original_location", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["parent_comment_id"], ["comments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_author_user_id", "comments", ["author_user_id"], unique=False)
    op.create_index(
        "ix_comments_document_id_is_resolved",
        "comments",
        ["document_id", "is_resolved"],
        unique=False,
    )
    op.create_index(
        "ix_comments_parent_comment_id", "comments", ["parent_comment_id"], unique=False
    )
    op.create_table(
        "flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=15), nullable=False),
        sa.Column("target_item_id", sa.Integer(), nullable=False),
        sa.Column("cause_item_id", sa.Integer(), nullable=True),
        sa.Column("cause_version_id", sa.Integer(), nullable=True),
        sa.Column("assignee_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "raised_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_with_edit", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["cause_item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["cause_version_id"], ["versions.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_flags_assignee_user_id_resolved_at",
        "flags",
        ["assignee_user_id", "resolved_at"],
        unique=False,
    )
    op.create_index("ix_flags_cause_item_id", "flags", ["cause_item_id"], unique=False)
    op.create_index("ix_flags_cause_version_id", "flags", ["cause_version_id"], unique=False)
    op.create_index("ix_flags_kind_resolved_at", "flags", ["kind", "resolved_at"], unique=False)
    op.create_index("ix_flags_resolved_by_user_id", "flags", ["resolved_by_user_id"], unique=False)
    op.create_index(
        "ix_flags_target_item_id_resolved_at",
        "flags",
        ["target_item_id", "resolved_at"],
        unique=False,
    )
    op.create_table(
        "propagation_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("choice", sa.String(length=12), nullable=False),
        sa.Column("affected_pks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_pks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id"),
    )
    op.create_index(
        "ix_propagation_decisions_choice_undecided",
        "propagation_decisions",
        ["choice"],
        unique=False,
        postgresql_where="choice = 'undecided'",
    )
    op.create_index(
        "ix_propagation_decisions_decided_by_user_id",
        "propagation_decisions",
        ["decided_by_user_id"],
        unique=False,
    )
    # ── 0008 그대로 ──
    op.add_column("flags", sa.Column("target_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "flags_target_version_id_fkey", "flags", "versions", ["target_version_id"], ["id"]
    )
    op.create_index("ix_flags_target_version_id", "flags", ["target_version_id"])
    # ── 0007·0008 그대로 ──
    for table, name in DEFERRABLE:
        op.execute(f"ALTER TABLE {table} ALTER CONSTRAINT {name} DEFERRABLE INITIALLY IMMEDIATE")
