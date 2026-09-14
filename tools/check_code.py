from __future__ import annotations

#!/usr/bin/env python3
"""SYNC-STD-004#DEV-14 — MINISPEC↔코드 일치 검사기.

MS 문서의 항목(시그니처)과 코드의 함수(docstring 첫 줄 = 항목 ID, DEV-3)를 대조한다.
  · 있음/없음: MS에 있는데 코드에 없거나(없음), 코드에 있는데 MS에 없으면(명세 밖) 미완
  · 시그니처: async 여부 · 인자 이름·타입·기본값 · 반환 타입 (공백·따옴표 무시)
코드는 import하지 않고 AST만 읽는다 — DB·환경 변수가 없어도 돈다.

사용: python tools/check_code.py [--doc SYNC-MS-006 ...] [--items ID ...]
      python tools/check_code.py --specs <저장소>/docs/specs --backend <저장소>/app
      필터 없으면 MS 전부. 종료 코드 1 = 불일치 또는 (필터 범위 안에서) 없음.

프로젝트 코드는 명세에서 읽는다 — `SYNC-`를 박아 두지 않는다 (STD-004 4장, #57).
**코드도 훑어서 찾는다** — 예전에는 파일 목록을 상수로 들고 있어 남의 저장소에서는
아무것도 못 봤다. 이제 `--backend` 아래 `.py` 전부에서 `{CODE}-MS-NNN#항목` docstring을
찾는다. 코드가 아직 없는 프로젝트면 「볼 것이 없다」고 말하고 통과한다.
"""

import argparse
import ast
import glob
import os
import re
import sys

import proj

ITEM = re.compile(r"^#{1,6} ([A-Za-z_]+\.[a-z_]+)\b", re.M)
SIG_INLINE = re.compile(r"\*\*시그니처\*\*\s*`([^`]+)`")
SIG_BLOCK = re.compile(r"\*\*시그니처\*\*\s*\n```python\n(.*?)```", re.S)
SIG = re.compile(r"^(async def |def )?(\w+)\((.*)\)\s*->\s*(.+)$", re.S)


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s).replace('"', "'")


def spec_items(specs: str, code: str) -> dict[str, tuple[str, bool, str, str] | None]:
    """{항목ID: (doc_id, async, params, ret)} · 시그니처를 못 읽으면 None."""
    out = {}
    for path in sorted(glob.glob(os.path.join(proj.type_dir(specs, "MS"), f"{code}-MS-*.md"))):
        text = open(path, encoding="utf-8").read()
        doc = os.path.basename(path)[:-3]
        heads = list(ITEM.finditer(text))
        for i, h in enumerate(heads):
            block = text[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            m = SIG_BLOCK.search(block) or SIG_INLINE.search(block)
            sig = SIG.match(" ".join(m.group(1).split())) if m else None
            out[h.group(1)] = (
                (
                    doc,
                    (sig.group(1) or "").startswith("async"),
                    norm(sig.group(3)),
                    norm(sig.group(4)),
                )
                if sig
                else None
            )
    return out


def code_items(backend: str, code: str) -> tuple[dict[str, tuple[str, bool, str, str]], int]:
    """({docstring 항목ID: (파일, async, params, ret)}, 훑은 파일 수)

    파일 목록을 상수로 들지 않고 뿌리 아래 `.py`를 전부 훑는다 — 상수로 들면 남의
    저장소에서 0건을 내고, 그게 「맞다」가 아니라 「안 봤다」다 (STD-004 4장, #57).
    """
    out = {}
    files = sorted(glob.glob(os.path.join(backend, "**", "*.py"), recursive=True))
    for path in files:
        rel = os.path.relpath(path, os.path.dirname(backend))
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            doc = ast.get_docstring(node) or ""
            first = doc.split("\n", 1)[0].strip()
            if "#" not in first or not first.startswith(f"{code}-MS-"):
                continue
            args = [a for a in node.args.args if a.arg not in ("self", "cls")]
            defaults = [None] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
            params = ",".join(
                f"{a.arg}:{ast.unparse(a.annotation) if a.annotation else '?'}"
                + (f"={ast.unparse(d)}" if d is not None else "")
                for a, d in zip(args, defaults, strict=True)
            )
            ret = ast.unparse(node.returns) if node.returns else "?"
            out[first.split("#", 1)[1]] = (
                rel,
                isinstance(node, ast.AsyncFunctionDef),
                norm(params),
                norm(ret),
            )
    return out, len(files)


def main() -> int:
    ap = argparse.ArgumentParser()
    proj.add_specs(ap)
    ap.add_argument("--backend", help="파이썬 소스 뿌리 (기본: 명세와 같은 저장소의 backend/app)")
    ap.add_argument("--doc", nargs="*", default=[])
    ap.add_argument("--items", nargs="*", default=[])
    a = ap.parse_args()
    project = proj.code_of(a.specs)
    spec = spec_items(a.specs, project)
    backend = a.backend or os.path.join(proj.repo_of(a.specs), "backend", "app")
    if not os.path.isdir(backend):
        print(f"{project}: MINISPEC 항목 {len(spec)}개 · 대조할 코드가 없다 ({backend})")
        return 0
    code, seen = code_items(backend, project)
    scope = {
        k
        for k, v in spec.items()
        if (not a.doc or (v and v[0] in a.doc)) and (not a.items or k in a.items)
    }
    bad = 0
    for k in sorted(scope):
        s, c = spec[k], code.get(k)
        if s is None:
            print(f"?  {k:45s} 시그니처를 못 읽음 (MS 형식)")
            continue
        if c is None:
            print(f"✗  {k:45s} 없음")
            bad += 1
        elif (s[1], s[2], s[3]) != (c[1], c[2], c[3]):
            bad += 1
            print(f"✗  {k:45s} 불일치")
            print(f"     MS  : {'async ' if s[1] else ''}({s[2]}) -> {s[3]}")
            print(f"     code: {'async ' if c[1] else ''}({c[2]}) -> {c[3]}")
        else:
            print(f"✓  {k}")
    extra = sorted(k for k in code if k not in spec)
    for k in extra:
        print(f"✗  {k:45s} 명세 밖 — MINISPEC에 없는 함수 ({code[k][0]})")
    bad += len(extra)
    ok = sum(1 for k in scope if code.get(k) and spec[k] and (spec[k][1:] == code[k][1:]))
    print(f"\n합계: {project} · 파일 {seen} · 대상 {len(scope)}, 일치 {ok}, 미완 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
