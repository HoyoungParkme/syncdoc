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
from app.core.account.models import User
from app.core.clock import now_utc
from app.core.project.models import Repository
from app.core.project.service import ProjectService
from app.core.types import SaveResult
from app.infra import git

log = logging.getLogger(__name__)


async def catch_up() -> list[SaveResult]:
    """SYNC-MS-007#scheduler.catch_up

    저장소마다 fetch → 뒤처짐을 DB에 적고 → 밀렸으면 process_commit.
    화면(MS-001 repo_status)이 읽는 behind_by·fetched_at을 적는 곳이 여기뿐이다.
    """
    with db.session_scope() as s:
        repos = [
            (p.code, p.repository.id, p.repository.workdir_path, p.repository.remote_url)
            for p in ProjectService(s).list_projects()
        ]
    out: list[SaveResult] = []
    for code, repo_id, workdir, remote_url in repos:
        try:
            # 웹훅·read_pending과 같은 저장소 읽기 락 — fetch와 처리가 겹치지 않는다. 처리 지점도
            # 락 안에서 읽는다: 기다리는 사이 웹훅이 따라잡아 놨을 수 있다 (MS-007 catch_up, #194)
            async with pipeline.read_lock(code):
                with db.session_scope() as s:
                    row = s.get(Repository, repo_id)
                    assert row is not None
                    last = row.last_processed_commit
                    # fetch 토큰의 주인 — 사람 없이 도는 폴링도 비공개 저장소를 읽는다 (#310)
                    registered = s.get(User, row.registered_by_user_id)
                head = await git.fetch(Path(workdir), registered)
                behind = (
                    await git.rev_list_count(Path(workdir), f"{last}..{head}") if last else None
                )
                with db.session_scope() as s:
                    s.execute(
                        update(Repository)
                        .where(Repository.id == repo_id)
                        # 성공한 주기가 옛 사유를 지운다 — 낡은 오류가 화면에 남으면 안 된다
                        .values(behind_by=behind, fetched_at=now_utc(), fetch_error=None)
                    )
                    s.commit()
                if head != last:
                    with db.session_scope() as s:
                        repo = s.get(Repository, repo_id)
                        out.extend(await pipeline.process_commit(repo, head, locked=True))
        except Exception as e:  # noqa: BLE001 — 저장소 하나가 죽어도 다음 저장소를 계속한다
            # 실패한 저장소의 behind_by는 건드리지 않는다. 낡은 값이 남지만
            # fetched_at이 언제 기준인지 말해 준다.
            #
            # **로그로만 남기지 않는다.** 그러면 폴링이 죽은 프로젝트가 조용히 멈추고
            # 사람은 "아무도 push를 안 했나 보다"로 읽는다 (#46). 사유를 DB에 적어
            # repo_status가 UI-14로 올린다
            log.warning("catch_up %s: %s", remote_url, e)
            try:
                with db.session_scope() as s:
                    s.execute(
                        update(Repository)
                        .where(Repository.id == repo_id)
                        .values(fetch_error=str(e)[:300])
                    )
                    s.commit()
            except Exception as e2:  # noqa: BLE001 — 사유를 못 적어도 폴링은 계속한다
                log.warning("catch_up %s: 실패 사유를 못 적었다: %s", remote_url, e2)
    return out


async def poll_loop(interval: int) -> None:
    """SYNC-MS-007#scheduler.poll_loop

    기동 시 한 번(main.lifespan)은 따로다. 여기는 그 뒤의 주기 반복만 맡는다.
    """
    while True:
        await asyncio.sleep(interval)
        # 반복 전체를 감싼다. catch_up은 저장소 하나가 실패해도 다음을 계속하지만,
        # 저장소 목록을 읽다 DB가 죽으면 그 예외가 여기까지 올라와 영영 폴링이 없다
        try:
            await catch_up()
        except Exception as e:  # noqa: BLE001 — 반복이 멈추면 안 된다 (MS-007)
            log.warning("poll_loop: %s", e)
