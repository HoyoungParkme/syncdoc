"""SYNC-MS-009 — infra/graphify.py. graphify CLI로 코드 호출 그래프를 뽑는다(카드 AX).

graphify(pip `graphifyy`)는 tree-sitter로 코드만 읽는다 — 모델이 필요 없다. 그래서 환경변수를
비운 채 돌린다: 모델 키가 graphify에 닿지 않는다(INFRA 4.3). 결과는 src_dir/graphify-out/graph.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from app.core.errors import CodeGraphFailed

_TIMEOUT = 120.0  # 초. 싱크독 저장소 전체가 3초 남짓이다


def _clean_env(src_dir: Path) -> dict[str, str]:
    """PATH·LANG만 넘기고 HOME은 src_dir로 — 키·토큰이 든 변수가 넘어가지 않는다."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "HOME": str(src_dir),
    }


async def extract(src_dir: Path) -> dict:
    """SYNC-MS-009#graphify.extract

    `python -m graphify update {src_dir} --no-cluster` — 코드만, 모델 없음. 실패·시간 초과·결과
    없음은 CodeGraphFailed로 접는다.
    """
    if not src_dir.is_dir():
        raise CodeGraphFailed(f"폴더 없음: {src_dir.name}")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "graphify",
        "update",
        str(src_dir),
        "--no-cluster",
        cwd=src_dir,
        env=_clean_env(src_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise CodeGraphFailed("시간 초과") from None
    if proc.returncode != 0:
        tail = (err.decode(errors="replace").strip().splitlines() or ["graphify 실패"])[-1]
        raise CodeGraphFailed(tail[:200])
    out = src_dir / "graphify-out" / "graph.json"
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CodeGraphFailed("graph.json 없음") from e
