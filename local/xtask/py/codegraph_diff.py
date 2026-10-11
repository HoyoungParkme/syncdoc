"""cargo xtask codegraph-diff — 폴더 하나에 파이썬 판 graphify 원형과 줄이기·보강 결과를 낸다(SYNC-MS-022, 카드 L12).

`uv run --project backend python local/xtask/py/codegraph_diff.py SRC OUT` — SRC는 커밋을 푼 폴더(graphify가
그 안에 graphify-out/을 만든다). Rust 판이 같은 원형·같은 폴더로 낸 답과 xtask가 비교한다.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

from app.core.codegraph import graph as cg
from app.infra import graphify

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import check_calls  # noqa: E402
import proj  # noqa: E402


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    specs = str(src / "docs" / "specs")
    raw = asyncio.run(graphify.extract(src))
    graph = cg.enrich(src, cg.reduce(copy.deepcopy(raw)))
    # 대조·층 — 검사기(check_calls)와 같은 재료
    items = check_calls.ms_items(specs)
    impl_of = proj.class_doc_of(specs)
    spec = cg.spec_calls(items, impl_of)
    diffs = cg.compare(graph, spec)
    bodies = [open(p, encoding="utf-8").read() for p in proj.all_by_title(specs, "DOM", "클래스")]
    rows = [r for b in bodies for r in cg.layer_table(b)]
    layer_of, unmatched = cg.layers(graph, rows)
    item_ids = sorted({f["item"] for f in graph["functions"] if f.get("item")})
    data = {
        "raw": raw,
        "enriched": graph,
        "items": items,
        "impl_of": impl_of,
        "bodies": bodies,
        "spec": {k: sorted(v) for k, v in spec.items()},
        "diffs": [
            {"ms_id": d.ms_id, "function": d.function, "same": d.same,
             "code_only": d.code_only, "spec_only": d.spec_only}
            for d in diffs
        ],  # fmt: skip
        "rows": rows,
        "layers": {k: layer_of[k] for k in sorted(layer_of)},
        "unmatched": unmatched,
        "item_function": {i: (cg.item_function(graph, i) or {}).get("key") for i in item_ids},
        "item_neighbors": {f["key"]: list(cg.item_neighbors(graph, f["key"])) for f in graph["functions"]},
    }
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
