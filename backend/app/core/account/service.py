"""SYNC-MS-006 — AccountService. users·commit_emails·access_tokens만. 비밀키는 config.SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.account.models import AccessToken, CommitEmail, User
from app.core.account.repository import AccountRepository
from app.core.clock import now_utc
from app.core.errors import EmailTaken, NotFound, Unauthorized
from app.core.types import IssuedToken, UserRef
from app.infra import github


def _key(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def _fernet() -> MultiFernet:
    """비밀키 → Fernet. SYNC-INFRA-001 5.1 — 암호화는 새 키로, 복호화는 옛 키도 시도.

    MultiFernet은 첫 키로 암호화하고 복호화는 앞에서부터 차례로 시도한다.
    교체 중에는 SECRET_KEY_OLD를 채워 두고, 재암호화가 끝나면 지운다.
    """
    keys = [_key(settings.SECRET_KEY)]
    if settings.SECRET_KEY_OLD:
        keys.append(_key(settings.SECRET_KEY_OLD))
    return MultiFernet(keys)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AccountRepository(session)

    async def login_github(self, code: str, state: str, redirect_uri: str) -> User:
        """SYNC-MS-006#AccountService.login_github"""
        token = await github.exchange_code(code, redirect_uri)
        info = await github.get_user(token)
        u = self.repo.user_by_github_user_id(info.id)
        if u is not None:
            u.github_login, u.display_name = info.login, info.name
        elif (u := self.repo.placeholder_by_login(info.login)) is not None:
            u.github_user_id, u.display_name = info.id, info.name
        else:
            u = self.repo.add_user(
                User(github_login=info.login, github_user_id=info.id, display_name=info.name)
            )
        u.github_token_encrypted = _fernet().encrypt(token.encode())
        self.session.flush()
        return u

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
            issued_at=now_utc(),
            expires_at=None,  # v1은 만료 없음 (INFRA 9장). 컬럼과 검증 분기는 남긴다
            last_used_at=None,
        )
        return IssuedToken(token=self.repo.add_token(token), raw=raw)

    def revoke_token(self, user: User, token_id: int) -> None:
        """SYNC-MS-006#AccountService.revoke_token"""
        t = self.repo.token_of_user(token_id, user.id)
        if t is None:
            raise NotFound("access_token", token_id)
        t.revoked_at = now_utc()
        self.session.flush()

    def authenticate_token(self, raw: str) -> User | None:
        """SYNC-MS-006#AccountService.authenticate_token"""
        t = self.repo.token_by_hash(_sha256(raw))
        if t is None or t.revoked_at or (t.expires_at and t.expires_at < now_utc()):
            return None
        t.last_used_at = now_utc()  # 통과한 요청만. 만료가 없어 이게 유일한 사용 흔적
        self.session.flush()
        return self.repo.user_by_id(t.user_id)

    def user_by_login(self, login: str) -> User | None:
        """SYNC-MS-006#AccountService.user_by_login"""
        return self.repo.user_by_login(login)

    def users_by_ids(self, ids: list[int]) -> dict[int, UserRef]:
        """SYNC-MS-006#AccountService.users_by_ids"""
        return {
            u.id: UserRef(id=u.id, github_login=u.github_login, display_name=u.display_name)
            for u in self.repo.users_by_ids([i for i in ids if i is not None])
        }

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

    def user_for_commit(self, email: str, login: str) -> User:
        """SYNC-MS-006#AccountService.user_for_commit

        이메일 → login → 자리표시. 순서가 규칙이다 — git 커밋이 남기는 신원 중
        계정으로 이어지는 것은 이메일뿐이고, login은 noreply 메일일 때만 진짜
        아이디이고 아니면 %an 대체값이다(SYNC-DOM-002 5장 결정 3).

        자리표시를 만드는 곳은 여기 하나다. process_commit과 rebuild가 각자
        만들면 판정이 두 경로에서 어긋난다 — 실제로 어긋나 있었다(#34).
        """
        if email and (u := self.repo.user_by_email(email.strip().lower())) is not None:
            return u
        return self.repo.user_by_login(login) or self.create_placeholder(login)

    def commit_emails(self, user: User) -> list[CommitEmail]:
        """SYNC-MS-006#AccountService.commit_emails"""
        return self.repo.emails_of(user.id)

    def add_commit_email(self, user: User, email: str) -> CommitEmail:
        """SYNC-MS-006#AccountService.add_commit_email"""
        e = email.strip().lower()  # git 이메일은 대소문자가 흔들린다
        row = self.repo.email_by_address(e)
        if row is not None:
            if row.user_id == user.id:
                return row  # 멱등 — 두 번 눌러도 오류가 아니다
            raise EmailTaken(e)
        return self.repo.add_email(CommitEmail(user_id=user.id, email=e))

    def remove_commit_email(self, user: User, email_id: int) -> None:
        """SYNC-MS-006#AccountService.remove_commit_email

        남의 것인지 없는 것인지 구분해 알려주지 않는다 — 둘 다 not-found다.
        """
        row = self.repo.email_of_user(email_id, user.id)
        if row is None:
            raise NotFound("commit_email", email_id)
        self.repo.delete_email(row)

    @staticmethod
    def github_token_for(user: User) -> str:
        """SYNC-MS-006#AccountService.github_token_for"""
        if user.github_token_encrypted is None:
            raise Unauthorized("미등록 사용자. 로그인 필요")
        try:
            return _fernet().decrypt(user.github_token_encrypted).decode()
        except InvalidToken as e:
            # 비밀키를 바꿨는데 재암호화를 안 했다. Problem으로 안 바꾸면 평문 500이 나가고
            # git.commit_push의 except Unauthorized도 못 잡는다 (INFRA 5.1)
            raise Unauthorized("토큰을 풀 수 없다. 다시 로그인해야 한다") from e
