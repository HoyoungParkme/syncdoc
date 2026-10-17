"""SYNC-MS-024 — core/codegraph/flow.py. 흐름 보기 — 코드 그래프에 흐름 키를 더한다(카드 CC~CE).

순수 함수다 — DB를 모른다. `pipeline.build_code_graph`가 enrich 뒤·communities 앞에 부른다.
더하는 키는 `files`·`units`·`http`·`infra`와 함수마다 `steps`·`route`(MS-024 0장). 한 단계가
실패해도 그 키만 비우고 나머지 그래프는 그대로 저장된다.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.codegraph import infra as infra_mod
from app.core.codegraph import routes as routes_mod
from app.core.codegraph import steps as steps_mod
from app.core.codegraph.graph import CODE_EXTS, _is_test

log = logging.getLogger(__name__)

# 모든 흐름 함수가 건너뛰는 폴더 (MS-024 0장) — 이름이 `.`으로 시작하는 폴더도
SKIP_DIRS = frozenset(
    "node_modules vendor target dist build out venv .venv __pycache__ site-packages coverage"
    " graphify-out".split()
)
_LANGS = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
          ".jsx": "javascript", ".mjs": "javascript", ".rs": "rust"}  # fmt: skip


def walk(src_dir: Path):
    """src_dir 아래 파일의 '/' 경로 — 건너뛰는 폴더 빼고, 링크를 따르지 않는다. 차례는 없다."""
    for dirpath, dirnames, filenames in os.walk(src_dir, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
        rel = Path(dirpath).relative_to(src_dir).as_posix()
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                continue
            yield name if rel == "." else f"{rel}/{name}"


def _loc(data: bytes) -> int:
    if not data:
        return 0
    n = data.count(b"\n")
    return n if data.endswith(b"\n") else n + 1


def files(src_dir: Path) -> list[dict]:
    """SYNC-MS-024#flow.files

    저장소의 코드 파일 전부 — `{path, lang, loc}`, 경로 바이트 순. 테스트 파일은 뺀다.
    """
    out: list[dict] = []
    for path in walk(src_dir):
        suffix = os.path.splitext(path)[1].lower()
        if suffix not in CODE_EXTS or _is_test(path):
            continue
        try:
            data = (src_dir / path).read_bytes()
        except OSError:
            continue
        out.append({"path": path, "lang": _LANGS.get(suffix, suffix[1:]), "loc": _loc(data)})
    out.sort(key=lambda f: f["path"].encode("utf-8"))
    return out


def extend(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-024#flow.extend

    파일 목록 → 실행 단위 → 호출 순서 → 라우트 → 화면 요청 → 장비 차례로 더하고, 대상도 장비도
    없는 호출을 지운다. 한 단계가 예외를 내면 그 키만 빈 값으로 두고 나머지는 계속한다.
    """
    try:
        graph["files"] = files(src_dir)
    except Exception:
        log.exception("flow files")
        graph["files"] = []
    try:
        graph["units"] = infra_mod.units(src_dir, graph)
    except Exception:
        log.exception("flow units")
        graph["units"] = []
    try:
        steps_mod.steps(src_dir, graph)
    except Exception:
        log.exception("flow steps")
        for f in graph["functions"]:
            f["steps"] = []
    try:
        routes_mod.routes(src_dir, graph)
    except Exception:
        log.exception("flow routes")
        for f in graph["functions"]:
            f["route"] = None
    try:
        graph["http"] = routes_mod.http_links(src_dir, graph)
    except Exception:
        log.exception("flow http")
        graph["http"] = []
    try:
        infra_mod.infra(src_dir, graph)
    except Exception:
        log.exception("flow infra")
        graph["infra"] = {"nodes": [], "links": []}
    for f in graph["functions"]:
        f.setdefault("route", None)
        # 대상도 장비도 없는 호출은 뺀다 — 재생에 쓸 데가 없고 그래프가 커진다 (MS-024 extend 7)
        f["steps"] = [
            st for st in f.get("steps", []) if st["k"] != "call" or "to" in st or "infra" in st
        ]
    return graph
