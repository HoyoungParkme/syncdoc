"""테스트 공통. 테스트 DB는 SYNCDOC_TEST_DATABASE_URL (없으면 로컬 5434 컨테이너)."""

import os

# **setdefault가 아니라 덮어쓴다.** setdefault면 셸에 DATABASE_URL이 떠 있을 때 테스트가
# 그 DB에서 돈다 — 저장소 `.env`는 개발 DB(5432)를 가리키고, 그 DB는 도커로 띄운 앱과
# 폴링이 같이 쓴다. 테스트가 만든 사용자 행이 남의 트랜잭션에 밀려 사라지면 웹 라우트가
# 401을 낸다. 실패하는 테스트가 매번 달라지는 것도 그래서다 (#17).
# 의도적으로 다른 DB를 쓰려면 SYNCDOC_TEST_DATABASE_URL로 말한다.
os.environ["DATABASE_URL"] = os.environ.get(
    "SYNCDOC_TEST_DATABASE_URL",
    "postgresql+psycopg://syncdoc:syncdoc@localhost:5434/syncdoc_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ["POLL_INTERVAL_SECONDS"] = "0"  # 폴링·기동 따라잡기를 끈다. 배경 작업이 세션을 함께 쓴다

# 테스트 DB가 아닌 곳을 가리키면 시작하지 않는다. 스키마를 지우고 다시 만드는 픽스처가
# 개발·운영 DB에 닿으면 그 데이터가 사라진다
if "test" not in os.environ["DATABASE_URL"].rsplit("/", 1)[-1]:
    raise SystemExit(
        f"테스트 DB가 아닙니다: {os.environ['DATABASE_URL']}\n"
        "SYNCDOC_TEST_DATABASE_URL로 테스트 DB를 지정하세요 (이름에 'test'가 들어가야 합니다)."
    )

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(scope="session")
def _schema() -> None:
    """테스트 DB를 head로. 각 테스트는 트랜잭션 안에서 돌고 롤백된다."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session(_schema: None) -> Session:
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            session = Session(bind=conn, join_transaction_mode="create_savepoint")
            try:
                yield session
            finally:
                session.close()
                tx.rollback()
    finally:
        # dispose를 try 밖에 두면 **테스트가 실패했을 때 건너뛴다** — 예외가 yield로
        # 올라오기 때문이다. 그러면 엔진과 풀의 연결이 GC 전까지 남아, 한 번 실패한
        # 뒤로는 실행 환경이 달라진다. 간헐 실패를 재는 통계가 오염된다 (#17)
        engine.dispose()


@pytest.fixture
def mock_github(monkeypatch: pytest.MonkeyPatch):
    """infra/github의 httpx.AsyncClient를 MockTransport로. install(handler) → 요청 기록 list."""
    import httpx  # noqa: E402

    from app.infra import github as gh  # noqa: E402

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

    from app import db

    @contextmanager
    def _scope():
        yield db_session

    monkeypatch.setattr(db, "session_scope", _scope)
    return db_session


@pytest.fixture(autouse=True)
def _fresh_repo_locks():
    """저장소 락(pipeline의 asyncio.Lock)은 모듈 전역인데 이벤트 루프는 테스트마다 새로 생긴다.
    앞 테스트가 경합으로 락을 자기 루프에 묶어 두면, 다음 테스트가 경합할 때 RuntimeError가 나고
    락이 잡힌 채 남아 뒤 테스트가 멈춘다 — 테스트마다 비운다 (#194, 운영은 루프가 하나다)."""
    from app.core import pipeline

    pipeline._locks.clear()
    pipeline._read_locks.clear()
    yield


@pytest.fixture(autouse=True)
def code_graph_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """코드 그래프 만들기(카드 AX)는 백그라운드에서 graphify를 돌린다 — 테스트에서는 걸기만 적는다.

    process_commit·rebuild를 부르는 테스트가 수십 개라 전부 추출이 돌면 느리고 루프를 넘어 새어
    나간다. 걸렸는지는 이 목록으로 보고, 만들기 자체는 build_code_graph를 직접 불러 시험한다.
    진짜 schedule_code_graph는 테스트 모듈이 임포트할 때 쥐어 둔 것을 쓴다.
    """
    from app.core import pipeline

    calls: list[tuple[str, str]] = []
    pipeline._graph_tasks.clear()
    pipeline._graph_next.clear()
    monkeypatch.setattr(
        pipeline, "schedule_code_graph", lambda code, commit: calls.append((code, commit))
    )
    return calls


# ── git 임시 저장소 픽스처 (infra·project 테스트 공유) ──
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

SEED = "docs/specs/02-PRD/SYNC-PRD-001.md"


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
def _client(db_session: Session, raise_server_exceptions: bool):
    """TestClient 하나. **동시에 둘을 열지 않는다** — 전역 app의 lifespan이 두 번
    드나들면서 MCP 세션 매니저의 태스크 그룹이 안쪽 클라이언트 퇴장에 취소된다 (#17)."""
    from fastapi.testclient import TestClient  # noqa: E402

    from app.db import get_session  # noqa: E402
    from app.main import app  # noqa: E402

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app, raise_server_exceptions=raise_server_exceptions) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(db_session: Session):
    yield from _client(db_session, raise_server_exceptions=True)


@pytest.fixture
def client_raw(db_session: Session):
    """서버 예외를 다시 던지지 않는 클라이언트 — 실제 problem+json 응답을 봐야 할 때."""
    yield from _client(db_session, raise_server_exceptions=False)
