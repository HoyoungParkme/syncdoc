#!/usr/bin/env python3
"""SYNC-STD-004#DEV-17 — 와이어프레임↔React 일치 검사기.

화면 문서의 각 화면 배치 HTML에 있는 요소 번호(data-el) 집합과, 그 화면 컴포넌트(docstring 첫 줄에
`SYNC-UI-002#UI-N`)의 JSX에 있는 data-el 집합을 대조한다.
화면 헤딩 `UI-N`은 단계와 무관하게 잡는다(`#`~`#####`, 코드블록 밖). 구간은 다음 화면 헤딩까지 — 사이에
낀 절은 배치가 없으니 무해하다 (STD-001 2.7, 카드 X).
요소 표(`| # |` 표)가 있는 화면은 표의 `#` 열과 배치의 data-el도 맞춰 본다 — 어긋나면 `!`로 알리되
셋(명세 배치·요소 표·React) 중 코드 대조만 종료 코드를 정한다.
공용 컴포넌트에 넘긴 `el="2.3"`·`elRow="2.1"`, 객체 리터럴 `el: '3.1'`, 마운트 때 붙이는 `dataset.el = '7.1'`도 센다.
  · 명세에만: 와이어프레임에는 있는데 컴포넌트가 안 그린 요소
  · 코드에만: 컴포넌트가 그리는데 와이어프레임에 없는 번호 (오타 또는 명세 밖)
코드는 import하지 않고 텍스트만 읽는다.

사용: python tools/check_ui.py [--screens UI-10 UI-11 ...]   필터 없으면 컴포넌트가 있는 화면 전부.
      문서는 제목이 「와이어프레임」인 것, 없으면 「화면 설계」인 것 — 하나로 합친 프로젝트도 잡힌다.
      python tools/check_ui.py --specs <저장소>/docs/specs --frontend <저장소>/frontend/src
      종료 코드 1 = 어느 화면이든 불일치.

프로젝트 코드는 명세에서 읽는다 — `SYNC-`를 박아 두지 않는다 (STD-004 4장, #57).
코드가 아직 없는 프로젝트면 「볼 것이 없다」고 말하고 통과한다 — 명세만 있는 단계가 정상이다.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

import proj

SECTION = re.compile(r"^#{1,6} (UI-\d+)\b", re.M)
ELEM_HEAD = re.compile(r"^#{1,6}\s*요소\b", re.M)
NEXT_HEAD = re.compile(r"^#{1,6} ", re.M)
ELNO = re.compile(r"^\d+[a-z]?(?:\.\d+[a-z]?)*$")  # 4b.1처럼 가운데 글자도
HTML_BLOCK = re.compile(r"```html\n(.*?)```", re.S)
DATA_EL = re.compile(r'data-el="([^"]+)"')
JSX_EL = re.compile(r'data-el=(?:"([^"]+)"|\{([^}]*)\})')
PROP_EL = re.compile(r"""\bel(?:[A-Z]\w*)?(?:="([^"]+)"|: '([^']+)')""")
DATASET_EL = re.compile(r"dataset\.el = '([^']+)'")
LITERAL = re.compile(r"'([0-9]+(?:\.[0-9]+)?[a-z]?)'")


def mask_code(text: str) -> str:
    """코드블록 안을 같은 길이의 공백으로 — 위치는 그대로, 헤딩·표만 안 보이게."""
    return re.sub(r"```.*?(?:```|\Z)", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def table_elements(masked_body: str) -> set[str] | None:
    """요소 표의 `#` 열 — `요소` 소제목 아래 다음 헤딩 전까지 모든 표의 합집합. 표가 없으면 None."""
    h = ELEM_HEAD.search(masked_body)
    if not h:
        return None
    seg = masked_body[h.end() :]
    n = NEXT_HEAD.search(seg)
    seg = seg[: n.start()] if n else seg
    out: set[str] = set()
    for line in seg.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and ELNO.match(cells[0]):
            out.add(cells[0])
    return out


def spec_elements(spec: str) -> dict[str, tuple[set[str], set[str] | None]]:
    """화면 → (배치의 data-el 집합, 요소 표의 # 집합 또는 None)."""
    text = open(spec, encoding="utf-8").read()
    masked = mask_code(text)
    heads = list(SECTION.finditer(masked))
    out: dict[str, tuple[set[str], set[str] | None]] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body, mbody = text[m.end() : end], masked[m.end() : end]
        els: set[str] = set()
        for block in HTML_BLOCK.findall(body):
            els.update(DATA_EL.findall(block))
        out[m.group(1)] = (els, table_elements(mbody))
    return out


def code_elements(src: str, screen_of: re.Pattern[str]) -> dict[str, tuple[str, set[str]]]:
    """화면 → (파일, data-el 집합). 화면은 파일 첫 주석의 {CODE}-UI-002#UI-N."""
    out: dict[str, tuple[str, set[str]]] = {}
    for path in sorted(glob.glob(os.path.join(src, "**", "*.tsx"), recursive=True)):
        text = open(path, encoding="utf-8").read()
        head = text.split("*/", 1)[0] if text.startswith("/**") else ""
        m = screen_of.search(head)
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
        out[m.group(1)] = (os.path.relpath(path, os.path.dirname(src)), els)
    return out


def sort_key(el: str) -> tuple:
    nums = tuple(int(p) for p in re.sub(r"[a-z]$", "", el).split(".") if p.isdigit())
    return nums, el[-1] if el[-1].isalpha() else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    proj.add_specs(ap)
    ap.add_argument("--frontend", help="React 소스 뿌리 (기본: 명세와 같은 저장소의 frontend/src)")
    ap.add_argument("--screens", nargs="*", help="UI-10 UI-11 ...")
    args = ap.parse_args()
    project = proj.code_of(args.specs)
    # 번호가 아니라 제목으로 찾는다 — 서브타입은 제목이 가른다 (#57)
    spec_path = proj.by_title(args.specs, "UI", "와이어프레임") or proj.by_title(
        args.specs, "UI", "화면 설계"
    )
    if spec_path is None:
        print(f"{project}: 화면 문서가 없다 (UI 제목에 「와이어프레임」이나 「화면 설계」)")
        return 0
    src = args.frontend or os.path.join(proj.repo_of(args.specs), "frontend", "src")
    spec = spec_elements(spec_path)
    if not os.path.isdir(src):
        print(f"{project}: 화면 명세 {len(spec)}개 · 대조할 코드가 없다 ({src})")
        return 0
    doc_id = os.path.basename(spec_path)[:-3]
    code = code_elements(src, re.compile(rf"{doc_id}#(UI-\d+)"))
    screens = args.screens or sorted(code, key=lambda s: int(s.split("-")[1]))
    bad = 0
    for screen in screens:
        if screen not in spec:
            print(f"✗  {screen:6} 화면 절 없음")
            bad += 1
            continue
        if screen not in code:
            print(f"✗  {screen:6} 컴포넌트 없음 (docstring에 {doc_id}#{screen})")
            bad += 1
            continue
        path, got = code[screen]
        want, table = spec[screen]
        only_spec, only_code = sorted(want - got, key=sort_key), sorted(got - want, key=sort_key)
        ok = not only_spec and not only_code
        print(
            f"{'✓' if ok else '✗'}  {screen:6} {path:45} 요소 {len(want)} · 일치 {len(want & got)}"
        )
        if only_spec:
            print(f"      명세에만: {' '.join(only_spec)}")
        if only_code:
            print(f"      코드에만: {' '.join(only_code)}")
        if table is not None and table != want:
            # 요소 표는 사람용 설명이라 종료 코드에는 안 넣는다 — 그래도 침묵하지는 않는다
            if table - want:
                print(f"   !  요소 표에만: {' '.join(sorted(table - want, key=sort_key))}")
            if want - table:
                print(f"   !  배치에만(요소 표 없음): {' '.join(sorted(want - table, key=sort_key))}")
        bad += not ok
    print(f"\n합계: {project} · 화면 {len(screens)}, 일치 {len(screens) - bad}, 불일치 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
