"""SYNC-MS-006 — AccountService. users·access_tokens만. 비밀키는 config.SECRET_KEY(DB 밖)."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime

from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from syncdoc.config import settings
from syncdoc.core.account.models import AccessToken, User
from syncdoc.core.account.repository import AccountRepository
from syncdoc.core.errors import NotFound, Unauthorized
from syncdoc.core.types import IssuedToken


def _fernet() -> Fernet:
    """SECRET_KEY → Fernet 키. SYNC-INFRA-001 5장 — 토큰은 앱 비밀키로 암호화."""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AccountRepository(session)

    def list_tokens(self, user: User) -> list[AccessToken]:
        """SYNC-MS-006#AccountService.list_tokens"""
        return self.repo.tokens_of(user.id)

    def issue_token(self, user: User, label: str) -> IssuedToken:
        """SYNC-MS-006#AccountService.issue_token"""
        raw = "syncdoc_pat_" + secrets.token_urlsafe(32)
        token = AccessToken(
            user_id=user.id,
            token_hash=_sha256(raw),
            label=label,
            issued_at=datetime.now(UTC),
            expires_at=None,
        )
        return IssuedToken(token=self.repo.add_token(token), raw=raw)

    def revoke_token(self, user: User, token_id: int) -> None:
        """SYNC-MS-006#AccountService.revoke_token"""
        t = self.repo.token_of_user(token_id, user.id)
        if t is None:
            raise NotFound("access_token", token_id)
        t.revoked_at = datetime.now(UTC)
        self.session.flush()

    def authenticate_token(self, raw: str) -> User | None:
        """SYNC-MS-006#AccountService.authenticate_token"""
        t = self.repo.token_by_hash(_sha256(raw))
        if t is None or t.revoked_at or (t.expires_at and t.expires_at < datetime.now(UTC)):
            return None
        return self.repo.user_by_id(t.user_id)

    def user_by_login(self, login: str) -> User | None:
        """SYNC-MS-006#AccountService.user_by_login"""
        return self.repo.user_by_login(login)

    def create_placeholder(self, login: str) -> User:
        """SYNC-MS-006#AccountService.create_placeholder"""
        try:
            with self.session.begin_nested():
                return self.repo.add_user(
                    User(
                        github_login=login,
                        github_user_id=None,
                        display_name=login,
                        github_token_encrypted=None,
                    )
                )
        except IntegrityError:
            existing = self.repo.user_by_login(login)
            assert existing is not None
            return existing

    @staticmethod
    def github_token_for(user: User) -> str:
        """SYNC-MS-006#AccountService.github_token_for"""
        if user.github_token_encrypted is None:
            raise Unauthorized("미등록 사용자. 로그인 필요")
        return _fernet().decrypt(user.github_token_encrypted).decode()
