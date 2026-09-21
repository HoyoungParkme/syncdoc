"""SYNC-CODE-001#A·V 테스트 — 마이그레이션 up/down.

테이블 10개(0011이 협업 테이블 셋을 지웠다) · 인덱스(DOM-003 3장) · downgrade 후 빈 스키마.
"""

import re

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.config import settings

TABLES = {
    "projects",
    "repositories",
    "documents",
    "items",
    "versions",
    "status_changes",
    "references",
    "users",
    "access_tokens",
    "commit_emails",
}
PARTIAL_INDEXES = {
    "ix_documents_has_convention_error",
    "ix_references_is_missing",
}


@pytest.fixture
def alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def _reset_schema() -> None:
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()


def test_upgrade_creates_10_tables_and_indexes(alembic_cfg: Config) -> None:
    _reset_schema()
    command.upgrade(alembic_cfg, "head")
    engine = create_engine(settings.DATABASE_URL)
    insp = inspect(engine)
    assert set(insp.get_table_names()) - {"alembic_version"} == TABLES
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'")
        )
        defs = {name: d for name, d in rows}
    assert PARTIAL_INDEXES <= set(defs)
    assert all("WHERE" in defs[n] for n in PARTIAL_INDEXES)
    assert "version_no DESC" in defs["ix_versions_document_id_version_no_desc"]
    via = next(c for c in insp.get_columns("versions") if c["name"] == "via")  # 0002
    assert via["nullable"] is False and via["default"] is None
    # FK 컬럼 전부 인덱스(DEV-8): 각 FK의 첫 컬럼이 어떤 인덱스의 선두 컬럼이다
    for table in TABLES:
        leading = {
            re.search(r"\(([^,)]+)", d).group(1).strip()
            for d in defs.values()
            if f" ON public.{table} " in d or f' ON public."{table}" ' in d
        }
        for fk in insp.get_foreign_keys(table):
            assert fk["constrained_columns"][0] in leading, (table, fk["constrained_columns"])
    engine.dispose()


def test_downgrade_removes_everything(alembic_cfg: Config) -> None:
    _reset_schema()
    command.upgrade(alembic_cfg, "head")
    # 0011 왕복 — downgrade가 협업 테이블 셋을 0001·0007·0008 모양 그대로 되살린다 (DEV-7)
    command.downgrade(alembic_cfg, "0010")
    engine = create_engine(settings.DATABASE_URL)
    insp = inspect(engine)
    assert {"flags", "propagation_decisions", "comments"} <= set(insp.get_table_names())
    assert "target_version_id" in {c["name"] for c in insp.get_columns("flags")}
    with engine.connect() as conn:
        deferrable = dict(
            conn.execute(
                text(
                    "SELECT conname, condeferrable FROM pg_constraint WHERE conname IN"
                    " ('propagation_decisions_version_id_fkey', 'flags_cause_version_id_fkey',"
                    " 'flags_target_version_id_fkey')"
                )
            ).all()
        )
    assert deferrable == {
        "propagation_decisions_version_id_fkey": True,
        "flags_cause_version_id_fkey": True,
        "flags_target_version_id_fkey": True,
    }
    engine.dispose()
    command.upgrade(alembic_cfg, "head")
    engine = create_engine(settings.DATABASE_URL)
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == TABLES
    engine.dispose()
    command.downgrade(alembic_cfg, "0001")
    engine = create_engine(settings.DATABASE_URL)
    assert "via" not in {c["name"] for c in inspect(engine).get_columns("versions")}
    engine.dispose()
    command.downgrade(alembic_cfg, "base")
    engine = create_engine(settings.DATABASE_URL)
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == set()
    engine.dispose()
    command.upgrade(alembic_cfg, "head")
