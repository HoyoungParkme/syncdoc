"""routers/hooks — SYNC-API-001 POST /hooks/github (UC-G1 1). 서명 검증 → 202, 파이프라인은 뒤에."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from sqlalchemy.orm import Session

from syncdoc.core import pipeline
from syncdoc.core.errors import NotFound, Unauthorized
from syncdoc.core.project.repository import normalize_remote
from syncdoc.core.project.service import ProjectService
from syncdoc.db import get_session
from syncdoc.infra import github

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/github", status_code=202)
async def github_push(
    request: Request,
    tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    """SYNC-API-001#POST/hooks/github"""
    body = await request.body()
    if not github.verify_signature(body, x_hub_signature_256):
        raise Unauthorized("서명 불일치")
    payload = await request.json()
    head = payload.get("after")
    repo_info = payload.get("repository") or {}
    urls = {
        normalize_remote(str(repo_info.get(k)))
        for k in ("clone_url", "html_url", "ssh_url", "git_url", "url")
        if repo_info.get(k)
    }
    repo = next(
        (
            p.repository
            for p in ProjectService(session).list_projects()
            if normalize_remote(p.repository.remote_url) in urls
        ),
        None,
    )
    if repo is None or not head:
        raise NotFound("repository", repo_info.get("clone_url") or "?")
    tasks.add_task(pipeline.process_commit, repo, head)
    return {"accepted": True}
