#!/usr/bin/env python3
"""SYNC-STD-004#DEV-14 — MINISPEC 「호출하는 것」 ↔ 코드 호출 그래프 대조 검사기(카드 AX).

명세가 말한 호출과 실제 호출을 셋으로 가른다 — 같음 · 코드만(명세에 빠진 호출) · 명세만(코드에
없는 호출). **서버와 같은 함수로 센다**(backend/app/core/codegraph/graph.py) — 그래서 백엔드의 uv
환경에서 돈다(graphify가 백엔드 의존성이다):

    uv run --project backend python tools/check_calls.py
    uv run --project backend python tools/check_calls.py --doc SYNC-MS-007 --verbose
    uv run --project backend python tools/check_calls.py --specs <저장소>/docs/specs --root <저장소>

작업 트리(추적하는 파일 + 추적하지 않지만 무시되지 않는 파일)를 임시 폴더에 복사해 거기서
graphify를 돌린다 — 저장소에 `graphify-out/`을 남기지 않는다. 저장소에 graphify-out/graph.json이
커밋돼 있으면 서버처럼 그것을 쓴다.

종료 코드 1 = 코드만·명세만이 하나라도 있다(필터 범위 안에서). 「코드에 없음」은 셈에 안 든다 —
함수가 있는지는 check_code가 본다.

층(카드 BM) — 클래스 명세 「폴더 구조」 절의 층 표로 항목 없는 함수마다 층을 매긴다(서버와 같은
codegraph.layers). 어느 층에도 안 걸리는 함수(「층 없음」)와 어느 함수에도 안 맞는 표 줄(「안 맞는
줄」)도 0이어야 통과다(STD-004 DEV-14). `--doc`으로 좁혀도 층은 그래프 전체를 본다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import proj

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.core.codegraph import graph as codegraph  # noqa: E402

BLOCK = re.compile(r"^#### ", re.M)


def ms_items(specs: str) -> list[tuple[str, str]]:
    """MS 문서의 항목마다 (항목 ID, 블록 본문). 코드블록 안 헤딩은 항목이 아니다."""
    out: list[tuple[str, str]] = []
    for path in proj.doc_files(specs):
        doc = os.path.basename(path)[:-3]
        m = proj.DOC_ID.fullmatch(doc)
        if not m or m.group(2) != "MS":
            continue
        body = open(path, encoding="utf-8").read()
        # 코드블록 안의 `#### `는 항목이 아니다 — 펜스 안은 비운다
        lines, fence = [], False
        for line in body.split("\n"):
            if line.startswith("```"):
                fence = not fence
            lines.append("" if fence and line.startswith("#### ") else line)
        for blk in BLOCK.split("\n".join(lines))[1:]:
            name = blk.split(maxsplit=1)[0] if blk.strip() else ""
            if name:
                out.append((f"{doc}#{name}", blk))
    return out


def copy_tree(root: Path, dest: Path) -> None:
    """작업 트리를 복사한다 — 추적 파일과 무시되지 않는 새 파일. .git은 안 간다."""
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "-co", "--exclude-standard"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    for f in files:
        if not f:
            continue
        rel = f.decode()
        src = root / rel
        if not src.is_file():
            continue  # 지웠지만 아직 커밋 안 한 파일
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def main() -> int:
    ap = argparse.ArgumentParser()
    proj.add_specs(ap)
    ap.add_argument("--root", default=str(REPO), help="코드 저장소 뿌리(작업 트리)")
    ap.add_argument("--doc", nargs="*", help="이 MS 문서만 (예: SYNC-MS-007)")
    ap.add_argument("--verbose", action="store_true", help="같은 것까지 줄마다")
    args = ap.parse_args()

    code = proj.code_of(args.specs)
    items = ms_items(args.specs)
    if not items:
        print(f"합계: {code} · MINISPEC 없음 — 볼 것이 없다")
        return 0
    spec = codegraph.spec_calls(items)
    with tempfile.TemporaryDirectory(prefix="check-calls-") as tmp:
        src = Path(tmp)
        copy_tree(Path(args.root), src)
        source, raw = asyncio.run(codegraph.load(src))
        graph = codegraph.enrich(src, codegraph.reduce(raw))
    diffs = codegraph.compare(graph, spec)
    if args.doc:
        diffs = [d for d in diffs if d.ms_id.split("#")[0] in args.doc]

    same = code_only = spec_only = missing = 0
    for d in diffs:
        if d.function is None:
            missing += 1
            continue
        same += len(d.same)
        code_only += len(d.code_only)
        spec_only += len(d.spec_only)
        if d.code_only or d.spec_only or args.verbose:
            print(f"{d.ms_id}  ({d.function})")
            if d.code_only:
                print("  코드만:", " · ".join(x.split("#", 1)[1] for x in d.code_only))
            if d.spec_only:
                print("  명세만:", " · ".join(x.split("#", 1)[1] for x in d.spec_only))
            if args.verbose and d.same:
                print("  같음:  ", " · ".join(x.split("#", 1)[1] for x in d.same))
    # 층 — 클래스 명세의 층 표 (카드 BM)
    cls_doc = proj.by_title(args.specs, "DOM", "클래스")
    rows = codegraph.layer_table(open(cls_doc, encoding="utf-8").read()) if cls_doc else []
    if not rows:
        print(f"층 표 없음 — {os.path.basename(cls_doc) if cls_doc else 'DOM 클래스 명세'}의 「폴더 구조」 절")
    layer_of, unmatched = codegraph.layers(graph, rows)
    no_layer = [
        f
        for f in graph["functions"]
        if not (f.get("item") or f.get("ms")) and f["key"] not in layer_of
    ]
    for f in sorted(no_layer, key=lambda f: f["key"]):
        print(f"층 없음  {f['key']}  {f['qual']}")
    for r in unmatched:
        print(f"안 맞는 줄  {os.path.basename(cls_doc or '')}:{r['line']}  {' · '.join(r['patterns'])}")
    print(
        f"합계: {code} · 그래프 {source} 함수 {len(graph['functions'])} 호출 선 {len(graph['calls'])}"
        f" · 항목 {len(diffs)} · 같음 {same} · 코드만 {code_only} · 명세만 {spec_only}"
        f" · 코드에 없음 {missing} · 층 없음 {len(no_layer)} · 안 맞는 줄 {len(unmatched)}"
    )
    return 1 if code_only or spec_only or no_layer or unmatched else 0


if __name__ == "__main__":
    sys.exit(main())
