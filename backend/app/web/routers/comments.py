"""routers/comments — SYNC-API-001 3.4·3.5. CommentService. 줄 내용은 get_document에서(SEQ-16).

author 이름은 AccountService.users_by_ids로 채운다 — Comment 스키마의 UserRef.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.collab.service import CommentService
from app.core.spec.service import SpecService
from app.db import get_session
from app.web.auth import current_user
from app.web.schemas.comments import AddComment, Comment, Resolve

router = APIRouter(prefix="/api", tags=["comments"])


def _users(session: Session, rows: list) -> dict:
    ids: list[int] = []

    def walk(cs: list) -> None:
        for c in cs:
            ids.append(c.author_user_id)
            walk(getattr(c, "replies", []))

    walk(rows)
    return AccountService(session).users_by_ids(ids)


@router.get("/docs/{doc_id}/comments", response_model=list[Comment])
async def list_comments(
    doc_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[Comment]:
    """SYNC-API-001#GET/api/docs/{docId}/comments"""
    document = SpecService(session).get_document(doc_id)
    rows = CommentService(session).list(document.id)
    users = _users(session, rows)
    return [Comment.of(c, doc_id, users) for c in rows]


@router.post("/docs/{doc_id}/comments", response_model=Comment, status_code=201)
async def add_comment(
    doc_id: str,
    req: AddComment,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Comment:
    """SYNC-API-001#POST/api/docs/{docId}/comments"""
    document = SpecService(session).get_document(doc_id)
    lines = document.body.split("\n")
    if req.line_no > len(lines):
        raise HTTPException(422, f"line_no {req.line_no} 범위 밖 (1~{len(lines)})")
    c = CommentService(session).add(
        document.id, req.line_no, lines[req.line_no - 1], req.body, user, req.parent_comment_id
    )
    session.commit()
    return Comment.of(c, doc_id, _users(session, [c]))


@router.post("/comments/{comment_id}/resolve", response_model=Comment)
async def resolve_comment(
    comment_id: int,
    req: Resolve | None = None,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Comment:
    """SYNC-API-001#POST/api/comments/{id}/resolve"""
    c = CommentService(session).resolve(comment_id, req.resolved if req else True)
    session.commit()
    doc_id = SpecService(session).describe_documents([c.document_id])[c.document_id].doc_id
    return Comment.of(c, doc_id, _users(session, [c]))
