"""화면 확인용 미리보기 서버 (DEV-14 일곱째 조건 — 사람이 브라우저에서 눌러 본다).

GitHub OAuth 없이 본다: 개발 DB(syncdoc_dev, 테스트 컨테이너)를 새로 만들고 이 저장소의 docs/specs를
파이프라인으로 올린 뒤 S4 상태(전파 미결정·확인 필요·끊어진 참조·하위 불일치·규약 오류·댓글·담당 미지정)를 심는다.
로그인은 /__dev/login/{login} (hoyoung · minjun). 앱 코드는 건드리지 않는다 — 라우트는 여기서 붙인다.

    uv run python tools/dev_preview.py            # 시드 + 서버 (http://localhost:8000/__dev/login/hoyoung)
    uv run python tools/dev_preview.py --serve    # 시드 없이 서버만
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = Path(os.environ.get("SYNCDOC_PREVIEW_DIR", "/tmp/syncdoc-preview"))
os.environ["DATABASE_URL"] = "postgresql+psycopg://syncdoc:syncdoc@localhost:5434/syncdoc_dev"
os.environ.setdefault("SECRET_KEY", "dev-preview-secret")
os.environ.setdefault("REPOS_DIR", str(PREVIEW / "repos"))
sys.path.insert(0, str(ROOT))

from fastapi import Depends, Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from syncdoc import db  # noqa: E402
from syncdoc.core import pipeline  # noqa: E402
from syncdoc.core.account.service import AccountService  # noqa: E402
from syncdoc.core.collab.service import CommentService  # noqa: E402
from syncdoc.core.errors import Problem  # noqa: E402
from syncdoc.core.project.models import Project, Repository  # noqa: E402
from syncdoc.core.reference.service import ReferenceService  # noqa: E402
from syncdoc.core.spec.service import SpecService  # noqa: E402
from syncdoc.core.tracking.service import TrackingService  # noqa: E402
from syncdoc.core.types import Author, AuthorKind, DocType, Entry, Propagation  # noqa: E402
from syncdoc.main import app  # noqa: E402
from syncdoc.web import auth  # noqa: E402

ORDER = ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE", "STD"]


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def git(cwd: Path, *args: str) -> str:
    return sh("git", "-c", "user.name=seed", "-c", "user.email=seed@example.com", *args, cwd=cwd)


def fresh_db() -> None:
    for q in ("DROP DATABASE IF EXISTS syncdoc_dev", "CREATE DATABASE syncdoc_dev"):
        sh(
            "docker",
            "exec",
            "syncdoc-test-pg",
            "psql",
            "-U",
            "syncdoc",
            "-d",
            "syncdoc_test",
            "-c",
            q,
        )
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")


def fresh_repo() -> tuple[Path, Path]:
    import shutil

    shutil.rmtree(PREVIEW, ignore_errors=True)
    PREVIEW.mkdir(parents=True)
    remote, seed, work = PREVIEW / "remote.git", PREVIEW / "seed", PREVIEW / "work"
    git(PREVIEW, "init", "-q", "--bare", "-b", "main", str(remote))
    git(PREVIEW, "clone", "-q", str(remote), str(seed))
    git(seed, "checkout", "-q", "-b", "main")
    (seed / "README.md").write_text("# 싱크독 미리보기\n", encoding="utf-8")
    git(seed, "add", "README.md")
    git(seed, "commit", "-q", "-m", "chore(SYNC): init")
    git(seed, "push", "-q", "origin", "HEAD:main")
    git(PREVIEW, "clone", "-q", str(remote), str(work))
    return remote, work


def agent(user) -> Author:
    return Author(kind=AuthorKind.agent, user=user, instructed_by=user, via=Entry.mcp)


async def save(author: Author, doc_id: str, body: str, expected: int, message: str, **kw):
    return await pipeline.save_pipeline(
        Entry.mcp, doc_id, None, body, expected, None, author, message, **kw
    )


def with_downstream(s: Session, doc_id: str, exclude: set[str] = frozenset()) -> tuple[str, int]:
    """하위 참조가 있는 항목 (item_id, pk) 하나."""
    spec, refs = SpecService(s), ReferenceService(s)
    for i in spec.get_document(doc_id).items:
        if i.item_id not in exclude and any(e.from_item_pk for e in refs.downstream(i.pk)):
            return i.item_id, i.pk
    raise RuntimeError(f"{doc_id}: 하위 참조 있는 항목 없음")


def edited(s: Session, doc_id: str, item_id: str) -> str:
    """항목 블록 끝에 한 줄 추가한 본문."""
    spec = SpecService(s)
    d = spec.get_document(doc_id)
    block = next(b for b in spec.item_blocks(d.body, DocType(d.doc_type)) if b.item_id == item_id)
    lines = d.body.split("\n")
    lines.insert(
        block.end_line, "미리보기용으로 이 항목의 내용이 바뀌었다. 하위 문서가 영향을 받는다."
    )
    return "\n".join(lines)


def without(s: Session, doc_id: str, item_id: str) -> str:
    spec = SpecService(s)
    d = spec.get_document(doc_id)
    block = next(b for b in spec.item_blocks(d.body, DocType(d.doc_type)) if b.item_id == item_id)
    lines = d.body.split("\n")
    del lines[block.start_line - 1 : block.end_line]
    return "\n".join(lines)


async def seed() -> None:
    from tests.core.account.test_service import make_user

    fresh_db()
    remote, work = fresh_repo()
    with db.SessionLocal() as s:
        p = Project(code="SYNC", name="싱크독")
        s.add(p)
        s.flush()
        s.add(Repository(project_id=p.id, remote_url=str(remote), workdir_path=str(work)))
        hoyoung = make_user(s, login="hoyoung")
        hoyoung.display_name = "박호영"
        minjun = make_user(s, login="minjun")
        minjun.display_name = "김민준"
        s.commit()
        h, m = agent(hoyoung), agent(minjun)
        hid = hoyoung.id

    # 1. 이 저장소의 명세를 단계 순서대로 올린다 (호영의 에이전트)
    for typ in ORDER:
        for f in sorted((ROOT / "docs/specs" / typ).glob("SYNC-*.md")):
            try:
                r = await pipeline.save_pipeline(
                    Entry.mcp,
                    None,
                    DocType(typ),
                    f.read_text(encoding="utf-8"),
                    None,
                    "SYNC",
                    h,
                    f"spec({f.stem}): 초안",
                    changed_items=[],
                )
                print(f"  {r.doc_id} v{r.version_no} 경고 {len(r.warnings)}")
            except Problem as e:
                print(f"  {f.stem} 실패: {e.to_dict()}")

    with db.SessionLocal() as s:
        # 단계 순으로 올려 STD 참조가 미존재로 남는다 — 재구축 7단계처럼 한 번 해제
        ReferenceService(s).resolve_missing(1)
        s.commit()
        spec = SpecService(s)
        q_edit, _ = with_downstream(s, "SYNC-RFQ-001")
        q_del, _ = with_downstream(s, "SYNC-RFQ-001", {q_edit})
        r_edit, r_pk = with_downstream(s, "SYNC-PRD-001")
        rfq_no = spec.get_document("SYNC-RFQ-001").current_version_no
        body_rfq = edited(s, "SYNC-RFQ-001", q_edit)
    # 2. 민준의 에이전트가 RFQ 항목 수정 → 민준이 전파 → PRD 등 하위(호영)에 확인 필요
    r = await save(
        m,
        "SYNC-RFQ-001",
        body_rfq,
        rfq_no,
        f"spec(SYNC-RFQ-001): {q_edit} 보강",
        changed_items=[q_edit],
    )
    with db.SessionLocal() as s:
        tr = TrackingService(s)
        minjun = AccountService(s).user_by_login("minjun")
        n = tr.record_decision(
            r.pending_decision_version_id, Propagation.propagate, None, minjun
        ).flags_raised
        s.commit()
        print(f"  RFQ {q_edit} 수정 → 확인 필요 {n}건")
        prd_no = SpecService(s).get_document("SYNC-PRD-001").current_version_no
        body_prd = edited(s, "SYNC-PRD-001", r_edit)
    # 3. 호영의 에이전트가 PRD 항목 수정 → 호영에게 전파 미결정 (UI-12)
    r = await save(
        h,
        "SYNC-PRD-001",
        body_prd,
        prd_no,
        f"spec(SYNC-PRD-001): {r_edit} 범위 변경\n\n하위 문서 영향 검토 필요",
        changed_items=[r_edit],
    )
    print(f"  PRD {r_edit} 수정 → 미결정 version {r.pending_decision_version_id}")
    # 4. 민준의 에이전트가 SCN 저장하며 PRD 항목이 어긋났다고 지정 → 호영에게 하위 불일치
    with db.SessionLocal() as s:
        scn = SpecService(s).get_document("SYNC-SCN-001")
    await save(
        m,
        "SYNC-SCN-001",
        scn.body + "\n",
        scn.current_version_no,
        "spec(SYNC-SCN-001): 상위 어긋남 지목",
        changed_items=[],
        upstream_impact=[f"SYNC-PRD-001#{r_edit}"],
    )
    # 5. 민준의 에이전트가 RFQ 항목 삭제(확인) → 하위(호영)에 끊어진 참조
    with db.SessionLocal() as s:
        rfq = SpecService(s).get_document("SYNC-RFQ-001")
        body_del = without(s, "SYNC-RFQ-001", q_del)
    await save(
        m,
        "SYNC-RFQ-001",
        body_del,
        rfq.current_version_no,
        f"spec(SYNC-RFQ-001): {q_del} 삭제",
        changed_items=[],
        confirm_item_deletion=True,
    )
    # 6. 규약 오류 · 미해결 댓글 · 담당 미지정
    with db.SessionLocal() as s:
        s.execute(
            text(
                "UPDATE documents SET has_convention_error=true, convention_error_detail='frontmatter.status: 미리보기용 오류' WHERE doc_id='SYNC-UC-001'"
            )
        )
        prd = SpecService(s).get_document("SYNC-PRD-001")
        minjun = AccountService(s).user_by_login("minjun")
        CommentService(s).add(
            prd.id,
            12,
            prd.body.split("\n")[11],
            "이 부분 에이전트가 파싱 가능한지 확인이 필요해요",
            minjun,
            None,
        )
        s.execute(
            text(
                "UPDATE flags SET assignee_user_id=NULL WHERE id=(SELECT max(id) FROM flags WHERE kind='needs_check')"
            )
        )
        s.commit()
    print("시드 완료 — hoyoung id", hid)


@app.get("/__dev/login/{login}")
def _dev_login(login: str, request: Request, session: Session = Depends(db.get_session)):
    user = AccountService(session).user_by_login(login)
    if user is None:
        return {"error": f"없는 사용자 {login}"}
    auth.login(request, user)
    return RedirectResponse("/todo", status_code=302)


if __name__ == "__main__":
    if "--serve" not in sys.argv:
        asyncio.run(seed())
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="warning")
