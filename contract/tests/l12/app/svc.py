"""서비스 — 계약 시험 L12의 코드."""

from app.util import fmt


def main():
    """LCG-MS-001#svc.main"""
    return helper() + extra() + len(fmt(1))


def helper():
    """LCG-MS-001#svc.helper"""
    return 1


def extra():
    return 2


class Repo:
    """저장소."""

    def __init__(self):
        self.n = 0

    def get(self, key):
        """LCG-MS-001#svc.get"""
        return helper() + self.n
