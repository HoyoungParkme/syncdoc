"""web 테스트 — 앱의 DB 세션을 테스트 트랜잭션 세션으로 바꾼다."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from syncdoc.db import get_session
from syncdoc.main import app


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
