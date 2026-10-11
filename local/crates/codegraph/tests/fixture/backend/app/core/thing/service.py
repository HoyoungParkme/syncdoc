"""물건 서비스 — FX-MS-001."""

from __future__ import annotations

from app.core import util
from app.core.thing.repository import ThingRepo
from app.core.util import clean as tidy


class ThingService:
    def __init__(self, session) -> None:
        self.session = session
        self.repo = ThingRepo(session)
        self.cache: ThingRepo = ThingRepo(session)

    def get(self, thing_id: int):
        """FX-MS-001#ThingService.get 하나 읽기"""
        return self.repo.get(thing_id)

    def create(self, name: str):
        """FX-MS-001#ThingService.create

        두 줄짜리 docstring — 첫 줄만 항목 ID다.
        """
        thing = ThingRepo.make(tidy(name))
        self.repo.add(thing)
        util.audit("create", thing)
        return self.get(thing["id"])

    async def rename(self, thing_id: int, name: str):
        """  FX-MS-001#ThingService.rename   """
        repo, other = ThingRepo(self.session), ThingRepo(self.session)
        found = repo.get(thing_id)
        other.add(found)
        return self.cache.get(thing_id)

    def _private(self):
        def inner():
            return 1

        return inner()


def build(session):
    """FX-MS-001#thing.build 서비스를 만든다"""
    svc = ThingService(session)
    svc.get(1)
    return svc
