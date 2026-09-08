"""SYNC-MS-006 — AccountService. users·access_tokens만. 비밀키는 config.SECRET_KEY(DB 밖)."""

import base64
import hashlib

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from syncdoc.config import settings
from syncdoc.core.account.models import User
from syncdoc.core.account.repository import AccountRepository
from syncdoc.core.errors import Unauthorized


def _fernet() -> Fernet:
    """SECRET_KEY → Fernet 키. SYNC-INFRA-001 5장 — 토큰은 앱 비밀키로 암호화."""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class AccountService:
    def __init__(self, session: Session) -> None:
        self.repo = AccountRepository(session)

    @staticmethod
    def github_token_for(user: User) -> str:
        """SYNC-MS-006#AccountService.github_token_for"""
        if user.github_token_encrypted is None:
            raise Unauthorized("미등록 사용자. 로그인 필요")
        return _fernet().decrypt(user.github_token_encrypted).decode()
