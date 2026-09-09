"""SYNC-MS-009 — infra/github.py. OAuth·webhook 검증. core는 이것을 통해서만 GitHub API를 만진다."""

import hashlib
import hmac

import httpx

from syncdoc.config import settings
from syncdoc.core.errors import Unauthorized
from syncdoc.core.types import GithubUser


def verify_signature(body: bytes, header: str) -> bool:
    """SYNC-MS-009#github.verify_signature"""
    digest = hmac.new(settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, header or "")


async def exchange_code(code: str) -> str:
    """SYNC-MS-009#github.exchange_code"""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
    token = r.json().get("access_token") if r.is_success else None
    if not token:
        raise Unauthorized("GitHub code 교환 실패")
    return token


async def get_user(token: str) -> GithubUser:
    """SYNC-MS-009#github.get_user"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
    if not r.is_success:
        raise Unauthorized("GitHub 사용자 조회 실패")
    d = r.json()
    return GithubUser(id=d["id"], login=d["login"], name=d.get("name") or d["login"])
