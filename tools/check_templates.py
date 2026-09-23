#!/usr/bin/env python3
"""템플릿이 자기 타입·서브타입의 필수 절을 다 갖췄는지 — SYNC-STD-001 1.1 (카드 AG).

템플릿대로 쓰면 미완성 경고가 안 나야 한다. 다른 검사기는 모두 `_templates/`를 건너뛴다 —
템플릿은 doc_id가 비어 있는 것이 정상이라 세면 가짜 위반이 쏟아지기 때문이다. 그 사이에
DOM 템플릿이 도메인 모델 골격만 든 채로 오래 살아남았고, 그대로 쓴 클래스 명세·ERD는
**반드시** 미완성이 됐다(#114). 이 검사기가 그 틈을 본다.

타입·서브타입마다:
  1. 쓸 템플릿 — `{TYPE}-{서브타입}.md`가 있으면 그것, 없으면 `{TYPE}.md`
     (MCP get_template이 고르는 규칙과 같다 — backend/app/mcp/tools.py)
  2. 제목에 서브타입 낱말이 있는가 — 없으면 그대로 쓴 문서가 `frontmatter.title.subtype` 위반
  3. 필수 절이 다 있는가 — validate와 같은 대조(번호를 떼고 앞부분 일치)
  4. 항목 예시가 하나라도 항목 패턴에 맞는가 — 안 맞으면 그대로 쓴 문서가 「항목이 하나도 없음」
     (CODE·STD는 항목 없는 문서가 정상이라 빼는 것도 validate와 같다)

본 것의 수를 함께 낸다(STD-004 DEV-17) — 0이면 실패다.

사용: python3 tools/check_templates.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import SUBTYPES, TYPES, strip_code  # noqa: E402 — 같은 폴더의 규약 원형

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TEMPLATES = os.path.join(ROOT, "docs", "specs", "_templates")
NO_ITEMS_OK = ("CODE", "STD")


def targets() -> list[tuple[str, str | None, list[str], list[str]]]:
    """(타입, 서브타입 또는 None, 항목 패턴, 필수 절) — 규약이 정한 것 전부."""
    out: list[tuple[str, str | None, list[str], list[str]]] = []
    for typ, (pats, secs) in TYPES.items():
        subs = [(k, p, s) for (t, k), (p, s) in SUBTYPES.items() if t == typ]
        if subs:
            out.extend((typ, k, p, s) for k, p, s in subs)
        else:
            out.append((typ, None, pats, secs or []))
    return out


def template_for(typ: str, sub: str | None) -> str:
    """서브타입 파일이 있으면 그것, 없으면 타입 파일 (get_template과 같은 규칙)."""
    if sub:
        own = os.path.join(TEMPLATES, f"{typ}-{sub}.md")
        if os.path.exists(own):
            return own
    return os.path.join(TEMPLATES, f"{typ}.md")


def read(path: str) -> tuple[str, str]:
    """제목과 본문(frontmatter 뒤)."""
    raw = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m:
        return "", raw
    title = ""
    for line in m.group(1).split("\n"):
        k, _, v = line.partition(":")
        if k.strip() == "title":
            title = v.strip()
    return title, raw[m.end() :]


def headings(body: str, item_re: re.Pattern[str] | None) -> tuple[list[str], list[str]]:
    """절 이름들(번호 뗀 것)과 항목 토큰들 — validate의 헤딩 순회와 같게."""
    sections, items = [], []
    for line in strip_code(body).split("\n"):
        h = re.match(r"^(#{1,6}) (.+)$", line)
        if not h:
            continue
        tok = h.group(2).split(" ")[0]
        if item_re and item_re.match(tok):
            items.append(tok)
        else:
            sections.append(re.sub(r"^[\d.]+\s*", "", h.group(2)))
    return sections, items


def main() -> int:
    bad = seen = 0
    used: set[str] = set()
    for typ, sub, pats, secs in targets():
        path = template_for(typ, sub)
        name = f"{typ}·{sub}" if sub else typ
        rel = os.path.basename(path)
        if not os.path.exists(path):
            print(f"✗  {name:14} {rel} — 파일이 없다")
            bad += 1
            continue
        used.add(rel)
        seen += 1
        title, body = read(path)
        item_re = re.compile(r"^(?:" + "|".join(pats) + r")$") if pats else None
        sections, items = headings(body, item_re)
        problems = []
        # 서브타입 파일이면 그 낱말이, 여럿이 나눠 쓰는 파일이면 그중 하나가 제목에 있어야 한다 —
        # frontmatter.title.subtype 위반의 조건 그대로다(「중 하나」, STD-001 3장)
        own = os.path.basename(path) != f"{typ}.md"
        keys = [sub] if own else [k for t, k in SUBTYPES if t == typ]
        if sub and not any(k in title for k in keys):
            want = "·".join(f"「{k}」" for k in keys)
            problems.append(f"제목에 {want}가 없다 — 그대로 쓰면 frontmatter.title.subtype 위반")
        missing = [s for s in secs if not any(x.startswith(s) for x in sections)]
        if missing:
            problems.append(f"필수 절 없음: {' · '.join(missing)}")
        if not items and typ not in NO_ITEMS_OK:
            problems.append("항목 예시가 항목 패턴에 안 맞는다 — 그대로 쓰면 「항목이 하나도 없음」")
        if problems:
            bad += 1
            print(f"✗  {name:14} {rel}")
            for p in problems:
                print(f"      {p}")
        else:
            print(f"✓  {name:14} {rel:18} 필수 절 {len(secs)} · 항목 예시 {len(items)}")
    # 서브타입 파일이 다 있는 타입의 {TYPE}.md는 고르는 안내다. 그 밖에 아무도 안 쓰는 파일은 알린다
    files = sorted(f for f in os.listdir(TEMPLATES) if f.endswith(".md"))
    choosers = {
        f"{t}.md"
        for t in TYPES
        if any(tt == t for tt, _ in SUBTYPES)
        and all(os.path.exists(os.path.join(TEMPLATES, f"{tt}-{k}.md")) for tt, k in SUBTYPES if tt == t)
    }
    for f in files:
        if f not in used and f not in choosers:
            print(f"!  {f} — 어느 타입·서브타입도 이 파일을 쓰지 않는다")
    if not seen:
        print("템플릿을 하나도 못 읽었다 — docs/specs/_templates/를 확인하라")
        return 1
    print(f"\n합계: 템플릿 {len(files)} · 대상 {seen}(타입·서브타입) · 고르는 안내 {len(choosers)} · 모자람 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
