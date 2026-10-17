"""SYNC-MS-024 — core/codegraph/routes.py. 라우트와 화면 요청(카드 CD).

카드 CC에서는 스텁이다 — `route`를 null로, `http`를 빈 목록으로 둔다(STD-004 DEV-12, CD가 푼다).
"""

from __future__ import annotations

from pathlib import Path


def routes(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-024#routes.routes

    함수마다 받는 라우트 `{method, path}` 또는 null. 스텁 — 카드 CD.
    """
    for f in graph["functions"]:
        f["route"] = None
    return graph


def http_links(src_dir: Path, graph: dict) -> list[dict]:
    """SYNC-MS-024#routes.http_links

    화면 요청 → 라우트 함수. 스텁 — 카드 CD.
    """
    return []
