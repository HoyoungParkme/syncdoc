"""0005_sync_status_and_token_usage — repositories.behind_by·fetched_at, access_tokens.last_used_at.

SYNC-DOM-003#repositories · SYNC-DOM-003#access_tokens · SYNC-STD-004#DEV-7.

폴링이 뒤처짐을 적고 화면은 읽기만 한다(SYNC-MS-001#ProjectService.repo_status).
토큰은 만료가 없으므로 마지막 사용이 안 쓰는 토큰을 찾는 단서다(SYNC-UI-002 UI-13 3.5).

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 셋 다 null 허용 — 아직 한 번도 재지 않았음을 null로 구분한다
    op.add_column("repositories", sa.Column("behind_by", sa.Integer(), nullable=True))
    op.add_column(
        "repositories", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "access_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("access_tokens", "last_used_at")
    op.drop_column("repositories", "fetched_at")
    op.drop_column("repositories", "behind_by")
