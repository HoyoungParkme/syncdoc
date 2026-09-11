"""0006_commit_emails — 커밋 이메일 테이블.

SYNC-DOM-003#commit_emails · SYNC-DOM-002#CommitEmail · SYNC-STD-004#DEV-7.

git 커밋이 남기는 신원은 이름과 이메일뿐이고 이름은 아무 문자열이라 계정과 못 잇는다.
GitHub 직접 push로 들어온 커밋을 사용자로 잇는 단서가 이메일이다(#34).

데이터는 안 넣는다 — 사람이 UI-13 2.6에서 직접 등록하고 인덱스를 재구축한다.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commit_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # 이메일 하나는 사람 하나여야 user_for_commit이 답을 하나로 낸다
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_commit_emails_user_id", "commit_emails", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_commit_emails_user_id", table_name="commit_emails")
    op.drop_table("commit_emails")
