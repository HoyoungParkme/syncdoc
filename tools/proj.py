#!/usr/bin/env python3
"""검사기가 프로젝트 코드를 스스로 찾게 하는 공용 조각 — SYNC-STD-004 4장.

`SYNC-`를 상수로 박으면 싱크독 자기 명세에만 도는 도구가 된다. 실제로 보험 프로젝트
명세 14개에 검사기를 돌려 보니 `validate.py` 하나만 됐다(#57). 저장소 하나에 프로젝트
하나이므로([[SYNC-DOM-001#Project]]) `docs/specs/`의 문서 이름이 곧 답이다.

명세 뿌리는 `--specs`로 받고 기본값만 자기 저장소다.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEFAULT_SPECS = os.path.join(REPO, "docs", "specs")
# STD-001 1.1 {CODE}-{TYPE}-{NNN}. 코드는 대문자 1~4자 — 숫자는 안 들어간다
DOC_ID = re.compile(r"([A-Z]{1,4})-([A-Z]+)-(\d{3})")
# 템플릿·자산은 명세가 아니다 (STD-001 1.1, #52)
SKIP = ("_templates", "assets")


def add_specs(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--specs", default=DEFAULT_SPECS, help="docs/specs 경로")


def doc_files(specs: str) -> list[str]:
    return sorted(
        p
        for p in glob.glob(os.path.join(specs, "*", "*.md"))
        if not any(s in p.split(os.sep) for s in SKIP)
    )


def code_of(specs: str) -> str:
    """명세 파일 이름에서 프로젝트 코드를 읽는다.

    **못 읽으면 멈춘다.** 기본값으로 도로 넘어가면 남의 저장소에서 「0건」을 내는데,
    그게 「맞다」가 아니라 「안 봤다」다 (STD-004 4장).
    """
    codes = sorted(
        {
            m.group(1)
            for p in doc_files(specs)
            if (m := DOC_ID.fullmatch(os.path.basename(p)[:-3]))
        }
    )
    if not codes:
        sys.exit(f"명세를 찾지 못했다: {specs}")
    if len(codes) > 1:
        sys.exit(f"한 저장소에 프로젝트 코드가 둘 이상이다: {' '.join(codes)}")
    return codes[0]


def type_dir(specs: str, typ: str) -> str:
    """`DOM` → `docs/specs/06-DOM`. 번호를 박지 않고 읽어서 찾는다 (STD-001 1.1)."""
    hits = sorted(
        d
        for d in glob.glob(os.path.join(specs, "*"))
        if os.path.isdir(d) and re.fullmatch(rf"(\d\d-)?{typ}", os.path.basename(d))
    )
    if not hits:
        sys.exit(f"{typ} 디렉터리가 없다: {specs}")
    return hits[0]


def doc(specs: str, code: str, name: str) -> str:
    """`DOM-002` → `docs/specs/06-DOM/{code}-DOM-002.md`."""
    return os.path.join(type_dir(specs, name.split("-")[0]), f"{code}-{name}.md")


def title_of(path: str) -> str:
    """frontmatter의 title. 본문은 안 읽는다 — 본문에도 `title:`이 나올 수 있다."""
    head = open(path, encoding="utf-8").read().split("\n---", 1)[0]
    m = re.search(r"^title:\s*(.+)$", head, re.M)
    return m.group(1).strip() if m else ""


def by_title(specs: str, typ: str, keyword: str) -> str | None:
    """제목에 그 말이 든 문서. **번호로 찾지 않는다** (#57).

    한 타입 안의 서브타입은 번호가 아니라 제목이 가른다(SpecService.validate SUBTYPES).
    싱크독은 DOM-001이 도메인이지만 게시판 프로젝트는 DOM-001이 ERD다 — 번호로 찾으면
    남의 저장소에서 엉뚱한 문서를 읽고도 「경고 7건」처럼 그럴듯한 답을 낸다.
    """
    for path in sorted(glob.glob(os.path.join(type_dir(specs, typ), "*.md"))):
        if keyword in title_of(path):
            return path
    return None


def repo_of(specs: str) -> str:
    """`…/docs/specs` → 그 저장소의 뿌리. **코드 기본값은 명세와 같은 저장소다** —
    자기 저장소로 되돌아가면 남의 명세를 싱크독 코드와 대조하고도 그럴듯한 답을 낸다."""
    return os.path.normpath(os.path.join(specs, "..", ".."))
