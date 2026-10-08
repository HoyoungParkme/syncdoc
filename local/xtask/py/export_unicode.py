"""cargo xtask unicode-tables — 파이썬 3.12의 문자 분류 표를 Rust 소스로 뽑는다.

SYNC-STD-004#DEV-7 · SYNC-DOM-004 1장 pycompat. 손으로 고치지 않는다 — 이 스크립트가 다시 만든다.
0..=0x10FFFF를 파이썬 `re`(str 패턴의 `\\s`·`\\d`·`\\w`)와 `str.isprintable()`에 돌려 구간으로 적는다.
`str.strip()`이 벗기는 글자는 `\\s`와 같다(`str.isspace`) — 다르면 멈춘다.
`uv run --project backend python local/xtask/py/export_unicode.py OUT`
"""

from __future__ import annotations

import re
import sys
import unicodedata

SPACE = re.compile(r"\s")
DECIMAL = re.compile(r"\d")
WORD = re.compile(r"\w")


def ranges(pred) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    for cp in range(0x110000):
        if pred(chr(cp)):
            if start is None:
                start = cp
        elif start is not None:
            out.append((start, cp - 1))
            start = None
    if start is not None:
        out.append((start, 0x10FFFF))
    return out


def check_same(name: str, a, b) -> None:
    for cp in range(0x110000):
        c = chr(cp)
        if bool(a(c)) != bool(b(c)):
            sys.exit(f"{name}: U+{cp:04X}에서 re와 str 메서드가 다르다 — 표를 나눠야 한다")


def table(name: str, doc: str, rs: list[tuple[int, int]]) -> str:
    lines = [f"/// {doc} — `(처음, 끝)` 둘 다 포함, 오름차순", f"pub const {name}: [(u32, u32); {len(rs)}] = ["]
    lines += [f"    (0x{lo:X}, 0x{hi:X})," for lo, hi in rs]
    lines.append("];")
    return "\n".join(lines)


def main() -> None:
    check_same("\\s", SPACE.fullmatch, str.isspace)
    check_same("\\d", DECIMAL.fullmatch, str.isdecimal)
    check_same("\\w", WORD.fullmatch, lambda c: c.isalnum() or c == "_")
    ver = sys.version.split()[0]
    head = (
        "//! 파이썬 3.12의 문자 분류 표 — `re`의 `\\s`·`\\d`·`\\w`와 `str.isprintable()` "
        "(SYNC-DOM-004 1장 pycompat).\n"
        f"//! 생성물: `cargo xtask unicode-tables`가 Python {ver} · unicodedata "
        f"{unicodedata.unidata_version}에서 0..=0x10FFFF를 돌려 뽑았다. 손으로 고치지 않는다.\n"
        "//! 파이썬 3.12(Docker 판의 python:3.12-slim)와 같은 유니코드 판이어야 한다.\n"
    )
    body = "\n\n".join(
        [
            table("SPACE", "`\\s` = `str.isspace()` — `strip()`이 벗기는 글자", ranges(SPACE.fullmatch)),
            table("DECIMAL", "`\\d` = `str.isdecimal()`", ranges(DECIMAL.fullmatch)),
            table("WORD", "`\\w` = `str.isalnum()` 또는 `_`", ranges(WORD.fullmatch)),
            table(
                "NON_PRINTABLE",
                "`str.isprintable()`이 거짓 — `repr`이 이스케이프할 글자",
                ranges(lambda c: not c.isprintable()),
            ),
        ]
    )
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(head + "\n" + body + "\n")


if __name__ == "__main__":
    main()
