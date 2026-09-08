"""0003_add_versions_message — versions.message text not null.

SYNC-DOM-003#versions (커밋 메시지 전문 사본 — 이력·최근 변경을 DB만으로) · SYNC-STD-004#DEV-7.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행은 빈 메시지. 앱이 항상 채우므로 기본값은 뗀다 (0002와 같은 방식)
    op.add_column("versions", sa.Column("message", sa.Text(), nullable=False, server_default=""))
    op.alter_column("versions", "message", server_default=None)


def downgrade() -> None:
    op.drop_column("versions", "message")
