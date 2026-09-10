"""SYNC-DOM-002 1장 core/markdown.py — 순수 함수. DB 없음. spec·reference가 같이 쓴다.

frontmatter 파싱 · 코드 마스킹(줄 수 유지) · 헤딩/참조 정규식 · 항목 블록 자르기. STD-001 1.3·1.5.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.core.types import ItemBlock

DOC_ID = re.compile(r"^[A-Z]{1,4}-[A-Z]+-\d{3}$")
REF = re.compile(r"\[\[([^\]]+)\]\]")
HEADING = re.compile(r"^(#{1,6}) (\S+)(?: (.*))?$")
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def parse_frontmatter(body: str) -> tuple[dict[str, str], int]:
    """frontmatter → (필드 dict, 차지하는 줄 수). 없으면 ({}, 0)."""
    m = FRONTMATTER.match(body)
    if not m:
        return {}, 0
    fm: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, m.group(0).count("\n")


def masked_lines(body: str) -> list[str]:
    """frontmatter·코드블록·인라인 코드를 같은 길이 공백으로. 줄 수 유지."""
    _, fm_lines = parse_frontmatter(body)
    out: list[str] = []
    in_block = False
    for i, line in enumerate(body.split("\n")):
        if i < fm_lines:
            out.append("")
            continue
        if line.startswith("```"):
            in_block = not in_block
            out.append("")
            continue
        if in_block:
            out.append("")
        else:
            out.append(re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line))
    return out


def headings(body: str) -> list[tuple[int, int, str, str]]:
    """마스킹한 본문의 헤딩 [(줄 idx, 레벨, 첫 토큰, 나머지)]."""
    out = []
    for i, line in enumerate(masked_lines(body)):
        h = HEADING.match(line)
        if h:
            out.append((i, len(h.group(1)), h.group(2), h.group(3) or ""))
    return out


def cut_blocks(body: str, is_item: Callable[[str], bool]) -> list[ItemBlock]:
    """항목 블록 = 항목 헤딩부터 같은 레벨 이상 다음 헤딩 직전까지. text는 원본 줄 범위."""
    lines = body.split("\n")
    heads = headings(body)
    blocks: list[ItemBlock] = []
    for n, (i, level, tok, rest) in enumerate(heads):
        if not is_item(tok):
            continue
        end = len(lines) - 1
        for j, lvl, _, _ in heads[n + 1 :]:
            if lvl <= level:
                end = j - 1
                break
        blocks.append(
            ItemBlock(
                item_id=tok,
                display_name=rest.strip(),
                level=level,
                start_line=i + 1,
                end_line=end + 1,
                text="\n".join(lines[i : end + 1]),
            )
        )
    return blocks
