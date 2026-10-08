"""날 HTTP — 머리를 보낸 그대로 보내고(같은 이름 둘·이상한 값까지) 받은 것을 그대로 읽는다.

계약 비교는 상태 코드·계약 안의 머리·본문 바이트다.
계약 밖(SYNC-CODE-002 2장): `date`·`server`·`connection` 머리,
본문을 나눠 보내는 꼴(`transfer-encoding`·`content-length`).
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

#: 비교하는 머리 — 나머지는 계약 밖
CONTRACT_HEADERS = ("content-type", "cache-control", "x-accel-buffering", "allow", "location")


@dataclass
class Reply:
    status: int
    headers: list[tuple[str, str]]
    body: bytes
    timed_out: bool = False

    def header(self, name: str) -> str | None:
        for k, v in self.headers:
            if k == name:
                return v
        return None

    def contract(self) -> dict:
        """비교할 꼴 — 상태·계약 안 머리(이름 순, 같은 이름은 받은 차례)·본문"""
        hs = [(k, v) for k, v in self.headers if k in CONTRACT_HEADERS]
        return {
            "status": self.status,
            "headers": sorted(hs, key=lambda kv: kv[0]),
            "body": self.body.decode("utf-8", "backslashreplace"),
        }


def _dechunk(data: bytes) -> bytes:
    out = b""
    while data:
        line, _, rest = data.partition(b"\r\n")
        size = int(line.split(b";")[0] or b"0", 16)
        if size == 0:
            break
        out += rest[:size]
        data = rest[size + 2 :]
    return out


def request(
    port: int,
    method: str,
    path: str,
    headers: list[tuple[str, str]] | None = None,
    body: bytes = b"",
    *,
    timeout: float = 30,
    read_for: float | None = None,
) -> Reply:
    """요청 하나. `Connection: close`·`Host`·`Content-Length`를 붙인다(이미 있으면 그대로).

    `read_for`를 주면 그 초만 읽고 끊는다 — 끝나지 않는 SSE(GET /mcp)용.
    """
    hs = list(headers or [])
    names = {k.lower() for k, _ in hs}
    if "host" not in names:
        hs.insert(0, ("Host", f"127.0.0.1:{port}"))
    if "connection" not in names:
        hs.append(("Connection", "close"))
    if "content-length" not in names and (body or method in ("POST", "PUT", "PATCH")):
        hs.append(("Content-Length", str(len(body))))
    head = f"{method} {path} HTTP/1.1\r\n".encode("latin-1")
    for k, v in hs:
        head += k.encode("latin-1") + b": " + v.encode("latin-1") + b"\r\n"
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.sendall(head + b"\r\n" + body)
    if read_for is not None:
        s.settimeout(read_for)
    raw = b""
    timed_out = False
    try:
        while True:
            b = s.recv(65536)
            if not b:
                break
            raw += b
    except TimeoutError:
        timed_out = True
    finally:
        s.close()
    head_raw, _, rest = raw.partition(b"\r\n\r\n")
    lines = head_raw.split(b"\r\n")
    status = int(lines[0].split(b" ")[1]) if lines and lines[0] else 0
    out_headers = []
    for line in lines[1:]:
        k, _, v = line.partition(b":")
        out_headers.append((k.decode("latin-1").strip().lower(), v.decode("latin-1").strip()))
    te = [v for k, v in out_headers if k == "transfer-encoding"]
    body_out = _dechunk(rest) if te and "chunked" in te[0] and not timed_out else rest
    if timed_out and te and "chunked" in te[0]:
        body_out = _dechunk(rest + b"0\r\n\r\n") if rest.endswith(b"\r\n") else rest
    return Reply(status, out_headers, body_out, timed_out)
