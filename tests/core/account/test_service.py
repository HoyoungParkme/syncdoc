"""SYNC-MS-006 테스트 관점 — AccountService."""

import pytest
from sqlalchemy.orm import Session

from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService, _fernet
from syncdoc.core.errors import Unauthorized


def make_user(session: Session, login: str = "hoyoung", token: str | None = "gho_x") -> User:
    u = User(
        github_login=login,
        github_user_id=None if token is None else abs(hash(login)) % 10**9,
        display_name=login,
        github_token_encrypted=None if token is None else _fernet().encrypt(token.encode()),
    )
    session.add(u)
    session.flush()
    return u


# ── github_token_for ──
def test_github_token_for_decrypts(db_session: Session) -> None:
    u = make_user(db_session, token="gho_secret")
    assert AccountService.github_token_for(u) == "gho_secret"


def test_github_token_for_placeholder_is_unauthorized(db_session: Session) -> None:
    u = make_user(db_session, login="ghost", token=None)
    with pytest.raises(Unauthorized):
        AccountService.github_token_for(u)
