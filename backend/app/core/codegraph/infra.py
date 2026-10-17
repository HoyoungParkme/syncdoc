"""SYNC-MS-024 — core/codegraph/infra.py. 장비와 실행 단위(카드 CE).

카드 CC에서는 스텁이다 — 빈 단위·빈 장비를 둔다(STD-004 DEV-12, CE가 푼다).
"""

from __future__ import annotations

from pathlib import Path


def units(src_dir: Path, graph: dict) -> list[dict]:
    """SYNC-MS-024#infra.units

    실행 단위 — 서버·화면·작업. 스텁 — 카드 CE.
    """
    return []


def infra(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-024#infra.infra

    장비·연결, 호출 순서에 닿는 장비 표시. 스텁 — 카드 CE.
    """
    graph["infra"] = {"nodes": [], "links": []}
    return graph
