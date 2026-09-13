"""0009_repositories_fetch_error — 폴링이 실패한 이유를 사람이 볼 수 있게 남긴다.

SYNC-DOM-003#repositories · SYNC-MS-007#scheduler.catch_up · SYNC-MS-001#ProjectService.repo_status · #46.

폴링은 저장소 하나가 죽어도 다음을 계속하고 로그만 남긴다(설계대로다). 그런데 그 실패가
화면에 닿는 길이 없어, 폴링이 죽은 프로젝트는 조용히 멈추고 사람은 "아무도 push를 안
했나 보다"로 읽는다. 성공한 주기가 이 값을 비운다.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("fetch_error", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("repositories", "fetch_error")
