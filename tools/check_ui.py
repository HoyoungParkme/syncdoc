#!/usr/bin/env python3
"""SYNC-STD-004#DEV-17 — 와이어프레임↔React 일치 검사기.

UI-002 각 화면의 배치 HTML에 있는 요소 번호(data-el) 집합과, 그 화면 컴포넌트(docstring 첫 줄에
`SYNC-UI-002#UI-N`)의 JSX에 있는 data-el 집합을 대조한다.
공용 컴포넌트에 넘긴 `el="2.3"`·`elRow="2.1"`, 객체 리터럴 `el: '3.1'`, 마운트 때 붙이는 `dataset.el = '7.1'`도 센다.
  · 명세에만: 와이어프레임에는 있는데 컴포넌트가 안 그린 요소
  · 코드에만: 컴포넌트가 그리는데 와이어프레임에 없는 번호 (오타 또는 명세 밖)
코드는 import하지 않고 텍스트만 읽는다.

사용: python tools/check_ui.py [--screens UI-10 UI-11 ...]   필터 없으면 컴포넌트가 있는 화면 전부.
      종료 코드 1 = 어느 화면이든 불일치.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SPEC = os.path.join(ROOT, "docs", "specs", "07-UI", "SYNC-UI-002.md")  # STD-001 1.1 {NN-TYPE}
SRC = os.path.join(ROOT, "frontend", "src")
SECTION = re.compile(r"^## (UI-\d+) ", re.M)
HTML_BLOCK = re.compile(r"```html\n(.*?)```", re.S)
DATA_EL = re.compile(r'data-el="([^"]+)"')
JSX_EL = re.compile(r'data-el=(?:"([^"]+)"|\{([^}]*)\})')
PROP_EL = re.compile(r"""\bel(?:[A-Z]\w*)?(?:="([^"]+)"|: '([^']+)')""")
DATASET_EL = re.compile(r"dataset\.el = '([^']+)'")
LITERAL = re.compile(r"'([0-9]+(?:\.[0-9]+)?[a-z]?)'")
SCREEN_OF = re.compile(r"SYNC-UI-002#(UI-\d+)")


def spec_elements() -> dict[str, set[str]]:
    text = open(SPEC, encoding="utf-8").read()
    heads = list(SECTION.finditer(text))
    out: dict[str, set[str]] = {}
    for i, m in enumerate(heads):
        body = text[m.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        els: set[str] = set()
        for block in HTML_BLOCK.findall(body):
            els.update(DATA_EL.findall(block))
        out[m.group(1)] = els
    return out


def code_elements() -> dict[str, tuple[str, set[str]]]:
    """화면 → (파일, data-el 집합). 화면은 파일 첫 주석의 SYNC-UI-002#UI-N."""
    out: dict[str, tuple[str, set[str]]] = {}
    for path in sorted(glob.glob(os.path.join(SRC, "**", "*.tsx"), recursive=True)):
        text = open(path, encoding="utf-8").read()
        head = text.split("*/", 1)[0] if text.startswith("/**") else ""
        m = SCREEN_OF.search(head)
        if not m:
            continue
        els: set[str] = set()
        for lit, expr in JSX_EL.findall(text):
            if lit:
                els.add(lit)
            else:
                els.update(LITERAL.findall(expr))
        els.update(a or b for a, b in PROP_EL.findall(text))
        els.update(DATASET_EL.findall(text))
        out[m.group(1)] = (os.path.relpath(path, ROOT), els)
    return out


def sort_key(el: str) -> tuple:
    nums = tuple(int(p) for p in re.sub(r"[a-z]$", "", el).split(".") if p.isdigit())
    return nums, el[-1] if el[-1].isalpha() else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screens", nargs="*", help="UI-10 UI-11 ...")
    args = ap.parse_args()
    spec, code = spec_elements(), code_elements()
    screens = args.screens or sorted(code, key=lambda s: int(s.split("-")[1]))
    bad = 0
    for screen in screens:
        if screen not in spec:
            print(f"✗  {screen:6} 와이어프레임 절 없음")
            bad += 1
            continue
        if screen not in code:
            print(f"✗  {screen:6} 컴포넌트 없음 (docstring에 SYNC-UI-002#{screen})")
            bad += 1
            continue
        path, got = code[screen]
        want = spec[screen]
        only_spec, only_code = sorted(want - got, key=sort_key), sorted(got - want, key=sort_key)
        ok = not only_spec and not only_code
        print(
            f"{'✓' if ok else '✗'}  {screen:6} {path:45} 요소 {len(want)} · 일치 {len(want & got)}"
        )
        if only_spec:
            print(f"      명세에만: {' '.join(only_spec)}")
        if only_code:
            print(f"      코드에만: {' '.join(only_code)}")
        bad += not ok
    print(f"\n합계: 화면 {len(screens)}, 일치 {len(screens) - bad}, 불일치 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
