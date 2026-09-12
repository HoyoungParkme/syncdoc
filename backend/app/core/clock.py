"""저장하는 시각. SYNC-STD-004#DEV-18.

`datetime.now(UTC)`는 **단조롭지 않다.** 시스템 시계는 NTP 보정·가상화 시간 동기화로
뒤로 튄다 — 이 프로젝트를 개발한 WSL2에서 부하 중 최대 54ms, 30초에 한 번꼴로 뒤로
가는 것을 쟀다.

그런데 앱은 그 값으로 순서와 인과를 판정한다. `recent_changes`는 버전과 상태변경을
`created_at`으로 섞어 정렬하고, `flag_view`는 대상이 플래그 뒤에 바뀌었는지를 묻는다.
시계가 뒤로 가면 이력이 뒤집히고 없던 인과가 생긴다 (#17).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

_TICK = timedelta(microseconds=1)
_lock = threading.Lock()
_last = datetime.min.replace(tzinfo=UTC)


def now_utc() -> datetime:
    """지금 시각. **직전에 내준 값보다 반드시 크다.**

    시계가 뒤로 가면 직전 값에 1μs를 더해 앞으로만 간다. 앱이 프로세스 하나라는
    전제(INFRA 5장, 저장소 락도 같은 전제) 위에서 성립한다. 스레드는 여럿이다 —
    TestClient가 포털·워커 스레드를 쓰고 웹 라우트도 스레드풀을 탄다.
    """
    global _last
    with _lock:
        t = datetime.now(UTC)
        if t <= _last:
            t = _last + _TICK
        _last = t
        return t
