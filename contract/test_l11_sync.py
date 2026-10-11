"""카드 L11 — 따라잡기·재구축 (SYNC-SCN-001 S7·S10, UC-G1·G2·S6·A10): 서버 저장소에 진짜 `git push`로 넣은 명세가
문서가 되고(밀린 커밋 처리), 관리 경로 여섯(`/api/admin/repos…`)과 MCP `upload_code`.

두 판에 같은 차례로 push하고, push 뒤 처리(파이썬은 응답 뒤 BackgroundTask, Rust는 따로 띄운 작업)가 끝나기를
처리 지점으로 기다린 뒤 응답 바이트를 파이썬 판의 것(스냅숏 `sync_closed`)과 비교한다. 커밋 해시와 시각만 가린다.
코드는 두 판 차이 시험의 단어와 겹치지 않게 쓴다.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L11")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")
HASH = re.compile(r"\b[0-9a-f]{40}\b")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")
CODE = "LSY"


def masked(reply) -> dict:
    """비교할 꼴 — 커밋 해시와 시각은 판마다 다르다"""
    c = reply.contract()
    c["body"] = STAMP.sub("T", HASH.sub("H", c["body"]))
    return c


def mcp(server, name: str, args: dict):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        ensure_ascii=False,
    ).encode()
    hs = [("Authorization", f"Bearer {token_for(server)}"), ACCEPT, JSON]
    return request(server.port, "POST", "/mcp", hs, body)


def rest(server, method: str, path: str, body=None):
    if body is None:
        return request(server.port, method, path)
    raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
    return request(server.port, method, path, [JSON], raw)


def git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(cwd.parent / "client-gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    r = subprocess.run(
        ["git", "-c", "user.name=밖", "-c", "user.email=out@example.com", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def processed(server) -> str | None:
    rows = json.loads(rest(server, "GET", "/api/admin/repos").body)
    return next(r["last_processed_commit"] for r in rows if r["code"] == CODE)


def push(server, work: Path, message: str) -> str:
    """민 뒤 처리가 끝나기를 처리 지점으로 기다린다(처리되지 않는 커밋이면 그대로 돌아온다)"""
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", message)
    git(work, "push", "-q", "origin", "HEAD:main")
    head = git(work, "rev-parse", "HEAD")
    end = time.monotonic() + 20
    while time.monotonic() < end and processed(server) != head:
        time.sleep(0.2)
    return head


PRD = (
    "---\ndoc_id: LSY-PRD-001\ntype: PRD\ntitle: 따라잡기\nstatus: draft\n---\n# 따라잡기\n\n## 1. 목표\n\n"
    "## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n{r1}\n\n#### R2 둘째 기능\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n"
)
SCN = (
    "---\ndoc_id: LSY-SCN-001\ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LSY-PRD-001]\n---\n"
    "# 시나리오\n\n## 1. 페르소나\n\n## 2. 시나리오\n\n#### S1 흐름\n근거: [[LSY-PRD-001#R1]] · [[LSY-PRD-001#R2]]\n\n## 3. 대응표\n"
)


def write(work: Path, path: str, text: str) -> None:
    f = work / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    """두 판에 같은 차례로 — 프로젝트 → git clone → push 여러 번. 단계마다 읽은 응답을 모은다"""
    done: dict[str, dict] = {}

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        tmp = tmp_path_factory.mktemp(f"l11-{server.target}")
        (tmp / "client-gitconfig").write_text("")
        mcp(server, "init_project", {"storage": "server", "code": CODE, "name": "따라잡기 시험"})
        url = f"http://x:{token_for(server)}@127.0.0.1:{server.port}/git/{CODE}.git"
        work = tmp / "w"
        git(tmp, "clone", "-q", url, str(work))
        # 1. 상위·하위를 한 커밋에 — 상위가 먼저 저장돼 하위의 참조가 미존재가 아니다
        write(work, "docs/specs/02-PRD/LSY-PRD-001.md", PRD.format(r1="설명."))
        write(work, "docs/specs/03-SCN/LSY-SCN-001.md", SCN)
        push(server, work, "spec: PRD·SCN")
        got["after_push_docs"] = rest(server, "GET", f"/api/projects/{CODE}/docs")
        got["after_push_prd"] = rest(server, "GET", "/api/docs/LSY-PRD-001")
        got["after_push_scn"] = rest(server, "GET", "/api/docs/LSY-SCN-001")
        got["after_push_versions"] = rest(server, "GET", "/api/docs/LSY-PRD-001/versions")
        # 2. 고친 커밋 — 판 2, 작성자는 로컬 사용자
        write(work, "docs/specs/02-PRD/LSY-PRD-001.md", PRD.format(r1="고친 설명."))
        push(server, work, "spec: PRD 고침\n\n본문 줄")
        got["edit_versions"] = rest(server, "GET", "/api/docs/LSY-PRD-001/versions")
        got["edit_diff"] = rest(server, "GET", "/api/docs/LSY-PRD-001/diff?from=1&to=2")
        # 3. 완료로 올린 뒤 밖에서 완료 그대로 고침 → 초안과 강등 커밋
        rest(server, "POST", "/api/docs/LSY-PRD-001/status", {"to": "approved"})
        git(work, "pull", "-q", "origin", "main")
        body = (work / "docs/specs/02-PRD/LSY-PRD-001.md").read_text(encoding="utf-8")
        write(
            work,
            "docs/specs/02-PRD/LSY-PRD-001.md",
            body.replace("둘째 기능\n설명.", "둘째 기능\n더 고침."),
        )
        head = push(server, work, "spec: 완료 문서를 밖에서")
        end = time.monotonic() + 20  # 강등 커밋이 처리 지점을 하나 더 민다
        while time.monotonic() < end and processed(server) == head:
            time.sleep(0.2)
        got["demoted_prd"] = rest(server, "GET", "/api/docs/LSY-PRD-001")
        got["demoted_versions"] = rest(server, "GET", "/api/docs/LSY-PRD-001/versions")
        git(work, "pull", "-q", "origin", "main")
        got["demote_commit_subject"] = git(work, "log", "-1", "--format=%s%n%b")
        # 4. 지우기 → 초안·file.deleted·하위 참조 끊김, 되살리기 → 풀린다
        git(work, "rm", "-q", "docs/specs/02-PRD/LSY-PRD-001.md")
        push(server, work, "PRD 지움")
        got["deleted_prd"] = rest(server, "GET", "/api/docs/LSY-PRD-001")
        got["deleted_scn"] = rest(server, "GET", "/api/docs/LSY-SCN-001")
        got["deleted_flags"] = rest(server, "GET", f"/api/projects/{CODE}/flags?kind=broken_ref")
        write(work, "docs/specs/02-PRD/LSY-PRD-001.md", PRD.format(r1="되살림."))
        push(server, work, "PRD 되살림")
        got["restored_prd"] = rest(server, "GET", "/api/docs/LSY-PRD-001")
        got["restored_scn"] = rest(server, "GET", "/api/docs/LSY-SCN-001")
        # 5. 파일 이름·디렉터리가 frontmatter와 다르다 → 저장되고 규약 오류
        write(
            work,
            "docs/specs/04-UC/LSY-UC-007.md",
            "---\ndoc_id: LSY-UC-001\ntype: SCN\ntitle: 이름 어긋남\nstatus: draft\n---\n# 이름\n",
        )
        push(server, work, "이름 어긋남")
        got["mismatch_doc"] = rest(server, "GET", "/api/docs/LSY-UC-007")
        # 6. 관리 경로
        got["admin_repos"] = rest(server, "GET", "/api/admin/repos")
        got["admin_sync"] = rest(server, "POST", f"/api/admin/repos/{CODE}/sync")
        got["admin_hook"] = rest(server, "POST", f"/api/admin/repos/{CODE}/hook")
        got["admin_rebuild"] = rest(server, "POST", f"/api/admin/repos/{CODE}/rebuild")
        got["after_rebuild_versions"] = rest(server, "GET", "/api/docs/LSY-PRD-001/versions")
        got["after_rebuild_docs"] = rest(server, "GET", f"/api/projects/{CODE}/docs")
        # 7. 코드 올리기 — 명세가 아닌 것만, 커밋 하나
        got["upload"] = mcp(
            server,
            "upload_code",
            {
                "project_code": CODE,
                "files": [
                    {"path": "src/a.py", "content": "def f():\n    return 1\n"},
                    {"path": "README.md", "content": "# 코드\n"},
                ],
                "message": "코드 올림",
            },
        )
        got["upload_same"] = mcp(
            server,
            "upload_code",
            {
                "project_code": CODE,
                "files": [{"path": "src/a.py", "content": "def f():\n    return 1\n"}],
                "message": "같은 것",
            },
        )
        got["upload_delete"] = mcp(
            server,
            "upload_code",
            {"project_code": CODE, "files": [], "delete": ["README.md"], "message": "지움"},
        )
        got["upload_repos"] = rest(server, "GET", "/api/admin/repos")
        # 8. 모르는 디렉터리 — 그 파일이 실패해 처리 지점이 멈춘다(사람 실수라 알린다)
        write(work, "docs/specs/BOGUS/LSY-BOGUS-001.md", "x\n")
        git(work, "pull", "-q", "origin", "main")
        before = processed(server)
        push(server, work, "모르는 디렉터리")
        time.sleep(1.5)
        got["bogus_stalls"] = processed(server) == before
        done[server.target] = got
        return got

    return run


FLOW_KEYS = [
    "after_push_docs",
    "after_push_prd",
    "after_push_scn",
    "after_push_versions",
    "edit_versions",
    "edit_diff",
    "demoted_prd",
    "demoted_versions",
    "deleted_prd",
    "deleted_scn",
    "deleted_flags",
    "restored_prd",
    "restored_scn",
    "mismatch_doc",
    "admin_repos",
    "admin_sync",
    "admin_hook",
    "admin_rebuild",
    "after_rebuild_versions",
    "after_rebuild_docs",
    "upload",
    "upload_same",
    "upload_delete",
    "upload_repos",
]


def only_this_project(c: dict) -> dict:
    """관리 목록은 내 프로젝트 전부다 — 같이 도는 다른 시험의 프로젝트를 빼고 이 시험의 것만"""
    rows = [r for r in json.loads(c["body"]) if r["code"] == CODE]
    return {**c, "body": json.dumps(rows, ensure_ascii=False, separators=(",", ":"))}


@pytest.mark.parametrize("key", FLOW_KEYS)
def test_push_flow_replies(server, flow, key):
    got = masked(flow(server)[key])
    if key in ("admin_repos", "upload_repos"):
        got = only_this_project(got)
    check("sync_closed", key, got, server.target)


def test_demotion_commit_and_stall(server, flow):
    got = flow(server)
    assert (
        got["demote_commit_subject"]
        == "status(LSY-PRD-001): approved → draft\n본문 수정으로 자동 강등"
    )
    assert got["bogus_stalls"] is True


CASES = [
    ("rebuild_missing", "POST", "/api/admin/repos/NOPE/rebuild", None),
    ("sync_missing", "POST", "/api/admin/repos/NOPE/sync", None),
    ("hook_missing", "POST", "/api/admin/repos/NOPE/hook", None),
    ("rebuild_get", "GET", f"/api/admin/repos/{CODE}/rebuild", None),
    ("repos_post", "POST", "/api/admin/repos", None),
    ("move_server", "POST", f"/api/admin/repos/{CODE}/move-to-server", None),
    ("move_server_missing", "POST", "/api/admin/repos/NOPE/move-to-server", None),
    (
        "move_github",
        "POST",
        f"/api/admin/repos/{CODE}/move-to-github",
        {"remote_url": "https://github.com/a/b"},
    ),
    ("move_github_missing", "POST", "/api/admin/repos/NOPE/move-to-github", {"remote_url": "x"}),
    ("move_github_empty", "POST", f"/api/admin/repos/{CODE}/move-to-github", {"remote_url": ""}),
    ("move_github_no_body", "POST", f"/api/admin/repos/{CODE}/move-to-github", None),
    ("move_github_not_json", "POST", f"/api/admin/repos/{CODE}/move-to-github", b"{x"),
    ("move_github_number", "POST", f"/api/admin/repos/{CODE}/move-to-github", {"remote_url": 3}),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_admin_edges(server, flow, case):
    flow(server)
    name, method, path, body = case
    check("sync_closed", name, masked(rest(server, method, path, body)), server.target)


UPLOADS = [
    (
        "upload_missing",
        {"project_code": "NOPE", "files": [{"path": "a.py", "content": "x"}], "message": "m"},
    ),
    (
        "upload_refused",
        {
            "project_code": CODE,
            "files": [
                {"path": "/abs.py", "content": "x"},
                {"path": "../up.py", "content": "x"},
                {"path": ".git/config", "content": "x"},
                {"path": "docs/specs/02-PRD/x.md", "content": "x"},
                {"path": "cfg/.env.local", "content": "x"},
                {"path": "keys/Server.PEM", "content": "x"},
                {"path": "a\\b.py", "content": "x"},
                {"path": "bin.dat", "content": "a\u0000b"},
            ],
            "delete": ["  "],
            "message": "m",
        },
    ),
    (
        "upload_too_many",
        {
            "project_code": CODE,
            "files": [{"path": f"f{i}.txt", "content": ""} for i in range(501)],
            "message": "m",
        },
    ),
    ("upload_no_files", {"project_code": CODE, "message": "m"}),
    (
        "upload_dup_paths",
        {
            "project_code": CODE,
            "files": [{"path": "d.txt", "content": "1"}, {"path": "d.txt", "content": "2"}],
            "message": "같은 경로 둘",
        },
    ),
]


@pytest.mark.parametrize("case", UPLOADS, ids=lambda c: c[0])
def test_upload_edges(server, flow, case):
    flow(server)
    name, args = case
    check("sync_closed", name, masked(mcp(server, "upload_code", args)), server.target)
