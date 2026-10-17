from fastapi import APIRouter, Depends

from app.core.db import save
from app.core.service import Svc, helper

router = APIRouter(prefix="/items")


def get_svc():
    return Svc()


@router.get("/{item_id}/")
async def read(item_id: int, svc: Svc = Depends(get_svc)):
    value = helper(helper(item_id))
    if not value:
        raise ValueError(f"없음 {helper(0)}")
    cb = lambda: helper(2)  # noqa: E731

    def inner():
        return helper(3)

    data = await svc.fetch(
        item_id,
    )
    return (data)


@router.api_route("", methods=["POST"])
def make(payload: dict):
    save(None, payload)
    return {"id": 1, "name": "아주 긴 이름을 가진 결과를 돌려준다 — 칠십 자를 넘겨 잘리는지 보려고 더 길게 쓴다"}
