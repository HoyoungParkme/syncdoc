"""SYNC-MS-009 — infra/github.py. OAuth·webhook 검증. core는 이것을 통해서만 GitHub API를 만진다."""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import settings
from app.core.errors import RepoCreateFailed, Unauthorized
from app.core.types import GithubUser

_API = "https://api.github.com"
_HDR = {"Accept": "application/vnd.github+json"}


def verify_signature(body: bytes, header: str) -> bool:
    """SYNC-MS-009#github.verify_signature"""
    digest = hmac.new(settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, header or "")


async def exchange_code(code: str, redirect_uri: str) -> str:
    """SYNC-MS-009#github.exchange_code"""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,  # authorize 때와 같은 값 — GitHub가 대조한다
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


async def create_repo(token: str, owner: str, name: str) -> str:
    """SYNC-MS-009#github.create_repo

    **항상 공개로 만든다.** v1은 공개 저장소만 지원한다 — 폴링 fetch가 토큰 없이
    돌기 때문이다(git.fetch). 비공개로 만들면 등록은 되고 폴링이 조용히 죽는다.

    **auto_init을 쓰지 않는다.** GitHub이 초기 커밋을 만들면 README가 생겨
    "빈 저장소" 경로가 아니라 "내용 있는 저장소" 경로를 타 흐름이 갈린다.
    골격 커밋이 그 저장소의 첫 커밋이어야 한다 (UC-A1 기본 흐름 3).
    """
    auth = {"Authorization": f"Bearer {token}", **_HDR}
    async with httpx.AsyncClient() as client:
        # 이미 있으면 만들지 않는다 — 같은 인자로 두 번 불러도 결과가 같아야 한다
        r = await client.get(f"{_API}/repos/{owner}/{name}", headers=auth)
        if r.is_success:
            return str(r.json()["clone_url"])
        r = await client.post(
            f"{_API}/user/repos",
            headers=auth,
            json={"name": name, "private": False, "auto_init": False},
        )
    if not r.is_success:
        detail = ""
        try:
            body = r.json()
            detail = body.get("message", "")
            errs = body.get("errors") or []
            if errs:
                detail += " — " + "; ".join(e.get("message", str(e)) for e in errs)
        except Exception:  # noqa: BLE001 — 본문이 JSON이 아니어도 상태 코드는 알린다
            detail = r.text[:200]
        raise RepoCreateFailed(f"{r.status_code} {detail}".strip())
    return str(r.json()["clone_url"])
