"""0012_add_projects_owner — projects.owner_user_id (카드 W).

SYNC-DOM-003#projects (등록한 사람이 소유자) · SYNC-PRD-001#R12 · SYNC-STD-004#DEV-7.
기존 행은 저장소 등록자로 채운다 — 실측으로 등록자가 곧 소유자였다(교차 작성 0건).
저장소가 없는 프로젝트(없어야 하지만)는 0004와 같이 가장 먼저 만들어진 사용자.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE projects p SET owner_user_id = COALESCE("
        " (SELECT r.registered_by_user_id FROM repositories r WHERE r.project_id = p.id),"
        " (SELECT min(id) FROM users))"
    )
    op.alter_column("projects", "owner_user_id", nullable=False)
    op.create_foreign_key(
        "fk_projects_owner_user_id_users", "projects", "users", ["owner_user_id"], ["id"]
    )
    op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_owner_user_id", table_name="projects")
    op.drop_constraint("fk_projects_owner_user_id_users", "projects", type_="foreignkey")
    op.drop_column("projects", "owner_user_id")
