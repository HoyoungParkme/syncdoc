"""파이썬 3.12 `random.Random(seed).shuffle`·`getrandbits`와 내장 `sum`(float — Neumaier 보정) 정답 (카드 L13, pycompat).

`uv run --project ../backend python xtask/py/pyrandom_cases.py > crates/pycompat/tests/golden/pyrandom.json`
networkx Louvain(seed 42)이 쓰는 난수와 modularity 합을 Rust가 같게 내는지 본다. 손으로 고치지 않는다.
"""

import json
import random
import struct
import sys

assert sys.version_info[:2] == (3, 12), sys.version


def bits(x: float) -> str:
    return struct.pack(">d", x).hex()


def main() -> None:
    shuffles = []
    for seed in (42, 0, 1, 2**32 + 5, 12345678901234567890):
        r = random.Random(seed)
        for n in (0, 1, 2, 3, 7, 50, 1000):
            xs = list(range(n))
            r.shuffle(xs)
            shuffles.append({"seed": str(seed), "n": n, "order": xs})
    r = random.Random(42)
    getbits = [[k, r.getrandbits(k)] for k in (1, 2, 5, 31, 32) * 20]
    g = random.Random(7)
    sums = []
    for _ in range(300):
        n = g.choice([1, 2, 3, 10, 100])
        xs = [g.uniform(-1, 1) * 10 ** g.randint(-8, 8) for _ in range(n)]
        if g.random() < 0.3:
            xs = [x / 3 for x in xs] + [-x / 7 for x in xs]
        sums.append({"xs": [bits(x) for x in xs], "sum": bits(sum(xs))})
    out = {"shuffles": shuffles, "getrandbits": getbits, "sums": sums}
    sys.stdout.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
