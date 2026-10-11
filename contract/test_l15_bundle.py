"""카드 L15 — 번들로 가져오기 (SYNC-UC-001 UC-A1 1c, 파이썬 판 카드 BX): `POST /api/projects/bundle`.

같은 번들(시험이 git으로 묶는다 — 작성자·시각을 고정해 해시가 늘 같다)을 두 판에 같은 차례로 올리고, 응답과
가져온 뒤의 프로젝트·문서·판 목록을 파이썬 판의 것(스냅숏 `bundle_closed`)과 비교한다. 폼 오류(빠진 칸·형식·
글자/파일 바꿈·urlencoded·JSON·경계 없음·깨진 multipart)와 `{code}` 경로의 405·404도 바이트로 같다. 시각만 가린다.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L15")

STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")
JSON = ("Content-Type", "application/json")
BOUNDARY = "----syncdoc-l15"
PRD = (
    "---\ndoc_id: {code}-PRD-001\ntype: PRD\ntitle: 번들 대조\nstatus: {status}\n---\n# 번들 대조\n\n## 1. 목표\n\n"
    "## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n첫 기능을 설명한다.\n\n## 4. 성공지표\n\n## 5. 미결사항\n"
)


def masked(reply) -> dict:
    c = reply.contract()
    c["body"] = STAMP.sub("T", c["body"])
    return c


def git(cwd: Path, *args: str, when: str = "2026-10-01T09:00:00+00:00") -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
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


def make_bundle(tmp: Path, code: str, branch: str = "main") -> bytes:
    """명세 두 커밋(초안 → 승인)과 태그가 든 저장소의 번들 — 파이썬 판 시험 `_bundle`과 같은 꼴"""
    src = tmp / f"src-{code}-{branch}"
    src.mkdir()
    git(src, "init", "-q", "-b", branch)
    doc = src / f"docs/specs/02-PRD/{code}-PRD-001.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(PRD.format(code=code, status="draft"), encoding="utf-8")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", f"spec({code}-PRD-001): 초안")
    doc.write_text(PRD.format(code=code, status="approved"), encoding="utf-8")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", f"status({code}-PRD-001): draft → approved", when="2026-10-01T10:00:00+00:00")
    git(src, "tag", "v1")
    out = tmp / f"{code}-{branch}.bundle"
    git(src, "bundle", "create", "-q", str(out), "--all")
    return out.read_bytes()


def form(*parts: tuple[str, bytes, str | None, str | None]) -> tuple[list, bytes]:
    """multipart 본문 — (이름, 값, 파일 이름, 종류)"""
    body = b""
    for name, value, filename, ctype in parts:
        disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename is not None else "")
        head = f"--{BOUNDARY}\r\nContent-Disposition: {disp}\r\n"
        if ctype:
            head += f"Content-Type: {ctype}\r\n"
        body += head.encode() + b"\r\n" + value + b"\r\n"
    body += f"--{BOUNDARY}--\r\n".encode()
    return [("Content-Type", f"multipart/form-data; boundary={BOUNDARY}")], body


def bundle_part(data: bytes, filename: str = "x.bundle") -> tuple[str, bytes, str | None, str | None]:
    return ("bundle", data, filename, "application/octet-stream")


def post(server, headers: list, body: bytes, path: str = "/api/projects/bundle"):
    return request(server.port, "POST", path, headers, body)


def only_lb(reply):
    """목록에서 이 시험의 프로젝트(LB…)만 — 다른 모듈이 같은 서버에 만든 것은 실행 조합마다 다르다"""
    rows = [p for p in json.loads(reply.body) if p["code"].startswith("LB")]
    reply.body = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    return reply


def rest(server, method: str, path: str, body=None):
    if body is None:
        return request(server.port, method, path, [])
    return request(server.port, method, path, [JSON], json.dumps(body, ensure_ascii=False).encode())


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    """두 판에 같은 차례로 — 가져오기 → 같은 코드 → 폼 오류 → 번들 아님 → 405·404 → 지운 코드로 다시 → 읽기"""
    done: dict[str, dict] = {}
    tmp = tmp_path_factory.mktemp("l15-bundles")
    good = make_bundle(tmp, "LBA")
    again = make_bundle(tmp, "LBC")
    trunk = make_bundle(tmp, "LBD", branch="trunk")

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        ok = ("code", b"LBA", None, None), ("name", "번들 대조".encode(), None, None), bundle_part(good)
        got["ok"] = post(server, *form(*ok))
        got["dup"] = post(server, *form(*ok))
        got["bad_code"] = post(server, *form(("code", b"lb", None, None), ("name", b"x", None, None), bundle_part(good)))
        got["long_name"] = post(
            server, *form(("code", b"LBE", None, None), ("name", ("가" * 101).encode(), None, None), bundle_part(good))
        )
        got["empty_form"] = post(server, *form())
        got["missing_file"] = post(server, *form(("code", b"LBE", None, None), ("name", b"x", None, None)))
        got["text_as_file"] = post(
            server, *form(("code", b"LBE", None, None), ("name", b"x", None, None), ("bundle", b"abc", None, None))
        )
        got["file_as_code"] = post(
            server, *form(("code", b"LBE", "c.txt", "text/plain"), ("name", b"x", None, None), bundle_part(good))
        )
        got["empty_code"] = post(server, *form(("code", b"", None, None), ("name", b"", None, None), bundle_part(good)))
        got["last_value_wins"] = post(
            server,
            *form(
                ("code", b"LBE", None, None),
                ("code", b"lower", None, None),
                ("name", b"x", None, None),
                bundle_part(good),
            ),
        )
        got["urlencoded"] = post(
            server, [("Content-Type", "application/x-www-form-urlencoded")], b"code=LBE&name=%EB%B2%88&bundle=abc"
        )
        got["json"] = post(server, [JSON], b'{"code": "LBE", "name": "x"}')
        got["no_body"] = post(server, [], b"")
        got["no_boundary"] = post(server, [("Content-Type", "multipart/form-data")], form()[1])
        got["broken"] = post(server, [("Content-Type", f"multipart/form-data; boundary={BOUNDARY}")], b"preamble\r\n" + form()[1])
        got["no_name"] = post(
            server,
            [("Content-Type", f"multipart/form-data; boundary={BOUNDARY}")],
            f"--{BOUNDARY}\r\nContent-Disposition: form-data\r\n\r\nv\r\n--{BOUNDARY}--\r\n".encode(),
        )
        got["not_bundle"] = post(
            server, *form(("code", b"LBE", None, None), ("name", b"x", None, None), bundle_part(b"nope"))
        )
        got["empty_file"] = post(
            server, *form(("code", b"LBE", None, None), ("name", b"x", None, None), bundle_part(b"", ""))
        )
        got["no_main"] = post(
            server, *form(("code", b"LBD", None, None), ("name", b"x", None, None), bundle_part(trunk))
        )
        # {code} 경로 — 파이썬 판은 bundle이 정적 경로다
        got["get_bundle"] = rest(server, "GET", "/api/projects/bundle")
        got["delete_bundle"] = rest(server, "DELETE", "/api/projects/bundle")
        got["put_bundle"] = rest(server, "PUT", "/api/projects/bundle")
        got["post_other"] = post(server, *form(*ok), path="/api/projects/LBX")
        got["patch_other"] = rest(server, "PATCH", "/api/projects/LBA")
        # 지운 코드로 다시 — 보관본은 되살리지 않고 번들의 것으로
        rest(server, "POST", "/api/projects", {"storage": "server", "code": "LBC", "name": "먼저"})
        rest(server, "DELETE", "/api/projects/LBC")
        got["after_delete"] = post(
            server, *form(("code", b"LBC", None, None), ("name", "다시".encode(), None, None), bundle_part(again))
        )
        # 가져온 뒤 읽기
        got["list"] = only_lb(rest(server, "GET", "/api/projects"))
        for key, path in [
            ("detail", "/api/projects/LBA"),
            ("docs", "/api/projects/LBA/docs"),
            ("doc", "/api/docs/LBA-PRD-001"),
            ("versions", "/api/docs/LBA-PRD-001/versions"),
            ("docs_again", "/api/projects/LBC/docs"),
            ("versions_again", "/api/docs/LBC-PRD-001/versions"),
        ]:
            got[key] = rest(server, "GET", path)
        done[server.target] = got
        return got

    return run


FLOW_KEYS = [
    "ok",
    "dup",
    "bad_code",
    "long_name",
    "empty_form",
    "missing_file",
    "text_as_file",
    "file_as_code",
    "empty_code",
    "last_value_wins",
    "urlencoded",
    "json",
    "no_body",
    "no_boundary",
    "broken",
    "no_name",
    "not_bundle",
    "empty_file",
    "no_main",
    "get_bundle",
    "delete_bundle",
    "put_bundle",
    "post_other",
    "patch_other",
    "after_delete",
    "list",
    "detail",
    "docs",
    "doc",
    "versions",
    "docs_again",
    "versions_again",
]


@pytest.mark.parametrize("key", FLOW_KEYS)
def test_bundle_replies(server, flow, key):
    check("bundle_closed", key, masked(flow(server)[key]), server.target)


def test_imported_history_is_the_bundles(server, flow):
    """골격 커밋 없이 번들의 두 커밋이 판 둘, 문서는 승인"""
    got = flow(server)
    assert got["ok"].status == 201
    versions = json.loads(got["versions"].body)
    assert len(versions) == 2
    assert json.loads(got["doc"].body)["status"] == "approved"
