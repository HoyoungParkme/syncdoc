"""엔진·세션. SYNC-DOM-002 1장·6장.

세션은 요청마다 하나. 서비스는 트랜잭션을 열지 않는다(SYNC-STD-004#DEV-10).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from syncdoc.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """요청 하나 = 세션 하나. 라우터 의존성."""
    with SessionLocal() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """pipeline·queries용 — 시그니처에 세션이 없어 스스로 연다. 테스트가 바꿔 끼운다."""
    with SessionLocal() as session:
        yield session
