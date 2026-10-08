"""공용 계약 시험의 틀 — SYNC-INFRA-001 9.8 · SYNC-CODE-002 2장 (카드 L2).

두 판을 이 시험이 직접 띄운다. 앱을 import하지 않는다 — 주소만 쓴다.
- python — 작업 트리로 만든 이미지(syncdoc-app:contract)를 폐쇄망판 구성으로(python.compose.yml)
- rust   — local/의 syncdoc-local을 임시 데이터 자리로

시험마다 그 기능을 닫는 카드를 적는다(@pytest.mark.card("L3")). 파이썬 판은 전부 돌고,
Rust 판은 CODE-002 완료란이 찬 카드(그리고 --with-card로 준 카드)만 돈다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parent.parent
LOCAL = REPO / "local"
CODE_002 = REPO / "docs" / "specs" / "11-CODE" / "SYNC-CODE-002.md"
LLM_KEY = "contract-key"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--target", default="both", choices=["python", "rust", "both"])
    parser.addoption("--with-card", action="append", default=[], help="Rust 판에서 더 돌릴 카드")
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        help="스냅숏을 파이썬 판의 답으로 다시 쓴다(--target python과 함께)",
    )
    parser.addoption("--diff-count", type=int, default=600, help="두 판 차이 시험의 사례 수")
    parser.addoption("--diff-seed", type=int, default=20261008, help="두 판 차이 시험의 씨앗")


def pytest_configure(config: pytest.Config) -> None:
    import snapshots

    snapshots.UPDATE = config.getoption("--update-snapshots")


def pytest_sessionfinish(session: pytest.Session) -> None:
    import snapshots

    snapshots.flush()


def done_cards() -> set[str]:
    """CODE-002에서 완료란이 찬 카드 — `#### L1 …` 아래 `| 완료 | … |`가 「—」가 아니다."""
    text = CODE_002.read_text(encoding="utf-8")
    out: set[str] = set()
    for m in re.finditer(r"^#### (L\d+) .*?^\| 완료 \| (.*?) \|$", text, re.M | re.S):
        if m.group(2).strip() not in ("", "—"):
            out.add(m.group(1))
    return out


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "server" in metafunc.fixturenames:
        opt = metafunc.config.getoption("--target")
        targets = ["python", "rust"] if opt == "both" else [opt]
        metafunc.parametrize("server", targets, indirect=True)


@dataclass
class Server:
    target: str
    url: str
    port: int

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.url, timeout=30)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(url: str, seconds: float = 180) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url}/health가 {seconds}초 안에 안 떴다")


class _FakeLLM(BaseHTTPRequestHandler):
    """OpenAI 호환 가짜 모델 — 질문 탭 카드(L14)가 쓴다. 지금은 주소가 있다는 것만."""

    def do_POST(self) -> None:
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "계약"}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def fake_llm() -> Iterator[int]:
    srv = ThreadingHTTPServer(("0.0.0.0", 0), _FakeLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _start_python(llm_port: int) -> Iterator[Server]:
    subprocess.run(["docker", "build", "-q", "-t", "syncdoc-app:contract", str(REPO)], check=True,
                   stdout=subprocess.DEVNULL)  # fmt: skip
    port = _free_port()
    env = {**os.environ, "CONTRACT_PORT": str(port),
           "CONTRACT_LLM_URL": f"http://host.docker.internal:{llm_port}/v1/chat/completions",
           "CONTRACT_LLM_KEY": LLM_KEY}  # fmt: skip
    compose = ["docker", "compose", "-f", str(Path(__file__).parent / "python.compose.yml")]
    subprocess.run([*compose, "up", "-d", "--wait"], check=True, env=env, stdout=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_health(url)
        yield Server("python", url, port)
    finally:
        subprocess.run([*compose, "down", "-v"], env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)  # fmt: skip


def _start_rust(llm_port: int) -> Iterator[Server]:
    cargo = shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo")
    subprocess.run([cargo, "build", "-q", "-p", "syncdoc_app"], cwd=LOCAL, check=True)
    data = Path(tempfile.mkdtemp(prefix="syncdoc-contract-"))
    (data / "settings.toml").write_text(
        f'LOCAL_LOGIN = "local"\nLLM_API_URL = "http://127.0.0.1:{llm_port}/v1/chat/completions"\n'
        f'LLM_API_KEY = "{LLM_KEY}"\n',
        encoding="utf-8",
    )
    env = {**os.environ, "SYNCDOC_LOCAL_PG_DIR": str(LOCAL / "target" / "pg" / "16.15.0")}
    proc = subprocess.Popen(
        [str(LOCAL / "target" / "debug" / "syncdoc-local"), "--data-dir", str(data),
         "--port", "0", "--no-browser", "--no-tray"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )  # fmt: skip
    try:
        end = time.monotonic() + 120
        while not (data / "instance.json").exists():
            if proc.poll() is not None:
                raise RuntimeError(f"syncdoc-local이 끝났다 — {proc.stderr.read().decode()}")
            if time.monotonic() > end:
                raise RuntimeError("syncdoc-local이 120초 안에 안 떴다")
            time.sleep(0.2)
        port = json.loads((data / "instance.json").read_text())["port"]
        url = f"http://127.0.0.1:{port}"
        _wait_health(url, 30)
        yield Server("rust", url, port)
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data, ignore_errors=True)


_STARTERS = {"python": _start_python, "rust": _start_rust}


@pytest.fixture(scope="session")
def _servers(fake_llm: int) -> Iterator[dict]:
    """대상마다 한 번만 띄운다 — 처음 쓰일 때."""
    running: dict[str, Server] = {}
    gens = []

    def get(target: str) -> Server:
        if target not in running:
            gen = _STARTERS[target](fake_llm)
            running[target] = next(gen)
            gens.append(gen)
        return running[target]

    yield {"get": get}
    for gen in reversed(gens):
        next(gen, None)


def _rust_allowed(request: pytest.FixtureRequest) -> bool:
    marker = request.node.get_closest_marker("card")
    card = marker.args[0] if marker else None
    if card is None:
        return True
    return card in done_cards() | set(request.config.getoption("--with-card"))


@pytest.fixture
def server(request: pytest.FixtureRequest, _servers: dict) -> Server:
    target = request.param
    if target == "rust" and not _rust_allowed(request):
        marker = request.node.get_closest_marker("card")
        pytest.skip(f"Rust 판은 카드 {marker.args[0]}가 아직이다")
    return _servers["get"](target)


@pytest.fixture
def both(request: pytest.FixtureRequest, _servers: dict) -> tuple[Server, Server]:
    """두 판 차이 시험 — 둘 다 띄울 때(`--target both`)만, Rust는 카드가 끝났거나 --with-card일 때만"""
    if request.config.getoption("--target") != "both":
        pytest.skip("두 판 차이 시험은 --target both에서만")
    if not _rust_allowed(request):
        pytest.skip("Rust 판은 이 카드가 아직이다")
    return _servers["get"]("python"), _servers["get"]("rust")


_TOKENS: dict[str, str] = {}


def token_for(srv: Server) -> str:
    """그 판에 MCP 토큰 하나 — 판마다 한 번 발급해 같이 쓴다"""
    if srv.url not in _TOKENS:
        r = srv.client().post("/api/me/tokens", json={"label": "contract"})
        assert r.status_code == 201, r.text
        _TOKENS[srv.url] = r.json()["token"]
    return _TOKENS[srv.url]
