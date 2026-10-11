"""routers/thing — FX-API-001."""

from fastapi import APIRouter

from app.core.thing import service as thing_service
from app.core.thing.service import ThingService, build

router = APIRouter()


@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int, svc: ThingService):
    """FX-API-001#GET/api/things/{thingId} — 물건 하나"""
    return svc.get(thing_id)


@router.post("/api/things")
def create_thing(name: str):
    """FX-API-001#POST/api/things"""
    svc = build(None)
    from app.core import util

    util.clean(name)
    return thing_service.build(None).create(name)
