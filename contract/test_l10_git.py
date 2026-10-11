"""카드 L10 — git 입구 (SYNC-SCN-001 S7 · SYNC-UC-001 UC-H21): `GET /git/{code}.git/info/refs`·
`POST …/git-upload-pack`·`POST …/git-receive-pack`.

두 갈래로 본다.
- 앱이 내는 응답(401 도전·404·405·415·Basic 해석) — 바이트까지 파이썬 판의 것(스냅숏 `git_closed`)과 비교한다
- git 프로토콜 본문 — 광고의 능력 목록·`agent=`가 git 판마다 달라(파이썬 판 이미지 2.47 · 이 기계 · MinGit) 바이트
  비교 밖이다(SYNC-MS-019 「다른 점」). 상태·계약 안 머리만 비교하고, 진짜 git 클라이언트로 clone·push가 되는지 본다
코드는 두 판 차이 시험의 단어와 겹치지 않게 쓴다.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L10")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")
UP = "/git/LGT.git/info/refs?service=git-upload-pack"


def mcp(server, name: str, args: dict) -> dict:
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
    reply = request(server.port, "POST", "/mcp", hs, body)
    data = json.loads(reply.body.decode().split("data: ", 1)[1])
    return json.loads(data["result"]["content"][0]["text"])


@pytest.fixture(scope="module")
def seeded(_servers):
    """두 판에 같은 서버 저장 프로젝트 하나"""
    done = {}

    def seed(server):
        if server.target not in done:
            mcp(server, "init_project", {"storage": "server", "code": "LGT", "name": "깃 입구"})
            done[server.target] = True

    return seed


def basic(raw: str) -> tuple[str, str]:
    return ("Authorization", "Basic " + raw)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def trailing_bits(s: str) -> str:
    """정규 `==` 앞 글자의 남는 네 비트를 1로 — 파이썬 3.12는 받는다"""
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    i = alpha.index(s[-3])
    return s[:-3] + alpha[i | 0b1111] + "=="


def compared(reply) -> dict:
    """참조 광고 본문(능력 목록·`agent=`)은 git 판마다 달라 비교 밖 — 상태와 계약 안 머리만. 나머지는 바이트까지"""
    c = reply.contract()
    if (reply.header("content-type") or "").endswith("-advertisement"):
        c["body"] = None
    return c


def auth(t: str) -> list:
    """맞는 토큰 — 아이디 칸은 아무것이나"""
    return [basic(b64(f"x:{t}"))]


def none(t: str) -> list:
    return []


def header(value):
    """토큰 → `Authorization` 값 그대로"""
    return lambda t: [("Authorization", value(t))]


def rpc(service: str, *extra):
    """맞는 토큰 + 서비스 요청의 Content-Type"""
    return lambda t: [*auth(t), ("Content-Type", f"application/x-git-{service}-request"), *extra]


def typed(content_type: str):
    return lambda t: [*auth(t), ("Content-Type", content_type)]


def refs(query: str, code: str = "LGT") -> str:
    return f"/git/{code}.git/info/refs{query}"


UPLOAD = "/git/LGT.git/git-upload-pack"
RECEIVE = "/git/LGT.git/git-receive-pack"
GZIP = ("Content-Encoding", "gzip")

# (이름, 메서드, 경로, 토큰 → 머리, 본문)
CASES = [
    # 인증 — 비밀번호 칸이 개인 토큰, 아이디 칸은 보지 않는다
    ("refs_no_auth", "GET", UP, none, b""),
    ("refs_bearer", "GET", UP, header(lambda t: f"Bearer {t}"), b""),
    ("refs_basic_garbage", "GET", UP, header(lambda t: "Basic !!!"), b""),
    ("refs_basic_empty", "GET", UP, header(lambda t: "Basic "), b""),
    ("refs_basic_no_colon", "GET", UP, header(lambda t: "Basic " + b64(t)), b""),
    ("refs_basic_empty_token", "GET", UP, header(lambda t: "Basic " + b64("x:")), b""),
    ("refs_wrong_token", "GET", UP, header(lambda t: "Basic " + b64("x:syncdoc_pat_nope")), b""),
    ("refs_ok", "GET", UP, auth, b""),
    ("refs_ok_lower", "GET", UP, header(lambda t: "basic " + b64(f"x:{t}")), b""),
    ("refs_ok_no_user", "GET", UP, header(lambda t: "Basic " + b64(f":{t}")), b""),
    ("refs_colon_in_token", "GET", UP, header(lambda t: "Basic " + b64(f"x:{t}:y")), b""),
    # base64 꼴 — 파이썬 3.12 `b64decode(validate=True)`는 엄격하다: 정규 `=`만, 남는 비트는 받는다.
    # 앞뒤 공백은 파이썬 `str.strip()`(`\xa0`·`\x85`까지) · 비ASCII 글자는 파이썬 판이 못 잡아 500
    ("b64_extra_pad", "GET", UP, header(lambda t: "Basic " + b64(f"x:{t}") + "=="), b""),
    ("b64_one_extra_pad", "GET", UP, header(lambda t: "Basic " + b64(f"x:{t}") + "="), b""),
    ("b64_three_pads", "GET", UP, header(lambda t: "Basic " + b64(f"x:{t}") + "==="), b""),
    ("b64_double_pad", "GET", UP, header(lambda t: "Basic " + b64(f"xyz:{t}") + "="), b""),
    ("b64_no_pad", "GET", UP, header(lambda t: "Basic " + b64(f"xy:{t}").rstrip("=")), b""),
    ("b64_short_pad", "GET", UP, header(lambda t: "Basic " + b64(f"xy:{t}")[:-1]), b""),
    (
        "b64_trailing_bits",
        "GET",
        UP,
        header(lambda t: "Basic " + trailing_bits(b64(f"xy:{t}"))),
        b"",
    ),
    (
        "b64_inner_space",
        "GET",
        UP,
        header(lambda t: "Basic " + b64(f"x:{t}")[:8] + " " + b64(f"x:{t}")[8:]),
        b"",
    ),
    ("b64_urlsafe", "GET", UP, header(lambda t: "Basic " + b64(f"x:{t}") + "-_"), b""),
    ("b64_nbsp", "GET", UP, header(lambda t: "Basic " + b64(f"x:{t}") + "\xa0"), b""),
    ("b64_nel", "GET", UP, header(lambda t: "Basic \x85" + b64(f"x:{t}")), b""),
    ("b64_non_ascii", "GET", UP, header(lambda t: "Basic \xe9"), b""),
    (
        "b64_not_utf8",
        "GET",
        UP,
        header(lambda t: "Basic " + base64.b64encode(b"x:\xff").decode()),
        b"",
    ),
    # 서비스 — 옛 「dumb」 프로토콜은 받지 않는다(인증보다 먼저) · 같은 이름이면 마지막 것
    ("refs_no_service", "GET", refs(""), none, b""),
    ("refs_empty_service", "GET", refs("?service="), none, b""),
    ("refs_other_service", "GET", refs("?service=git-upload-archive"), none, b""),
    ("refs_service_last_wins", "GET", refs("?service=x&service=git-receive-pack"), auth, b""),
    ("refs_service_first_only", "GET", refs("?service=git-upload-pack&service=x"), none, b""),
    ("refs_service_encoded", "GET", refs("?service=git%2Dupload%2Dpack"), auth, b""),
    ("refs_receive", "GET", refs("?service=git-receive-pack"), auth, b""),
    ("refs_v2", "GET", UP, lambda t: [*auth(t), ("Git-Protocol", "version=2")], b""),
    # 프로젝트 — 없는 것·남의 것은 404, 인증이 먼저
    ("refs_missing_project", "GET", refs("?service=git-upload-pack", "NOPE"), auth, b""),
    ("refs_missing_no_auth", "GET", refs("?service=git-upload-pack", "NOPE"), none, b""),
    ("refs_dotted_code", "GET", refs("?service=git-upload-pack", "a.b"), auth, b""),
    ("refs_encoded_dot", "GET", "/git/LGT%2Egit/info/refs?service=git-upload-pack", auth, b""),
    ("refs_double_encoded", "GET", "/git/LGT%252Egit/info/refs?service=git-upload-pack", auth, b""),
    ("refs_korean_code", "GET", refs("?service=git-upload-pack", "%ED%95%9C"), auth, b""),
    # 경로·메서드
    ("git_bare_name", "GET", "/git/LGT/info/refs?service=git-upload-pack", none, b""),
    ("git_other_file", "GET", "/git/LGT.git/HEAD", none, b""),
    ("git_one_segment", "GET", "/git/x", none, b""),
    ("git_root", "GET", "/git", none, b""),
    ("refs_post", "POST", UP, auth, b""),
    ("refs_delete", "DELETE", UP, none, b""),
    ("upload_get", "GET", UPLOAD, none, b""),
    ("receive_put", "PUT", RECEIVE, none, b""),
    # 본문 — http-backend의 415 문장(머리 그대로, latin-1 글자까지), gzip은 `gzip`·`x-gzip`만
    ("upload_no_auth", "POST", UPLOAD, lambda t: rpc("upload-pack")(t)[1:], b"0000"),
    ("upload_no_type", "POST", UPLOAD, auth, b"0000"),
    ("upload_empty_type", "POST", UPLOAD, typed(""), b"0000"),
    ("upload_wrong_type", "POST", UPLOAD, typed("application/x-git-receive-pack-request"), b"0000"),
    (
        "upload_type_params",
        "POST",
        UPLOAD,
        typed("application/x-git-upload-pack-request; a=b"),
        b"",
    ),
    ("upload_type_latin1", "POST", UPLOAD, typed("text/\xe9"), b"0000"),
    ("receive_wrong_type", "POST", RECEIVE, typed("text/plain"), b"0000"),
    ("upload_flush_only", "POST", UPLOAD, rpc("upload-pack"), b"0000"),
    ("upload_empty_body", "POST", UPLOAD, rpc("upload-pack"), b""),
    ("upload_gzip_flush", "POST", UPLOAD, rpc("upload-pack", GZIP), gzip.compress(b"0000")),
    ("upload_gzip_broken", "POST", UPLOAD, rpc("upload-pack", GZIP), b"not gzip at all"),
    ("upload_gzip_cut", "POST", UPLOAD, rpc("upload-pack", GZIP), gzip.compress(b"0000")[:12]),
    ("upload_gzip_empty", "POST", UPLOAD, rpc("upload-pack", GZIP), b""),
    (
        "upload_gzip_trailing",
        "POST",
        UPLOAD,
        rpc("upload-pack", GZIP),
        gzip.compress(b"0000") + b"xx",
    ),
    ("receive_gzip_broken", "POST", RECEIVE, rpc("receive-pack", GZIP), b"not gzip"),
    (
        "upload_gzip_upper",
        "POST",
        UPLOAD,
        rpc("upload-pack", ("Content-Encoding", "GZIP")),
        b"0000",
    ),
    (
        "upload_x_gzip",
        "POST",
        UPLOAD,
        rpc("upload-pack", ("Content-Encoding", "x-gzip")),
        gzip.compress(b"0000"),
    ),  # fmt: skip
    ("receive_flush_only", "POST", RECEIVE, rpc("receive-pack"), b"0000"),
    (
        "receive_missing_project",
        "POST",
        "/git/NOPE.git/git-receive-pack",
        rpc("receive-pack"),
        b"0000",
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_git_entrance_replies(server, seeded, case):
    seeded(server)
    name, method, path, headers, body = case
    reply = request(server.port, method, path, headers(token_for(server)), body)
    got = compared(reply)
    if reply.status == 401:  # 계약 밖 머리지만 없으면 git이 토큰을 묻지 않는다
        assert reply.header("www-authenticate") == 'Basic realm="SyncDoc"'
    check("git_closed", name, got, server.target)


def test_v2_advertisement_has_no_service_line(server, seeded):
    """http-backend는 v2 요청이면 `# service=` 줄을 앞에 붙이지 않는다"""
    seeded(server)
    auth = basic(b64(f"x:{token_for(server)}"))
    v0 = request(server.port, "GET", UP, [auth]).body
    assert v0.startswith(b"001e# service=git-upload-pack\n0000")
    v2 = request(server.port, "GET", UP, [auth, ("Git-Protocol", "version=2")]).body
    assert v2.startswith(b"000eversion 2\n")
    for proto in ("version=20", "xversion=2", "version=1"):
        got = request(server.port, "GET", UP, [auth, ("Git-Protocol", proto)]).body
        assert got.startswith(b"001e# service=git-upload-pack\n0000"), proto
    both = request(server.port, "GET", UP, [auth, ("Git-Protocol", "version=1:version=2")]).body
    assert both.startswith(b"000eversion 2\n")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(cwd / ".." / "client-gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_real_git_clone_and_push(server, seeded, tmp_path):
    """S7 — 진짜 git으로 받고 민다. `main`에 앞으로 미는 것과 다른 가지는 받고, 되감기·지우기는 받지 않는다"""
    seeded(server)
    (tmp_path / "client-gitconfig").write_text("")
    url = f"http://x:{token_for(server)}@127.0.0.1:{server.port}/git/LGT.git"
    work = tmp_path / "w"
    r = git(tmp_path, "clone", "-q", url, str(work))
    assert r.returncode == 0, r.stderr
    assert (work / "docs/specs/README.md").is_file()
    (work / "src").mkdir()
    (work / "src/a.py").write_text("def f():\n    return 1\n")
    git(work, "add", "src/a.py")
    git(work, "commit", "-q", "-m", "코드")
    r = git(work, "push", "-q", "origin", "main")
    assert r.returncode == 0, r.stderr
    r = git(work, "push", "-q", "origin", "main:topic")
    assert r.returncode == 0, r.stderr
    git(work, "reset", "-q", "--hard", "HEAD~1")
    (work / "b.txt").write_text("b")
    git(work, "add", "b.txt")
    git(work, "commit", "-q", "-m", "갈라짐")
    r = git(work, "push", "-q", "--force", "origin", "main")
    assert r.returncode != 0 and "non-fast-forward" in r.stderr, r.stderr
    r = git(work, "push", "-q", "origin", ":topic")
    assert r.returncode != 0 and "deletion prohibited" in r.stderr, r.stderr
    again = tmp_path / "again"
    r = git(tmp_path, "clone", "-q", url, str(again))
    assert r.returncode == 0, r.stderr
    assert (again / "src/a.py").read_text() == "def f():\n    return 1\n"
    heads = git(again, "ls-remote", "--heads", "origin").stdout
    assert sorted(line.split("\t")[1] for line in heads.splitlines()) == [
        "refs/heads/main",
        "refs/heads/topic",
    ]
    r = git(tmp_path, "ls-remote", url.replace(token_for(server), "syncdoc_pat_nope"))
    assert r.returncode != 0
