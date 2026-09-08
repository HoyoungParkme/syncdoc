"""테스트 공통. 테스트 DB는 SYNCDOC_TEST_DATABASE_URL (없으면 로컬 5434 컨테이너)."""

import os

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "SYNCDOC_TEST_DATABASE_URL",
        "postgresql+psycopg://syncdoc:syncdoc@localhost:5434/syncdoc_test",
    ),
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from syncdoc.config import settings  # noqa: E402


@pytest.fixture(scope="session")
def _schema() -> None:
    """테스트 DB를 head로. 각 테스트는 트랜잭션 안에서 돌고 롤백된다."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session(_schema: None) -> Session:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        tx = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            tx.rollback()
    engine.dispose()
