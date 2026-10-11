"""starlette 1.6.0 `Request.form()`(python-multipart 0.0.32) 정답 (카드 L15, server compat::form).

`uv run --project ../backend python xtask/py/form_cases.py > crates/server/tests/golden/form.json`
씨앗 고정 — 손으로 고른 꼴과 무작위로 깨뜨린 본문을 starlette에 그대로 넣어 답(항목 또는 400 제목)을 적는다.
FastAPI처럼 starlette의 HTTPException은 그 문장, 그 밖의 예외는 `There was an error parsing the body`다. 손으로 고치지 않는다.
"""

import asyncio
import base64
import json
import random
import sys

from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request

assert sys.version_info[:2] == (3, 12), sys.version


async def form(ct: str | None, body: bytes) -> dict:
    headers = [] if ct is None else [(b"content-type", ct.encode("latin-1"))]
    scope = {"type": "http", "method": "POST", "headers": headers, "app": object()}
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    try:
        data = await Request(scope, receive).form()
    except HTTPException as e:
        return {"error": e.detail}
    except Exception:  # noqa: BLE001 — FastAPI get_request_handler가 덮는 것
        return {"error": "There was an error parsing the body"}
    items = []
    for k, v in data.multi_items():
        if isinstance(v, UploadFile):
            raw = await v.read()
            items.append([k, {"f": [v.filename, v.content_type, base64.b64encode(raw).decode()]}])
        else:
            items.append([k, {"t": v}])
    return {"items": items}


B = "XyZ-bnd"
MP = f"multipart/form-data; boundary={B}"


def part(name: str, value: bytes, filename: str | None = None, ctype: str | None = None, extra: str = "") -> bytes:
    disp = f'Content-Disposition: form-data; name="{name}"'
    if filename is not None:
        disp += f'; filename="{filename}"'
    head = disp + "\r\n"
    if ctype is not None:
        head += f"Content-Type: {ctype}\r\n"
    head += extra
    return f"--{B}\r\n".encode() + head.encode("utf-8") + b"\r\n" + value + b"\r\n"


def end() -> bytes:
    return f"--{B}--\r\n".encode()


def handpicked() -> list[tuple[str | None, bytes]]:
    ok = part("code", b"BND") + part("name", "번들".encode()) + part("bundle", b"\x00\x01PACK", "x.bundle", "application/octet-stream") + end()
    cases: list[tuple[str | None, bytes]] = [
        (None, b""),
        (None, b"a=1"),
        ("text/plain", b"a=1"),
        ("application/json", b'{"a": 1}'),
        ("application/x-www-form-urlencoded", b""),
        ("application/x-www-form-urlencoded", b"a=1&b=2"),
        ("application/x-www-form-urlencoded", b"a=1&a=2"),
        ("application/x-www-form-urlencoded", b"&&a=b&&c=d&"),
        ("application/x-www-form-urlencoded", b"a"),
        ("application/x-www-form-urlencoded", b"a&b="),
        ("application/x-www-form-urlencoded", b"=v"),
        ("application/x-www-form-urlencoded", b"a+b=c%20d+e"),
        ("application/x-www-form-urlencoded", b"%E2%82%AC=%FF%fe"),
        ("application/x-www-form-urlencoded", "이름=값".encode()),
        ("application/x-www-form-urlencoded", b"a=%&b=%4&c=%zz&d=%%41"),
        ("application/x-www-form-urlencoded", b"a=b=c;d=e"),
        ("application/x-www-form-urlencoded", b"&"),
        ("Application/X-WWW-Form-Urlencoded", b"a=1"),
        ("application/x-www-form-urlencoded; charset=utf-8", b"a=1"),
        (MP, ok),
        ("Multipart/Form-Data; boundary=" + B, ok),
        ("MULTIPART/FORM-DATA", ok),
        ("multipart/form-data", ok),
        ("multipart/form-data;", ok),
        (f'multipart/form-data; boundary="{B}"', ok),
        (f"multipart/form-data; BOUNDARY={B}", ok),
        (f"multipart/form-data; boundary*={B}", ok),
        (f"multipart/form-data; boundary=wrong; boundary={B}", ok),
        (f"multipart/form-data; charset=latin-1; boundary={B}", ok),
        (f"multipart/form-data; charset=ascii; boundary={B}", ok),
        (f"multipart/form-data; charset=UTF8; boundary={B}", ok),
        (f"multipart/form-data; charset=nope; boundary={B}", ok),
        (f"multipart/form-data; boundary={B}; charset=\"utf 8\"", ok),
        ("multipart/form-data; boundary=" + "b" * 256, ok),
        ("multipart/form-data; boundary=" + "b" * 257, ok),
        ("multipart/form-data; boundary=", b"--\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\nv\r\n----\r\n"),
        (MP, b""),
        (MP, b"\r\n\r\n" + ok),
        (MP, b"preamble\r\n" + ok),
        (MP, ok + b"epilogue"),
        (MP, ok[:-2]),
        (MP, ok[:-4]),
        (MP, ok[: len(ok) // 2]),
        (MP, part("a", b"") + end()),
        (MP, part("a", b"1") + part("a", b"2") + part("a", b"", "") + end()),
        (MP, part("a", b"line1\r\nline2\r\n--XyZ-bn\r\n--XyZ-bndx") + end()),
        (MP, part("f", b"data", "C:\\dir\\f.txt") + part("g", b"d", "\\\\srv\\share\\g.txt") + end()),
        (MP, part("f", b"data", "a\"b") + end()),
        (MP, part("f", b"data", "x.bin", None, "Content-Type: text/plain\r\n") + end()),
        (MP, part("f", b"data", "x.bin", "image/png", "content-type: text/plain\r\n") + end()),
        (MP, part("이름", "값".encode(), "파일.txt", "text/plain; charset=utf-8") + end()),
        (MP, f"--{B}\r\nContent-Disposition: form-data\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nX-A: b\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nContent-Disposition form-data; name=a\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nBad Header: x\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\n: x\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nContent-Disposition:   form-data; name=a\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nContent-Disposition:\tform-data; name=a\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nContent-Disposition: form-data; name=a\r\n folded\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\nContent-Disposition: form-data; name=a\n\nv\n--{B}--\n".encode()),
        (MP, f"--{B}\r\nContent-Disposition: form-data; name=a\rX\r\n\r\nv\r\n".encode() + end()),
        (MP, f"--{B}\r\nContent-Disposition: form-data; name=a\r\n\rX\r\nv\r\n".encode() + end()),
        (MP, (f"--{B}\r\n" + "".join(f"X-{n}: v\r\n" for n in range(7)) + 'Content-Disposition: form-data; name="a"\r\n\r\nv\r\n').encode() + end()),
        (MP, (f"--{B}\r\n" + "".join(f"X-{n}: v\r\n" for n in range(8)) + 'Content-Disposition: form-data; name="a"\r\n\r\nv\r\n').encode() + end()),
        (MP, (f"--{B}\r\nX-Long: " + "v" * 4200 + '\r\nContent-Disposition: form-data; name="a"\r\n\r\nv\r\n').encode() + end()),
        (MP, (f"--{B}\r\nX-Long: " + "v" * 4300 + '\r\nContent-Disposition: form-data; name="a"\r\n\r\nv\r\n').encode() + end()),
        (MP, f"--{B}--\r\n".encode()),
        (MP, f"--{B}-x\r\n".encode()),
        (MP, f"--{B}x\r\n".encode()),
        (MP, f"--{B}\rx".encode()),
        (MP, f"-{B}\r\n".encode()),
        (MP, part("a", b"v") + f"--{B}-x".encode()),
        (MP, part("a", b"v") + f"--{B}\r\r".encode()),
        (MP, part("a", b"v")[:-2] + f"\r\n--{B}  \r\n".encode()),
        (MP, part("a", b"\xff\xfe raw") + end()),
        (f"multipart/form-data; charset=latin-1; boundary={B}", part("a", "é".encode()) + end()),
        (f"multipart/form-data; charset=utf-8; boundary={B}", part("a", b"\xe9") + end()),
    ]
    return cases


ALPHA = b"\r\n-:;\"= abcXyZ"


def mutate(r: random.Random, body: bytes) -> bytes:
    b = bytearray(body)
    for _ in range(r.randint(1, 3)):
        op = r.random()
        if not b:
            break
        at = r.randrange(len(b))
        if op < 0.3:
            del b[at]
        elif op < 0.6:
            b.insert(at, r.choice(ALPHA))
        elif op < 0.8:
            b[at] = r.choice(ALPHA)
        else:
            del b[at:]
    return bytes(b)


def randomized(r: random.Random) -> list[tuple[str | None, bytes]]:
    cases: list[tuple[str | None, bytes]] = []
    for _ in range(400):
        parts = []
        for _ in range(r.randint(0, 4)):
            name = r.choice(["code", "name", "bundle", "a", "이름", ""])
            value = r.choice([b"", b"v", b"BND", "번들".encode(), b"\r\n--Xy", b"--XyZ-bnd", bytes(r.randrange(256) for _ in range(r.randint(0, 40)))])
            if r.random() < 0.4:
                parts.append(part(name, value, r.choice(["x.bundle", "", "a b.txt", "파일"]), r.choice([None, "application/octet-stream", "text/plain"])))
            else:
                parts.append(part(name, value))
        body = b"".join(parts) + (end() if r.random() < 0.9 else b"")
        if r.random() < 0.7:
            body = mutate(r, body)
        cases.append((MP, body))
    for _ in range(150):
        n = r.randint(0, 30)
        body = bytes(r.choice(b"ab=&%+2F\xe2\x82\xac 4%1") for _ in range(n))
        cases.append(("application/x-www-form-urlencoded", body))
    for _ in range(120):
        tokens = ["multipart/form-data", " multipart/form-data", "Multipart/form-data", ";", "; ", "boundary=" + B, 'boundary="' + B + '"', "boundary=a;b", '"', "\\", "charset=utf-8", "x=y", "=", "*", " ", "\t", "boundary*=" + B, '"a;b"']
        ct = "".join(r.choice(tokens) for _ in range(r.randint(1, 6)))
        cases.append((ct, part("a", b"v") + end()))
    return cases


def main() -> None:
    r = random.Random(20261011)
    cases = handpicked() + randomized(r)
    out = []
    for ct, body in cases:
        res = asyncio.run(form(ct, body))
        out.append({"ct": ct, "body": base64.b64encode(body).decode(), "out": res})
    json.dump(out, sys.stdout, ensure_ascii=False, indent=0)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
