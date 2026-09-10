#!/usr/bin/env python3
"""뷰 CSS가 두 곳에서 같은지 — SYNC-STD-002.

정적 뷰(`tools/view_build.py`)와 React 유저용 탭(`frontend/src/styles.view.css`)이
같은 CSS를 써야 사람이 어디서 보든 같은 그림이 나온다. 규약은 그걸 요구하는데
지금까지 지키는 장치가 없어서, 한쪽만 고쳐도 조용히 갈라졌다.

첫 주석 블록은 파일마다 다르므로 벗기고 나머지를 문자열로 비교한다.

사용: python3 tools/check_view_css.py
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
VIEW_CSS = os.path.join(ROOT, "frontend", "src", "styles.view.css")
BUILDER = os.path.join(ROOT, "tools", "view_build.py")
CSS_CONST = re.compile(r'CSS = r"""(.*?)"""', re.S)


def strip_header(text: str) -> str:
    """맨 앞 `/* … */` 주석 하나를 벗긴다. 두 파일이 서로를 가리키는 안내가 달라서다."""
    return re.sub(r"\A\s*/\*.*?\*/\s*", "", text, count=1, flags=re.S).strip()


def main() -> int:
    css = strip_header(open(VIEW_CSS, encoding="utf-8").read())
    m = CSS_CONST.search(open(BUILDER, encoding="utf-8").read())
    if not m:
        print(f"✗  {BUILDER} 에서 CSS 상수를 못 찾았다")
        return 1
    built = m.group(1).strip()

    if css == built:
        print(f"뷰 CSS: 같음 ({len(css)} 바이트)")
        return 0

    print("✗  뷰 CSS가 갈라졌다")
    print(f"   frontend/src/styles.view.css : {len(css)} 바이트")
    print(f"   tools/view_build.py CSS      : {len(built)} 바이트")
    a, b = css.split("\n"), built.split("\n")
    for i in range(max(len(a), len(b))):
        x, y = a[i] if i < len(a) else "(없음)", b[i] if i < len(b) else "(없음)"
        if x != y:
            print(f"   첫 차이 {i + 1}행")
            print(f"     styles.view.css : {x[:120]}")
            print(f"     view_build.py   : {y[:120]}")
            break
    print("   고칠 때는 view_build.py 를 먼저 고치고 그 내용을 styles.view.css 로 옮긴다")
    return 1


if __name__ == "__main__":
    sys.exit(main())
