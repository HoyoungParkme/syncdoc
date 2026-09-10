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


@pytest.fixture
def mock_github(monkeypatch: pytest.MonkeyPatch):
    """infra/github의 httpx.AsyncClient를 MockTransport로. install(handler) → 요청 기록 list."""
    import httpx  # noqa: E402

    from syncdoc.infra import github as gh  # noqa: E402

    real = httpx.AsyncClient
    calls: list[httpx.Request] = []

    def install(handler):
        def h(req: httpx.Request) -> httpx.Response:
            calls.append(req)
            return handler(req)

        monkeypatch.setattr(
            gh.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(h), **kw)
        )
        return calls

    return install


def github_ok(user_id: int = 42, login: str = "hoyoung", name: str | None = "박호영"):
    """exchange_code → gho_{login}, get_user → {id, login, name} 인 정상 GitHub 핸들러."""
    import httpx  # noqa: E402

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": f"gho_{login}"})
        if req.url.path == "/user":
            return httpx.Response(200, json={"id": user_id, "login": login, "name": name})
        return httpx.Response(404)

    return handler


@pytest.fixture
def scoped(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    """pipeline·queries의 db.session_scope()가 테스트 트랜잭션 세션을 쓰게 한다."""
    from contextlib import contextmanager

    from syncdoc import db

    @contextmanager
    def _scope():
        yield db_session

    monkeypatch.setattr(db, "session_scope", _scope)
    return db_session


# ── git 임시 저장소 픽스처 (infra·project 테스트 공유) ──
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

SEED = "docs/specs/PRD/SYNC-PRD-001.md"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=seed", "-c", "user.email=seed@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_commit_push(repo: Path, path: str, content: str, message: str = "seed") -> str:
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "commit", "-q", "-m", message)
    git(repo, "push", "-q", "origin", "HEAD:main")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, Path]:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    git(other, "checkout", "-q", "-b", "main")
    write_commit_push(other, SEED, "---\ndoc_id: SYNC-PRD-001\n---\n# PRD\n", "seed")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    return {"remote": remote, "work": work, "other": other}


# ── FastAPI TestClient (web·mcp 공유) ──
@pytest.fixture
def client(db_session: Session):
    from fastapi.testclient import TestClient  # noqa: E402

    from syncdoc.db import get_session  # noqa: E402
    from syncdoc.main import app  # noqa: E402

    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
