"""0002_add_versions_via — versions.via varchar(8) not null.

SYNC-DOM-003#versions · SYNC-STD-004#DEV-7.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행은 github로 본다(이 리비전 전엔 웹·MCP 저장이 없었다). 앱이 항상 채우므로 기본값은 뗀다
    op.add_column(
        "versions", sa.Column("via", sa.String(length=8), nullable=False, server_default="github")
    )
    op.alter_column("versions", "via", server_default=None)


def downgrade() -> None:
    op.drop_column("versions", "via")
