"""SYNC-DOM-002 4.6 — users·commit_emails·access_tokens 조회·저장. DB만 안다."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.account.models import AccessToken, CommitEmail, User


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def user_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def user_by_login(self, login: str) -> User | None:
        return self.session.scalar(select(User).where(User.github_login == login))

    def user_by_github_user_id(self, github_user_id: int) -> User | None:
        return self.session.scalar(select(User).where(User.github_user_id == github_user_id))

    def users_by_ids(self, ids: list[int]) -> list[User]:
        if not ids:
            return []
        return list(self.session.scalars(select(User).where(User.id.in_(ids))))

    def placeholder_by_login(self, login: str) -> User | None:
        return self.session.scalar(
            select(User).where(User.github_login == login, User.github_user_id.is_(None))
        )

    def add_user(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def user_by_email(self, email: str) -> User | None:
        stmt = select(User).join(CommitEmail, CommitEmail.user_id == User.id)
        return self.session.scalar(stmt.where(CommitEmail.email == email))

    def emails_of(self, user_id: int) -> list[CommitEmail]:
        stmt = select(CommitEmail).where(CommitEmail.user_id == user_id)
        return list(self.session.scalars(stmt.order_by(CommitEmail.added_at, CommitEmail.id)))

    def email_by_address(self, email: str) -> CommitEmail | None:
        return self.session.scalar(select(CommitEmail).where(CommitEmail.email == email))

    def email_of_user(self, email_id: int, user_id: int) -> CommitEmail | None:
        return self.session.scalar(
            select(CommitEmail).where(CommitEmail.id == email_id, CommitEmail.user_id == user_id)
        )

    def add_email(self, row: CommitEmail) -> CommitEmail:
        self.session.add(row)
        self.session.flush()
        return row

    def delete_email(self, row: CommitEmail) -> None:
        self.session.delete(row)
        self.session.flush()

    def tokens_of(self, user_id: int) -> list[AccessToken]:
        stmt = (
            select(AccessToken)
            .where(AccessToken.user_id == user_id)
            .order_by(AccessToken.issued_at.desc())
        )
        return list(self.session.scalars(stmt))

    def token_by_hash(self, token_hash: str) -> AccessToken | None:
        return self.session.scalar(select(AccessToken).where(AccessToken.token_hash == token_hash))

    def token_of_user(self, token_id: int, user_id: int) -> AccessToken | None:
        return self.session.scalar(
            select(AccessToken).where(AccessToken.id == token_id, AccessToken.user_id == user_id)
        )

    def add_token(self, token: AccessToken) -> AccessToken:
        self.session.add(token)
        self.session.flush()
        return token
