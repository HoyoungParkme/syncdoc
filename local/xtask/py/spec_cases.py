"""cargo xtask spec-diff — 파이썬 쪽: 사례를 만들고 파이썬 판의 답을 붙인다 (SYNC-MS-014 0장).

사례: ① 지금의 `docs/specs/**`·`_templates/` 전부 ② 명세 파일마다 git 이력 최근 다섯 판의 이웃 짝 diff
③ 씨앗 고정 무작위 — 실제 문서의 조각을 줄 넣기·빼기·바꾸기·꼴 조각(유니코드·펜스·참조·헤딩)으로 흔든 본문과 짝 diff,
줄 목록의 unified_diff. 한 줄에 사례 하나(JSON)로 OUT에 쓴다 — Rust가 같은 입력으로 돌려 비교한다. 커밋하지 않는다.
`uv run --project backend python local/xtask/py/spec_cases.py --seed S --count N OUT`
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_answers  # noqa: E402
from app.core import markdown  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SPECS = os.path.join(ROOT, "docs", "specs")
TYPES = [t for t, _, _ in spec_answers.patterns()["types"]]
ENTRIES = ["mcp", "github", "web_revert", "web_status"]

# 흔들 때 넣는 글자·조각 — 파이썬과 Rust가 갈리기 쉬운 곳
CHARS = ["\x1c", "\x1f", "\x0b", "\x85", " ", "　", "​", "﻿", " ", "１", "٣", "²",
         "\t", "\r", "_", "-", ".", ":", "#", "`", "[", "]", "|", "가", "é", "é", "\U0001f600", "'", '"', "\\"]
SNIPPETS = [
    "```", "```python", "  ```", "````", "~~~", "---", "--- ", "+++x", "-- y", "@@ z", "",
    "#### R1 항목", "#### R01 패딩", "#### R1. 점", "#### R１ 전각", "####\tR2", "####  R3", "#### R4\x1c",
    "#### `R5` 코드", "#### C1 제약", "출처: RFQ", "  출처: x", "근거: [[SYNC-RFQ-001]]",
    "## 1. 폴더 구조", "| 경로 | 층 | 명세 |", "|---|---|---|", "## 2. 엔티티", "## 4. 설계 클래스",
    "    class Document {", "        +int id", "        +str x", "    }",
    "[[SYNC-RFQ-001#Q1]]", "[[#R1]]", "[[bad ref]]", "[[SYNC-PRD-001#R 1]]", "`[[x]]`", "a `b` c `d",
    "### 3.1 절", "### 절", "## 미결사항", "# 제목", "status: approved", "doc_id: SYNC-PRD-002",
    "#### SpecService.save 저장", "#### GET/api/me 나", "#### create_document 만들기", "#### UI-1 화면",
    "#### UC-A1 하나", "#### SEQ-C1 둘", "#### DEV-1 규칙", "#### AB 카드", "#### documents 표",
]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def doc_files() -> list[str]:
    out = []
    for d in sorted(os.listdir(SPECS)):
        full = os.path.join(SPECS, d)
        if os.path.isdir(full):
            out += [os.path.join(full, f) for f in sorted(os.listdir(full)) if f.endswith(".md")]
    return out


def type_of(body: str, path: str = "") -> str:
    t = markdown.parse_frontmatter(body)[0].get("type", "")
    if t in TYPES:
        return t
    name = os.path.basename(path).split("-")[0].removesuffix(".md")
    return name if name in TYPES else "STD"


def ids_in(body: str) -> list[str]:
    return sorted({tok for _, _, tok, _ in markdown.headings(body)})


def body_case(rng: random.Random, name: str, body: str, doc_type: str, checks: int, applies: int) -> dict:
    ids = ids_in(body)
    cs = []
    for _ in range(checks):
        deleted = rng.sample(ids, k=min(len(ids), rng.randrange(0, 3)))
        cs.append({"entry": rng.choice(ENTRIES), "current_status": rng.choice([None, "draft", "approved"]),
                   "deleted": deleted})
    did = markdown.parse_frontmatter(body)[0].get("doc_id", "")
    ap = []
    for _ in range(applies):
        ap.append({"doc_id": rng.choice([did or "SYNC-PRD-001", "SYNC-PRD-009", "SYNC-MS-014"]),
                   "doc_type": rng.choice(TYPES), "status": rng.choice(["draft", "approved"])})
    title = rng.choice([None, None, None, "", "클래스 명세", "ERD", "REST", "화면 설계", "아무 제목"])
    return {"kind": "body", "name": name, "body": body, "doc_type": doc_type, "title": title,
            "checks": cs, "apply": ap}


def mutate(rng: random.Random, lines: list[str]) -> list[str]:
    lines = list(lines)
    for _ in range(rng.randrange(1, 12)):
        op = rng.randrange(7)
        i = rng.randrange(len(lines) + 1)
        if op == 0:
            lines.insert(i, rng.choice(SNIPPETS))
        elif op == 1 and lines:
            del lines[min(i, len(lines) - 1)]
        elif op == 2 and lines:
            j = min(i, len(lines) - 1)
            lines.insert(j, lines[j])
        elif op == 3 and len(lines) > 1:
            a, b = rng.randrange(len(lines)), rng.randrange(len(lines))
            lines[a], lines[b] = lines[b], lines[a]
        elif op == 4 and lines:
            j = min(i, len(lines) - 1)
            s = lines[j]
            k = rng.randrange(len(s) + 1)
            lines[j] = s[:k] + rng.choice(CHARS) + s[k:]
        elif op == 5 and lines:
            j = min(i, len(lines) - 1)
            lines[j] = rng.choice(["#", "##", "###", "####", "#####"]) + " " + lines[j]
        elif op == 6 and lines:
            j = min(i, len(lines) - 1)
            lines[j] = lines[j].replace(" ", rng.choice(["  ", "\t", " ", " "]), 1)
    return lines


def random_body(rng: random.Random, bodies: list[str]) -> str:
    src = rng.choice(bodies).split("\n")
    fm_n = markdown.parse_frontmatter("\n".join(src))[1]
    start = rng.randrange(max(1, len(src)))
    piece = src[start : start + rng.randrange(5, 150)]
    if fm_n and rng.random() < 0.7:
        piece = src[:fm_n] + piece
    out = "\n".join(mutate(rng, piece))
    r = rng.random()
    if r < 0.08:
        out = out.replace("\n", "\r\n")
    elif r < 0.12:
        out = "﻿" + out
    return out


def random_lines(rng: random.Random) -> list[str]:
    alphabet = ["x", "y", "z", "", "가", "---", "+++", "@@ a", " ", "- [ ] 하나"]
    n = rng.choice([0, 1, 3, 10, 50, 199, 200, 201, 250, 400])
    return [rng.choice(alphabet[: rng.randrange(2, len(alphabet) + 1)]) for _ in range(n)]


def cases(seed: int, count: int):
    rng = random.Random(seed)
    files = doc_files()
    bodies = [read(p) for p in files]
    # ① 지금의 명세·템플릿
    for path, body in zip(files, bodies):
        yield body_case(rng, f"doc:{os.path.relpath(path, ROOT)}", body, type_of(body, path), 4, 2)
    # ② git 이력 — 명세마다 최근 다섯 판의 이웃 짝
    for path in files:
        if "/_templates/" in path:
            continue
        rel = os.path.relpath(path, ROOT)
        revs = subprocess.run(["git", "log", "--format=%H", "-n", "5", "--", rel], cwd=ROOT,
                              capture_output=True, check=True).stdout.decode().split()
        old = []
        for rev in reversed(revs):
            got = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=ROOT, capture_output=True)
            if got.returncode == 0:
                old.append((rev[:8], got.stdout.decode()))
        for (ra, a), (rb, b) in zip(old, old[1:]):
            yield {"kind": "diff", "name": f"git:{rel}@{ra}..{rb}", "from": a, "to": b,
                   "doc_type": type_of(b, path), "from_no": 1, "to_no": 2, "context": 3}
    # ③ 무작위
    for k in range(count):
        body = random_body(rng, bodies)
        dt = type_of(body) if rng.random() < 0.7 else rng.choice(TYPES)
        yield body_case(rng, f"random:{seed}:{k}", body, dt, 2, 1)
        other = "\n".join(mutate(rng, body.split("\n")))
        nos = rng.choice([(1, 2), (2, 1), (3, 7)])
        yield {"kind": "diff", "name": f"random-diff:{seed}:{k}", "from": body, "to": other, "doc_type": dt,
               "from_no": nos[0], "to_no": nos[1], "context": rng.choice([0, 1, 3, 3, 5])}
        if k % 4 == 0:
            a = random_lines(rng)
            b = mutate(rng, a) if a else random_lines(rng)
            yield {"kind": "difflib", "name": f"random-difflib:{seed}:{k}", "a": a, "b": b,
                   "n": rng.choice([0, 1, 3, 5])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("out")
    args = ap.parse_args()
    with open(args.out, "w", encoding="utf-8") as f:
        for c in cases(args.seed, args.count):
            f.write(json.dumps(spec_answers.answer(c), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
