"""SYNC-MS-009 테스트 관점 — github 어댑터. GitHub 응답은 httpx.MockTransport로 모킹."""

import hashlib
import hmac

from syncdoc.config import settings
from syncdoc.infra import github as gh


def _sig(body: bytes, secret: str = settings.WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── verify_signature ──
def test_verify_signature_accepts_valid_and_rejects_others() -> None:
    body = b'{"ref":"refs/heads/main"}'
    assert gh.verify_signature(body, _sig(body)) is True
    assert gh.verify_signature(body, _sig(body, "wrong-secret")) is False
    assert gh.verify_signature(body + b" ", _sig(body)) is False
    assert gh.verify_signature(body, "") is False
    assert gh.verify_signature(body, "sha1=abc") is False
