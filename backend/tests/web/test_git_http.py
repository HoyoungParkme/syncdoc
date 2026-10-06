"""SYNC-API-001 3.9 · UC-H21 — 실제 git 클라이언트로 서버 저장소 git 입구를 (카드 BB, SEQ-29).

TestClient로는 git이 붙지 못해 앱을 uvicorn으로 스레드에 띄운다. 그래서 행은 테스트 DB에 **커밋**하고
끝에 지운다(한 DB에 pytest 하나라는 규칙은 그대로다). git은 임시 HOME·빈 전역 설정으로 돌린다 —
사용자의 자격 증명 저장소에 토큰이 남지 않게.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import db
from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.project.service import ProjectService
from app.core.types import Storage
from app.infra import git as infra_git
from tests.core.account.test_service import make_user

CODE = "GITP"
LOGINS = ("gitowner", "gitother")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _git(cwd: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "user.name=t", "-c", "user.email=t@x", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _cleanup() -> None:
    with db.SessionLocal() as s:
        ids = [
            r[0]
            for r in s.execute(
                text("SELECT id FROM users WHERE github_login = ANY(:l)"), {"l": list(LOGINS)}
            )
        ]
        pid = s.execute(text("SELECT id FROM projects WHERE code = :c"), {"c": CODE}).scalar()
        if pid is not None:  # 코드만 push하므로 문서 행은 생기지 않는다
            s.execute(text("DELETE FROM repositories WHERE project_id = :p"), {"p": pid})
            s.execute(text("DELETE FROM projects WHERE id = :p"), {"p": pid})
        if ids:
            s.execute(text("DELETE FROM access_tokens WHERE user_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM users WHERE id = ANY(:i)"), {"i": ids})
        s.commit()


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code_graph_calls: list):
    """앱을 스레드의 uvicorn으로. 서버 저장 프로젝트 GITP(소유자 gitowner)와 토큰 둘."""
    monkeypatch.setattr(settings, "REPOS_DIR", tmp_path / "repos")
    _cleanup()
    from app.main import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    with db.SessionLocal() as s:
        owner = make_user(s, login=LOGINS[0], token=None)
        other = make_user(s, login=LOGINS[1], token=None)
        s.commit()
        acc = AccountService(s)
        tok, other_tok = acc.issue_token(owner, "git").raw, acc.issue_token(other, "git").raw
        s.commit()
        owner_id = owner.id
    try:
        yield {
            "port": port,
            "tok": tok,
            "other_tok": other_tok,
            "owner_id": owner_id,
            "calls": code_graph_calls,
        }
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        _cleanup()


async def test_clone_push_and_processing_over_http(live, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with db.SessionLocal() as s:
        owner = s.get(User, live["owner_id"])
        await ProjectService(s).init_project(None, CODE, "git 시험", owner, storage=Storage.server)
        s.commit()
    base = f"127.0.0.1:{live['port']}/git/{CODE}.git"

    # 소유자 토큰 — clone 되고 골격이 보인다
    work = tmp_path / "work"
    r = _git(tmp_path, home, "clone", "-q", f"http://x:{live['tok']}@{base}", str(work))
    assert r.returncode == 0, r.stderr
    assert (work / "docs" / "specs" / "README.md").exists()

    # 코드를 push — main이 그 커밋이 되고, 응답 뒤 처리가 처리 지점을 옮기고 그래프를 건다
    (work / "app").mkdir()
    (work / "app" / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    _git(work, home, "add", "app/main.py")
    _git(work, home, "commit", "-q", "-m", "code: main")
    r = _git(work, home, "push", "-q", "origin", "HEAD:main")
    assert r.returncode == 0, r.stderr
    head = _git(work, home, "rev-parse", "HEAD").stdout.strip()
    for _ in range(100):
        with db.SessionLocal() as s:
            last = s.execute(
                text(
                    "SELECT r.last_processed_commit FROM repositories r "
                    "JOIN projects p ON p.id = r.project_id WHERE p.code = :c"
                ),
                {"c": CODE},
            ).scalar()
        if last == head and (CODE, head) in live["calls"]:
            break
        time.sleep(0.1)
    assert last == head and (CODE, head) in live["calls"]

    # 작업 브랜치 — 받아 두기만, 처리 지점은 main 그대로
    (work / "app" / "wip.py").write_text("WIP = 1\n", encoding="utf-8")
    _git(work, home, "add", "app/wip.py")
    _git(work, home, "commit", "-q", "-m", "작업 중")
    r = _git(work, home, "push", "-q", "origin", "HEAD:refs/heads/feature")
    assert r.returncode == 0, r.stderr
    time.sleep(0.5)  # 응답 뒤 처리가 돌 틈
    with db.SessionLocal() as s:
        still = s.execute(
            text(
                "SELECT r.last_processed_commit FROM repositories r "
                "JOIN projects p ON p.id = r.project_id WHERE p.code = :c"
            ),
            {"c": CODE},
        ).scalar()
    assert still == head
    _git(work, home, "reset", "-q", "--hard", head)

    # 되감기 push는 저장소가 거절한다
    _git(work, home, "reset", "-q", "--hard", "HEAD~1")
    (work / "other.py").write_text("X = 1\n", encoding="utf-8")
    _git(work, home, "add", "other.py")
    _git(work, home, "commit", "-q", "-m", "갈래")
    r = _git(work, home, "push", "-q", "--force", "origin", "HEAD:main")
    assert r.returncode != 0 and "non-fast-forward" in r.stderr

    # 틀린 토큰 → 인증 실패(git이 다시 묻는데 묻지 못한다) · 남의 토큰 → 없는 것과 같다
    r = _git(tmp_path, home, "clone", "-q", f"http://x:wrong@{base}", str(tmp_path / "w1"))
    assert r.returncode != 0 and ("Authentication failed" in r.stderr or "401" in r.stderr)
    other = f"http://x:{live['other_tok']}@{base}"
    r = _git(tmp_path, home, "clone", "-q", other, str(tmp_path / "w2"))
    assert r.returncode != 0 and ("404" in r.stderr or "not found" in r.stderr.lower())
    # 사용자의 전역 git 설정·자격 증명 저장소를 건드리지 않았다
    assert not (home / ".git-credentials").exists()


async def test_auth_commits_before_streaming(
    live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#318 — 인증이 통과하면 응답 전에 곧바로 커밋한다(SEQ-29 4).

    예전에는 `last_used_at`을 flush만 한 채 응답을 흘려 토큰 행 잠금을 응답 내내 쥐었다. fetch가 곧바로
    잇는 POST가 그 잠금을 이벤트 루프 위에서 기다려 앱 전체가 멈췄다(실물). 세션이 닫힐 때 롤백돼
    사용 흔적도 남지 않았다. 경합은 운이라 **잠금 자체를 본다** — 응답을 흘리는 자리에서 다른 연결이
    토큰 행을 기다리지 않고 잠가 본다.
    """
    home = tmp_path / "home"
    home.mkdir()
    with db.SessionLocal() as s:
        owner = s.get(User, live["owner_id"])
        await ProjectService(s).init_project(None, CODE, "git 시험", owner, storage=Storage.server)
        s.commit()
    held: list[bool] = []
    real = infra_git.http_backend

    async def probe(*args, **kwargs):
        with db.engine.connect() as c:
            try:
                c.execute(
                    text("SELECT 1 FROM access_tokens WHERE user_id = :u FOR UPDATE NOWAIT"),
                    {"u": live["owner_id"]},
                )
                held.append(False)
            except OperationalError:
                held.append(True)
        return await real(*args, **kwargs)

    monkeypatch.setattr(infra_git, "http_backend", probe)
    url = f"http://x:{live['tok']}@127.0.0.1:{live['port']}/git/{CODE}.git"
    r = _git(tmp_path, home, "clone", "-q", url, str(tmp_path / "work"))

    assert r.returncode == 0, r.stderr
    assert held and not any(held), "인증의 잠금을 쥔 채 응답을 흘린다"
    with db.SessionLocal() as s:
        used = s.execute(
            text("SELECT last_used_at FROM access_tokens WHERE user_id = :u"),
            {"u": live["owner_id"]},
        ).scalar()
    assert used is not None, "인증이 커밋하지 않으면 last_used_at이 롤백된다"
