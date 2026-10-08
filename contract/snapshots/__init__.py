"""스냅숏 — 파이썬 판의 답을 파일로 두고 두 판을 그것과 비교한다 (SYNC-CODE-002 2장).

다시 뜨기: `uv run pytest --target python --update-snapshots`(또는 both — 파이썬 판이 먼저 돌아 새 값으로 Rust를 본다).
파일은 `snapshots/{이름}.json`, 키 = 사례 이름. 손으로 고치지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).parent
UPDATE = False
_cache: dict[str, dict] = {}
_dirty: set[str] = set()


def _load(name: str) -> dict:
    if name not in _cache:
        p = DIR / f"{name}.json"
        _cache[name] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _cache[name]


def _plain(x):
    return json.loads(json.dumps(x, ensure_ascii=False))


def check(name: str, key: str, got: dict, target: str) -> None:
    """`got`이 스냅숏과 같아야 한다. 고쳐 뜨는 중이면 파이썬 판의 값을 적는다"""
    snap = _load(name)
    got = _plain(got)
    if UPDATE and target == "python":
        snap[key] = got
        _dirty.add(name)
        return
    assert key in snap, f"스냅숏에 {key}가 없다 — 파이썬 판에서 --update-snapshots로 뜬다"
    assert got == snap[key], f"{key}: 파이썬 판(스냅숏)과 다르다"


def flush() -> None:
    for name in sorted(_dirty):
        data = dict(sorted(_cache[name].items()))
        (DIR / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
