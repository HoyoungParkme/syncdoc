"""routers/specs — SYNC-API-001 3.10. 이미지 안의 규약·템플릿 사본 (카드 BC).

폐쇄망판 README의 규약 링크가 여기를 가리킨다(SPECS_URL 기본값, INFRA 8.1) — 바깥 GitHub에 닿지
못하니 이미지에 담긴 `docs/specs/STD`·`_templates`를 글자로 준다. 공개다 — 싱크독 자신의 규약이라
비밀이 없고, 인터넷판에서도 같은 것을 준다. 둘 밖이나 `..`는 없는 것과 같은 404.
"""

from __future__ import annotations

from html import escape
from pathlib import Path, PurePosixPath

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.core.errors import NotFound

router = APIRouter(tags=["specs"])

# backend/app/web/routers → 저장소 뿌리. 이미지 안에서도 같은 깊이다 (Dockerfile, DOM-002 1장)
SPECS_ROOT = Path(__file__).resolve().parents[4] / "docs" / "specs"
_SHARED = ("STD", "_templates")


def _listing(rel: str, folder: Path) -> str:
    """폴더 → 파일 목록 HTML. 링크는 절대 경로 — README가 `/specs/_templates`를 슬래시 없이 건다."""
    rows = "".join(
        f'<li><a href="/specs/{escape(rel)}/{escape(p.name)}">{escape(p.name)}</a></li>'
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix == ".md"
    )
    return (
        '<!doctype html><meta charset="utf-8">'
        f"<title>{escape(rel)}</title><h1>{escape(rel)}</h1><ul>{rows}</ul>"
    )


@router.get("/specs/{path:path}")
async def spec_copy(path: str) -> Response:
    """SYNC-API-001#GET/specs/{path}"""
    parts = PurePosixPath(path.strip("/")).parts
    if not parts or parts[0] not in _SHARED or ".." in parts:
        raise NotFound("specs", path)
    base = (SPECS_ROOT / parts[0]).resolve()
    target = (SPECS_ROOT / "/".join(parts)).resolve()
    if not target.is_relative_to(base):  # 심볼릭 링크로 밖을 가리켜도 안 나간다
        raise NotFound("specs", path)
    if target.is_dir():
        return HTMLResponse(_listing("/".join(parts), target))
    if target.is_file() and target.suffix == ".md":
        return PlainTextResponse(
            target.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8"
        )
    raise NotFound("specs", path)
