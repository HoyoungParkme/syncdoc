"""web 테스트 — 세션 로그인 헬퍼(테스트 전용 라우트)와 git 저장소 프로젝트 픽스처."""

from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from syncdoc.core.account.models import User
from syncdoc.core.account.service import AccountService
from syncdoc.db import get_session
from syncdoc.main import app
from syncdoc.web import auth
from tests.core.account.test_service import make_user
from tests.core.test_pipeline import proj  # noqa: F401 — 픽스처 재사용


@app.get("/__test/login/{login}", status_code=204)
def _test_login(login: str, request: Request, session: Session = Depends(get_session)) -> None:
    user = AccountService(session).user_by_login(login)
    assert user is not None
    auth.login(request, user)


@app.get("/__test/whoami")
def _test_whoami(user: User = Depends(auth.current_user)) -> dict[str, str]:
    return {"login": user.github_login}


def login(client: TestClient, db_session: Session, login: str = "hoyoung") -> User:
    """User 행을 만들고(없으면) 세션 쿠키를 얻는다."""
    user = AccountService(db_session).user_by_login(login) or make_user(db_session, login=login)
    assert client.get(f"/__test/login/{login}").status_code == 204
    return user
