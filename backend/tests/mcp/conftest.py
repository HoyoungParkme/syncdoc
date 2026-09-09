"""MCP 테스트 — 인증 통과한 사용자 컨텍스트."""

import pytest
from sqlalchemy.orm import Session

from app.mcp import tools
from tests.core.spec.test_service import author


@pytest.fixture
def as_user(scoped: Session):
    a = author(scoped)
    tok = tools.current_user_id.set(a.user.id)
    yield a
    tools.current_user_id.reset(tok)
