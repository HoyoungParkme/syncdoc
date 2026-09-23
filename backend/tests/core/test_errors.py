"""SYNC-API-001 2장 · SYNC-STD-004 DEV-5 — 에러 상태 코드 (#76).

앞단 Cloudflare는 원본이 보낸 502·504를 자기 오류 페이지로 바꾼다. 그러면 problem+json이
사라져 사람이 `reason`을 못 본다. 에러 클래스를 새로 만들 때 다시 502를 고르지 않게 여기서 막는다.
"""

from app.core.errors import LlmUnavailable, Problem, PushFailed, RepoCreateFailed


def _subclasses(cls: type[Problem]) -> list[type[Problem]]:
    return [c for sub in cls.__subclasses__() for c in (sub, *_subclasses(sub))]


def test_no_problem_uses_502_or_504() -> None:
    bad = [f"{c.__name__}={c.status}" for c in _subclasses(Problem) if c.status in (502, 504)]
    assert bad == []


def test_outside_failures_are_424() -> None:
    """앱 밖(GitHub·모델)이 실패한 것은 424 Failed Dependency."""
    assert {c.status for c in (PushFailed, RepoCreateFailed, LlmUnavailable)} == {424}
