"""0010_documents_trashed — 휴지통. 문서를 지우는 대신 표시한다 (카드 R).

SYNC-DOM-003#documents trashed_at·trashed_by_user_id · SYNC-PRD-001#N3 · SYNC-MS-002#SpecService.trash.

카드 N의 하드 삭제는 「이력 없는 초안」에만 열려 있어 실물에서 바로 막혔다. 휴지통은
파일 삭제 커밋 + 이 두 컬럼이 전부다 — 행·버전·항목은 남고 되살리면 돌아온다.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "documents",
        sa.Column("trashed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_documents_trashed_by_user_id", "documents", ["trashed_by_user_id"])  # DEV-8


def downgrade() -> None:
    op.drop_index("ix_documents_trashed_by_user_id", table_name="documents")
    op.drop_column("documents", "trashed_by_user_id")
    op.drop_column("documents", "trashed_at")
