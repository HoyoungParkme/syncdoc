"""0001_initial — ERD·DD 테이블 12개 + 인덱스(SYNC-DOM-003 3장) 한 번에. SYNC-STD-004#DEV-7.

Revision ID: 0001
Revises:
Create Date: 2026-09-08 16:05:13.481497
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("code ~ '^[A-Z]{1,4}$'", name="ck_projects_code"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_login", sa.String(length=50), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("github_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_login"),
        sa.UniqueConstraint("github_user_id"),
    )
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_access_tokens_user_id", "access_tokens", ["user_id"], unique=False)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.String(length=30), nullable=False),
        sa.Column("doc_type", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("current_body", sa.Text(), nullable=False),
        sa.Column("current_version_no", sa.Integer(), nullable=False),
        sa.Column(
            "has_convention_error", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("convention_error_detail", sa.Text(), nullable=True),
        sa.Column("incomplete_warnings", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("current_version_no >= 1", name="ck_documents_version_no"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id"),
    )
    op.create_index(
        "ix_documents_has_convention_error",
        "documents",
        ["has_convention_error"],
        unique=False,
        postgresql_where="has_convention_error",
    )
    op.create_index(
        "ix_documents_project_id_doc_type", "documents", ["project_id", "doc_type"], unique=False
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("remote_url", sa.String(length=300), nullable=False),
        sa.Column("workdir_path", sa.String(length=300), nullable=False),
        sa.Column("last_processed_commit", sa.String(length=40), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
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
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_comment_id"],
            ["comments.id"],
        ),
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
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "item_id", name="uq_items_document_id_item_id"),
    )
    op.create_index(
        "ix_items_document_id_is_deleted", "items", ["document_id", "is_deleted"], unique=False
    )
    op.create_table(
        "status_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=10), nullable=True),
        sa.Column("to_status", sa.String(length=10), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("commit_hash", sa.String(length=40), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_status_changes_changed_by_user_id",
        "status_changes",
        ["changed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_status_changes_document_id_changed_at",
        "status_changes",
        ["document_id", "changed_at"],
        unique=False,
    )
    op.create_table(
        "versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("commit_hash", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_kind", sa.String(length=10), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("instructed_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["instructed_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_no", name="uq_versions_document_id_version_no"),
    )
    op.create_index(
        "ix_versions_author_user_id_created_at",
        "versions",
        ["author_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_versions_document_id_version_no_desc",
        "versions",
        ["document_id", sa.literal_column("version_no DESC")],
        unique=False,
    )
    op.create_index(
        "ix_versions_instructed_by_user_id", "versions", ["instructed_by_user_id"], unique=False
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
        sa.ForeignKeyConstraint(
            ["assignee_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["cause_item_id"],
            ["items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["cause_version_id"],
            ["versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_item_id"],
            ["items.id"],
        ),
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
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
        ),
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
    op.create_table(
        "references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_item_id", sa.Integer(), nullable=True),
        sa.Column("from_document_id", sa.Integer(), nullable=False),
        sa.Column("to_item_id", sa.Integer(), nullable=True),
        sa.Column("to_document_id", sa.Integer(), nullable=True),
        sa.Column("raw_target", sa.String(length=100), nullable=False),
        sa.Column("is_missing", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("extracted_version_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(is_missing AND to_item_id IS NULL AND to_document_id IS NULL) OR "
            "(NOT is_missing AND ((to_item_id IS NULL) <> (to_document_id IS NULL)))",
            name="ck_references_target",
        ),
        sa.ForeignKeyConstraint(
            ["extracted_version_id"],
            ["versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["from_document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["from_item_id"],
            ["items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["to_document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["to_item_id"],
            ["items.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_references_extracted_version_id", "references", ["extracted_version_id"], unique=False
    )
    op.create_index(
        "ix_references_from_document_id", "references", ["from_document_id"], unique=False
    )
    op.create_index("ix_references_from_item_id", "references", ["from_item_id"], unique=False)
    op.create_index(
        "ix_references_is_missing",
        "references",
        ["is_missing"],
        unique=False,
        postgresql_where="is_missing",
    )
    op.create_index("ix_references_to_document_id", "references", ["to_document_id"], unique=False)
    op.create_index("ix_references_to_item_id", "references", ["to_item_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_references_to_item_id", table_name="references")
    op.drop_index("ix_references_to_document_id", table_name="references")
    op.drop_index(
        "ix_references_is_missing", table_name="references", postgresql_where="is_missing"
    )
    op.drop_index("ix_references_from_item_id", table_name="references")
    op.drop_index("ix_references_from_document_id", table_name="references")
    op.drop_index("ix_references_extracted_version_id", table_name="references")
    op.drop_table("references")
    op.drop_index("ix_propagation_decisions_decided_by_user_id", table_name="propagation_decisions")
    op.drop_index(
        "ix_propagation_decisions_choice_undecided",
        table_name="propagation_decisions",
        postgresql_where="choice = 'undecided'",
    )
    op.drop_table("propagation_decisions")
    op.drop_index("ix_flags_target_item_id_resolved_at", table_name="flags")
    op.drop_index("ix_flags_resolved_by_user_id", table_name="flags")
    op.drop_index("ix_flags_kind_resolved_at", table_name="flags")
    op.drop_index("ix_flags_cause_version_id", table_name="flags")
    op.drop_index("ix_flags_cause_item_id", table_name="flags")
    op.drop_index("ix_flags_assignee_user_id_resolved_at", table_name="flags")
    op.drop_table("flags")
    op.drop_index("ix_versions_instructed_by_user_id", table_name="versions")
    op.drop_index("ix_versions_document_id_version_no_desc", table_name="versions")
    op.drop_index("ix_versions_author_user_id_created_at", table_name="versions")
    op.drop_table("versions")
    op.drop_index("ix_status_changes_document_id_changed_at", table_name="status_changes")
    op.drop_index("ix_status_changes_changed_by_user_id", table_name="status_changes")
    op.drop_table("status_changes")
    op.drop_index("ix_items_document_id_is_deleted", table_name="items")
    op.drop_table("items")
    op.drop_index("ix_comments_parent_comment_id", table_name="comments")
    op.drop_index("ix_comments_document_id_is_resolved", table_name="comments")
    op.drop_index("ix_comments_author_user_id", table_name="comments")
    op.drop_table("comments")
    op.drop_table("repositories")
    op.drop_index("ix_documents_project_id_doc_type", table_name="documents")
    op.drop_index(
        "ix_documents_has_convention_error",
        table_name="documents",
        postgresql_where="has_convention_error",
    )
    op.drop_table("documents")
    op.drop_index("ix_access_tokens_user_id", table_name="access_tokens")
    op.drop_table("access_tokens")
    op.drop_table("users")
    op.drop_table("projects")
