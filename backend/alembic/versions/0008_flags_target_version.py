"""0008_flags_target_version — 플래그가 부여 시점의 대상 버전을 들고 있게 한다.

SYNC-DOM-003#flags · SYNC-MS-008#queries.flag_view · SYNC-STD-004#DEV-18 · #17.

「플래그를 세운 뒤로 대상이 바뀌었나」를 지금까지 시각으로 판정했다
(`versions.created_at > flags.raised_at`). `datetime.now(UTC)`가 뒤로 갈 수 있어
부여 직후의 버전이 더 옛날로 보였다. 버전 **id**로 견주면 시계가 필요 없다.

FK는 0007과 같은 이유로 DEFERRABLE INITIALLY IMMEDIATE다 — 재구축이 한 트랜잭션
안에서 versions를 지우고 다시 만든다.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "flags_target_version_id_fkey"


def upgrade() -> None:
    op.add_column("flags", sa.Column("target_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(FK, "flags", "versions", ["target_version_id"], ["id"])
    op.execute(f"ALTER TABLE flags ALTER CONSTRAINT {FK} DEFERRABLE INITIALLY IMMEDIATE")
    # FK는 전부 인덱스 (SYNC-DOM-003 3장) — 재연결이 이 열로 훑는다
    op.create_index("ix_flags_target_version_id", "flags", ["target_version_id"])
    # 이미 있던 플래그는 null로 남는다. flag_view가 null을 "바뀌었다고 말할 근거가
    # 없다"로 읽어 False를 준다 (MS-008). 뒤늦게 채우면 없던 인과를 만든다


def downgrade() -> None:
    op.drop_index("ix_flags_target_version_id", table_name="flags")
    op.drop_constraint(FK, "flags", type_="foreignkey")
    op.drop_column("flags", "target_version_id")
