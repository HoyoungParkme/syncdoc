"""명세 엔진의 답 — `cargo xtask spec-golden`·`spec-diff`가 같이 쓴다 (SYNC-MS-014 0장).

파이썬 판(backend/app/core)이 원본이다. 사례(입력)에 답을 붙여 돌려준다 — Rust 쪽
`crates/core/tests/support/spec_answers.rs`가 같은 꼴로 답을 만들어 비교한다.
DB는 쓰지 않는다 — 삭제된 ID와 판 본문은 사례가 준다(`_deleted_item_ids`·`repo`를 바꿔 끼운다).
"""

from __future__ import annotations

import dataclasses
import difflib
import os
import sys
import unicodedata
from types import SimpleNamespace

os.environ.update(
    {
        "EDITION": "closed",
        "SECRET_KEY": "export-only",
        "DATABASE_URL": "postgresql+psycopg://x:x@127.0.0.1:1/x",
        "LOCAL_LOGIN": "local",
        "LLM_API_URL": "",
        "LLM_API_KEY": "",
    }
)

from app.core import markdown  # noqa: E402
from app.core.errors import ConventionViolation  # noqa: E402
from app.core.spec.service import SUBTYPES, TYPES, SpecService  # noqa: E402
from app.core.types import DocStatus, DocType, Entry  # noqa: E402


def versions() -> dict:
    return {"python": sys.version.split()[0], "unicodedata": unicodedata.unidata_version}


def patterns() -> dict:
    """TYPES·SUBTYPES — Rust 상수가 글자 하나 다르지 않아야 한다(L6 get_template이 내보낸다)."""
    return {
        "types": [[k, p, s] for k, (p, s) in TYPES.items()],
        "subtypes": [[t, k, p, s] for (t, k), (p, s) in SUBTYPES.items()],
    }


def body_answer(case: dict) -> dict:
    """본문 하나 — frontmatter·마스킹·헤딩·항목 블록·검사(입구·현재 상태·삭제 집합마다)·frontmatter 채움."""
    body, dt = case["body"], DocType(case["doc_type"])
    svc = SpecService(None)  # type: ignore[arg-type]
    fm, n = markdown.parse_frontmatter(body)
    out = dict(case)
    out["frontmatter"] = [[k, v] for k, v in fm.items()]
    out["frontmatter_lines"] = n
    out["masked"] = markdown.masked_lines(body)
    out["headings"] = [list(h) for h in markdown.headings(body)]
    out["item_blocks"] = [
        dataclasses.asdict(b) for b in svc.item_blocks(body, dt, case.get("title"))
    ]
    checks = []
    for c in case.get("checks", []):
        deleted = set(c["deleted"])
        svc._deleted_item_ids = lambda _doc_id, d=deleted: d  # type: ignore[method-assign]
        cs = DocStatus(c["current_status"]) if c["current_status"] else None
        r = svc.validate(body, dt, Entry(c["entry"]), cs)
        checks.append({**c, "result": dataclasses.asdict(r)})
    out["checks"] = checks
    applied = []
    for a in case.get("apply", []):
        try:
            got: dict = {
                "ok": svc.apply_frontmatter(
                    body, a["doc_id"], DocType(a["doc_type"]), DocStatus(a["status"])
                )
            }
        except ConventionViolation as e:
            got = {"error": e.to_dict()}
        applied.append({**a, **got})
    out["apply"] = applied
    return out


class _Repo:
    """diff가 읽는 두 판 — 사례가 준다."""

    def __init__(self, doc_type: str, bodies: dict[int, str]) -> None:
        self.doc_type, self.bodies = doc_type, bodies

    def document_by_doc_id(self, _doc_id: str):
        return SimpleNamespace(id=1, doc_type=self.doc_type)

    def version_bodies(self, _document_id: int, _nos: list[int]) -> dict[int, str]:
        return self.bodies


def diff_answer(case: dict) -> dict:
    """두 본문 diff — 판 번호는 서로 다르다(같으면 파이썬은 한 본문만 읽는다)."""
    assert case["from_no"] != case["to_no"]
    svc = SpecService(None)  # type: ignore[arg-type]
    svc.repo = _Repo(case["doc_type"], {case["from_no"]: case["from"], case["to_no"]: case["to"]})  # type: ignore[assignment]
    d = svc.diff("X-DIFF-001", case["from_no"], case["to_no"], case["context"])
    return {**case, "diff": dataclasses.asdict(d)}


def difflib_answer(case: dict) -> dict:
    """줄 목록 둘의 `unified_diff(lineterm="")` 그대로 — autojunk(200줄 이상)까지."""
    return {**case, "unified": list(difflib.unified_diff(case["a"], case["b"], n=case["n"], lineterm=""))}


def answer(case: dict) -> dict:
    kind = case["kind"]
    if kind == "body":
        return body_answer(case)
    if kind == "diff":
        return diff_answer(case)
    if kind == "difflib":
        return difflib_answer(case)
    raise ValueError(f"모르는 사례 {kind}")
