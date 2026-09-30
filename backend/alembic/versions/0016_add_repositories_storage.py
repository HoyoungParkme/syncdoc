"""0016_add_repositories_storage — repositories.storage (카드 BA).

SYNC-DOM-003#repositories · SYNC-PRD-001#R14.
저장 방식 github · server. 그때까지의 저장소는 전부 GitHub라 server_default 'github'가 곧 백필이다.
내리기 전에 서버 저장 프로젝트를 해제해야 한다 — 그 행의 remote_url은 서버 안 경로라 뜻이 어긋난다.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("storage", sa.String(length=8), nullable=False, server_default="github"),
    )


def downgrade() -> None:
    op.drop_column("repositories", "storage")
