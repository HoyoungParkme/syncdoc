#!/usr/bin/env python3
"""명세의 미결사항을 모은다 — SYNC-STD-003 5장을 손으로 맞추지 않게.

각 문서의 `## N. 미결사항` 절에서 `- [ ]`(열림) · `- [x]`(닫힘) 줄을 읽는다.
STD-003 5장은 이 출력으로 만든다 — 사본을 손으로 고치면 원본과 벌어진다.

사용: python3 tools/open_items.py            열린 것만, 문서별
      python3 tools/open_items.py --all      닫힌 것까지
      python3 tools/open_items.py --markdown STD-003 5장에 넣을 목록
      python3 tools/open_items.py --check    STD-003 5장과 대조. 다르면 종료코드 1
"""

from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SPECS = os.path.join(ROOT, "docs", "specs")
MAP = os.path.join(SPECS, "STD", "SYNC-STD-003.md")
SECTION = re.compile(r"^## \d+\.\s*미결", re.M)
NEXT_SECTION = re.compile(r"^## ", re.M)
ITEM = re.compile(r"^- \[([ x])\] (.+)$", re.M)
DOC_ID = re.compile(r"^doc_id:\s*(\S+)", re.M)
# PRD 인수기준·CODE 카드 안 체크박스는 미결이 아니다 — 미결 절 안에서만 읽으므로 자연히 걸러진다


def outside_fences(text: str) -> str:
    """코드블록 안을 공백으로 덮은 사본. 규약 문서는 예시로 `## 5. 미결사항`을 적는다."""
    keep, fence = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
            keep.append("")
            continue
        keep.append("" if fence else line)
    return "\n".join(keep)


def items_of(path: str) -> tuple[str, list[tuple[bool, str]]]:
    text = open(path, encoding="utf-8").read()
    m = DOC_ID.search(text)
    doc_id = m.group(1) if m else os.path.basename(path)
    out: list[tuple[bool, str]] = []
    for sec in SECTION.finditer(outside_fences(text)):
        rest = outside_fences(text)[sec.end() :]
        end = NEXT_SECTION.search(rest)
        body = rest[: end.start()] if end else rest
        out += [(mark == "x", line.strip()) for mark, line in ITEM.findall(body)]
    return doc_id, out


def collect(include_map: bool = False) -> list[tuple[str, list[tuple[bool, str]]]]:
    paths = sorted(p for p in glob.glob(os.path.join(SPECS, "*", "*.md")) if "_templates" not in p)
    out = []
    for p in paths:
        if not include_map and os.path.abspath(p) == os.path.abspath(MAP):
            continue  # 자기 사본은 세지 않는다
        doc_id, items = items_of(p)
        if items:
            out.append((doc_id, items))
    return out


def markdown(rows) -> str:
    lines = []
    for doc_id, items in rows:
        open_ones = [t for done, t in items if not done]
        if not open_ones:
            continue
        lines.append(f"**{doc_id}**")
        lines += [f"- [ ] {t}" for t in open_ones]
        lines.append("")
    if not lines:  # 하나도 안 열려 있으면 빈 절이 아니라 그렇다고 적는다
        return "_열린 미결이 없다. 각 문서의 미결사항 절에 결정과 함께 닫혀 있다._\n"
    return "\n".join(lines).rstrip() + "\n"


def list_lines(block: str) -> list[str]:
    """문서 제목(**…**)과 열린 항목(- [ ])만. 머리말·빈 줄은 뺀다."""
    keep = []
    for ln in block.splitlines():
        ln = ln.rstrip()
        if ln.startswith("- [ ] ") or (ln.startswith("**") and ln.endswith("**")) or ln.startswith("_"):
            keep.append(ln)
    return keep


def main() -> int:
    args = sys.argv[1:]
    rows = collect()
    if "--markdown" in args or "--check" in args:
        want = markdown(rows)
        if "--markdown" in args:
            print(want, end="")
            return 0
        text = open(MAP, encoding="utf-8").read()
        m = re.search(r"^## \d+\.\s*미결 모음\n(.*?)(?=^## )", text, re.S | re.M)
        have = m.group(1) if m else ""
        # 양쪽을 다 본다 — 빠진 줄뿐 아니라 닫혔는데 5장에 남은 줄도 낡음이다
        ok = list_lines(have) == list_lines(want)
        print("STD-003 5장: " + ("최신" if ok else "낡음 — --markdown 출력으로 갈아 끼워라"))
        return 0 if ok else 1
    show_done = "--all" in args
    n_open = n_done = 0
    for doc_id, items in rows:
        shown = [(d, t) for d, t in items if show_done or not d]
        n_open += sum(1 for d, _ in items if not d)
        n_done += sum(1 for d, _ in items if d)
        if not shown:
            continue
        print(f"\n{doc_id}")
        for done, t in shown:
            print(f"  [{'x' if done else ' '}] {t[:110]}")
    print(f"\n합계: 열림 {n_open}, 닫힘 {n_done}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
