"""0017_add_users_kind — users.kind (카드 BC).

SYNC-DOM-003#users · SYNC-PRD-001#R15.
사용자 종류 github · local · placeholder. 기본 github로 더하고, github_user_id가 빈 행을
placeholder로 채운다 — 그때까지 자리표시를 github_user_id IS NULL로 가렸으므로 그 판정을 옮긴 것이다.
내리면 칸이 사라져 로컬 사용자 행은 다시 자리표시처럼 보인다.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("kind", sa.String(length=12), nullable=False, server_default="github"),
    )
    op.execute("UPDATE users SET kind = 'placeholder' WHERE github_user_id IS NULL")


def downgrade() -> None:
    op.drop_column("users", "kind")
