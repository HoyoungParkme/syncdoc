"""0007_deferrable_version_fks — 재구축이 버전을 갈아 끼우는 동안만 FK 검사를 미룬다.

SYNC-DOM-003#propagation_decisions · SYNC-DOM-003#flags · SYNC-MS-007#pipeline.rebuild · #38.

재구축은 한 트랜잭션 안에서 versions를 지우고 다시 만든다. 그 사이 전파결정과
플래그는 사라진 버전을 가리키고, 트랜잭션 끝에서 새 버전으로 다시 이어진다.
DEFERRABLE이 아니면 DELETE 문 자체가 막혀 재구축이 아예 안 된다.

INITIALLY IMMEDIATE로 둔다 — 평소에는 지금까지와 똑같이 문장마다 검사한다.
재구축만 SET CONSTRAINTS ... DEFERRED로 그 트랜잭션에서 미룬다.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FKS = (
    ("propagation_decisions", "propagation_decisions_version_id_fkey"),
    ("flags", "flags_cause_version_id_fkey"),
)


def upgrade() -> None:
    for table, name in FKS:
        op.execute(f"ALTER TABLE {table} ALTER CONSTRAINT {name} DEFERRABLE INITIALLY IMMEDIATE")


def downgrade() -> None:
    for table, name in FKS:
        op.execute(f"ALTER TABLE {table} ALTER CONSTRAINT {name} NOT DEFERRABLE")
