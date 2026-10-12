"""카드 L17 — 두 판 속도 (SYNC-PRD-001 R15 「빠르다」 · SYNC-INFRA-001 9.8). `cargo xtask speed`가 부른다.

같은 PC에서 두 판을 나란히 띄워 같은 일을 시킨다 — 켜기(첫 실행·다시 켜기), 싱크독 저장소(main)를 번들로 가져오기,
그 코드 그래프가 생길 때까지, 화면 조회, 문서 저장(git 포함), 켜 둔 메모리(DB 포함). 표를 찍고 JSON을 남긴다.
Rust 판은 release 실행 파일, 파이썬 판은 작업 트리 이미지(폐쇄망판 Docker 묶음과 같은 구성 — 계약 시험의 것).
목표는 R15 그대로: 켜기 3초(첫 실행 15초) · 조회 0.1초 · 저장 0.3초 · 코드 그래프 10초 · 메모리 300MB, 그리고
파이썬 판보다 느린 항목이 없다.
리눅스와 윈도에서 돈다 — 윈도는 윈도 디스크의 사본에서(파이썬 판은 Docker Desktop).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOCAL = REPO / "local"
PROJECT = "syncdoc-speed"
WINDOWS = os.name == "nt"
EXE = LOCAL / "target" / "release" / ("syncdoc-local.exe" if WINDOWS else "syncdoc-local")
PG_DIR = LOCAL / "target" / "pg" / ("x86_64-pc-windows-msvc/16.15.0" if WINDOWS else "16.15.0")
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", str(HERE / "python.compose.yml")]
CODE = "SYNC"
READS = [
    "/api/projects",
    f"/api/projects/{CODE}",
    f"/api/projects/{CODE}/docs",
    f"/api/projects/{CODE}/flags?kind=broken_ref",
    f"/api/projects/{CODE}/graph",
    "/api/docs/SYNC-PRD-001",
    "/api/docs/SYNC-PRD-001/versions",
    "/api/docs/SYNC-PRD-001/items/R1/references",
    "/api/docs/SYNC-MS-001",
]
TARGETS = {"first_start": 15.0, "restart": 3.0, "read": 0.1, "save": 0.3, "graph": 10.0, "memory_mb": 300.0}


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_health(url: str, limit: float = 600) -> float:
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                return time.monotonic() - t0
        except httpx.HTTPError:
            pass
        time.sleep(0.02)
    raise RuntimeError(f"{url} 안 떴다")


# ── Rust 판 ──


class Rust:
    def __init__(self, data: Path) -> None:
        self.data, self.port, self.proc = data, free_port(), None
        self.url = f"http://127.0.0.1:{self.port}"

    def start(self) -> float:
        env = {**os.environ, "SYNCDOC_LOCAL_PG_DIR": str(PG_DIR)}
        if WINDOWS:  # xtask가 설치판과 같은 고정 MinGit을 넘긴다(카드 L19) — 없으면 시스템 git
            env.setdefault("SYNCDOC_LOCAL_GIT", shutil.which("git") or "git")
        t0 = time.monotonic()
        self.proc = subprocess.Popen(
            [str(EXE), "--data-dir", str(self.data),
             "--port", str(self.port), "--no-browser", "--no-tray"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        wait_health(self.url)
        return time.monotonic() - t0

    def stop(self) -> None:
        if not self.proc or self.proc.poll() is not None:
            return
        if WINDOWS:
            # 콘솔 없는 자식에는 Ctrl+C를 못 보낸다 —
            # 설치 시험(local-release.yml)처럼 끝내고 PostgreSQL은 pg_ctl로
            self.proc.kill()
            self.proc.wait(60)
            pg_ctl = str(PG_DIR / "bin" / "pg_ctl.exe")
            pgdata = str(self.data / "pgdata")
            subprocess.run([pg_ctl, "stop", "-D", pgdata, "-m", "fast", "-w"], capture_output=True)
            return
        self.proc.send_signal(signal.SIGINT)
        self.proc.wait(60)

    def memory_mb(self) -> float:
        """실행 파일과 그 PostgreSQL(데이터 자리의 pgdata로 띄운 것)의 PSS 합.
        윈도는 개인 작업 집합(작업 관리자의 「메모리」)"""
        if WINDOWS:
            return private_ws_mb(self.proc.pid, str(self.data / "pgdata"))
        pids = {self.proc.pid}
        out = subprocess.run(["pgrep", "-f", str(self.data / "pgdata")], capture_output=True, text=True).stdout
        for pid in out.split():
            pids.add(int(pid))
            kids = subprocess.run(["pgrep", "-P", pid], capture_output=True, text=True).stdout
            pids.update(int(k) for k in kids.split())
        return sum(pss_kb(p) for p in pids) / 1024


def pss_kb(pid: int) -> int:
    try:
        text = Path(f"/proc/{pid}/smaps_rollup").read_text()
    except OSError:
        return 0
    m = re.search(r"^Pss:\s+(\d+) kB", text, re.M)
    return int(m.group(1)) if m else 0


def private_ws_mb(pid: int, pgdata: str) -> float:
    """윈도 — 실행 파일과, 명령 줄에 pgdata가 있는 프로세스(postmaster)와 그 자손의
    개인 작업 집합 합"""
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "@{p = @(Get-CimInstance Win32_Process"
        " | Select-Object ProcessId, ParentProcessId, CommandLine);"
        " w = @(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process"
        " | Select-Object IDProcess, WorkingSetPrivate)}"
        " | ConvertTo-Json -Depth 3 -Compress"
    )
    cmd = ["powershell", "-NoProfile", "-Command", script]
    out = subprocess.run(cmd, capture_output=True, encoding="utf-8", check=True).stdout
    data = json.loads(out)
    # pg_ctl은 경로를 C:/…처럼 슬래시로 넘긴다
    want = pgdata.replace("\\", "/").lower()
    found = {p["ProcessId"] for p in data["p"] if want in (p["CommandLine"] or "").lower()}
    pids = {pid} | found
    grown = True
    while grown:
        kids = {p["ProcessId"] for p in data["p"] if p["ParentProcessId"] in pids} - pids
        pids |= kids
        grown = bool(kids)
    used = sum(int(w["WorkingSetPrivate"]) for w in data["w"] if w["IDProcess"] in pids)
    return used / 1024 / 1024


# ── 파이썬 판 ──


class Python:
    def __init__(self) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "CONTRACT_PORT": str(self.port)}

    def build(self) -> None:
        subprocess.run(["docker", "build", "-q", "-t", "syncdoc-app:contract", str(REPO)], check=True,
                       stdout=subprocess.DEVNULL)  # fmt: skip

    def first_start(self) -> float:
        subprocess.run([*COMPOSE, "down", "-v"], env=self.env, capture_output=True)
        t0 = time.monotonic()
        subprocess.run([*COMPOSE, "up", "-d"], env=self.env, check=True, capture_output=True)
        wait_health(self.url)
        return time.monotonic() - t0

    def restart(self) -> float:
        subprocess.run([*COMPOSE, "stop"], env=self.env, check=True, capture_output=True)
        t0 = time.monotonic()
        subprocess.run([*COMPOSE, "start"], env=self.env, check=True, capture_output=True)
        wait_health(self.url)
        return time.monotonic() - t0

    def down(self) -> None:
        subprocess.run([*COMPOSE, "down", "-v"], env=self.env, capture_output=True)

    def memory_mb(self) -> float:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}"],
            capture_output=True, encoding="utf-8", check=True,
        ).stdout  # fmt: skip
        total = 0.0
        for line in out.splitlines():
            name, usage = line.split(" ", 1)
            if not name.startswith(PROJECT + "-"):
                continue
            used = usage.split("/")[0].strip()
            n = float(re.match(r"[\d.]+", used).group(0))
            unit = used[len(re.match(r"[\d.]+", used).group(0)) :].strip()
            total += n * {"B": 1 / 1024 / 1024, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[unit]
        return total


# ── 같은 일 ──


def token(url: str) -> str:
    r = httpx.post(f"{url}/api/me/tokens", json={"label": "speed"}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def mcp(url: str, tok: str, name: str, args: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    r = httpx.post(
        f"{url}/mcp",
        json=body,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json, text/event-stream"},
        timeout=120,
    )
    data = json.loads(r.text.split("data: ", 1)[1])
    text = data["result"]["content"][0]["text"]
    if data["result"].get("isError"):
        raise RuntimeError(f"{name}: {text[:300]}")
    return json.loads(text)


def import_bundle(url: str, bundle: Path) -> float:
    t0 = time.monotonic()
    with bundle.open("rb") as f:
        r = httpx.post(
            f"{url}/api/projects/bundle",
            data={"code": CODE, "name": "싱크독"},
            files={"bundle": ("syncdoc.bundle", f, "application/octet-stream")},
            timeout=1800,
        )
    if r.status_code != 201:
        raise RuntimeError(f"가져오기 {r.status_code}: {r.text[:300]}")
    return time.monotonic() - t0


def wait_graph(url: str, limit: float = 1800) -> float:
    """가져오기가 끝난 뒤 코드 그래프가 생길 때까지(오류 없이)"""
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        g = httpx.get(f"{url}/api/projects/{CODE}/code-calls", timeout=30).json().get("graph")
        if g and g.get("error"):
            raise RuntimeError(f"그래프 오류: {g['error']}")
        if g:
            return time.monotonic() - t0
        time.sleep(0.1)
    raise RuntimeError("그래프가 안 생겼다")


def reads(url: str, rounds: int) -> dict:
    out = {}
    with httpx.Client(base_url=url, timeout=30) as c:
        for path in READS:
            for _ in range(3):
                c.get(path)
            ts = []
            for _ in range(rounds):
                t0 = time.perf_counter()
                r = c.get(path)
                ts.append(time.perf_counter() - t0)
                if r.status_code != 200:
                    raise RuntimeError(f"{path}: {r.status_code}")
            out[path] = statistics.median(ts)
    return out


def saves(url: str, tok: str, rounds: int) -> list[float]:
    """같은 문서를 고쳐 저장한다(git 커밋 포함) — 저장소 main의 원문에서 항목 하나의 설명 끝을 번갈아.
    승인 문서는 고치면 초안으로 내려가므로 저장 전마다 지금 상태·판을 읽어 frontmatter를 맞춘다"""
    path = "docs/specs/01-RFQ/SYNC-RFQ-001.md"
    show = ["git", "-C", str(REPO), "show", f"main:{path}"]
    body = subprocess.run(show, capture_output=True, encoding="utf-8", check=True).stdout
    ts = []
    for i in range(rounds):
        cur = httpx.get(f"{url}/api/docs/SYNC-RFQ-001", timeout=30).json()
        text = re.sub(r"^status: \w+", f"status: {cur['status']}", body, count=1, flags=re.M)
        text = re.sub(r"(\n#### Q1 [^\n]*\n[^\n]*)", lambda m: m.group(1) + f" (속도 {i})", text, count=1)
        t0 = time.perf_counter()
        mcp(url, tok, "update_document", {
            "doc_id": "SYNC-RFQ-001", "body": text, "expected_version": cur["current_version_no"],
            "message": f"속도 {i}", "changed_items": ["Q1"],
        })  # fmt: skip
        ts.append(time.perf_counter() - t0)
    return ts


def run(rounds: int, out: Path) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="syncdoc-speed-"))
    bundle = tmp / "syncdoc.bundle"
    subprocess.run(["git", "-C", str(REPO), "bundle", "create", "-q", str(bundle), "main"], check=True)
    cargo = shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo")
    subprocess.run([cargo, "build", "-q", "--release", "-p", "syncdoc_app"], cwd=LOCAL, check=True)
    py = Python()
    py.build()
    rs = Rust(tmp / "data")
    result: dict = {"rust": {}, "python": {}}
    try:
        for name, ed in (("rust", rs), ("python", py)):
            r = result[name]
            r["first_start"] = ed.start() if name == "rust" else ed.first_start()
            restarts = []
            for _ in range(3):
                if name == "rust":
                    ed.stop()
                    restarts.append(ed.start())
                else:
                    restarts.append(ed.restart())
            r["restart"] = statistics.median(restarts)
            url = ed.url
            tok = token(url)
            print(f"{name}: 켜기 {r['first_start']:.2f}s · 다시 {r['restart']:.2f}s", flush=True)
            r["import"] = import_bundle(url, bundle)
            r["graph"] = wait_graph(url)
            print(f"{name}: 가져오기 {r['import']:.2f}s · 그래프 {r['graph']:.2f}s", flush=True)
            r["reads"] = reads(url, rounds)
            r["read"] = max(r["reads"].values())
            ts = saves(url, tok, rounds)
            r["saves"] = ts
            r["save"] = statistics.median(ts)
            time.sleep(5)
            r["memory_mb"] = ed.memory_mb()
            print(f"{name}: {json.dumps({k: v for k, v in r.items() if k not in ('reads', 'saves')})}", flush=True)
    finally:
        rs.stop()
        py.down()
    rows, ok = [], True
    for key, target in TARGETS.items():
        a, b = result["rust"][key], result["python"][key]
        good = a <= target and a <= b
        ok &= good
        rows.append(f"| {key} | {target} | {a:.3f} | {b:.3f} | {'통과' if good else '못 미침'} |")
    a, b = result["rust"]["import"], result["python"]["import"]
    rows.append(f"| import | — | {a:.3f} | {b:.3f} | {'통과' if a <= b else '느림'} |")
    ok &= a <= b
    print("| 항목 | 목표 | Rust | 파이썬 | 판정 |\n|---|---|---|---|---|\n" + "\n".join(rows))
    for path in READS:
        print(f"  {path}: Rust {result['rust']['reads'][path] * 1000:.1f}ms · 파이썬 {result['python']['reads'][path] * 1000:.1f}ms")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print("판정:", "통과" if ok else "못 미침")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--out", type=Path, default=REPO / "local" / "target" / "speed.json")
    args = ap.parse_args()
    raise SystemExit(run(args.rounds, args.out))
