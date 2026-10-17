"""cargo xtask codegraph-golden — 코드 그래프 정답 파일(SYNC-MS-022 0장, 카드 L12).

고정 시험 저장소(`crates/codegraph/tests/fixture`, 흐름은 `tests/flow_fixture` — 카드 L22)를 임시 자리에 베껴 graphify로 원형을 뽑고(파이썬 판
`codegraph.load`의 server 갈래), 파이썬 판의 줄이기·보강·커뮤니티(카드 L13) 결과와 함께 얼린다. Rust 시험이 같은 원형·같은
파일로 같은 답을 내는지 본다. 손으로 고치지 않는다 — 이 스크립트가 다시 만든다.
`uv run --project backend python local/xtask/py/codegraph_golden.py FIXTURE OUT`
"""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

import flow_cases
from app.core.codegraph import flow
from app.core.codegraph import graph as cg
from app.infra import graphify


def main() -> None:
    fixture, out = Path(sys.argv[1]), Path(sys.argv[2])
    flow_fixture = fixture.parent / "flow_fixture"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        shutil.copytree(fixture, src)
        raw = asyncio.run(graphify.extract(src))
        for k in ("extracted_sources", "failed_sources"):
            raw.pop(k, None)  # 절대 경로 — 자리마다 다르다
        reduced = cg.reduce(copy.deepcopy(raw))
        enriched = cg.enrich(src, cg.reduce(copy.deepcopy(raw)))
        grouped = cg.communities(copy.deepcopy(raw), cg.enrich(src, cg.reduce(copy.deepcopy(raw))))
    # 흐름 키(SYNC-MS-024 · MS-026, 카드 L22~L24) — 흐름 전용 시험 저장소의 원형과 더한 결과
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        shutil.copytree(flow_fixture, src)
        flow_raw = asyncio.run(graphify.extract(src))
        for k in ("extracted_sources", "failed_sources"):
            flow_raw.pop(k, None)
        flowed = flow.extend(src, cg.enrich(src, cg.reduce(copy.deepcopy(flow_raw))))
    data = {
        "raw": raw,
        "reduced": reduced,
        "enriched": enriched,
        "communities": grouped,
        "flow_raw": flow_raw,
        "flow": flowed,
        # 흐름 사례 — 파이썬 판 흐름 시험의 입력과 답(flow_cases.py)
        "flow_cases": [{**c, "out": flow_cases.run(c)} for c in flow_cases.cases()],
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
