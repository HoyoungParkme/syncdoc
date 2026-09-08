"""SYNC-MS-006 테스트 관점 — AccountService."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService, _fernet
from syncdoc.core.errors import NotFound, Unauthorized


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


# ── list_tokens ──
def test_list_tokens_newest_first_including_revoked(db_session: Session) -> None:
    svc = AccountService(db_session)
    u = make_user(db_session)
    a = svc.issue_token(u, "first").token
    b = svc.issue_token(u, "second").token
    svc.revoke_token(u, a.id)
    other = make_user(db_session, login="other")
    svc.issue_token(other, "theirs")
    got = svc.list_tokens(u)
    assert [t.label for t in got] == ["second", "first"]
    assert got[1].revoked_at is not None and got[0].id == b.id


# ── issue_token ──
def test_issue_token_raw_only_in_return_and_authenticates(db_session: Session) -> None:
    svc = AccountService(db_session)
    u = make_user(db_session)
    issued = svc.issue_token(u, "Claude Code 노트북")
    assert issued.raw.startswith("syncdoc_pat_") and len(issued.raw) > 30
    stored = db_session.execute(text("SELECT token_hash, label FROM access_tokens")).all()
    assert stored == [(hashlib.sha256(issued.raw.encode()).hexdigest(), "Claude Code 노트북")]
    assert issued.raw not in str(stored)
    assert issued.token.expires_at is None and issued.token.issued_at is not None
    assert svc.authenticate_token(issued.raw).id == u.id


# ── revoke_token ──
def test_revoke_token_marks_revoked_and_keeps_row(db_session: Session) -> None:
    svc = AccountService(db_session)
    u = make_user(db_session)
    issued = svc.issue_token(u, "x")
    svc.revoke_token(u, issued.token.id)
    assert issued.token.revoked_at is not None
    assert svc.list_tokens(u)[0].id == issued.token.id


def test_revoke_token_of_other_user_is_not_found(db_session: Session) -> None:
    svc = AccountService(db_session)
    u, other = make_user(db_session), make_user(db_session, login="other")
    issued = svc.issue_token(u, "x")
    with pytest.raises(NotFound):
        svc.revoke_token(other, issued.token.id)
    with pytest.raises(NotFound):
        svc.revoke_token(u, 999_999)
    assert issued.token.revoked_at is None


# ── authenticate_token ──
def test_authenticate_token_none_for_revoked_typo_or_expired(db_session: Session) -> None:
    svc = AccountService(db_session)
    u = make_user(db_session)
    issued = svc.issue_token(u, "x")
    assert svc.authenticate_token(issued.raw).id == u.id
    assert svc.authenticate_token(issued.raw[:-1] + "X") is None
    assert svc.authenticate_token("") is None
    svc.revoke_token(u, issued.token.id)
    assert svc.authenticate_token(issued.raw) is None
    expired = svc.issue_token(u, "old")
    expired.token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    assert svc.authenticate_token(expired.raw) is None
    future = svc.issue_token(u, "new")
    future.token.expires_at = datetime.now(UTC) + timedelta(days=1)
    db_session.flush()
    assert svc.authenticate_token(future.raw).id == u.id
