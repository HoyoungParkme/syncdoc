"""폴링 스케줄러 — SYNC-INFRA-001 7장 보조 경로 · SYNC-UC-001#UC-G1 1a·1b.

기동 시 한 번(1a) + POLL_INTERVAL_SECONDS마다(1b) 저장소마다 fetch해 원격 HEAD가
last_processed_commit과 다르면 pipeline.process_commit을 부른다.
DOM-002 1장에 이 파일은 없다(보고). main.lifespan이 켠다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import update

from app import db
from app.core import pipeline
from app.core.project.models import Repository
from app.core.project.service import ProjectService
from app.core.spec.service import now_utc
from app.core.types import SaveResult
from app.infra import git

log = logging.getLogger(__name__)


async def catch_up() -> list[SaveResult]:
    """SYNC-MS-007#scheduler.catch_up

    저장소마다 fetch → 뒤처짐을 DB에 적고 → 밀렸으면 process_commit.
    화면(MS-001 repo_status)이 읽는 behind_by·fetched_at을 적는 곳이 여기뿐이다.
    """
    with db.session_scope() as s:
        repos = [(p.repository.id, p.repository.workdir_path, p.repository.remote_url,
                  p.repository.last_processed_commit) for p in ProjectService(s).list_projects()]
    out: list[SaveResult] = []
    for repo_id, workdir, remote_url, last in repos:
        try:
            head = await git.fetch(Path(workdir))
            behind = (
                await git.rev_list_count(Path(workdir), f"{last}..{head}") if last else None
            )
            with db.session_scope() as s:
                s.execute(
                    update(Repository)
                    .where(Repository.id == repo_id)
                    .values(behind_by=behind, fetched_at=now_utc())
                )
                s.commit()
            if head != last:
                with db.session_scope() as s:
                    repo = s.get(Repository, repo_id)
                    out.extend(await pipeline.process_commit(repo, head))
        except Exception as e:  # noqa: BLE001 — 저장소 하나가 죽어도 다음 저장소를 계속한다
            # 실패한 저장소의 behind_by는 건드리지 않는다. 낡은 값이 남지만
            # fetched_at이 언제 기준인지 말해 준다.
            log.warning("catch_up %s: %s", remote_url, e)
    return out


async def poll_loop(interval: int) -> None:
    """SYNC-MS-007#scheduler.poll_loop

    기동 시 한 번(main.lifespan)은 따로다. 여기는 그 뒤의 주기 반복만 맡는다.
    """
    while True:
        await asyncio.sleep(interval)
        await catch_up()
