"""0018_add_status_changes_via — status_changes.via (카드 BE).

SYNC-DOM-003#status_changes · SYNC-UC-001#UC-H8.
어느 길로 바뀌었나 — web / mcp / github. versions.via와 같은 값이다. 지금까지는 상태를
웹에서만 바꿀 수 있었으므로 옛 행은 전부 web이다. 에이전트가 MCP change_status로 바꾼
행이 mcp가 되고, 이력이 「에이전트 · 지시 {사람}」으로 그린다.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "status_changes",
        sa.Column("via", sa.String(length=8), nullable=False, server_default="web"),
    )


def downgrade() -> None:
    op.drop_column("status_changes", "via")
