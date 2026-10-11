"""물건 리포지토리 — DB만 안다."""

from __future__ import annotations


class ThingRepo:
    def __init__(self, session):
        self.session = session

    def get(self, thing_id: int):
        return self.session.get(thing_id)

    def add(self, thing) -> None:
        self.session.add(thing)

    @staticmethod
    def make(name: str):
        return {"name": name}
