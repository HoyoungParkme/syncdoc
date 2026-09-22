"""routers/hooks — SYNC-API-001 POST /hooks/github (UC-G1 1). 서명 검증 → 202, 파이프라인은 뒤에."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core import pipeline
from app.core.errors import NotFound, Unauthorized
from app.core.project.repository import normalize_remote
from app.core.project.service import ProjectService
from app.db import get_session
from app.infra import github

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/github", status_code=202)
async def github_push(
    request: Request,
    tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
    session: Session = Depends(get_session),
) -> dict[str, bool | str]:
    """SYNC-API-001#POST/hooks/github"""
    body = await request.body()
    if not github.verify_signature(body, x_hub_signature_256):
        raise Unauthorized("서명 불일치")
    payload = await request.json()
    # push의 main만 받는다 (UC-G1 1c·1d, 카드 AF). 무시한 것도 202로 답하되 사유를 담는다 —
    # GitHub 전달 로그에서 보이게. 작업 브랜치를 받으면 그 끝이 last_processed_commit에 박혀
    # 이후 밀림 계산이 어긋나고, 브랜치 삭제(after가 0뿐)는 지울 커밋이 없다
    if x_github_event != "push":
        return {"accepted": False, "ignored": f"event={x_github_event or '?'}"}
    ref = payload.get("ref")
    if ref != "refs/heads/main":
        return {"accepted": False, "ignored": f"ref={ref or '?'}"}
    head = payload.get("after")
    if head and set(str(head)) == {"0"}:
        return {"accepted": False, "ignored": "branch-deleted"}
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
