"""카드 L16 — Docker 묶음(파이썬 판)의 백업을 Rust 판이 되살린다 (SYNC-INFRA-001 6.1·9.6, CODE-002 4장 미결).

파이썬 판 컨테이너에서 `scripts/backup.sh`(카드 BR)와 같은 차례로 백업을 뜨고 — DB 덤프(`pg_dump -Fc`)와 볼륨
`origins`의 tar를 tar 하나로, gpg가 있으면 `gpg --symmetric --cipher-algo AES256`으로 — 새로 띄운 Rust 판의 「이 PC」
경로로 되살린 뒤, 프로젝트 목록·문서 목록·문서·판 목록이 파이썬 판과 바이트로 같은지 본다. 시각만 가린다.
`/api/local*`은 Rust 판만 있어 비교하지 않는다(계약 밖) — 이 시험은 그 경로로 결과를 만들 뿐이다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import conftest
from test_l6_projects import mcp
from wire import request

pytestmark = pytest.mark.card("L16")

STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")
JSON = ("Content-Type", "application/json")
CODE = "LRA"
PASSWORD = "계약 백업"
PRD = (
    "# 되살리기 대조\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명.\n\n"
    "## 4. 성공지표\n\n## 5. 미결사항\n"
)


def masked(reply) -> dict:
    c = reply.contract()
    c["body"] = STAMP.sub("T", c["body"])
    return c


def rest(server, method: str, path: str, body=None):
    if body is None:
        return request(server.port, method, path, [])
    return request(server.port, method, path, [JSON], json.dumps(body, ensure_ascii=False).encode())


def br_backup(dest: Path, tmp: Path) -> str:
    """scripts/backup.sh와 같은 차례 — 덤프 → origins tar → tar 하나 → (gpg). 이름은 BR 꼴"""
    work = tmp / "br"
    work.mkdir()
    dump = subprocess.run(
        ["docker", "exec", "syncdoc-contract-db-1", "sh", "-c", 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
        capture_output=True,
        check=True,
    ).stdout
    (work / "db.dump").write_bytes(dump)
    origins = subprocess.run(
        ["docker", "exec", "syncdoc-contract-app-1", "tar", "-C", "/var/syncdoc", "-cf", "-", "origins"],
        capture_output=True,
        check=True,
    ).stdout
    (work / "origins.tar").write_bytes(origins)
    plain = tmp / "plain.tar"
    subprocess.run(["tar", "-C", str(work), "-cf", str(plain), "db.dump", "origins.tar"], check=True)
    if shutil.which("gpg") is None:
        name = "syncdoc-20261011-120000.tar"
        shutil.copy(plain, dest / name)
        return name
    home = tmp / "gnupg"
    home.mkdir(mode=0o700)
    name = "syncdoc-20261011-120000.tar.gpg"
    subprocess.run(
        ["gpg", "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback", "--passphrase", PASSWORD,
         "--symmetric", "--cipher-algo", "AES256", "-o", str(dest / name), str(plain)],
        env={"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin"},
        check=True,
    )  # fmt: skip
    return name


def wait_op(server, kind: str) -> dict:
    """다시 켜기를 기다린다 — 마지막 다시 켜기가 그 종류가 될 때까지(내려간 동안은 연결이 안 된다)"""
    end = time.monotonic() + 180
    while time.monotonic() < end:
        try:
            r = server.client().get("/api/local")
            if r.status_code == 200 and (r.json().get("last_op") or {}).get("kind") == kind:
                return r.json()
        except Exception:  # noqa: BLE001 — 내려가 있다
            pass
        time.sleep(0.5)
    raise AssertionError(f"180초 안에 다시 켜지지 않았다 — {kind}")


def test_rust_restores_python_backup(both, fake_llm, tmp_path):
    py, _ = both
    # 1. 파이썬 판에 프로젝트와 문서 둘(판 둘)
    mcp(py, "init_project", {"storage": "server", "code": CODE, "name": "되살리기 대조"})
    mcp(py, "create_document", {"project_code": CODE, "doc_type": "PRD", "body": PRD, "message": "첫 판"})
    body = "---\ndoc_id: LRA-PRD-001\ntype: PRD\ntitle: 되살리기 대조\nstatus: draft\n---\n" + PRD.replace("설명.", "설명을 고쳤다.")
    mcp(py, "update_document", {"doc_id": "LRA-PRD-001", "body": body, "expected_version": 1, "message": "둘째 판", "changed_items": ["R1"]})
    assert json.loads(rest(py, "GET", "/api/docs/LRA-PRD-001/versions").body)[0]["version_no"] == 2
    # 2. Docker 묶음의 백업
    backups = tmp_path / "backups"
    backups.mkdir()
    name = br_backup(backups, tmp_path)
    # 3. 새 Rust 판 — 백업 폴더를 정하고 되살린다
    gen = conftest._start_rust(fake_llm)
    rs = next(gen)
    try:
        r = rs.client().put("/api/local/settings", json={"backup_dir": str(backups)})
        assert r.status_code == 202, r.text
        wait_op(rs, "settings")
        r = rs.client().post("/api/local/restore", json={"name": name, "password": PASSWORD})
        assert r.status_code == 202, r.text
        done = wait_op(rs, "restore")
        assert done["last_op"]["ok"], done
        # 4. 두 판이 같은 것을 낸다
        for path in [
            "/api/projects",
            f"/api/projects/{CODE}/docs",
            "/api/docs/LRA-PRD-001",
            "/api/docs/LRA-PRD-001/versions",
            "/api/docs/LRA-PRD-001/diff?from=1&to=2",
        ]:
            assert masked(rest(rs, "GET", path)) == masked(rest(py, "GET", path)), path
        assert rs.client().get("/api/local").json()["backup"]["files"][0]["name"] == name
        # Rust 판에서 이어서 쓴다 — 켤 때 다시 만든 작업 사본으로 판 셋째
        body3 = body.replace("설명을 고쳤다.", "셋째로 고쳤다.")
        mcp(rs, "update_document", {"doc_id": "LRA-PRD-001", "body": body3, "expected_version": 2, "message": "셋째 판", "changed_items": ["R1"]})
        versions = json.loads(rest(rs, "GET", "/api/docs/LRA-PRD-001/versions").body)
        assert [v["version_no"] for v in versions] == [3, 2, 1]
    finally:
        next(gen, None)
