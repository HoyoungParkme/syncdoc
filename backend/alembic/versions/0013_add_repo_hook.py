"""0013_add_repo_hook — repositories.hook_id · hook_error (카드 AF).

SYNC-DOM-003#repositories · SYNC-INFRA-001 7장 · #115.
둘 다 nullable로 더한다 — 비어 있는 것이 「아직 안 걸어 봤다」는 맞는 초기 상태다.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("hook_id", sa.Integer(), nullable=True))
    op.add_column("repositories", sa.Column("hook_error", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("repositories", "hook_error")
    op.drop_column("repositories", "hook_id")
