"""0004_add_repositories_registered_by — repositories.registered_by_user_id.

SYNC-DOM-003#repositories (등록자. 감사용이자 v2 private fetch의 토큰 주인) · SYNC-STD-004#DEV-7.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행은 가장 먼저 만들어진 사용자로 본다. 앱이 항상 채우므로 이후엔 필수
    op.add_column("repositories", sa.Column("registered_by_user_id", sa.Integer(), nullable=True))
    op.execute("UPDATE repositories SET registered_by_user_id = (SELECT min(id) FROM users)")
    op.alter_column("repositories", "registered_by_user_id", nullable=False)
    op.create_foreign_key(
        "fk_repositories_registered_by_user_id_users",
        "repositories",
        "users",
        ["registered_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_repositories_registered_by_user_id", "repositories", ["registered_by_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_repositories_registered_by_user_id", table_name="repositories")
    op.drop_constraint(
        "fk_repositories_registered_by_user_id_users", "repositories", type_="foreignkey"
    )
    op.drop_column("repositories", "registered_by_user_id")
