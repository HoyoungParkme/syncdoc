"""폴링 스케줄러 — SYNC-INFRA-001 7장 보조 경로 · SYNC-UC-001#UC-G1 1a·1b.

기동 시 한 번(1a) + POLL_INTERVAL_SECONDS마다(1b) 저장소마다 fetch해 원격 HEAD가
last_processed_commit과 다르면 pipeline.process_commit을 부른다.
DOM-002 1장에 이 파일은 없다(보고). main.lifespan이 켠다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from syncdoc import db
from syncdoc.core import pipeline
from syncdoc.core.project.service import ProjectService
from syncdoc.core.types import SaveResult
from syncdoc.infra import git

log = logging.getLogger(__name__)


async def catch_up() -> list[SaveResult]:
    """저장소마다 fetch → 밀렸으면 process_commit. 하나 실패해도 다음 저장소 계속."""
    with db.session_scope() as s:
        repos = [p.repository for p in ProjectService(s).list_projects()]
    out: list[SaveResult] = []
    for repo in repos:
        try:
            head = await git.fetch(Path(repo.workdir_path))
            if head != repo.last_processed_commit:
                out.extend(await pipeline.process_commit(repo, head))
        except Exception as e:  # noqa: BLE001 — 폴링은 죽지 않는다
            log.warning("catch_up %s: %s", repo.remote_url, e)
    return out


async def poll_loop(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        await catch_up()
