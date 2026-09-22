#!/usr/bin/env python3
"""뷰 CSS가 두 곳에서 같은지 — SYNC-STD-002.

정적 뷰(`tools/view_build.py`)와 React 유저용 탭(`frontend/src/styles.view.css`)이
같은 CSS를 써야 사람이 어디서 보든 같은 그림이 나온다. 규약은 그걸 요구하는데
지금까지 지키는 장치가 없어서, 한쪽만 고쳐도 조용히 갈라졌다.

첫 주석 블록은 파일마다 다르므로 벗기고 나머지를 문자열로 비교한다.

둘째·셋째 쌍(카드 Z): 배치 iframe의 FRAME_CSS·SANDBOX — `frontend/src/view/frame.ts` ↔ `tools/wf_build.py`.
같은 srcdoc 조립이어야 웹과 정적 뷰의 배치가 같은 그림이다.

넷째 쌍(카드 AC): 화면 뷰 CSS — `frontend/src/view/wireframe.ts wireframeCss` ↔ `tools/wf_build.py WF_SCREEN_CSS`.
탭·배치 틀·도구 줄·요소 표의 값이 여기 산다. 지금까지 우연히 같았을 뿐 대조하는 장치가 없어
한쪽만 고쳐도 잡히지 않았다(#134 조사에서 드러났다).

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
FRAME_TS = os.path.join(ROOT, "frontend", "src", "view", "frame.ts")
WF_PY = os.path.join(ROOT, "tools", "wf_build.py")
TS_FRAME = re.compile(r"export const FRAME_CSS = `(.*?)`", re.S)
PY_FRAME = re.compile(r'FRAME_CSS = r"""(.*?)"""', re.S)
TS_SANDBOX = re.compile(r"""export const SANDBOX = ["'](.*?)["']""")
PY_SANDBOX = re.compile(r'SANDBOX = "(.*?)"')
WF_TS = os.path.join(ROOT, "frontend", "src", "view", "wireframe.ts")
TS_SCREEN = re.compile(r"export const wireframeCss = `(.*?)`", re.S)
PY_SCREEN = re.compile(r'WF_SCREEN_CSS = r"""(.*?)"""', re.S)


def strip_header(text: str) -> str:
    """맨 앞 `/* … */` 주석 하나를 벗긴다. 두 파일이 서로를 가리키는 안내가 달라서다."""
    return re.sub(r"\A\s*/\*.*?\*/\s*", "", text, count=1, flags=re.S).strip()


def _diff(a: str, b: str, la: str, lb: str) -> None:
    xs, ys = a.split("\n"), b.split("\n")
    for i in range(max(len(xs), len(ys))):
        x, y = xs[i] if i < len(xs) else "(없음)", ys[i] if i < len(ys) else "(없음)"
        if x != y:
            print(f"   첫 차이 {i + 1}행")
            print(f"     {la}: {x[:120]}")
            print(f"     {lb}: {y[:120]}")
            break


def _pair(name: str, a: str | None, b: str | None, la: str, lb: str) -> bool:
    if a is None or b is None:
        print(f"✗  {name}: {'없음' if a is None else '있음'} / {'없음' if b is None else '있음'} — 상수를 못 찾았다")
        return False
    if a == b:
        print(f"{name}: 같음 ({len(a)} 바이트)")
        return True
    print(f"✗  {name}가 갈라졌다")
    print(f"   {la}: {len(a)} 바이트 / {lb}: {len(b)} 바이트")
    _diff(a, b, la, lb)
    return False


def main() -> int:
    css = strip_header(open(VIEW_CSS, encoding="utf-8").read())
    m = CSS_CONST.search(open(BUILDER, encoding="utf-8").read())
    built = m.group(1).strip() if m else None
    ok = _pair("뷰 CSS", css, built, "frontend/src/styles.view.css", "tools/view_build.py CSS")
    if not ok:
        print("   고칠 때는 view_build.py 를 먼저 고치고 그 내용을 styles.view.css 로 옮긴다")

    ts = open(FRAME_TS, encoding="utf-8").read() if os.path.exists(FRAME_TS) else ""
    py = open(WF_PY, encoding="utf-8").read()
    tf, pf = TS_FRAME.search(ts), PY_FRAME.search(py)
    ok &= _pair("프레임 CSS", tf.group(1).strip() if tf else None, pf.group(1).strip() if pf else None,
                "frontend/src/view/frame.ts", "tools/wf_build.py")
    ts_sb, py_sb = TS_SANDBOX.search(ts), PY_SANDBOX.search(py)
    ok &= _pair("sandbox", ts_sb.group(1) if ts_sb else None, py_sb.group(1) if py_sb else None,
                "frame.ts", "wf_build.py")
    wts = open(WF_TS, encoding="utf-8").read() if os.path.exists(WF_TS) else ""
    tw, pw = TS_SCREEN.search(wts), PY_SCREEN.search(py)
    ok &= _pair("화면 뷰 CSS", tw.group(1) if tw else None, pw.group(1) if pw else None,
                "frontend/src/view/wireframe.ts", "tools/wf_build.py WF_SCREEN_CSS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
