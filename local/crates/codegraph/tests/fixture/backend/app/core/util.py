"""도우미."""

import functools


def clean(text: str) -> str:
    """FX-MS-002#util.clean"""
    return text.strip()


@functools.cache
def audit(action, thing):
    """FX-MS-002#util.audit 기록"""
    return log(action, thing)


def log(action, thing):
    print(action, thing)
    # 끝 주석은 끝 줄이 아니다


def typed(repo: "ThingRepo | None", other: object):
    if repo:
        repo.get(1)
    value: int = 3
    return value
