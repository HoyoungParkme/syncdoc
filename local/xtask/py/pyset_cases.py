"""파이썬 3.12 정수 set의 순회 차례 정답 (카드 L8, core pycompat::pyset).

`uv run --project ../backend python xtask/py/pyset_cases.py > crates/core/tests/golden/pyset.json`
씨앗 고정 — 넣기·빼기 차례와 그때마다의 순회 차례를 적는다. 손으로 고치지 않는다.
"""

import json
import random
import sys

assert sys.version_info[:2] == (3, 12), sys.version


def case(r: random.Random) -> dict:
    hi = r.choice([16, 64, 500, 5000, 10**6])
    n = r.choice([0, 1, 3, 5, 6, 7, 20, 50, 120, 400])
    ops: list[list] = []
    s: set[int] = set()
    for _ in range(n):
        if s and r.random() < 0.12:
            v = r.choice(sorted(s)) if r.random() < 0.8 else r.randint(0, hi)
            s.discard(v)
            ops.append(["discard", v])
        else:
            v = r.randint(0, hi)
            s.add(v)
            ops.append(["add", v])
    return {"ops": ops, "order": list(s)}


r = random.Random(20261011)
cases = [case(r) for _ in range(400)]
# item_chain 꼴 — 너비 우선으로 넣고 끝에 시작점을 뺀다
for start in [1, 7, 40, 300]:
    ops, s = [], set()
    for v in [start + 3, start + 1, start, start + 9, start + 2, start + 17, start + 8]:
        s.add(v)
        ops.append(["add", v])
    s.discard(start)
    ops.append(["discard", start])
    cases.append({"ops": ops, "order": list(s)})
print(json.dumps({"python": sys.version.split()[0], "cases": cases}, separators=(",", ":")))
