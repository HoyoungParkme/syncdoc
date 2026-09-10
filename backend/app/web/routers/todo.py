"""routers/todo — SYNC-API-001 3.6. queries.todo 하나."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core import queries
from app.core.account.models import User
from app.web.auth import current_user
from app.web.schemas.tracking import Todo

router = APIRouter(prefix="/api/todo", tags=["todo"])


@router.get("", response_model=Todo)
async def todo(user: User = Depends(current_user)) -> Todo:
    """SYNC-API-001#GET/api/todo"""
    return Todo.of(await queries.todo(user))
