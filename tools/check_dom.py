#!/usr/bin/env python3
"""DOM 세 문서의 이름이 서로 맞는지 — SYNC-STD-001 4장 `dom.name`.

도메인(DOM-001)·클래스(DOM-002)·데이터(DOM-003)가 같은 개념을 다른 이름으로 부르면
읽는 사람도 에이전트도 헷갈린다. 이름 규칙을 추측하지 않고, **클래스 명세가 항목마다
적어 둔 링크를 정답으로 삼는다.**

    #### Document 문서
    테이블: [[SYNC-DOM-003#documents]] · 도메인: [[SYNC-DOM-001#Document]]

링크가 없는 클래스는 "테이블 없음"을 선언한 것으로 읽는다 — DTO·열거형이 저절로 걸러진다.

**이름만 본다. 컬럼은 아직 안 본다.** 컬럼까지 대조하면 지금 명세에서 경고가 23건 나온다 —
DD 표가 `id`·외래키·표준 시각을 싣기도 하고 빼기도 해서 규약이 일정하지 않기 때문이다.
어느 컬럼을 표에 싣는지를 먼저 정해야 컬럼 검사가 쓸모 있어진다. `class_attrs`와
`table_columns`를 남겨 두었으니 그때 이어 붙이면 된다.

경고만 낸다. 세 문서가 서로 다른 시점에 진행되므로 저장을 막지 않는다(STD-001 4장).

사용: python3 tools/check_dom.py          경고만
      python3 tools/check_dom.py --all    맞는 것까지
      python3 tools/check_dom.py --specs <다른 저장소>/docs/specs

프로젝트 코드는 명세에서 읽는다 — `SYNC-`를 박아 두지 않는다 (STD-004 4장, #57).
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import proj

ITEM = re.compile(r"^#{1,6} ([A-Za-z_][A-Za-z0-9_]*)\s", re.M)


def read(path: str) -> str:
    return open(path, encoding="utf-8").read()


def outside_fences(text: str) -> str:
    """코드블록 안을 지운 사본. 예시 헤딩을 항목으로 세지 않는다."""
    keep, fence = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
            keep.append("")
            continue
        keep.append("" if fence else line)
    return "\n".join(keep)


def items_of(path: str) -> set[str]:
    return set(ITEM.findall(outside_fences(read(path))))


CLASS_BLOCK = re.compile(r"class (\w+) \{(.*?)\}", re.S)
DD_TABLE = re.compile(r"^### ([a-z_][a-z0-9_]*)\n(.*?)(?=^### |\Z)", re.S | re.M)


def class_attrs(class_doc: str) -> dict[str, set[str]]:
    """클래스 2장(엔티티) mermaid의 `+타입 이름` 속성.

    4장(설계)과의 대조는 validate의 `entity.mismatch`가 이미 한다.
    """
    text = read(class_doc).split("## 3.")[0]
    return {
        m.group(1): {a.split()[-1] for a in m.group(2).split("\n") if a.strip().startswith("+")}
        for m in CLASS_BLOCK.finditer(text)
    }


def table_columns(data_doc: str) -> dict[str, set[str]]:
    """DD 표의 첫 열. 표는 `id`처럼 자명한 것을 줄여 적으므로 있는 것만 모은다."""
    text = outside_fences(read(data_doc))
    out: dict[str, set[str]] = {}
    for m in DD_TABLE.finditer(text):
        names = set()
        for row in m.group(2).split("\n"):
            if not row.startswith("|") or "---" in row:
                continue
            first = row.split("|")[1].strip()
            if first and first != "컬럼":
                names.add(first)
        out[m.group(1)] = names
    return out


def class_links(class_doc: str, link: re.Pattern[str]) -> dict[str, dict[str, str]]:
    """{클래스: {"테이블": 이름, "도메인": 이름}}. 항목 헤딩 바로 아래 줄만 본다."""
    text = outside_fences(read(class_doc))
    out: dict[str, dict[str, str]] = {}
    current = None
    for line in text.split("\n"):
        m = ITEM.match(line + " ")
        if m:
            current = m.group(1)
            continue
        if current:
            found = dict(link.findall(line))
            if found:
                out[current] = found
                current = None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    proj.add_specs(ap)
    ap.add_argument("--all", action="store_true", help="맞는 것까지 보인다")
    a = ap.parse_args()
    code = proj.code_of(a.specs)
    show_ok = a.all
    # **번호가 아니라 제목으로 찾는다** — 싱크독은 DOM-001이 도메인이지만 게시판
    # 프로젝트는 DOM-001이 ERD다. 번호로 찾으면 엉뚱한 문서를 읽고도 답을 낸다 (#57)
    paths = {k: proj.by_title(a.specs, "DOM", k) for k in ("도메인", "클래스", "ERD")}
    missing = [k for k, v in paths.items() if v is None]
    if missing:
        print(f"{code}: DOM 문서를 못 찾았다 — 제목에 {' · '.join(missing)}이(가) 없다")
        return 0
    domain = items_of(paths["도메인"])
    tables = items_of(paths["ERD"])
    links = class_links(
        paths["클래스"],
        # 링크 대상 문서 번호는 안 본다 — 어느 문서의 항목인지는 뒤에서 집합으로 가른다
        re.compile(r"(테이블|도메인):\s*\[\[[^\]#]+#([^\]]+)\]\]"),
    )
    warnings: list[tuple[str, str]] = []

    linked_tables = set()
    name = {k: os.path.basename(v)[:-3] for k, v in paths.items()}
    for cls, refs in links.items():
        table, concept = refs.get("테이블"), refs.get("도메인")
        if table:
            linked_tables.add(table)
            if table not in tables:
                warnings.append((cls, f"테이블 `{table}`이 {name['ERD']}에 없다"))
            elif show_ok:
                print(f"✓  {cls:24} 테이블 {table}")
        if concept:
            if concept not in domain:
                warnings.append((cls, f"도메인 `{concept}`이 {name['도메인']}에 없다"))
            elif show_ok:
                print(f"✓  {cls:24} 도메인 {concept}")

    for t in sorted(tables - linked_tables):
        warnings.append(("—", f"테이블 `{t}`을 가리키는 클래스가 없다"))

    for cls, msg in warnings:
        print(f"⚠  {cls:24} dom.name: {msg}")
    print(
        f"\n합계: {code} · 클래스 {len(links)} · 테이블 {len(tables)}"
        f" · 개념 {len(domain)} · 경고 {len(warnings)}"
    )
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
