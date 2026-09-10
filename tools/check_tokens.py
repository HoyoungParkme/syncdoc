#!/usr/bin/env python3
"""디자인 토큰이 명세와 같은지 — SYNC-UI-001 3장 ↔ frontend/src/styles.css `:root`.

명세의 토큰 표가 원본이고 CSS 변수는 그 전사다(SYNC-STD-004#DEV-17). 전사는 조용히 갈라진다 —
누가 CSS에서 색 하나를 고쳐도 아무도 모른다. 그래서 값을 대조한다.

**이름은 안 본다. 값의 집합만 본다.** 명세는 용도를 한국어로("배경 앱") 적고 CSS는 영어 이름
(`--bg-app`)을 쓰므로 이름을 이으려면 사람이 만든 대조표가 하나 더 필요해지고, 그 표가 또
갈라진다. 값 집합이 같으면 "명세에 없는 색을 쓰지 않았다"와 "명세의 색을 빠뜨리지 않았다"가
둘 다 확인된다.

타이포만 예외로 범위를 허용한다 — 명세가 `14.5~15px`처럼 폭으로 적은 행이 있다.

사용: python3 tools/check_tokens.py
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SPEC = os.path.join(ROOT, "docs", "specs", "07-UI", "SYNC-UI-001.md")
CSS = os.path.join(ROOT, "frontend", "src", "styles.css")

COLOR = re.compile(r"#[0-9a-fA-F]{6}|rgba?\([^)]*\)")
PX = re.compile(r"(\d+(?:\.\d+)?)px")
SHADOW = re.compile(r"`(\d[^`]*rgba\([^)]*\))`")


def spec_chapter() -> str:
    """3장만. 4장부터는 배치 이야기라 값이 예시로 섞여 있다."""
    text = open(SPEC, encoding="utf-8").read()
    return text.split("## 3. 디자인 토큰", 1)[1].split("\n## 4.", 1)[0]


def spec_section(ch: str, num: str) -> str:
    body = ch.split(f"### {num} ", 1)[1]
    return body.split("\n### ", 1)[0]


def css_root() -> dict[str, str]:
    text = open(CSS, encoding="utf-8").read()
    block = text.split(":root{", 1)[1].split("\n}", 1)[0]
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)  # 주석 안 값은 설명이다
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block))


def group(tokens: dict[str, str], prefix: str) -> dict[str, str]:
    return {k: v.strip() for k, v in tokens.items() if k.startswith(prefix)}


def compare(label: str, want: set[str], got: set[str], out: list[str]) -> None:
    for v in sorted(want - got):
        out.append(f"{label}: 명세에만 `{v}`")
    for v in sorted(got - want):
        out.append(f"{label}: CSS에만 `{v}`")


def norm(v: str) -> str:
    """비교용 표준형. 괄호 안 여백만 지운다 — `rgba(23, 24, 28, .3)`와 `rgba(23,24,28,.3)`은 같다.
    괄호 밖 여백은 남긴다. 그림자는 여백이 값의 일부고, 어긋났을 때 읽을 수 있어야 한다."""
    v = re.sub(r"\s+", " ", v.lower().strip())
    return re.sub(r"\(([^)]*)\)", lambda m: "(" + m.group(1).replace(" ", "") + ")", v)


def main() -> int:
    ch = spec_chapter()
    tok = css_root()
    bad: list[str] = []

    # 3.1 색 — 값 열의 hex·rgba 전부. var(...)로 다른 토큰을 가리키는 별칭은 새 값이 아니다
    want = {norm(c) for c in COLOR.findall(spec_section(ch, "3.1"))}
    got = {
        norm(v)
        for k, v in tok.items()
        if COLOR.fullmatch(v.strip()) and not k.startswith(("--shadow-", "--font-"))
    }
    compare("색", want, got, bad)

    # 3.2 타이포 — 명세는 `14.5~15px`처럼 폭으로 적기도 한다. 그 안이면 통과
    ranges: list[tuple[float, float]] = []
    for row in spec_section(ch, "3.2").split("\n"):
        m = re.search(r"\|\s*(\d+(?:\.\d+)?)(?:~(\d+(?:\.\d+)?))?px", row)
        if m:
            lo = float(m.group(1))
            ranges.append((lo, float(m.group(2)) if m.group(2) else lo))
    for k, v in sorted(group(tok, "--text-").items()):
        px = float(PX.match(v.strip()).group(1))  # type: ignore[union-attr]
        if not any(lo <= px <= hi for lo, hi in ranges):
            bad.append(f"타이포: `{k}: {v}`가 3.2 어느 행에도 안 맞는다")

    s33 = spec_section(ch, "3.3")
    line = {t.split(" ", 1)[0]: t for t in (x.strip("- ") for x in s33.split("\n")) if t}

    # 3.3 간격 — `2 · 3 · … · 30px`. px는 마지막에 한 번뿐이라 숫자만 센다
    compare(
        "간격",
        set(re.findall(r"\d+", line["간격"])),
        {v.removesuffix("px") for v in group(tok, "--space-").values()},
        bad,
    )
    # 3.3 모서리 — `3px 작은 뱃지 · … · 50% 점`. 값은 px 아니면 50%
    compare(
        "모서리",
        set(re.findall(r"\d+px|\d+%", line["모서리"])),
        set(group(tok, "--radius-").values()),
        bad,
    )
    # 3.3 겹침 순서 — 뒤 설명문("열린 깊이만큼 더한다")에는 숫자가 없다
    compare("겹침", set(re.findall(r"\d+", line["겹침"])), set(group(tok, "--z-").values()), bad)
    # 3.3 그림자 — 백틱 안 값 그대로
    compare(
        "그림자",
        {norm(x) for x in SHADOW.findall(line["그림자"])},
        {norm(v) for v in group(tok, "--shadow-").values()},
        bad,
    )

    for m in bad:
        print(f"⚠  {m}")
    print(f"\n합계: :root 토큰 {len(tok)} · 어긋남 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
